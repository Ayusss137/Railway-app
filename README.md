# Railway App — Find the Best Train for You

A Flask-based web application designed to help users search trains between stations, track route schedules, analyze historical delay patterns, and view real-time train running status across Indian Railways.

---

## Key Features

* **Train Search Between Stations:** Find available direct train options connecting departure and destination cities.
* **Direct Train Lookup:** Quick lookup using either train number or train name.
* **Journey Segment Calculations:** View departure times, arrival times, and estimated journey durations for your specific leg.
* **Live Running Status Integration:** Fetch live station updates, delay metrics, and current train status via external APIs.
* **Historical Delay & Punctuality Stats:** Displays average delay, maximum recorded delay, and overall on-time percentages based on tracked runs.
* **Interactive Route Maps:** Embedded route visualization maps generated for individual train routes.
* **Station Route Timeline:** Detailed breakdown of scheduled station stops, platform numbers, distance markers, and punctuality status.

---

## Project Structure

```text
├── app.py              # Main Flask application and web routes
├── live_rail.py        # Module for handling external Live Rail API requests
├── train_data.py       # Local dataset for static schedules and history fallback
├── requirements.txt    # Project dependencies
├── static/             # Static assets (CSS styles and generated route maps)
│   ├── style.css
│   └── map_*.html
└── templates/          # HTML view templates    ├──
