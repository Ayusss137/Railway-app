
from pathlib import Path
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent

df = pd.read_csv(
    BASE_DIR / "stops_new.csv",
    dtype={"train_number": str, "station_code": str}
)


def time_to_minutes(day, time_value):
    if pd.isna(day) or pd.isna(time_value):
        return None

    try:
        hours, minutes = map(int, str(time_value).strip().split(":")[:2])
        day = int(day)

        if not (0 <= hours <= 23 and 0 <= minutes <= 59 and day >= 1):
            return None

        return (day - 1) * 1440 + hours * 60 + minutes
    except (ValueError, TypeError):
        return None


def find_trains_between_cities(city_a_codes, city_b_codes):
    if not city_a_codes or not city_b_codes:
        return []

    a_rows = df[df["station_code"].isin(city_a_codes)][
        ["train_number", "seq", "station_code", "day", "departure"]
    ]

    b_rows = df[df["station_code"].isin(city_b_codes)][
        ["train_number", "seq", "station_code", "day", "arrival"]
    ]

    merged = a_rows.merge(
        b_rows,
        on="train_number",
        suffixes=("_a", "_b")
    )

    valid = merged[merged["seq_a"] < merged["seq_b"]]

    results = []

    for row in valid.itertuples(index=False):
        departure = time_to_minutes(row.day_a, row.departure)
        arrival = time_to_minutes(row.day_b, row.arrival)

        if departure is None or arrival is None:
            continue

        duration = arrival - departure

        if duration <= 0:
            continue

        results.append({
            "train_no": str(row.train_number),
            "dep_station": row.station_code_a,
            "dep_time": row.departure,
            "dep_day": int(row.day_a),
            "arr_station": row.station_code_b,
            "arr_time": row.arrival,
            "arr_day": int(row.day_b),
            "duration_min": duration,
            "duration_h": duration // 60,
            "duration_m": duration % 60
        })

    # Keep the shortest valid station pair per train.
    # For regional searches this avoids duplicate trains.
    best = {}

    for result in results:
        number = result["train_no"]

        if (
            number not in best
            or result["duration_min"] < best[number]["duration_min"]
        ):
            best[number] = result

    return list(best.values())
