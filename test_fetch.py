from asyncio.base_futures import _FINISHED

from ntes import NTESClient
import json
from datetime import datetime
import os
import time

client = NTESClient()
TRAIN_NUMBER = ["12658", "12141", "12163"]
TRAIN_DATE = "10-Sep-2026"
os.makedirs("snapshots", exist_ok=True)

finished_trains = set()
while True:
    for train_no in TRAIN_NUMBER:
        if train_no in finished_trains:
            continue

        try:
            status = client.live_status(train_no, TRAIN_DATE)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"snapshots/{train_no}_{timestamp}.json"
            with open(filename, "w") as f:
                json.dump(status, f, indent=2)
            print(f"Saved {filename}")

            if status["CPOS"].startswith("Arrived"):
                print(f"Train {train_no} has arrived, no longer polling it.")
                finished_trains.add(train_no)
        except Exception as e:
            print(f"Fetch failed for {train_no}: {e}")
    time.sleep(1800)
