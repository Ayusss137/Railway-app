import json
import pandas as pd
from ntes import NTESClient

with open('schedules.json') as f:
    data = json.load(f)

df = pd.DataFrame(data)
client = NTESClient()

def validate_train(train_no):
    try:
        client.live_status(train_no, "10-Sep-2026")
        return True
    except Exception:
        return False

def find_station_code(place_name):
    matches = stations_df[stations_df['Station Name(en)'].str.contains(place_name.upper(), na=False)]
    if len(matches) == 0:
        return None
    return matches.iloc[0]['Station Code']

def find_trains(station_a, station_b):
    a_rows = df[df['station_code'] == station_a][['train_number', 'day', 'departure']]
    b_rows = df[df['station_code'] == station_b][['train_number', 'day', 'departure']]
    merged = a_rows.merge(b_rows, on='train_number', suffixes=('_a', '_b'))
    valid = merged[
        (merged['day_a'] < merged['day_b']) |
        ((merged['day_a'] == merged['day_b']) & (merged['departure_a'] < merged['departure_b']))
    ]
    candidates = valid['train_number'].unique()
    return [t for t in candidates if validate_train(t)]

def get_route(train_no):
    train_stops = df[df['train_number'] == train_no].copy()
    train_stops = train_stops.sort_values(['day', 'departure'])
    return train_stops[['station_code', 'station_name', 'day', 'arrival', 'departure']]

if __name__ == "__main__":
    results = find_trains('MAS', 'SBC')
    print(results)
    print(f"Found {len(results)} trains")
