import os
from pathlib import Path
from dotenv import load_dotenv
from flask import Flask, request, render_template_string, redirect

# Load .env so Supabase credentials are always found
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

from history_store import get_delay_summaries
from live_rail import get_live_status
from train_data import (
    CITY_CENTERS, trains_df, HERO_TRAIN,
    is_curated_city, get_city_station_codes, get_train_info, get_station_name,
    get_route_timeline, get_map_html,
    find_trains_between_cities,
)

app = Flask(__name__, static_folder="public/static")

# ==============================================================================
# CLEAN MODERN RAILWAY STYLES
# ==============================================================================
STYLE = """
<style>
:root {
    --primary: #1e3a8a;
    --primary-light: #3b82f6;
    --bg: #f8fafc;
    --card-bg: #ffffff;
    --border: #e2e8f0;
    --text-dark: #0f172a;
    --text-muted: #64748b;
    --success: #15803d;
    --success-bg: #dcfce7;
    --danger: #b91c1c;
    --danger-bg: #fee2e2;
    --warning: #b45309;
    --warning-bg: #fef3c7;
}
* { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
body { background: var(--bg); color: var(--text-dark); line-height: 1.5; padding-bottom: 60px; }
.container { max-width: 900px; margin: 0 auto; padding: 20px 16px; }

/* Headers & Nav */
.header-nav { display: flex; align-items: center; gap: 12px; margin-bottom: 20px; }
.header-nav h1 { font-size: 1.4rem; font-weight: 700; color: var(--primary); }
.back-link { color: var(--primary-light); text-decoration: none; font-size: 0.9rem; font-weight: 600; }
.back-link:hover { text-decoration: underline; }

/* Cards & Forms */
.card { background: var(--card-bg); border: 1px solid var(--border); border-radius: 10px; padding: 20px; margin-bottom: 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
.search-grid { display: flex; gap: 10px; align-items: flex-end; flex-wrap: wrap; }
.input-group { flex: 1; min-width: 200px; display: flex; flex-direction: column; gap: 4px; }
.input-group label { font-size: 0.8rem; font-weight: 600; color: var(--text-muted); text-transform: uppercase; }
input { padding: 10px 12px; border: 1px solid var(--border); border-radius: 6px; font-size: 0.95rem; }
input:focus { outline: none; border-color: var(--primary-light); }
.swap-btn { padding: 10px 14px; background: #e2e8f0; border: none; border-radius: 6px; cursor: pointer; font-size: 1.1rem; }
.primary-btn { padding: 10px 20px; background: var(--primary); color: #fff; border: none; border-radius: 6px; font-weight: 600; cursor: pointer; }
.primary-btn:hover { background: #1e40af; }

/* Train Cards */
.results-header { display: flex; justify-content: space-between; align-items: center; margin: 24px 0 12px; }
.train-card { background: var(--card-bg); border: 1px solid var(--border); border-radius: 10px; padding: 18px; margin-bottom: 14px; position: relative; transition: border-color 0.2s; }
.train-card.recommended { border: 2px solid #22c55e; }
.rec-pill { position: absolute; top: -11px; left: 16px; background: #15803d; color: #fff; font-size: 0.72rem; font-weight: 700; padding: 2px 10px; border-radius: 20px; letter-spacing: 0.5px; }

.train-top { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 12px; }
.train-num { font-size: 1.15rem; font-weight: 800; color: var(--primary); margin-right: 8px; }
.train-name { font-weight: 600; color: var(--text-dark); font-size: 1.05rem; }

/* Journey Times */
.journey-row { display: flex; align-items: center; justify-content: space-between; background: #f1f5f9; border-radius: 8px; padding: 12px 16px; margin: 12px 0; }
.time-col { min-width: 90px; }
.time-val { font-size: 1.3rem; font-weight: 800; color: var(--text-dark); }
.stn-val { font-size: 0.82rem; color: var(--text-muted); font-weight: 500; }
.duration-col { flex: 1; text-align: center; padding: 0 16px; position: relative; }
.duration-text { font-size: 0.85rem; font-weight: 700; color: var(--primary); background: #e2e8f0; padding: 2px 8px; border-radius: 10px; display: inline-block; }
.duration-line { height: 2px; background: #cbd5e1; margin-top: 6px; position: relative; }

/* Delay Badges */
.train-bottom { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px; font-size: 0.85rem; }
.delay-badge { padding: 4px 10px; border-radius: 6px; font-weight: 600; display: inline-flex; align-items: center; gap: 6px; }
.delay-ok { background: var(--success-bg); color: var(--success); }
.delay-warn { background: var(--warning-bg); color: var(--warning); }
.delay-late { background: var(--danger-bg); color: var(--danger); }
.delay-none { background: #f1f5f9; color: var(--text-muted); }

/* Map */
.map-iframe { width: 100%; height: 380px; border: none; border-radius: 8px; }
</style>
<link rel="stylesheet" href="/static/style.css">
"""

SWAP_SCRIPT = """
<script>
function swapCities() {
    const a = document.querySelector('input[name="city_a"]');
    const b = document.querySelector('input[name="city_b"]');
    if (a && b) { [a.value, b.value] = [b.value, a.value]; }
}
</script>
"""

# ==============================================================================
# HOME PAGE
# ==============================================================================
HOME_PAGE = STYLE + """
<div class="container">
    <div class="card" style="text-align:center; padding: 32px 20px;">
        <h1 style="color:var(--primary); font-size:2rem; margin-bottom:8px;">Know Your Train</h1>
        <p style="color:var(--text-muted); margin-bottom:24px;">Check station-to-station trains with genuine 30-day historical delay data.</p>
        <form method="post" action="/">
            <div class="search-grid" style="justify-content:center;">
                <div class="input-group">
                    <label>From Station / City</label>
                    <input name="city_a" placeholder="e.g. Udupi" list="city-list" required>
                </div>
                <button type="button" class="swap-btn" onclick="swapCities()" title="Swap stations">&#8646;</button>
                <div class="input-group">
                    <label>To Station / City</label>
                    <input name="city_b" placeholder="e.g. Goa (Madgaon)" list="city-list" required>
                </div>
                <button type="submit" class="primary-btn">Search Trains &rarr;</button>
            </div>
            <datalist id="city-list">
            {% for c in city_names %}<option value="{{ c.title() }}">{% endfor %}
            </datalist>
        </form>
    </div>

    <div class="card">
        <h3 style="margin-bottom:12px; font-size:1rem; color:var(--text-muted);">Direct Train Punctuality Lookup</h3>
        <form method="get" action="/train/lookup" style="display:flex; gap:10px;">
            <input name="train_no" placeholder="Enter Train No. e.g. 12658" required style="flex:1;">
            <button type="submit" class="primary-btn" style="background:#475569;">Check Punctuality</button>
        </form>
        {% if lookup_error %}<p style="color:var(--danger); font-size:0.85rem; margin-top:8px;">Train number not found.</p>{% endif %}
    </div>

    {% if hero_map_path %}
    <div class="card">
        <h3 style="margin-bottom:12px; font-size:1.1rem; color:var(--primary);">Featured Route Map: Train {{ hero_train }}</h3>
        <iframe src="{{ hero_map_path }}" class="map-iframe"></iframe>
    </div>
    {% endif %}
</div>
""" + SWAP_SCRIPT

# ==============================================================================
# SEARCH RESULTS PAGE
# ==============================================================================
RESULTS_PAGE = STYLE + """
<div class="container">
    <div class="header-nav">
        <a class="back-link" href="/">&larr; New Search</a>
        <h1>{{ city_a.title() }} &rarr; {{ city_b.title() }}</h1>
    </div>

    <div class="card" style="padding:14px;">
        <form method="post" id="search-form">
            <div class="search-grid">
                <div class="input-group">
                    <label>From</label>
                    <input name="city_a" value="{{ city_a }}">
                </div>
                <button type="button" class="swap-btn" onclick="swapCities()">&#8646;</button>
                <div class="input-group">
                    <label>To</label>
                    <input name="city_b" value="{{ city_b }}">
                </div>
                <button type="submit" class="primary-btn">Update</button>
            </div>
        </form>
    </div>

    {% if error %}<div class="card" style="color:var(--danger)">{{ error }}</div>{% endif %}

    {% if results is not none %}
        <div class="results-header">
            <h2 style="font-size:1.1rem; font-weight:700;">{{ results|length }} Trains Available</h2>
            <div>
                <label style="font-size:0.85rem; font-weight:600; color:var(--text-muted);">Sort by: </label>
                <select name="sort_by" onchange="document.getElementById('search-form').submit()" style="padding:4px 8px; border-radius:4px;">
                    <option value="delay" {% if sort_by == 'delay' %}selected{% endif %}>Lowest Delay</option>
                    <option value="duration" {% if sort_by == 'duration' %}selected{% endif %}>Shortest Duration</option>
                    <option value="departure" {% if sort_by == 'departure' %}selected{% endif %}>Earliest Departure</option>
                </select>
            </div>
        </div>

        {% for r in results %}
        <div class="train-card {% if r.is_recommended %}recommended{% endif %}">
            {% if r.is_recommended %}
                <span class="rec-pill">&#9733; RECOMMENDED &middot; {{ r.reason }}</span>
            {% endif %}
            <div class="train-top">
                <div>
                    <span class="train-num">{{ r.train_no }}</span>
                    <span class="train-name">{{ r.name }}</span>
                </div>
                <a class="back-link" href="/train/{{ r.train_no }}?from={{ city_a }}&to={{ city_b }}">View Route &rarr;</a>
            </div>

            <!-- Accurate Segment Journey Times -->
            <div class="journey-row">
                <div class="time-col">
                    <div class="time-val">{{ r.dep_time }}</div>
                    <div class="stn-val">{{ r.dep_station_name }} ({{ r.dep_station }})</div>
                </div>
                <div class="duration-col">
                    <span class="duration-text">{{ r.duration_h }}h {{ r.duration_m }}m</span>
                    <div class="duration-line"></div>
                </div>
                <div class="time-col" style="text-align:right;">
                    <div class="time-val">{{ r.arr_time }}{% if r.arr_day > r.dep_day %} <small style="font-size:0.75rem; color:var(--primary-light);">+{{ r.arr_day - r.dep_day }}d</small>{% endif %}</div>
                    <div class="stn-val">{{ r.arr_station_name }} ({{ r.arr_station }})</div>
                </div>
            </div>

            <!-- Historical Delay Badge -->
            <div class="train-bottom">
                <span style="color:var(--text-muted)">Runs: <strong>{{ r.runs_days }}</strong></span>
                <div>
                    {% if r.average_delay is not none %}
                        {% if r.average_delay == 0 %}
                            <span class="delay-badge delay-ok">Avg delay: 0 min (On Time &middot; {{ r.journeys }} recorded journeys)</span>
                        {% elif r.average_delay <= 15 %}
                            <span class="delay-badge delay-warn">Avg delay: {{ r.average_delay }} min ({{ r.journeys }} recorded journeys)</span>
                        {% else %}
                            <span class="delay-badge delay-late">Avg delay: {{ r.average_delay }} min ({{ r.journeys }} recorded journeys)</span>
                        {% endif %}
                    {% else %}
                        <span class="delay-badge delay-none">No delay history available</span>
                    {% endif %}
                </div>
            </div>
        </div>
        {% endfor %}
    {% endif %}
</div>
""" + SWAP_SCRIPT

# ==============================================================================
# TRAIN DETAILS & MAP PAGE
# ==============================================================================
TRAIN_PAGE = STYLE + """
<div class="container">
    <div class="header-nav">
        <a class="back-link" href="/">&larr; Home</a>
        {% if from_city and to_city %}
            <span style="color:var(--text-muted)">/</span>
            <a class="back-link" href="javascript:history.back()">Back to Search</a>
        {% endif %}
    </div>

    <!-- Segment Highlight (if searched from a route) -->
    {% if segment_info %}
    <div class="card" style="border-left: 4px solid var(--primary-light);">
        <div style="font-size:0.8rem; font-weight:700; color:var(--text-muted); text-transform:uppercase;">Your Leg: {{ from_city.title() }} &rarr; {{ to_city.title() }}</div>
        <div class="journey-row" style="background:transparent; padding:8px 0 0;">
            <div class="time-col">
                <div class="time-val">{{ segment_info.dep_time }}</div>
                <div class="stn-val">{{ segment_info.dep_station }}</div>
            </div>
            <div class="duration-col">
                <span class="duration-text">{{ segment_info.duration_h }}h {{ segment_info.duration_m }}m</span>
                <div class="duration-line"></div>
            </div>
            <div class="time-col" style="text-align:right;">
                <div class="time-val">{{ segment_info.arr_time }}</div>
                <div class="stn-val">{{ segment_info.arr_station }}</div>
            </div>
        </div>
    </div>
    {% endif %}

    <!-- Train Overview -->
    <div class="card">
        <div class="train-top">
            <div>
                <span class="train-num">{{ summary.train_no }}</span>
                <span class="train-name">{% if info %}{{ info.name }}{% endif %}</span>
                <p style="color:var(--text-muted); font-size:0.9rem; margin-top:4px;">
                    Full Route: <strong>{{ info.from_station_name }} ({{ info.from_station_code }}) &rarr; {{ info.to_station_name }} ({{ info.to_station_code }})</strong>
                </p>
                <p style="color:var(--text-muted); font-size:0.85rem; margin-top:2px;">
                    Days: <strong>{{ info.runs_days if info else 'N/A' }}</strong> &middot; Distance: <strong>{{ info.distance }} km</strong>
                </p>
            </div>
            <div style="display:flex; gap:8px;">
                <a class="primary-btn" href="https://www.irctc.co.in/nget/train-search" target="_blank" style="text-decoration:none; font-size:0.85rem; padding:6px 12px;">IRCTC</a>
                <a class="primary-btn" href="https://www.ixigo.com/trains/train-name-number-search?q={{ summary.train_no }}" target="_blank" style="text-decoration:none; font-size:0.85rem; padding:6px 12px; background:#e11d48;">ixigo</a>
            </div>
        </div>
    </div>

    <!-- 30-Day Historical Punctuality Stats -->
    <div class="card">
        <h3 style="font-size:1.05rem; font-weight:700; color:var(--text-dark); margin-bottom:12px;">30-Day Historical Punctuality (NTES Verified)</h3>
        {% if stats %}
        <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(130px, 1fr)); gap:12px; text-align:center;">
            <div style="background:#f1f5f9; padding:12px; border-radius:8px;">
                <div style="font-size:0.75rem; color:var(--text-muted); font-weight:600;">AVG DELAY</div>
                <div style="font-size:1.3rem; font-weight:800; color:var(--primary);">{{ stats.average }} min</div>
            </div>
            <div style="background:#f1f5f9; padding:12px; border-radius:8px;">
                <div style="font-size:0.75rem; color:var(--text-muted); font-weight:600;">MAX DELAY</div>
                <div style="font-size:1.3rem; font-weight:800; color:var(--danger);">{{ stats.maximum }} min</div>
            </div>
            <div style="background:#f1f5f9; padding:12px; border-radius:8px;">
                <div style="font-size:0.75rem; color:var(--text-muted); font-weight:600;">ON-TIME RATE</div>
                <div style="font-size:1.3rem; font-weight:800; color:var(--success);">{{ stats.on_time_pct }}%</div>
            </div>
            <div style="background:#f1f5f9; padding:12px; border-radius:8px;">
                <div style="font-size:0.75rem; color:var(--text-muted); font-weight:600;">JOURNEYS</div>
                <div style="font-size:1.3rem; font-weight:800; color:var(--text-dark);">{{ summary.journeys }}</div>
            </div>
        </div>
        {% else %}
        <p style="color:var(--text-muted); font-size:0.9rem;">No delay history available for this train in the last 30 days.</p>
        {% endif %}
    </div>

    <!-- Map Section (In-Memory Folium) -->
    {% if map_path %}
    <div class="card">
        <h3 style="font-size:1.05rem; font-weight:700; color:var(--text-dark); margin-bottom:12px;">Route Map</h3>
        <iframe src="{{ map_path }}" class="map-iframe"></iframe>
    </div>
    {% endif %}

    <!-- Station Timeline -->
    {% if route_timeline %}
    <div class="card">
        <h3 style="font-size:1.05rem; font-weight:700; color:var(--text-dark); margin-bottom:12px;">Timetable & Stops</h3>
        <div style="font-size:0.9rem;">
        {% for stop in route_timeline %}
            <div style="display:flex; justify-content:space-between; padding:8px 0; border-bottom:1px solid #f1f5f9;">
                <div>
                    <strong>{{ stop.name }}</strong> <span style="color:var(--text-muted)">({{ stop.code }})</span>
                </div>
                <div><strong>{{ stop.time }}</strong></div>
            </div>
        {% endfor %}
        </div>
    </div>
    {% endif %}
</div>
"""

# ==============================================================================
# FLASK ROUTES
# ==============================================================================
@app.route("/", methods=["GET", "POST"])
def home():
    if request.method == "GET":
        hero_map_path = f"/map/{HERO_TRAIN}"
        hero_info = get_train_info(HERO_TRAIN)
        lookup_error = request.args.get("error") == "train_not_found"
        return render_template_string(
            HOME_PAGE, hero_map_path=hero_map_path, hero_train=HERO_TRAIN,
            hero_info=hero_info, lookup_error=lookup_error, city_names=list(CITY_CENTERS.keys()),
        )

    results = None
    error = None
    city_a = request.form.get("city_a", "").strip()
    city_b = request.form.get("city_b", "").strip()
    sort_by = request.form.get("sort_by", "delay")

    # Reject empty submissions before station lookup
    if not city_a or not city_b:
        return redirect("/")

    a_codes = get_city_station_codes(city_a)
    b_codes = get_city_station_codes(city_b)

    if len(a_codes) == 0 or len(b_codes) == 0:
        error = "Could not find matching stations. Please enter valid station or city names."
    elif (not is_curated_city(city_a) and len(a_codes) > 30) or (not is_curated_city(city_b) and len(b_codes) > 30):
        error = "Search matched too many stations — try a more specific city or station name."
    else:
        # 1. Segment-matched trains (calculates segment timings from timetable)
        matches = find_trains_between_cities(a_codes, b_codes)
        top_matches = matches[:20]

        # 2. 1 Batched Supabase query for all 20 trains
        train_nos = [m["train_no"] for m in top_matches]
        delay_map = get_delay_summaries(train_nos)

        results = []
        for m in top_matches:
            info = get_train_info(m["train_no"])
            summary = delay_map.get(m["train_no"], {"average_delay": None, "journeys": 0})
            results.append({
                "train_no": m["train_no"],
                "name": info["name"] if info else "Unknown Train",
                "dep_station": m["dep_station"],
                "dep_station_name": get_station_name(m["dep_station"]),
                "dep_time": m["dep_time"],
                "dep_day": m["dep_day"],
                "arr_station": m["arr_station"],
                "arr_station_name": get_station_name(m["arr_station"]),
                "arr_time": m["arr_time"],
                "arr_day": m["arr_day"],
                "average_delay": summary.get("average_delay"),
                "journeys": summary.get("journeys", 0),
                "runs_days": info["runs_days"] if info else "N/A",
                "duration_h": m["duration_h"],
                "duration_m": m["duration_m"],
                "duration_min": m["duration_min"],
                "is_recommended": False,
                "reason": "",
            })

        # 3. Crash-proof sorting
        if sort_by == "duration":
            results.sort(key=lambda r: r["duration_min"])
        elif sort_by == "departure":
            results.sort(key=lambda r: r["dep_time"])
        else:
            results.sort(key=lambda r: (
                r["average_delay"] is None,
                r["average_delay"] if r["average_delay"] is not None else 999999
            ))

        # 4. Recommend only trains with genuine verified history
        eligible = [r for r in results if r["average_delay"] is not None and r["journeys"] > 0]
        if eligible:
            best = min(eligible, key=lambda x: x["average_delay"])
            best["is_recommended"] = True
            best["reason"] = f"Lowest avg delay ({best['average_delay']} min over {best['journeys']} runs)"

    return render_template_string(
        RESULTS_PAGE, results=results, error=error, city_a=city_a, city_b=city_b, sort_by=sort_by,
    )


@app.route("/train/<train_no>")
def train_detail(train_no):
    from_city = request.args.get("from", "")
    to_city = request.args.get("to", "")

    delays_data = get_delay_summaries([train_no]).get(train_no, {})
    avg_delay = delays_data.get("average_delay")
    journeys = delays_data.get("journeys", 0)
    stats = delays_data.get("stats")

    info = get_train_info(train_no)
    map_path = f"/map/{train_no}"
    route_timeline = get_route_timeline(train_no)

    summary = {
        "train_no": train_no,
        "average_delay": avg_delay,
        "journeys": journeys,
    }

    segment_info = None
    if from_city and to_city:
        a_codes = get_city_station_codes(from_city)
        b_codes = get_city_station_codes(to_city)
        matches = find_trains_between_cities(a_codes, b_codes)
        segment_match = next((m for m in matches if m["train_no"] == train_no), None)
        if segment_match:
            segment_info = {
                "dep_station": segment_match["dep_station"],
                "arr_station": segment_match["arr_station"],
                "dep_time": segment_match["dep_time"],
                "arr_time": segment_match["arr_time"],
                "duration_h": segment_match["duration_h"],
                "duration_m": segment_match["duration_m"],
            }

    return render_template_string(
        TRAIN_PAGE,
        summary=summary,
        info=info,
        map_path=map_path,
        from_city=from_city,
        to_city=to_city,
        segment_info=segment_info,
        route_timeline=route_timeline,
        stats=stats,
    )


@app.route("/map/<train_no>")
def route_map(train_no):
    if not train_no.isdigit() or len(train_no) > 6:
        return "Invalid train number", 400
    html = get_map_html(train_no)
    if not html:
        return "<p style='font-family:sans-serif;padding:16px'>Route map unavailable.</p>", 404
    return html, 200, {
        "Content-Type": "text/html; charset=utf-8",
        "Cache-Control": "public, max-age=300"
    }


@app.route("/train/lookup")
def train_lookup():
    train_no = request.args.get("train_no", "").strip()
    if train_no in trains_df.index:
        return redirect(f"/train/{train_no}")
    return redirect("/?error=train_not_found")


if __name__ == "__main__":
    app.run(debug=True)
