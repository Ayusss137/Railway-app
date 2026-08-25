import json
import os

TRAIN_NUMBER_FILTER = "12163"
snapshot_files = sorted(f for f in os.listdir("snapshots") if f.startswith(TRAIN_NUMBER_FILTER))
for filename in snapshot_files:
    with open(f"snapshots/{filename}") as f:
        data = json.load(f)
    print(filename, "-", data["CPOS"], "-", data["LASTUPD"])
