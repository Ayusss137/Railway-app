# Railway Delay Tracker

Check how a train *actually* runs before you book it. Search two cities, compare every direct train between them, and see real delay history, live status and an interactive route map for each one.

> Live demo: _add your Vercel URL here after deploy_

![screenshot](docs/screenshot.png)
<!-- Add 2-3 screenshots to docs/: search results, train detail page, route map -->

## Why this exists

Timetable apps tell you *when a train is supposed to run*. They don't tell you whether it is usually 10 minutes late or 6 hours late. This project answers the question a traveller really has: **"Does this specific train delay regularly, and what are my alternatives?"**

## Features

- **City-to-city search** – finds direct trains between any two curated cities, using nearby-station matching (so "Mumbai" covers CSMT, LTT, Dadar and others)
- **Train number lookup** – jump straight to any train's detail page
- **Delay history** – average, median, worst case and on-time percentage across recent journeys, with a per-journey bar chart
- **Honest data labelling** – trains with little history are flagged as limited data and never get a "Recommended" badge
- **Your journey vs. the whole train** – detail page separates your A→B leg from the train's full route
- **Interactive route map** – animated Folium map of the train's real station sequence
- **Live running status** – optional, via RapidAPI
- **Sorting** – by lowest delay, shortest duration or earliest departure
- **Special-train notice** – `0xxxx` trains run irregularly, so the app says so

## How it works

```
 Browser ──► Flask app (app.py) ──► train_data.py ──┬─► CSV datasets (stations, trains, stops)
                                                    ├─► ntes-client  (live NTES status, delay lookback)
                                                    └─► journey_history.py (saved snapshots)
```

1. Station coordinates come from `indian_stations.csv`; a city name is resolved to nearby stations with haversine distance.
2. The train schedule dataset was rebuilt with a crawler (`railpull`) because the public datasets were ~10 years old and listed trains that no longer run.
3. Candidate trains are validated against live NTES data before being shown.
4. Delay history comes from a poller that saves timestamped NTES snapshots, with a multi-day live lookback as fallback for trains with no saved history.
5. Delay minutes are parsed from raw NTES text, de-duplicated into distinct journeys, then summarised.

## Tech stack

Python · Flask · pandas · Folium · ntes-client · Jinja2 · Vercel

## Run locally

```bash
git clone https://github.com/Ayusss137/Railway-app.git
cd Railway-app

python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env            # then add your RapidAPI key (optional, for live status)
python app.py
```

Open http://127.0.0.1:5000

### Optional: run the delay poller

```bash
python test_fetch.py
```

Saves a timestamped snapshot of each tracked train every 30 minutes into `snapshots/`. The more it runs, the richer the delay history gets.

## Deploy to Vercel

1. Push the repo to GitHub.
2. Import it at vercel.com/new (Vercel detects Flask automatically).
3. Add the environment variable `RAPIDAPI_KEY` (optional).
4. Set the function region to Mumbai (`bom1`) so calls to NTES come from an Indian IP.
5. Deploy.

The poller needs a long-running process, so it does **not** run on Vercel. The deployed app uses live NTES lookups; run the poller on your own machine if you want snapshot history.

## Project structure

```
app.py               Flask routes and page templates
train_data.py        data loading, city matching, delay stats, map building
journey_history.py   journey extraction and history summaries
analyze_delays.py    delay parsing from raw NTES text
find_alternative.py  finds trains connecting two cities
live_rail.py         optional live status via RapidAPI
test_fetch.py        snapshot poller
public/static/       stylesheet
```

## Known limitations

- Uses an **unofficial** NTES wrapper, which can break or rate-limit without notice
- City search covers ~40 curated cities; other names fall back to station-name matching
- Delay history is only as deep as the data collected so far
- No seat availability (links out to IRCTC and ixigo instead)
- No ML prediction yet

## Roadmap

- [ ] Fuzzy and phonetic station matching (e.g. Madgaon / Margao)
- [ ] Broader city coverage and station autocomplete
- [ ] Delay prediction model once enough history exists
- [ ] Move templates into real Jinja files
- [ ] Scheduled poller (GitHub Actions or a small worker)

## Disclaimer

Independent project. Not affiliated with Indian Railways, IRCTC, CRIS or NTES. Delay figures are historical and informational only; always confirm with official sources before travel.

## License

MIT
