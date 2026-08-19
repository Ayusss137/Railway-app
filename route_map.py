import pandas as pd
stations = pd.read_csv("indian_stations.csv")

import json
with open("snapshots/snapshot_20260819_181934.json") as route_ma:  # use any real filename you have
    data = json.load(route_ma)

route_codes = [stop["SC"] for stop in data["STNS"]]
print(route_codes)

stations_indexed = stations.set_index("Station Code")  # set the index to the station code

coords = []
for code in route_codes:
    try:
        row = stations_indexed.loc[code]
        coords.append((row["Latitude"], row["Longitude"]))
    except KeyError:
        print(f"Station code not found: {code}")

print(coords)

import folium

m = folium.Map(location=coords[0], zoom_start=7)

for i, (lat, lon) in enumerate(coords):
    folium.Marker(
        location=(lat, lon),
        popup=route_codes[i]
    ).add_to(m)

folium.PolyLine(coords, color="blue").add_to(m)

m.save("route_map.html")
