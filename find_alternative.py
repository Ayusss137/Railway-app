import pandas as pd
from datetime import datetime
from ntes import NTESClient

df = pd.read_csv('stops_new.csv', dtype={'train_number': str})
trains_df = pd.read_csv('trains_new.csv', dtype={'number': str}).set_index('number')

client = NTESClient()

def validate_train(train_no):
    today = datetime.now().strftime("%d-%b-%Y")
    try:
        client.live_status(train_no, today)
        return True
    except Exception:
        return False

def find_trains_between_cities(city_a_codes, city_b_codes):
    a_rows = df[df['station_code'].isin(city_a_codes)][['train_number', 'seq', 'station_code', 'day', 'departure']]
    b_rows = df[df['station_code'].isin(city_b_codes)][['train_number', 'seq', 'station_code', 'day', 'arrival']]

    merged = a_rows.merge(b_rows, on='train_number', suffixes=('_a', '_b'))

    valid = merged[merged['seq_a'] < merged['seq_b']]
    valid = valid.sort_values('train_number').drop_duplicates('train_number')

    results = []
    for _, row in valid.iterrows():
        train_no = row['train_number']
        if not validate_train(train_no):
            continue
        results.append({
            "train_no": train_no,
            "dep_station": row['station_code_a'],
            "dep_time": row['departure'],
            "dep_day": int(row['day_a']),
            "arr_station": row['station_code_b'],
            "arr_time": row['arrival'],
            "arr_day": int(row['day_b']),
        })
    return results
