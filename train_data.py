import pandas as pd
import folium
from folium.plugins import AntPath, Fullscreen, MiniMap
import json
import os
import statistics
from datetime import datetime, timedelta
from math import radians, sin, cos, sqrt, atan2
from functools import lru_cache
from journey_history import get_train_summary, get_last_n_rides, client
from find_alternative import find_trains_between_cities

stations = pd.read_csv("indian_stations.csv").set_index("Station Code")
trains_df = pd.read_csv("trains_new.csv", dtype={"number": str}).set_index("number")
stops_df = pd.read_csv("stops_new.csv", dtype={"train_number": str})
station_train_counts = stops_df.groupby("station_code")["train_number"].nunique()

HERO_TRAIN = "12658"

CITY_CENTERS = {
    "MUMBAI": (19.0760, 72.8777), "BOMBAY": (19.0760, 72.8777),
    "DELHI": (28.6139, 77.2090), "NEW DELHI": (28.6139, 77.2090),
    "BANGALORE": (12.9716, 77.5946), "BENGALURU": (12.9716, 77.5946),
    "CHENNAI": (13.0827, 80.2707), "MADRAS": (13.0827, 80.2707),
    "KOLKATA": (22.5726, 88.3639), "CALCUTTA": (22.5726, 88.3639),
    "HYDERABAD": (17.3850, 78.4867), "PUNE": (18.5204, 73.8567),
    "AHMEDABAD": (23.0225, 72.5714), "JAIPUR": (26.9124, 75.7873),
    "LUCKNOW": (26.8467, 80.9462), "GOA": (15.2993, 74.1240),
    "GUWAHATI": (26.1445, 91.7362), "SURAT": (21.1702, 72.8311),
    "KANPUR": (26.4499, 80.3319), "NAGPUR": (21.1458, 79.0882),
    "PATNA": (25.5941, 85.1376), "INDORE": (22.7196, 75.8577),
    "BHOPAL": (23.2599, 77.4126), "VISAKHAPATNAM": (17.6868, 83.2185),
    "VIZAG": (17.6868, 83.2185), "VADODARA": (22.3072, 73.1812),
    "COIMBATORE": (11.0168, 76.9558), "MADURAI": (9.9252, 78.1198),
    "NASHIK": (19.9975, 73.7898), "CHANDIGARH": (30.7333, 76.7794),
    "AMRITSAR": (31.6340, 74.8723), "VARANASI": (25.3176, 82.9739),
    "PRAYAGRAJ": (25.4358, 81.8463), "AGRA": (27.1767, 78.0081),
    "MYSORE": (12.2958, 76.6394), "KOCHI": (9.9312, 76.2673),
    "BHUBANESWAR": (20.2961, 85.8245), "JODHPUR": (26.2389, 73.0243),
    "GWALIOR": (26.2183, 78.1828), "MANGALORE": (12.9141, 74.8560),
}


def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371
    dlat, dlon = radians(lat2 - lat1), radians(lon2 - lon1)
    a = sin(dlat/2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon/2)**2
    return 2 * R * atan2(sqrt(a), sqrt(1 - a))


def is_curated_city(name):
    return name.upper().strip() in CITY_CENTERS


@lru_cache(maxsize=128)
def get_city_station_codes(place_name, radius_km=50, min_trains=5):
    key = place_name.upper().strip()
    if key in CITY_CENTERS:
        center_lat, center_lon = CITY_CENTERS[key]
        nearby = stations[
            stations.apply(lambda row: haversine_km(center_lat, center_lon, row['Latitude'], row['Longitude']) <= radius_km, axis=1)
        ]
        codes = list(nearby.index)
        return [c for c in codes if station_train_counts.get(c, 0) >= min_trains]
    matches = stations[stations['Station Name(en)'].str.contains(key, na=False)]
    return list(matches.index)


def get_train_info(train_no):
    if str(train_no) in trains_df.index:
        row = trains_df.loc[str(train_no)]
        duration_h, duration_m = "?", "?"
        if pd.notna(row["travel_time"]) and ":" in str(row["travel_time"]):
            duration_h, duration_m = str(row["travel_time"]).split(":")[:2]
        return {
            "name": row["name"], "from_station_code": row["source_code"], "from_station_name": row["source"],
            "to_station_code": row["dest_code"], "to_station_name": row["destination"],
            "duration_h": duration_h, "duration_m": duration_m, "distance": row["distance_km"],
            "runs_days": row["runs_days"],
            "is_special": str(train_no).startswith("0"),
        }
    return None


def get_station_name(code):
    try:
        return stations.loc[code, 'Station Name(en)']
    except KeyError:
        return code


def get_quick_delay(train_no):
    summary = get_train_history(train_no)
    return summary["average_delay"], summary["journeys"]


@lru_cache(maxsize=256)
def get_train_history(train_no):
    summary = get_train_summary(train_no)
    if summary["journeys"] == 0:
        rides = get_last_n_rides(train_no, n=7)
        delays = [r["delay"] for r in rides if r["delay"] is not None]
        summary = {
            "train_no": train_no, "journeys": len(delays),
            "average_delay": round(sum(delays) / len(delays), 1) if delays else None,
            "individual_delays": delays
        }
    return summary


def get_delay_stats(delays):
    if not delays:
        return None
    on_time = sum(1 for d in delays if d <= 15)
    return {
        "average": round(sum(delays) / len(delays), 1),
        "median": round(statistics.median(delays), 1),
        "maximum": max(delays),
        "minimum": min(delays),
        "on_time_pct": round((on_time / len(delays)) * 100),
        "count": len(delays),
    }


def get_train_coords(train_no):
    files = sorted(f for f in os.listdir("snapshots") if f.startswith(train_no))
    if files:
        with open(f"snapshots/{files[-1]}") as f:
            return json.load(f).get("STNS")
    for days_back in range(0, 8):
        date = (datetime.now() - timedelta(days=days_back)).strftime("%d-%b-%Y")
        try:
            data = client.live_status(train_no, date)
            if "STNS" in data:
                return data["STNS"]
        except Exception:
            continue
    return None


def get_route_timeline(train_no):
    stns = get_train_coords(train_no)
    if not stns:
        return []
    timeline = []
    for stop in stns:
        code = stop.get("SC", "?")
        name = stop.get("SN", code)
        time = stop.get("STA") or stop.get("STD") or "?"
        timeline.append({"code": code, "name": name, "time": time})
    return timeline


def build_delay_bars(delays):
    if not delays:
        return ""
    max_delay = max(max(delays, default=0), 1)
    bars = ""
    for i, d in enumerate(delays):
        pct = min(100, (d / max_delay) * 100) if d > 0 else 3
        color = "#16a34a" if d <= 15 else "#f59e0b" if d <= 45 else "#dc2626"
        label = f"+{d} min" if d > 0 else "On time"
        bars += f'''<div class="bar-row">
            <span class="bar-label">Journey {i+1}</span>
            <div class="bar-track"><div class="bar-fill" style="width:{pct}%; background:{color}"></div></div>
            <span class="bar-value">{label}</span>
        </div>'''
    return bars


def get_delay_verdict(delays):
    if not delays:
        return None, None, None
    on_time_count = sum(1 for d in delays if d <= 15)
    total = len(delays)
    avg = sum(delays) / total
    worst = max(delays)
    if on_time_count / total >= 0.7:
        label, color = "Usually on time", "#16a34a"
    elif on_time_count / total >= 0.4:
        label, color = "Occasionally delayed", "#f59e0b"
    else:
        label, color = "Frequently delayed", "#dc2626"
    sentence = f"On time on {on_time_count} of the last {total} tracked journeys. Average delay: {avg:.1f} min."
    if worst > 45:
        sentence += f" One recent journey saw a {worst}-minute delay."
    return label, color, sentence


def build_route_map(train_no):
    stns = get_train_coords(train_no)
    if not stns:
        return None
    MAJOR_KEYWORDS = ["JN", "JUNCTION", "CENTRAL", "TERMINUS", "TERM", "CITY", "CANTT"]
    coords, names = [], []
    for stop in stns:
        try:
            row = stations.loc[stop["SC"]]
            coords.append((row["Latitude"], row["Longitude"]))
            names.append(stop.get("SN", stop["SC"]))
        except KeyError:
            continue
    if not coords:
        return None
    m = folium.Map(location=coords[0], zoom_start=6, tiles="OpenStreetMap")
    AntPath(coords, color="#2563eb", weight=4, opacity=0.8, delay=800, dash_array=[10, 20]).add_to(m)
    for i, (lat, lon) in enumerate(coords):
        is_endpoint = i == 0 or i == len(coords) - 1
        is_major = is_endpoint or any(kw in names[i].upper() for kw in MAJOR_KEYWORDS)
        if is_major:
            folium.CircleMarker(location=(lat, lon), radius=8, color="#dc2626", fill=True, fill_color="#dc2626", fill_opacity=1, weight=2).add_to(m)
            folium.Marker(location=(lat, lon), icon=folium.DivIcon(html=f'<div style="font-size:11px;font-weight:600;color:#111;white-space:nowrap;transform:translate(8px,-8px);">{names[i]}</div>')).add_to(m)
        else:
            folium.CircleMarker(location=(lat, lon), radius=3, color="#93c5fd", fill=True, fill_opacity=0.8, weight=1).add_to(m)
    m.fit_bounds(coords, padding=(30, 30))
    Fullscreen(position="topright").add_to(m)
    MiniMap(toggle_display=True, position="bottomleft").add_to(m)
    os.makedirs("static", exist_ok=True)
    map_path = f"static/map_{train_no}.html"
    m.save(map_path)
    return map_path
