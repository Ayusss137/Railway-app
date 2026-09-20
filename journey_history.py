import json
import os
from datetime import datetime, timedelta
from analyze_delays import extract_delay_minutes
from ntes import NTESClient

client = NTESClient()

def get_all_arrived_snapshots(train_no):
    files = sorted(f for f in os.listdir("snapshots") if f.startswith(train_no))
    arrived = []
    for filename in files:
        with open(f"snapshots/{filename}") as f:
            data = json.load(f)
        if "Arrived at PURATCHI" in data["CPOS"] or "MAS" in data["CPOS"]:
            arrived.append(data["CPOS"])
    return arrived

def get_train_summary(train_no):
    unique_journeys = set(get_all_arrived_snapshots(train_no))
    delays = [extract_delay_minutes(j) for j in unique_journeys]
    delays = [d for d in delays if d is not None]

    if delays:
        average = sum(delays) / len(delays)
        return {
            "train_no": train_no,
            "journeys": len(delays),
            "average_delay": round(average, 1),
            "individual_delays": delays
        }
    else:
        return {
            "train_no": train_no,
            "journeys": 0,
            "average_delay": None,
            "individual_delays": []
        }

def get_live_last_ride(train_no):
    for days_back in range(1, 4):
        date = (datetime.now() - timedelta(days=days_back)).strftime("%d-%b-%Y")
        try:
            status = client.live_status(train_no, date)
            if status["CPOS"].startswith("Arrived"):
                delay = extract_delay_minutes(status["CPOS"])
                return {"train_no": train_no, "date": date, "delay": delay, "source": "live"}
        except Exception:
            continue
    return None

def get_last_n_rides(train_no, n=7, max_lookback=30):
    results = []
    for days_back in range(1, max_lookback):
        if len(results) >= n:
            break
        date = (datetime.now() - timedelta(days=days_back)).strftime("%d-%b-%Y")
        try:
            status = client.live_status(train_no, date)
            if status["CPOS"].startswith("Arrived"):
                delay = extract_delay_minutes(status["CPOS"])
                results.append({"date": date, "delay": delay})
        except Exception:
            continue
    return results

if __name__ == "__main__":
    for train_no in ["12658", "12141", "12163"]:
        summary = get_train_summary(train_no)
        print(summary)
