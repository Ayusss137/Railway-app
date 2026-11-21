"""
Read verified historical delays for the previous 30 completed IST days.
Uses urllib only (no supabase SDK). Returns honest empty state when no data.
"""
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")
log = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30), "IST")
WINDOW_DAYS = 30
ON_TIME_THRESHOLD_MIN = 15
CACHE_TTL_SECONDS = 300
ERROR_TTL_SECONDS = 30

_cache = {}  # train_no -> (expires_at_monotonic, summary)

def normalize_train_no(value):
    number = str(value).strip()
    if number.endswith(".0"):
        number = number[:-2]
    return number.zfill(5) if number.isdigit() and len(number) <= 5 else None

def empty_summary(state="no_data"):
    return {
        "state": state,
        "average_delay": None,
        "journeys": 0,
        "max_delay": None,
        "on_time_pct": None,
        "last_journey_date": None,
    }

def _base_url():
    url = (os.environ.get("SUPABASE_URL") or "").strip().rstrip("/")
    if url.endswith("/rest/v1"):
        url = url[: -len("/rest/v1")]
    return url

def _key():
    return (os.environ.get("SUPABASE_KEY") or "").strip()

def _fetch(train_nos):
    """Return {train_no: summary}. Raises on network/HTTP failure."""
    import time
    url, key = _base_url(), _key()
    if not url or not key:
        log.warning("SUPABASE_URL / SUPABASE_KEY missing, returning no_data")
        return {t: empty_summary("unavailable") for t in train_nos}

    today = datetime.now(IST).date()
    cutoff = (today - timedelta(days=WINDOW_DAYS)).isoformat()

    params = [
        ("select", "train_no,journey_date,delay_minutes"),
        ("train_no", f"in.({','.join(train_nos)})"),
        ("journey_date", f"gte.{cutoff}"),
        ("journey_date", f"lt.{today.isoformat()}"),
        ("order", "train_no,journey_date.desc"),
        ("limit", "5000"),
    ]
    full = f"{url}/rest/v1/train_history?{urlencode(params)}"
    req = Request(full, headers={"apikey": key, "Accept": "application/json"})
    if key.startswith("eyJ"):
        req.add_header("Authorization", f"Bearer {key}")

    with urlopen(req, timeout=20) as response:
        body = response.read().decode()
    rows = json.loads(body) if body else []

    grouped = {t: [] for t in train_nos}
    for row in rows:
        tn = normalize_train_no(row.get("train_no"))
        delay = row.get("delay_minutes")
        if tn in grouped and delay is not None:
            grouped[tn].append({
                "delay": int(delay),
                "date": str(row.get("journey_date"))[:10],
            })

    out = {}
    for tn, items in grouped.items():
        if not items:
            out[tn] = empty_summary("no_data")
            continue
        clean = [max(0, it["delay"]) for it in items]      # early arrivals count as 0 for average
        avg = round(sum(clean) / len(clean), 1)
        out[tn] = {
            "state": "ok",
            "average_delay": avg,
            "journeys": len(items),
            "max_delay": max(clean),
            "on_time_pct": round(100 * sum(c <= ON_TIME_THRESHOLD_MIN for c in clean) / len(clean)),
            "last_journey_date": max(it["date"] for it in items),
        }
    return out

def get_delay_summaries(train_nos):
    """Public API. Returns {train_no: summary_dict}. Never raises."""
    import time

    wanted = []
    for raw in train_nos or []:
        tn = normalize_train_no(raw)
        if tn and tn not in wanted:
            wanted.append(tn)
    if not wanted:
        return {}

    now = time.monotonic()
    result, missing = {}, []
    for tn in wanted:
        hit = _cache.get(tn)
        if hit and hit[0] > now:
            result[tn] = hit[1]
        else:
            missing.append(tn)

    if missing:
        try:
            fetched = _fetch(missing)
            ttl = CACHE_TTL_SECONDS
        except Exception as exc:
            log.warning("Supabase read failed: %s", exc)
            fetched = {t: empty_summary("unavailable") for t in missing}
            ttl = ERROR_TTL_SECONDS
        expires = time.monotonic() + ttl
        for tn, summary in fetched.items():
            _cache[tn] = (expires, summary)
            result[tn] = summary

    return result
