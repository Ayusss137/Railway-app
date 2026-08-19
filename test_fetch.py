from ntes import NTESClient
import json
from datetime import datetime
import os
import time

client = NTESClient()
os.makedirs("snapshots", exist_ok=True)

while True:
    try:
        status = client.live_status("12658", "19-Aug-2026")

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"snapshots/snapshot_{timestamp}.json"

        with open(filename, "w") as f:
            json.dump(status, f, indent=2)

        print(f"Saved {filename}")
    except Exception as e:
        print(f"Fetch failed, skipping this round: {e}")

    time.sleep(1800)
