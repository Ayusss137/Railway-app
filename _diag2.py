import os
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from dotenv import load_dotenv

load_dotenv(Path("/home/ayush/railway-app/.env"))
url = os.environ["SUPABASE_URL"].strip().rstrip("/")
key = os.environ["SUPABASE_KEY"].strip()

print("URL:", url)
print("Key: len=%d startswith=%r" % (len(key), key[:12]))
if url.endswith("/rest/v1"):
    url = url[: -len("/rest/v1")]

def get(table, params):
    full = f"{url}/rest/v1/{table}?{urlencode(params)}"
    req = Request(full, headers={"apikey": key, "Accept": "application/json"})
    if key.startswith("eyJ"):
        req.add_header("Authorization", f"Bearer {key}")
    try:
        with urlopen(req, timeout=20) as r:
            body = r.read().decode()
            print("HTTP", r.status, "| Content-Range:", r.headers.get("Content-Range"))
            return body
    except Exception as e:
        print("ERROR:", type(e).__name__, e)
        try:
            print(e.read().decode()[:500])
        except Exception:
            pass
        return None

print("\n=== LATEST 5 ROWS IN TABLE ===")
b = get("train_history", {
    "select": "train_no,journey_date,delay_minutes",
    "limit": "5",
    "order": "journey_date.desc",
})
print(b[:900] if b else "(no body)")

print("\n=== THE 4 TEST TRAINS (no date filter) ===")
b = get("train_history", {
    "select": "train_no,journey_date,delay_minutes",
    "train_no": "in.(06903,09014,10108,12620)",
    "limit": "20",
})
print(b[:900] if b else "(no body)")
