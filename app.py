from flask import Flask, request, render_template_string
import pandas as pd
import folium
import json
import os
from journey_history import get_train_summary, get_live_last_ride, client

from find_alternative import find_trains

app = Flask(__name__)

stations = pd.read_csv("indian_stations.csv").set_index("Station Code")

def find_station_code(place_name):
    matches = stations[stations['Station Name(en)'].str.contains(place_name.upper(), na=False)]
    if len(matches) == 0:
        return None

    priority_keywords = ["CENTRAL", "TERMINUS", "JN", "CSTM", "CST"]
    for keyword in priority_keywords:
        priority_match = matches[matches['Station Name(en)'].str.contains(keyword, na=False)]
        if len(priority_match) > 0:
            return priority_match.index[0]

    return matches.index[0]


def build_route_map(train_no):
    files = sorted(f for f in os.listdir("snapshots") if f.startswith(train_no))

    if files:
        with open(f"snapshots/{files[-1]}") as f:
            data = json.load(f)
    else:
        try:
            data = client.live_status(train_no, "10-Sep-2026")
        except Exception:
            return None

    if "STNS" not in data:
        return None

    route_codes = [stop["SC"] for stop in data["STNS"]]
    route_names = [stop["SN"] for stop in data["STNS"]]

    coords = []
    labels = []
    for i, code in enumerate(route_codes):
        try:
            row = stations.loc[code]
            coords.append((row["Latitude"], row["Longitude"]))
            labels.append(route_names[i])
        except KeyError:
            continue

    if not coords:
        return None

    m = folium.Map(location=[22, 79], zoom_start=5, tiles="cartodbpositron")
    for i, (lat, lon) in enumerate(coords):
        folium.Marker(
            location=(lat, lon),
            popup=folium.Popup(f"<b>{labels[i]}</b>", max_width=200),
            icon=folium.Icon(color="red", icon="train", prefix="fa"),
            tooltip=labels[i]
        ).add_to(m)
    folium.PolyLine(coords, color="blue").add_to(m)

    os.makedirs("static", exist_ok=True)
    map_path = f"static/map_{train_no}.html"
    m.save(map_path)
    return map_path
PAGE = """
<h1>Railway Delay Predictor</h1>

<h2>Check a train</h2>
<form method="post">
    <input name="train_no" placeholder="Enter train number">
    <button type="submit" name="action" value="check_train">Check Train</button>
</form>

{% if summary %}
    <h3>Train {{ summary.train_no }}</h3>
    <p>Journeys tracked: {{ summary.journeys }}</p>
    <p>Average delay: {{ summary.average_delay }} minutes</p>
    <p>Individual delays: {{ summary.individual_delays }}</p>
{% endif %}

{% if map_path %}
    <h3>Route Map</h3>
    <iframe src="/{{ map_path }}" width="700" height="500"></iframe>
{% elif map_checked %}
    <p>No route data available for this train yet.</p>
{% endif %}

<hr>

<h2>Find alternate trains</h2>
<form method="post">
    <input name="station_a" placeholder="From station code (e.g. MAS)">
    <input name="station_b" placeholder="To station code (e.g. SBC)">
    <button type="submit" name="action" value="find_alternates">Find Trains</button>
</form>

{% if alternates is not none %}
    <p>Found {{ alternates|length }} trains: {{ alternates }}</p>
{% endif %}
"""
@app.route("/", methods=["GET", "POST"])
def home():
    summary = None
    map_path = None
    map_checked = False
    alternates = None

    if request.method == "POST":
        action = request.form.get("action")

        if action == "check_train":
            train_no = request.form.get("train_no", "").strip()
            if train_no:
                summary = get_train_summary(train_no)
                if summary["journeys"] == 0:
                    live_result = get_live_last_ride(train_no)
                    if live_result:
                        summary = {
                            "train_no": train_no,
                            "journeys": 1,
                            "average_delay": live_result["delay"],
                            "individual_delays": [live_result["delay"]]
                        }
                map_checked = True
                map_path = build_route_map(train_no)

        elif action == "find_alternates":
            station_a_input = request.form.get("station_a", "").strip()
            station_b_input = request.form.get("station_b", "").strip()

            station_a = find_station_code(station_a_input) or station_a_input.upper()
            station_b = find_station_code(station_b_input) or station_b_input.upper()

            if station_a and station_b:
                alternates = list(find_trains(station_a, station_b))

    return render_template_string(
        PAGE,
        summary=summary,
        map_path=map_path,
        map_checked=map_checked,
        alternates=alternates,
    )
if __name__ == "__main__":
    app.run(debug=True)
