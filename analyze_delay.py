import json
import os
import re

def get_latest_snapshot(train_no):
    files = sorted(f for f in os.listdir("snapshots") if f.startswith(train_no))
    if not files:
        return None
    with open(f"snapshots/{files[-1]}") as f:
        return json.load(f)

def extract_delay_minutes(cpos_text):
    if "On Time" in cpos_text:
        return 0
    match = re.search(r"Delay: (\d+):(\d+)", cpos_text)
    if match:
        hours, minutes = match.groups()
        return int(hours) * 60 + int(minutes)
    return None

for train_no in ["12658", "12141", "12163"]:
    snapshot = get_latest_snapshot(train_no)
    if snapshot:
        delay = extract_delay_minutes(snapshot["CPOS"])
        print(train_no, "-", delay, "minutes delay")
