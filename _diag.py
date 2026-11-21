import os
from dotenv import load_dotenv
load_dotenv("/home/ayush/railway-app/.env")

print("Working dir:", os.getcwd())
print("SUPABASE_URL prefix:", (os.environ.get("SUPABASE_URL", "MISSING") or "MISSING")[:45])

import history_store
print("history_store file:", history_store.__file__)
print("history_store public attrs:", [x for x in dir(history_store) if not x.startswith("_")])

from supabase import create_client
db = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])
rows = db.table("train_history").select("train_no,journey_date,delay_minutes").in_(
    "train_no", ["06903", "09014", "10108", "12620"]
).order("journey_date", desc=True).execute().data
print(f"\nRows in train_history for those 4 trains: {len(rows)}")
for r in rows[:15]:
    print(" ", r)
