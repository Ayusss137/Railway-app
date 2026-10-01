from flask import Flask, request, render_template_string, redirect
from concurrent.futures import ThreadPoolExecutor
from live_rail import get_live_status
import os
from train_data import (
    CITY_CENTERS, trains_df, HERO_TRAIN,
    is_curated_city, get_city_station_codes, get_train_info, get_station_name,
    get_quick_delay, get_train_history, get_delay_stats,
    get_route_timeline, build_delay_bars, get_delay_verdict, build_route_map,
    find_trains_between_cities,
)

app = Flask(__name__)
os.makedirs("snapshots", exist_ok=True)
STYLE = '<link rel="stylesheet" href="/static/style.css">'

SWAP_SCRIPT = """
<script>
function swapCities() {
    const a = document.querySelector('input[name="city_a"]');
    const b = document.querySelector('input[name="city_b"]');
    [a.value, b.value] = [b.value, a.value];
}
</script>
"""

# ==============================================================================
# PRETTY & USABLE FRONT PAGE
# ==============================================================================
HOME_PAGE = STYLE + """
<div class="home-container">
    <div class="brand-hero">

        <h1>Find The Best Train For You</h1>
        <p class="tagline">Search trains between stations or track delay history and live maps in one click.</p>
    </div>

    <div class="search-card-wrapper">
        <div class="card search-card">
            <h3 class="search-title">Find Trains Between Stations</h3>
            <form method="post" action="/">
                <div class="search-grid">
                    <div class="input-group">
                        <label>From Station / City</label>
                        <input name="city_a" placeholder="e.g. Mumbai (LTT)" list="city-list" autocomplete="off" required>
                    </div>

                    <button type="button" class="swap-btn" onclick="swapCities()" title="Swap origin & destination">&#8646;</button>

                    <div class="input-group">
                        <label>To Station / City</label>
                        <input name="city_b" placeholder="e.g. Haridwar (HW)" list="city-list" autocomplete="off" required>
                    </div>
                </div>

                <button type="submit" class="primary-btn search-submit-btn">Search Trains &rarr;</button>
                <datalist id="city-list">
                {% for c in city_names %}<option value="{{ c.title() }}">{% endfor %}
                </datalist>
            </form>
        </div>

        <div class="card search-card direct-track-card">
            <h3 class="search-title">Direct Train Lookup</h3>
            <form method="get" action="/train/lookup">
                <div class="input-group">
                    <label>Train Number or Name</label>
                    <input name="train_no" placeholder="e.g. 12171 or LTT HW AC EXP" required>
                </div>
                <button type="submit" class="secondary-btn track-submit-btn">Track Train</button>
            </form>
        </div>
    </div>

    {% if lookup_error %}
        <p class="error">Train not found. Please double-check the train number or name.</p>
    {% endif %}

    {% if hero_map_path %}
    <div class="card hero-map-card">
        <div class="section-title-row">
            <div>
                <h2>Featured Route Tracking: Train {{ hero_train }}</h2>
                <p class="helper-text">{% if hero_info %}{{ hero_info.name }}{% endif %}</p>
            </div>
            <a href="/train/{{ hero_train }}" class="details-link">Full Stats &rarr;</a>
        </div>
        <iframe src="/{{ hero_map_path }}" class="map-iframe"></iframe>
    </div>
    {% endif %}
</div>
""" + SWAP_SCRIPT


# ==============================================================================
# SEARCH RESULTS PAGE
# ==============================================================================
RESULTS_PAGE = STYLE + """
<div class="header-nav">
    <a class="back-link" href="/">&larr; New Search</a>
    <h1>Train Options: {{ city_a.title() }} &rarr; {{ city_b.title() }}</h1>
</div>

<div class="card search-card inline-search">
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
""" + SWAP_SCRIPT + """

{% if error %}<p class="error">{{ error }}</p>{% endif %}

{% if results is not none %}
    <div class="results-toolbar">
        <h2>{{ results|length }} trains available</h2>
        <div class="sort-wrapper">
            <label for="sort_by">Sort by:</label>
            <select name="sort_by" id="sort_by" onchange="document.getElementById('search-form').submit()">
                <option value="delay" {% if sort_by == 'delay' %}selected{% endif %}>Lowest Delay</option>
                <option value="duration" {% if sort_by == 'duration' %}selected{% endif %}>Shortest Duration</option>
                <option value="departure" {% if sort_by == 'departure' %}selected{% endif %}>Earliest Departure</option>
            </select>
        </div>
    </div>

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
            <a class="details-link" href="/train/{{ r.train_no }}?from={{ city_a }}&to={{ city_b }}">View Details &rarr;</a>
        </div>
        <div class="journey-row">
            <div class="journey-point">
                <div class="journey-time">{{ r.dep_time }}</div>
                <div class="journey-station">{{ r.dep_station_name }} ({{ r.dep_station }})</div>
            </div>
            <div class="journey-line">
                <span class="duration-badge">{{ r.duration_h }}h {{ r.duration_m }}m</span>
                <div class="line-graphic"></div>
            </div>
            <div class="journey-point" style="text-align: right;">
                <div class="journey-time">{{ r.arr_time }}{% if r.arr_day > r.dep_day %} <span class="day-offset">+{{ r.arr_day - r.dep_day }}d</span>{% endif %}</div>
                <div class="journey-station">{{ r.arr_station_name }} ({{ r.arr_station }})</div>
            </div>
        </div>
        <div class="train-card-meta">
            <span>Runs: <strong>{{ r.runs_days }}</strong></span>
            <span class="delay-tag">
                {% if r.average_delay is not none %}
                    Avg Delay: <strong>{{ r.average_delay }} mins</strong>
                {% else %}
                    No delay history recorded
                {% endif %}
            </span>
        </div>
    </div>
    {% endfor %}
{% endif %}
"""


# ==============================================================================
# TRAIN DETAILS PAGE (STRICT SECTION ORDER)
# ==============================================================================
TRAIN_PAGE = STYLE + """
<div class="header-nav">
    <a class="back-link" href="/">&larr; Home</a>
    {% if from_city and to_city %}
        <span class="nav-separator">/</span>
        <a class="back-link" href="javascript:history.back()">Back to Search Results</a>
    {% endif %}
</div>

<!-- SECTION 1: YOUR SPECIFIC JOURNEY (Point A to Point B Focus) -->
{% if segment_info %}
<div class="card journey-hero-card">
    <div class="journey-badge">Your Specific Journey: {{ from_city.title() }} &rarr; {{ to_city.title() }}</div>

    <div class="journey-main-row">
        <div class="journey-time-block">
            <span class="j-label">Departs {{ segment_info.dep_station }}</span>
            <span class="j-time">{{ segment_info.dep_time }}</span>
        </div>

        <div class="journey-arrow-block">
            <span class="j-duration">{{ segment_info.duration_h }}h {{ segment_info.duration_m }}m</span>
            <div class="j-line"></div>
        </div>

        <div class="journey-time-block" style="text-align: right;">
            <span class="j-label">Arrives {{ segment_info.arr_station }}</span>
            <span class="j-time">{{ segment_info.arr_time }}</span>
        </div>
    </div>

    <div class="journey-delay-banner">
        {% if summary.average_delay is not none %}
            <span>Expected Delay for your leg: <strong>~{{ summary.average_delay }} mins</strong></span>
        {% else %}
            <span>No delay history recorded for this segment.</span>
        {% endif %}
        <small class="disclaimer-text">Based on historical run trends (Past data)</small>
    </div>
</div>
{% endif %}

<!-- SECTION 2: WHOLE TRAIN JOURNEY OVERVIEW -->
<div class="card">
    <div class="train-header-block">
        <div>
            <span class="train-num">{{ summary.train_no }}</span>
            <h1 class="train-title" style="display:inline-block;">{% if info %}{{ info.name }}{% endif %}</h1>
            <p class="route-subtitle" style="margin-top:4px;">
                Whole Route: <strong>{{ info.from_station_name }} ({{ info.from_station_code }}) &rarr; {{ info.to_station_name }} ({{ info.to_station_code }})</strong>
            </p>
            <p class="runs-line">Operating Days: <strong>{{ info.runs_days if info else 'N/A' }}</strong> &middot; Total Distance: <strong>{{ info.distance }} km</strong></p>
        </div>
        <div class="button-group">
            <a class="irctc-btn" href="https://www.irctc.co.in/nget/train-search" target="_blank">IRCTC Seats</a>
            <a class="irctc-btn ixigo-btn" href="https://www.ixigo.com/trains/train-name-number-search?q={{ summary.train_no }}" target="_blank">ixigo Live Status</a>
        </div>
    </div>
</div>

<!-- LIVE RUNNING STATUS CARD (INSERTED HERE) -->
<div class="card" style="border-left: 4px solid #2563eb;">
    <div class="section-title-row">
        <h2>Live Running Status</h2>
        <span class="schedule-tag" style="background:#dbeafe; color:#1e40af; font-weight:700;">REAL-TIME</span>
    </div>
    {% if live_data %}
        <div class="stat-row" style="margin-top:12px;">
            <div class="stat">
                <div class="stat-label">Current Location</div>
                <div class="stat-value" style="font-size:0.95rem;">{{ summary.current_station }}</div>
            </div>
            <div class="stat">
                <div class="stat-label">Current Delay</div>
                <div class="stat-value {% if summary.live_delay and summary.live_delay > 0 %}text-danger{% else %}text-success{% endif %}">
                    {% if summary.live_delay %}{{ summary.live_delay }} min{% else %}On Time{% endif %}
                </div>
            </div>
            <div class="stat" style="grid-column: span 2;">
                <div class="stat-label">Live Status</div>
                <div class="stat-value" style="font-size:0.95rem;">{{ summary.live_status }}</div>
            </div>
        </div>
    {% else %}
        <p class="helper-text" style="margin-top:8px;">Live API data currently unavailable. Showing historical statistics below.</p>
    {% endif %}
</div>

<!-- SECTION 3: RECORDED DELAY HISTORY & PUNCTUALITY STATS -->
<div class="card">
    <h2>Delay History & Punctuality Stats</h2>
    <p class="helper-text" style="margin-bottom:12px;">Recorded historical delays over past tracked runs.</p>

    {% if stats %}
    <div class="stat-row">
        <div class="stat"><div class="stat-label">Average Delay</div><div class="stat-value">{{ stats.average }} min</div></div>
        <div class="stat"><div class="stat-label">Max Delay</div><div class="stat-value">{{ stats.maximum }} min</div></div>
        <div class="stat"><div class="stat-label">On-Time Rate</div><div class="stat-value">{{ stats.on_time_pct }}%</div></div>
        <div class="stat"><div class="stat-label">Tracked Journeys</div><div class="stat-value">{{ summary.journeys }}</div></div>
    </div>
    {% else %}
        <p class="helper-text">No recorded historical delay metrics available for this train.</p>
    {% endif %}
</div>

<!-- SECTION 4: MAP (IN BETWEEN - PRIZED POSSESSION) -->
{% if map_path %}
<div class="card hero-map-card">
    <div class="section-title-row">
        <h2>Interactive Route Map</h2>
        <span class="schedule-tag">Whole Train Route</span>
    </div>
    <iframe src="/{{ map_path }}" class="map-iframe"></iframe>
</div>
{% endif %}

<!-- SECTION 5: STATION ROUTE TIMELINE -->
{% if route_timeline %}
<div class="card">
    <div class="section-title-row">
        <h2>Station Route & Scheduled Timings</h2>
        <span class="schedule-tag">All Stops</span>
    </div>

    <div class="wmt-timeline">
    {% for stop in route_timeline %}
        {% set is_user_dep = (segment_info and stop.code == segment_info.dep_station) %}
        {% set is_user_arr = (segment_info and stop.code == segment_info.arr_station) %}

        <div class="wmt-stop {% if is_user_dep %}is-user-start{% endif %} {% if is_user_arr %}is-user-end{% endif %} {% if loop.first %}is-first{% endif %} {% if loop.last %}is-last{% endif %}">
            <div class="wmt-node-col">
                <div class="wmt-line-upper"></div>
                <div class="wmt-dot"></div>
                <div class="wmt-line-lower"></div>
            </div>

            <div class="wmt-info">
                <div class="wmt-station-name">
                    {{ stop.name }} <span class="wmt-station-code">({{ stop.code }})</span>
                    {% if is_user_dep %}<span class="user-tag">Boarding</span>{% endif %}
                    {% if is_user_arr %}<span class="user-tag">Destination</span>{% endif %}
                </div>
                <div class="wmt-meta">
                    {% if stop.platform %}PF {{ stop.platform }} &middot; {% endif %}
                    {% if stop.distance %}{{ stop.distance }} km{% endif %}
                </div>
            </div>

            <div class="wmt-timing">
                <div class="wmt-time">{{ stop.time }}</div>
                {% if stop.delay %}
                    <div class="wmt-delay text-danger">+{{ stop.delay }}m delay</div>
                {% else %}
                    <div class="wmt-delay text-success">On Time</div>
                {% endif %}
            </div>
        </div>
    {% endfor %}
    </div>
</div>
{% endif %}
"""

# ==============================================================================
# FLASK ROUTING LOGIC
# ==============================================================================
@app.route("/", methods=["GET", "POST"])
def home():
    if request.method == "GET":
        hero_map_path = build_route_map(HERO_TRAIN)
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
    a_codes = get_city_station_codes(city_a)
    b_codes = get_city_station_codes(city_b)

    if len(a_codes) == 0 or len(b_codes) == 0:
        error = "Could not find matching stations. Please enter valid station or city names."
    elif (not is_curated_city(city_a) and len(a_codes) > 30) or (not is_curated_city(city_b) and len(b_codes) > 30):
        error = "Search matched too many stations — try a more specific city or station name."
    else:
        matches = find_trains_between_cities(a_codes, b_codes)[:5]

        with ThreadPoolExecutor(max_workers=5) as ex:
            delay_results = list(ex.map(lambda m: get_quick_delay(m["train_no"]), matches))

        results = []
        for m, (avg_delay, journeys) in zip(matches, delay_results):
            info = get_train_info(m["train_no"])
            duration_h = int(info["duration_h"]) if info and str(info["duration_h"]).isdigit() else 0
            duration_m = int(info["duration_m"]) if info and str(info["duration_m"]).isdigit() else 0
            results.append({
                "train_no": m["train_no"], "name": info["name"] if info else "Unknown Train",
                "dep_station": m["dep_station"], "dep_station_name": get_station_name(m["dep_station"]),
                "dep_time": m["dep_time"], "dep_day": m["dep_day"],
                "arr_station": m["arr_station"], "arr_station_name": get_station_name(m["arr_station"]),
                "arr_time": m["arr_time"], "arr_day": m["arr_day"],
                "average_delay": avg_delay, "journeys": journeys,
                "runs_days": info["runs_days"] if info else "N/A",
                "duration_h": duration_h, "duration_m": duration_m,
                "duration_min": duration_h * 60 + duration_m,
            })

        if sort_by == "duration":
            results.sort(key=lambda r: r["duration_min"])
        elif sort_by == "departure":
            results.sort(key=lambda r: r["dep_time"])
        else:
            results.sort(key=lambda r: (r["average_delay"] is None, r["average_delay"]))

        # Reset recommendations
        for r in results:
            r["is_recommended"] = False

        # Pick lowest delay train from sorted results
        eligible = [r for r in results if r["average_delay"] is not None]
        if eligible:
            # Sort eligible list specifically by average delay to guarantee lowest delay gets recommended
            best = min(eligible, key=lambda x: x["average_delay"])
            best["is_recommended"] = True
            best["reason"] = f"Lowest avg delay ({best['average_delay']} mins)"

    return render_template_string(
        RESULTS_PAGE, results=results, error=error, city_a=city_a, city_b=city_b, sort_by=sort_by,
    )


@app.route("/train/<train_no>")
def train_detail(train_no):
    from_city = request.args.get("from", "")
    to_city = request.args.get("to", "")

    # 1. Fetch local dataset information
    summary = get_train_history(train_no)
    info = get_train_info(train_no)
    map_path = build_route_map(train_no)
    route_timeline = get_route_timeline(train_no)
    stats = get_delay_stats(summary.get("individual_delays", []))

    # 2. Fetch real-time live running status from API
    live_data = get_live_status(train_no)

    # Merge live tracking details into your summary dictionary
    if live_data:
        summary["current_station"] = live_data.get("current_station", "N/A")
        summary["live_delay"] = live_data.get("delay_minutes", 0)
        summary["live_status"] = live_data.get("status_message", "Running on time")
        # Overwrite default average with current real-time delay if available
        summary["average_delay"] = live_data.get("delay_minutes", summary.get("average_delay"))
    else:
        summary["current_station"] = "Unknown"
        summary["live_delay"] = None
        summary["live_status"] = "Live status unavailable"

    # 3. Calculate segment info for searched routes
    segment_info = None
    if from_city and to_city:
        a_codes = get_city_station_codes(from_city)
        b_codes = get_city_station_codes(to_city)
        matches = find_trains_between_cities(a_codes, b_codes)
        segment_match = next((m for m in matches if m["train_no"] == train_no), None)
        if segment_match:
            duration_h = int(info["duration_h"]) if info and str(info.get("duration_h", "")).isdigit() else 0
            duration_m = int(info["duration_m"]) if info and str(info.get("duration_m", "")).isdigit() else 0
            segment_info = {
                "dep_station": segment_match["dep_station"],
                "arr_station": segment_match["arr_station"],
                "dep_time": segment_match["dep_time"],
                "arr_time": segment_match["arr_time"],
                "duration_h": duration_h,
                "duration_m": duration_m
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
        live_data=live_data
    )

@app.route("/train/lookup")
def train_lookup():
    train_no = request.args.get("train_no", "").strip()
    if train_no in trains_df.index:
        return redirect(f"/train/{train_no}")
    return redirect("/?error=train_not_found")


if __name__ == "__main__":
    app.run(debug=True)
