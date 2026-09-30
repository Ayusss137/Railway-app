import requests

# Get this from your RapidAPI Dashboard
API_KEY = "YOUR_RAPIDAPI_KEY_HERE"

def get_live_status(train_no):
    """
    Fetches real-time status for a train using RapidAPI Indian Railways endpoint.
    """
    url = "https://indian-railway-api.p.rapidapi.com/live_status"

    headers = {
        "X-RapidAPI-Key": API_KEY,
        "X-RapidAPI-Host": "indian-railway-api.p.rapidapi.com"
    }

    params = {"train_no": str(train_no)}

    try:
        response = requests.get(url, headers=headers, params=params, timeout=5)
        if response.status_code == 200:
            data = response.json()
            return {
                "current_station": data.get("current_station_name", "In Transit"),
                "delay_minutes": data.get("delay", 0),
                "status_message": data.get("status_as_of", "Running on time")
            }
    except Exception as e:
        print(f"RapidAPI Request Failed: {e}")

    return None
