import requests
import json
import os
from django.core.cache import cache


# Used by forms that accept URLs.
def normalize_url(url):
    """
    Ensures that a URL has a valid scheme (http:// or https://).

    - Checks if the input URL starts with 'http://' or 'https://'.
    - If the scheme is missing, 'https://' is prepended to the URL.
    - Returns the normalized URL.

    Args:
        url (str): The URL to normalize.

    Returns:
        str: The normalized URL with a valid scheme.
    """
    # Check if the URL starts with a valid scheme (http or https).
    if not url.startswith(("http://", "https://")):
        # If no scheme is present, prepend 'https://'.
        url = f"https://{url}"

    # Return the normalized URL.
    return url


# ---------------------------------------------------------------------------
#  Cache TTLs (seconds)
# ---------------------------------------------------------------------------

# ZIP → coordinates/city/state.
# Google TOS allows caching Geocoding results for up to 30 days.
GEO_CACHE_TTL = 60 * 60 * 24 * 30  # 2,592,000 seconds (i.e. 30 days)

# Road distance between two ZIPs changes rarely.
# Increased to 30 days to maximize free tier usage.
ROAD_DISTANCE_CACHE_TTL = 60 * 60 * 24 * 30  # 2,592,000 seconds (i.e. 30 days)


# ---------------------------------------------------------------------------
#  Geocoding — coordinates only (legacy interface)
# ---------------------------------------------------------------------------

# This is code for converting a ZIP code into GPS coordinates.
# Currently used by the ISS Tracker, Satellite Pass Predictor,
# and Grid Square Converter apps.
def get_coordinates(zip_code):
    """
    Convert a ZIP code to (lat, lng) via the Google Geocoding API.

    Results are cached for 24 hours because ZIP-to-coordinate
    mappings are effectively static.

    Returns:
        tuple: (lat, lng) or None on failure.
    """
    # Check the cache first.
    cache_key = f"geo_coords_{zip_code}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    # API key for accessing the Google Geocoding API.
    API_KEY_LOCATION = os.environ.get("GOOGLE_MAPS_KEY")
    # Construct the API URL with the zip code and API key.
    API_URL = f"https://maps.googleapis.com/maps/api/geocode/json?address={zip_code}&key={API_KEY_LOCATION}"

    try:
        # Send a GET request to the Google Geocoding API.
        response = requests.get(API_URL, timeout=5)
        # Parse the JSON response content.
        data = json.loads(response.content)
        # Check if the API call was successful and if results were found.
        if response.status_code == 200 and data["status"] == "OK":
            # Extract the location data (latitude and longitude).
            location = data["results"][0]["geometry"]["location"]
            result = (location["lat"], location["lng"])
            # Cache the successful result.
            cache.set(cache_key, result, GEO_CACHE_TTL)
            # Return the latitude and longitude as a tuple.
            return result
    except Exception:
        pass

    # Return None if the API call was unsuccessful or if no results were found.
    return None


# ---------------------------------------------------------------------------
#  Geocoding — coordinates + city/state (used by Weather Forecast)
# ---------------------------------------------------------------------------

def get_location_data(zip_code):
    """
    Single Geocoding API call that returns coordinates AND city/state.
    Replaces the need to call get_coordinates() + get_city_and_state() separately.

    Used by the Weather Forecast app to cut Geocoding API usage in half.
    Results are cached for 24 hours because ZIP-to-coordinate
    mappings are effectively static.

    Args:
        zip_code (str): A US ZIP code.

    Returns:
        dict with keys: lat, lng, city, state — or None on failure.
    """
    # Check the cache first.
    cache_key = f"geo_location_{zip_code}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    API_KEY = os.environ.get("GOOGLE_MAPS_KEY")
    # Append +USA to ensure we don't match international postal codes or get ambiguous results
    url = f"https://maps.googleapis.com/maps/api/geocode/json?address={zip_code}+USA&key={API_KEY}"

    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        data = response.json()

        if data.get("status") != "OK" or not data.get("results"):
            return None

        result = data["results"][0]
        location = result["geometry"]["location"]

        # Parse city and state from address_components by type.
        # This is more robust than indexing by position, which can
        # break depending on how Google structures the response.
        city = None
        state = None
        for component in result.get("address_components", []):
            types = component.get("types", [])
            if "locality" in types:
                city = component["long_name"]
            elif "administrative_area_level_1" in types:
                state = component["long_name"]

        location_data = {
            "lat": location["lat"],
            "lng": location["lng"],
            "city": city,
            "state": state,
        }
        # Cache the successful result.
        cache.set(cache_key, location_data, GEO_CACHE_TTL)
        return location_data
    except Exception:
        return None


# ---------------------------------------------------------------------------
#  Distance Matrix — road miles between two ZIPs
# ---------------------------------------------------------------------------

# Used by the Freight Partial Calculator, Deadhead Calculator,
# Multi-Stop Splitter, Lane Rate Analyzer, and Freight Margin Calculator
# to get actual highway miles.
def get_road_distance(origin_zip, dest_zip):
    """
    Get exact driving distance in miles between two US ZIP codes
    via the Google Distance Matrix API.

    Results are cached for 4 hours. Road distances change rarely,
    and the freight tools often re-run the same lane during a
    single pricing session.

    Returns:
        float: Distance in miles, or None on failure.
    """
    # Check the cache first.
    # Key is directional (A→B may differ from B→A for one-way roads),
    # though in practice the difference is negligible for ZIP-level queries.
    cache_key = f"road_dist_{origin_zip}_{dest_zip}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    API_KEY = os.environ.get("GOOGLE_MAPS_KEY")
    # "units=imperial" ensures the distance is returned in miles
    url = f"https://maps.googleapis.com/maps/api/distancematrix/json?origins={origin_zip}+USA&destinations={dest_zip}+USA&units=imperial&key={API_KEY}"

    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        data = response.json()

        if data.get("status") == "OK":
            # Extract the distance in miles from the JSON response
            # Google returns it as text like "2,045 mi", so we parse out the number.
            element = data["rows"][0]["elements"][0]
            if element.get("status") == "OK":
                distance_text = element["distance"]["text"]
                # Clean the text (e.g., "2,045 mi" -> 2045.0)
                exact_miles = float(distance_text.replace(" mi", "").replace(",", ""))
                # Cache the successful result.
                cache.set(cache_key, exact_miles, ROAD_DISTANCE_CACHE_TTL)
                return exact_miles
    except Exception as e:
        print(f"Error fetching road distance: {e}")

    return None