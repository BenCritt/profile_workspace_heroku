import requests
import json
import os
import datetime

def get_city_and_state(zip_code):
    """
    Fetches city and state from Google Maps Geocoding API.
    """
    API_KEY_CITY = os.environ.get("GOOGLE_MAPS_KEY")
    url = f"https://maps.googleapis.com/maps/api/geocode/json?address={zip_code}&key={API_KEY_CITY}"
    
    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        data = response.json()
        
        if data.get("status") == "OK":
            results = data["results"][0]["address_components"]
            # Note: This index logic relies on Google's specific return format.
            # Ideally, we would loop through finding types="locality", but this works for now.
            city_name = results[1]["long_name"]
            state_name = results[3]["long_name"]
            return city_name, state_name
    except Exception:
        pass
        
    return None, None

def parse_weather_data(data):
    """
    Parses the OpenWeatherMap OneCall API response into context dictionaries.
    Handles missing keys safely.
    """
    current = data.get("current", {})
    daily = data.get("daily", [])

    # fix: Handle visibility safely (default to 0 if missing)
    vis_meters = current.get("visibility", 0)
    vis_miles = int(vis_meters * 0.00062137)

    # 1. Build Current Weather Report
    # We use .get() everywhere to prevent crashes if API changes
    current_weather_report = [{
        "icon_url_current": f"https://openweathermap.org/img/wn/{current.get('weather', [{}])[0].get('icon')}.png",
        "current_temperature": int(current.get("temp", 0)),
        "current_description": current.get("weather", [{}])[0].get("description", "N/A"),
        "current_humidity": current.get("humidity", "N/A"),
        "current_rain": current.get("rain", "No Rain"),
        "current_snow": current.get("snow", "No Snow"),
        "current_wind_gust": current.get("wind_gust", "N/A"),
        "current_wind_speed": current.get("wind_speed", "N/A"),
        "current_wind_direction": current.get("wind_deg", "N/A"),
        "current_cloud": current.get("clouds", "N/A"),
        "current_uv": current.get("uvi", "N/A"),
        "current_dew": int(current.get("dew_point", 0)),
        "current_visibility": vis_miles,
        "current_sunrise": datetime.datetime.fromtimestamp(current.get("sunrise", 0)),
        "current_sunset": datetime.datetime.fromtimestamp(current.get("sunset", 0)),
    }]

    # 2. Build Daily Forecast
    daily_forecast = []
    for day in daily:
        daily_forecast.append({
            "day_of_week": datetime.datetime.fromtimestamp(day["dt"]).strftime("%A"),
            "date": datetime.datetime.fromtimestamp(day["dt"]),
            "high_temp": int(day["temp"]["max"]),
            "low_temp": int(day["temp"]["min"]),
            "morn_temp": int(day["temp"]["morn"]),
            "morn_temp_feel": int(day["feels_like"]["morn"]),
            "day_temp": int(day["temp"]["day"]),
            "day_temp_feel": int(day["feels_like"]["day"]),
            "eve_temp": int(day["temp"]["eve"]),
            "eve_temp_feel": int(day["feels_like"]["eve"]),
            "night_temp": int(day["temp"]["night"]),
            "night_temp_feel": int(day["feels_like"]["night"]),
            "summary": day.get("summary", ""),
            "sunrise": datetime.datetime.fromtimestamp(day["sunrise"]),
            "sunset": datetime.datetime.fromtimestamp(day["sunset"]),
            "dew_point": day.get("dew_point", "N/A"),
            "humidity": day.get("humidity", "N/A"),
            "precipitation_chance": round(day.get("pop", 0) * 100),
        })

    return {
        "current_weather_report": current_weather_report,
        "daily_forecast": daily_forecast
    }