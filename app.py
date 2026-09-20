from flask import Flask, request, render_template_string
import pandas as pd
import folium
from folium.plugins import AntPath, Fullscreen, MiniMap
import json
import os
import statistics
from datetime import datetime, timedelta
from math import radians, sin, cos, sqrt, atan2
from journey_history import get_train_summary, get_live_last_ride, get_last_n_rides, client
from find_alternative import find_trains_between_cities

app = Flask(__name__)

stations = pd.read_csv("indian_stations.csv").set_index("Station Code")
trains_df = pd.read_csv("trains_new.csv", dtype={"number": str}).set_index("number")
stops_df = pd.read_csv("stops_new.csv", dtype={"train_number": str})
station_train_counts = stops_df.groupby("station_code")["train_number"].nunique()

HERO_TRAIN = "12658"
MAJOR_KEYWORDS = ["JN", "JUNCTION", "CENTRAL", "TERMINUS", "TERM", "CITY", "CANTT"]

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
        }
    return None

def get_station_name(code):
    try:
        return stations.loc[code, 'Station Name(en)']
    except KeyError:
        return code

def get_quick_delay(train_no):
    summary = get_train_summary(train_no)
    if summary["journeys"] > 0:
        return summary["average_delay"], summary["journeys"]
    rides = get_last_n_rides(train_no, n=3)
    delays = [r["delay"] for r in rides if r["delay"] is not None]
    if delays:
        return round(sum(delays) / len(delays), 1), len(delays)
    return None, 0

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

def is_major_station(name):
    return any(kw in name.upper() for kw in MAJOR_KEYWORDS)

def build_route_timeline_html(train_no):
    stns = get_train_coords(train_no)
    if not stns:
        return ""

    stops = []
    for i, stop in enumerate(stns):
        code = stop.get("SC", "?")
        name = stop.get("SN", code)
        time = stop.get("STA") or stop.get("STD") or "?"
        is_endpoint = i == 0 or i == len(stns) - 1
        major = is_endpoint or is_major_station(name)
        stops.append({"code": code, "name": name, "time": time, "major": major})

    html = '<div class="timeline">'
    group_id = 0
    pending_group = []

    for stop in stops:
        if stop["major"]:
            if pending_group:
                html += f'<div class="timeline-group" id="grp-{group_id}" style="display:none">'
                for s in pending_group:
                    html += f'''<div class="timeline-row minor">
                        <div class="timeline-time">{s["time"]}</div>
                        <div class="timeline-dot minor-dot"></div>
                        <div class="timeline-station">{s["name"]} <small>({s["code"]})</small></div>
                    </div>'''
                html += '</div>'
                pending_group = []
                group_id += 1
            extra = f' onclick="toggleGroup({group_id})" style="cursor:pointer"' if True else ''
            html += f'''<div class="timeline-row major"{extra}>
                <div class="timeline-time">{stop["time"]}</div>
                <div class="timeline-dot major-dot"></div>
                <div class="timeline-station"><strong>{stop["name"]}</strong> <small>({stop["code"]})</small> <span class="expand-hint">&#9660; tap to expand</span></div>
            </div>'''
        else:
            pending_group.append(stop)

    if pending_group:
        html += f'<div class="timeline-group" id="grp-{group_id}" style="display:none">'
        for s in pending_group:
            html += f'''<div class="timeline-row minor">
                <div class="timeline-time">{s["time"]}</div>
                <div class="timeline-dot minor-dot"></div>
                <div class="timeline-station">{s["name"]} <small>({s["code"]})</small></div>
            </div>'''
        html += '</div>'

    html += '</div>'
    return html

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
        is_major = is_endpoint or is_major_station(names[i])
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

STYLE = '<link rel="stylesheet" href="/static/style.css">'

SWAP_SCRIPT = """
<script>
function swapCities() {
    const a = document.querySelector('input[name="city_a"]');
    const b = document.querySelector('input[name="city_b"]');
    [a.value, b.value] = [b.value, a.value];
}
function toggleGroup(id) {
    const el = document.getElementById('grp-' + id);
    if (el) el.style.display = el.style.display === 'none' ? 'block' : 'none';
}
</script>
"""

HOME_PAGE = STYLE + """
<h1>Railway Delay Tracker</h1>
<p class="tagline">Find trains. Compare routes. Understand delays.</p>

<div class="search-box">
    <form method="post">
        <label>From</label>
        <input name="city_a" placeholder="e.g. Mumbai">
        <button type="button" onclick="swapCities()" style="background:#6b7280">&#8646;</button>
        <label>To</label>
        <input name="city_b" placeholder="e.g. Chennai">
        <button type="submit">Find trains</button>
    </form>
    <p><small>Searches nearby major stations automatically.</small></p>
</div>
""" + SWAP_SCRIPT + """
<div class="feature-row">
    <div class="feature-card">
        <div class="feature-icon">&#128506;</div>
        <div class="feature-title">Live Route Maps</div>
        <div class="feature-desc">See exactly where your train goes, station by station.</div>
    </div>
    <div class="feature-card">
        <div class="feature-icon">&#128200;</div>
        <div class="feature-title">Real Delay History</div>
        <div class="feature-desc">Tracked from actual past journeys, not guesses.</div>
    </div>
    <div class="feature-card">
        <div class="feature-icon">&#128260;</div>
        <div class="feature-title">Smart Alternatives</div>
        <div class="feature-desc">Compare every train on your route, sorted by reliability.</div>
    </div>
</div>
{% if hero_map_path %}
<div class="card" style="margin-top:32px">
    <h2 style="margin-top:0">Explore: Train {{ hero_train }} {% if hero_info %}&mdash; {{ hero_info.name }}{% endif %}</h2>
    <p><small>See real delay history and live route tracking &mdash; this is what we track for every train.</small></p>
    <iframe src="/{{ hero_map_path }}" width="100%" height="380"></iframe>
</div>
{% endif %}
"""

RESULTS_PAGE = STYLE + """
<h1>Railway Delay Tracker</h1>
<a class="back-link" href="/">&larr; New search</a>

<div class="search-box" style="margin-top:12px">
    <form method="post">
        <label>From</label>
        <input name="city_a" placeholder="e.g. Mumbai" value="{{ city_a }}">
        <button type="button" onclick="swapCities()" style="background:#6b7280">&#8646;</button>
        <label>To</label>
        <input name="city_b" placeholder="e.g. Chennai" value="{{ city_b }}">
        <button type="submit">Find trains</button>
    </form>
</div>
""" + SWAP_SCRIPT + """
{% if error %}<p class="error">{{ error }}</p>{% endif %}

{% if results is not none %}
    <h2>{{ results|length }} trains found</h2>
    {% for r in results %}
    <div class="train-card {% if r.is_recommended %}recommended{% endif %}">
        {% if r.is_recommended %}
        <div class="rec-header">&#9733; RECOMMENDED &middot; {{ r.reason }}</div>
        {% endif %}
        <div class="train-card-top">
            <div>
                <span class="train-num">{{ r.train_no }}</span>
                <span class="train-name">{{ r.name }}</span>
            </div>
            <a class="details-link" href="/train/{{ r.train_no }}?from={{ city_a }}&to={{ city_b }}">View details &rarr;</a>
        </div>
        <div class="journey-row">
            <div class="journey-point">
                <div class="journey-time">{{ r.dep_time }}</div>
                <div class="journey-station">{{ r.dep_station_name }} ({{ r.dep_station }})</div>
            </div>
            <div class="journey-line">&rarr;</div>
            <div class="journey-point">
                <div class="journey-time">{{ r.arr_time }}{% if r.arr_day > r.dep_day %} <small>+{{ r.arr_day - r.dep_day }}d</small>{% endif %}</div>
                <div class="journey-station">{{ r.arr_station_name }} ({{ r.arr_station }})</div>
            </div>
        </div>
        <div class="train-card-meta">
            <span>Runs: {{ r.runs_days }}</span>
            <span class="delay-tag">
                {% if r.average_delay is not none %}
                    Avg delay: {{ r.average_delay }} min
                    {% if r.journeys < 3 %}<small>&middot; limited data ({{ r.journeys }} journey{{ 's' if r.journeys != 1 else '' }})</small>{% endif %}
                {% else %}
                    No delay data yet
                {% endif %}
            </span>
        </div>
    </div>
    {% endfor %}
{% endif %}
"""

TRAIN_PAGE = STYLE + """
<h1>Railway Delay Tracker</h1>
<a class="back-link" href="/">&larr; Home</a>
{% if from_city and to_city %} | <a class="back-link" href="javascript:history.back()">&larr; Back to results</a>{% endif %}

<div class="card">
    <div class="train-num" style="font-size:1.4rem">{{ summary.train_no }}</div>
    {% if info %}<div class="train-name" style="font-size:1.1rem">{{ info.name }}</div>{% endif %}
    {% if info %}
        <p style="margin-top:10px">{{ info.from_station_name }} ({{ info.from_station_code }}) &rarr; {{ info.to_station_name }} ({{ info.to_station_code }})</p>
        <p class="runs-line">Runs: {{ info.runs_days }}</p>
    {% endif %}
    <div class="stat-row">
        {% if info %}
        <div class="stat"><div class="stat-label">Duration</div><div class="stat-value">{{ info.duration_h }}h {{ info.duration_m }}m</div></div>
        <div class="stat"><div class="stat-label">Distance</div><div class="stat-value">{{ info.distance }} km</div></div>
        {% endif %}
        <div class="stat"><div class="stat-label">Journeys Tracked</div><div class="stat-value">{{ summary.journeys }}</div></div>
        <div class="stat"><div class="stat-label">Avg Delay</div><div class="stat-value">{{ summary.average_delay if summary.average_delay is not none else "No data yet" }}{% if summary.average_delay is not none %} min{% endif %}</div></div>
    </div>
    <a class="irctc-btn" href="https://www.irctc.co.in/nget/train-search" target="_blank">Check seat availability on IRCTC</a>
    <a class="irctc-btn" style="background:#f97316" href="https://www.ixigo.com/trains/train-name-number-search?q={{ summary.train_no }}" target="_blank">Check on ixigo</a>
</div>

{% if stats %}
<div class="card">
    <h2 style="margin-top:0">Delay Statistics</h2>
    {% if stats.count < 3 %}<p class="warn-note">&#9888; Limited data &mdash; based on only {{ stats.count }} tracked journey{{ 's' if stats.count != 1 else '' }}.</p>{% endif %}
    <div class="stat-row">
        <div class="stat"><div class="stat-label">Average</div><div class="stat-value">{{ stats.average }} min</div></div>
        <div class="stat"><div class="stat-label">Median</div><div class="stat-value">{{ stats.median }} min</div></div>
        <div class="stat"><div class="stat-label">Maximum</div><div class="stat-value">{{ stats.maximum }} min</div></div>
        <div class="stat"><div class="stat-label">Minimum</div><div class="stat-value">{{ stats.minimum }} min</div></div>
        <div class="stat"><div class="stat-label">On-Time %</div><div class="stat-value">{{ stats.on_time_pct }}%<small>*</small></div></div>
    </div>
    <p><small>*Based on {{ stats.count }} tracked journey{{ 's' if stats.count != 1 else '' }}.</small></p>
</div>
{% endif %}

{% if verdict_label %}
<div class="card">
    <h2 style="margin-top:0">Delay Pattern</h2>
    <span class="verdict-badge" style="background:{{ verdict_color }}">{{ verdict_label }}</span>
    <p>{{ verdict_sentence }}</p>
    {{ delay_bars_html | safe }}
</div>
{% endif %}

{% if map_path %}
<div class="card">
    <h2 style="margin-top:0">Route Map</h2>
    <iframe src="/{{ map_path }}" width="100%" height="480"></iframe>
</div>
{% else %}
    <p class="error">No route data available for this train yet.</p>
{% endif %}

{% if route_timeline_html %}
<div class="card">
    <h2 style="margin-top:0">Route Timeline</h2>
    <p><small>Major stations shown. Tap one to see the stops in between.</small></p>
    {{ route_timeline_html | safe }}
</div>
{% endif %}
""" + SWAP_SCRIPT

@app.route("/", methods=["GET", "POST"])
def home():
    if request.method == "GET":
        hero_map_path = build_route_map(HERO_TRAIN)
        hero_info = get_train_info(HERO_TRAIN)
        return render_template_string(HOME_PAGE, hero_map_path=hero_map_path, hero_train=HERO_TRAIN, hero_info=hero_info)

    results = None
    error = None
    city_a = request.form.get("city_a", "").strip()
    city_b = request.form.get("city_b", "").strip()
    a_codes = get_city_station_codes(city_a)
    b_codes = get_city_station_codes(city_b)
    if len(a_codes) == 0 or len(b_codes) == 0:
        error = "Could not find one or both cities. Try a fuller name."
    elif (not is_curated_city(city_a) and len(a_codes) > 30) or (not is_curated_city(city_b) and len(b_codes) > 30):
        error = "Search matched too many stations — try a more specific city name."
    else:
        matches = find_trains_between_cities(a_codes, b_codes)[:8]
        results = []
        for m in matches:
            avg_delay, journeys = get_quick_delay(m["train_no"])
            info = get_train_info(m["train_no"])
            results.append({
                "train_no": m["train_no"], "name": info["name"] if info else "Unknown",
                "dep_station": m["dep_station"], "dep_station_name": get_station_name(m["dep_station"]),
                "dep_time": m["dep_time"], "dep_day": m["dep_day"],
                "arr_station": m["arr_station"], "arr_station_name": get_station_name(m["arr_station"]),
                "arr_time": m["arr_time"], "arr_day": m["arr_day"],
                "average_delay": avg_delay, "journeys": journeys,
                "runs_days": info["runs_days"] if info else "?",
            })
        results.sort(key=lambda r: (r["average_delay"] is None, r["average_delay"]))
        if results:
            results[0]["is_recommended"] = True
            best = results[0]
            if best["average_delay"] is not None:
                results[0]["reason"] = f"Lowest avg delay ({best['average_delay']} min)"
            else:
                results[0]["reason"] = "Earliest departure with a valid route"
            for r in results[1:]:
                r["is_recommended"] = False
    return render_template_string(RESULTS_PAGE, results=results, error=error, city_a=city_a, city_b=city_b)

@app.route("/train/<train_no>")
def train_detail(train_no):
    from_city = request.args.get("from", "")
    to_city = request.args.get("to", "")
    summary = get_train_history(train_no)
    info = get_train_info(train_no)
    map_path = build_route_map(train_no)
    route_timeline_html = build_route_timeline_html(train_no)
    verdict_label, verdict_color, verdict_sentence = get_delay_verdict(summary["individual_delays"])
    delay_bars_html = build_delay_bars(summary["individual_delays"])
    stats = get_delay_stats(summary["individual_delays"])
    return render_template_string(
        TRAIN_PAGE, summary=summary, info=info, map_path=map_path,
        from_city=from_city, to_city=to_city, route_timeline_html=route_timeline_html,
        verdict_label=verdict_label, verdict_color=verdict_color, verdict_sentence=verdict_sentence,
        delay_bars_html=delay_bars_html, stats=stats,
    )

if __name__ == "__main__":
    app.run(debug=True)
