#!/usr/bin/env python3
"""
Know Your Train: historical delay collector (NTES -> Supabase).

Saves ONLY verified completed-arrival delays. Missing data is never stored as 0.

Environment variables:
  SUPABASE_URL, SUPABASE_KEY  required (base project URL; service-role key)
  TRAIN_NUMBERS               optional comma list, overrides CSV ("12658,12141")
  TRAINS_CSV                  default trains_new.csv
  TRAIN_COLUMN                optional explicit train-number column name
  LOOKBACK_DAYS               default 3 -> journey dates today-1 .. today-N (IST)
                              (HISTORY_LOOKBACK_DAYS accepted as legacy alias)
  MAX_TRAINS                  default 0 (no cap)
  SHARD_COUNT / SHARD_INDEX   default 1 / 0
  REQUEST_DELAY_SECONDS       default 1.5
  NTES_MAX_RETRIES            default 3
  MAX_CONSECUTIVE_ERRORS      default 15 (circuit breaker)
  MAX_RUNTIME_MINUTES         default 0 (no limit)
  UPSERT_BATCH_SIZE           default 50
  SKIP_EXISTING               default 1
  DRY_RUN                     default 0 (1 = query NTES, write nothing)
  LOG_LEVEL                   default INFO

Exit codes: 0 ok (incl. time budget reached), 1 failure, 2 config error.
"""
from __future__ import annotations

import csv
import json
import logging
import os
import random
import sys
import time
from collections import Counter
from datetime import date, datetime, timedelta, timezone
import urllib.request
import urllib.parse

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from ntes import NTESClient
from analyze_delays import extract_delay_minutes
from supabase_rest import SupabaseREST, SupabaseConfigError

IST = timezone(timedelta(hours=5, minutes=30), "IST")  # IST has no DST: no tzdata needed
log = logging.getLogger("collect_history")

VERIFIED_STATUS = "verified_arrival"   # match your existing rows' status value (see Phase 1)
MIN_VALID_DELAY = -180                 # early arrivals are stored raw
MAX_VALID_DELAY = 48 * 60

# ---------------------------------------------------------------------------
# NTES adapter: the ONLY code that depends on NTES formats.
# ---------------------------------------------------------------------------

def ntes_date_arg(journey_date):
    return journey_date.strftime("%d-%b-%Y")

def is_completed_arrival(status) -> bool:
    if not isinstance(status, dict):
        return False
    position = status.get("CPOS")
    if not isinstance(position, str):
        return False
    return position.strip().lower().startswith("arrived")

def parse_verified_delay(status):
    """Return (outcome, delay_minutes_or_None, detail)."""
    if not status:
        return "no_running_data", None, "empty response"
    if not is_completed_arrival(status):
        return "no_running_data", None, "no completed arrival (CPOS)"
    raw = extract_delay_minutes(status["CPOS"])
    if raw is None:
        return "no_running_data", None, "arrived but delay not extractable"
    try:
        delay = int(round(float(raw)))
    except (TypeError, ValueError):
        return "invalid", None, f"non-numeric delay {raw!r}"
    if not (MIN_VALID_DELAY <= delay <= MAX_VALID_DELAY):
        return "invalid", None, f"delay out of range: {delay}"
    return "verified", delay, ""


def fetch_status(client, train_no: str, journey_date, max_retries: int):
    """Fetches NTES data directly (local) or via Vercel proxy (cloud)."""
    api_date = journey_date.strftime("%d-%b-%Y")
    use_proxy = os.environ.get("USE_VERCEL_PROXY") == "1"

    # Your Vercel production URL
    url = f"https://know-your-train.vercel.app/api/ntes?train={train_no}&date={urllib.parse.quote(api_date)}"

    last_exc = None
    for attempt in range(1, max_retries + 1):
        try:
            if use_proxy:
                req = urllib.request.Request(url, headers={"User-Agent": "GitHubActions"})
                with urllib.request.urlopen(req, timeout=30) as response:
                    status = json.loads(response.read().decode())
                    if "error" in status:
                        raise RuntimeError(status["error"])
                    return status, None
            else:
                # Direct call for local development
                return client.live_status(train_no, api_date), None
        except Exception as exc:
            last_exc = exc
            if attempt < max_retries:
                wait = min(30, 2 ** attempt) + random.uniform(0, 1)
                log.warning("NTES %s %s attempt %d/%d failed (%s); retry in %.1fs",
                            train_no, api_date, attempt, max_retries,
                            type(exc).__name__, wait)
                time.sleep(wait)

    return None, f"{type(last_exc).__name__}: {last_exc}"[:300]
# ---------------------------------------------------------------------------
# Config and inputs
# ---------------------------------------------------------------------------

def env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        raise SystemExit(f"Config error: {name} must be an integer, got {raw!r}")


def env_float(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        raise SystemExit(f"Config error: {name} must be a number, got {raw!r}")


def env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    return default if not raw else raw in ("1", "true", "yes", "on")


def normalize_train_no(raw) -> str | None:
    s = str(raw).strip()
    if s.endswith(".0"):            # pandas float artifact
        s = s[:-2]
    if not s.isdigit() or len(s) > 5:
        return None
    return s.zfill(5)               # Indian train numbers are 5 digits (e.g. 01234)


CANDIDATE_COLUMNS = ("train_no", "train_number", "trainno", "train no",
                     "train_num", "trainnumber", "number", "train")


def load_train_numbers(csv_path: str, column: str | None):
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise SystemExit(f"{csv_path} has no header row")
        if not column:
            lookup = {n.strip().lower(): n for n in reader.fieldnames}
            column = next((lookup[c] for c in CANDIDATE_COLUMNS if c in lookup), None)
            if not column:
                raise SystemExit(f"No train-number column in {csv_path}. "
                                 f"Columns: {reader.fieldnames}. Set TRAIN_COLUMN.")
        trains, bad = set(), 0
        for row in reader:
            t = normalize_train_no(row.get(column, ""))
            if t:
                trains.add(t)
            else:
                bad += 1
    return sorted(trains), column, bad


def journey_dates(lookback_days: int) -> list[date]:
    today = datetime.now(IST).date()
    # Oldest first: those dates are closest to falling out of NTES availability
    return [today - timedelta(days=k) for k in range(lookback_days, 0, -1)]


def load_existing(db: SupabaseREST, dates: list[date]) -> set[tuple[str, str]]:
    rows = db.select_all("train_history", [
        ("select", "train_no,journey_date"),
        ("journey_date", f"gte.{min(dates).isoformat()}"),
        ("journey_date", f"lte.{max(dates).isoformat()}"),
        ("order", "train_no,journey_date"),
    ])
    return {(normalize_train_no(r["train_no"]), str(r["journey_date"])[:10]) for r in rows}

# ---------------------------------------------------------------------------
# Buffered writer
# ---------------------------------------------------------------------------

class Collector:
    def __init__(self, db, dry_run: bool, batch_size: int, audit_enabled: bool):
        self.db = db
        self.dry_run = dry_run
        self.batch_size = batch_size
        self.audit_enabled = audit_enabled
        self.pending: list[dict] = []
        self.audit: list[dict] = []
        self.stats: Counter = Counter()
        self.write_failures = 0

    def record(self, train_no, journey_date, outcome, delay, detail):
        self.stats[outcome] += 1
        now = datetime.now(IST).isoformat()
        if outcome == "verified":
            self.pending.append({
                "train_no": train_no,
                "journey_date": journey_date.isoformat(),
                "delay_minutes": delay,
                "status": VERIFIED_STATUS,
                "collected_at": now,
            })
        if self.audit_enabled:
            self.audit.append({
                "train_no": train_no,
                "journey_date": journey_date.isoformat(),
                "outcome": outcome,
                "detail": (detail or None),
                "last_attempt_at": now,
            })
        self.flush()

    def flush(self, force: bool = False):
        if self.pending and (force or len(self.pending) >= self.batch_size):
            rows, self.pending = self.pending, []
            self._write("train_history", rows, "train_no,journey_date", critical=True)
        if self.audit and (force or len(self.audit) >= self.batch_size):
            rows, self.audit = self.audit, []
            if self.audit_enabled:
                self._write("collection_attempts", rows, "train_no,journey_date", critical=False)

    def _write(self, table, rows, on_conflict, critical):
        if self.dry_run:
            log.info("[dry-run] would upsert %d rows into %s", len(rows), table)
            return
        for attempt in range(1, 4):
            try:
                self.db.upsert(table, rows, on_conflict)
                self.stats[f"{table}_rows_written"] += len(rows)
                return
            except Exception as exc:
                log.warning("Upsert to %s failed (attempt %d/3): %s", table, attempt, exc)
                time.sleep(2 ** attempt)
        if critical:
            self.write_failures += len(rows)
            log.error("Could not save %d verified rows; dumping for manual recovery:", len(rows))
            for r in rows:
                log.error("UNSAVED %s", json.dumps(r))
        else:
            log.warning("Disabling audit logging for this run after repeated failures")
            self.audit_enabled = False


def write_step_summary(lines: list[str]):
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

# ---------------------------------------------------------------------------

def main() -> int:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(message)s",
        stream=sys.stdout,
    )
    lookback = env_int("LOOKBACK_DAYS", env_int("HISTORY_LOOKBACK_DAYS", 3))
    max_trains = env_int("MAX_TRAINS", 0)
    shard_count = env_int("SHARD_COUNT", 1)
    shard_index = env_int("SHARD_INDEX", 0)
    delay_s = env_float("REQUEST_DELAY_SECONDS", 1.5)
    max_retries = env_int("NTES_MAX_RETRIES", 3)
    max_consec = env_int("MAX_CONSECUTIVE_ERRORS", 15)
    max_runtime = env_int("MAX_RUNTIME_MINUTES", 0)
    batch_size = env_int("UPSERT_BATCH_SIZE", 50)
    skip_existing = env_bool("SKIP_EXISTING", True)
    dry_run = env_bool("DRY_RUN", False)

    if not 1 <= lookback <= 10:
        log.error("LOOKBACK_DAYS must be 1..10 (NTES keeps roughly a week of full data)")
        return 2
    if shard_count < 1 or not 0 <= shard_index < shard_count:
        log.error("Invalid shard %d/%d", shard_index, shard_count)
        return 2

    override = os.environ.get("TRAIN_NUMBERS", "").strip()
    if override:
        trains = sorted({t for t in (normalize_train_no(x) for x in override.split(",")) if t})
        log.info("Using %d trains from TRAIN_NUMBERS", len(trains))
    else:
        csv_path = os.environ.get("TRAINS_CSV", "trains_new.csv")
        trains, col, bad = load_train_numbers(csv_path, os.environ.get("TRAIN_COLUMN") or None)
        log.info("Loaded %d unique trains from %s (column %r, %d unparseable rows)",
                 len(trains), csv_path, col, bad)

    trains = [t for i, t in enumerate(trains) if i % shard_count == shard_index]
    if max_trains > 0:
        trains = trains[:max_trains]
    dates = journey_dates(lookback)
    log.info("Shard %d/%d: %d trains x %d dates (%s .. %s IST)%s",
             shard_index, shard_count, len(trains), len(dates),
             dates[0], dates[-1], " [DRY RUN]" if dry_run else "")

    try:
        db = SupabaseREST(timeout=20)
    except SupabaseConfigError as exc:
        log.error("%s", exc)
        return 2

    existing: set = set()
    if skip_existing:
        try:
            existing = load_existing(db, dates)
        except Exception as exc:
            log.error("Cannot read from Supabase, aborting before any NTES calls: %s", exc)
            return 1

    audit_ok = db.table_exists("collection_attempts")
    if not audit_ok:
        log.warning("Table collection_attempts not found; audit logging disabled")

    collector = Collector(db, dry_run, batch_size, audit_ok)
    work = [(t, d) for d in dates for t in trains if (t, d.isoformat()) not in existing]
    collector.stats["skipped_existing"] = len(trains) * len(dates) - len(work)
    log.info("%d requests to make (%d already in database)",
             len(work), collector.stats["skipped_existing"])

    client = NTESClient()
    deadline = time.monotonic() + max_runtime * 60 if max_runtime > 0 else None
    consecutive_errors = 0
    aborted = None
    started = time.monotonic()

    try:
        for i, (train_no, jd) in enumerate(work, 1):
            if deadline and time.monotonic() > deadline:
                aborted = "time budget reached"
                break
            status, err = fetch_status(client, train_no, jd, max_retries)
            if err:
                consecutive_errors += 1
                outcome, delay, detail = "error", None, err
            else:
                consecutive_errors = 0
                try:
                    outcome, delay, detail = parse_verified_delay(status)
                except NotImplementedError:
                    raise
                except Exception as exc:
                    outcome, delay, detail = "invalid", None, f"parse error: {type(exc).__name__}: {exc}"[:300]
            collector.record(train_no, jd, outcome, delay, detail)

            if outcome == "verified":
                log.info("VERIFIED %s %s delay=%d min", train_no, jd, delay)
            elif outcome == "error":
                log.warning("ERROR %s %s %s", train_no, jd, detail)
            else:
                log.debug("%s %s %s %s", outcome.upper(), train_no, jd, detail)

            if i % 50 == 0:
                log.info("Progress %d/%d  %s", i, len(work), dict(collector.stats))
            if consecutive_errors >= max_consec:
                aborted = f"circuit breaker: {consecutive_errors} consecutive NTES errors"
                break
            time.sleep(delay_s + random.uniform(0, delay_s * 0.3))
    except KeyboardInterrupt:
        aborted = "interrupted"
    finally:
        collector.flush(force=True)

    s = collector.stats
    minutes = (time.monotonic() - started) / 60
    summary = [
        "## Train history collection",
        f"- Shard: {shard_index}/{shard_count}, trains: {len(trains)}, dates: {dates[0]} .. {dates[-1]}",
        f"- Requests attempted: {s['verified'] + s['no_running_data'] + s['invalid'] + s['error']} of {len(work)}",
        f"- Verified delays: **{s['verified']}**",
        f"- No running data: {s['no_running_data']}, invalid: {s['invalid']}, errors: {s['error']}",
        f"- Skipped (already stored): {s['skipped_existing']}",
        f"- Rows written: {s['train_history_rows_written']}, unsaved: {collector.write_failures}",
        f"- Runtime: {minutes:.1f} min" + (f", stopped early: {aborted}" if aborted else ""),
    ]
    for line in summary:
        log.info(line)
    write_step_summary(summary)

    if collector.write_failures or (aborted and aborted != "time budget reached"):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
