"""
Minimal Supabase PostgREST client using `requests`.
Shared by collect_history.py (writes) and history_store.py (reads).
Never logs or returns the API key.
"""
from __future__ import annotations

import json
import os

import requests


class SupabaseConfigError(RuntimeError):
    pass


class SupabaseError(RuntimeError):
    pass


class SupabaseREST:
    def __init__(self, url: str | None = None, key: str | None = None, timeout=10):
        url = (url or os.environ.get("SUPABASE_URL", "")).strip().rstrip("/")
        key = (key or os.environ.get("SUPABASE_KEY", "")).strip()
        if not url or not key:
            raise SupabaseConfigError("SUPABASE_URL and SUPABASE_KEY must be set")
        if url.endswith("/rest/v1"):
            url = url[: -len("/rest/v1")]
        self.base = f"{url}/rest/v1"
        self.timeout = timeout
        self.session = requests.Session()
        headers = {
            "apikey": key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        # Legacy JWT keys (eyJ...) also go in Authorization.
        # New-style sb_secret_/sb_publishable_ keys only need `apikey`.
        if key.startswith("eyJ"):
            headers["Authorization"] = f"Bearer {key}"
        self.session.headers.update(headers)

    def _check(self, resp: requests.Response, table: str):
        if resp.status_code >= 400:
            raise SupabaseError(f"HTTP {resp.status_code} on '{table}': {resp.text[:300]}")

    def select(self, table: str, params: list[tuple[str, str]]) -> list[dict]:
        resp = self.session.get(f"{self.base}/{table}", params=params, timeout=self.timeout)
        self._check(resp, table)
        return resp.json()

    def select_all(self, table: str, params: list[tuple[str, str]], page_size: int = 1000) -> list[dict]:
        """Paginate past PostgREST's default 1000-row cap. Caller should include an `order` param."""
        out: list[dict] = []
        offset = 0
        while True:
            page = self.select(table, list(params) + [("limit", str(page_size)), ("offset", str(offset))])
            out.extend(page)
            if len(page) < page_size:
                return out
            offset += page_size

    def upsert(self, table: str, rows: list[dict], on_conflict: str) -> None:
        if not rows:
            return
        resp = self.session.post(
            f"{self.base}/{table}",
            params={"on_conflict": on_conflict},
            data=json.dumps(rows),
            headers={"Prefer": "resolution=merge-duplicates,return=minimal"},
            timeout=self.timeout,
        )
        self._check(resp, table)

    def table_exists(self, table: str) -> bool:
        try:
            self.select(table, [("select", "*"), ("limit", "1")])
            return True
        except SupabaseError:
            return False
