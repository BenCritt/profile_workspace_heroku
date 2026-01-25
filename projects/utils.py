import requests
import json
import os

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


# This is code for converting a ZIP code into GPS coordinates.
# Currently used by the Weather Forecast app and ISS Tracker app.
def get_coordinates(zip_code):
    # API key for accessing the Google Geocoding API.
    API_KEY_LOCATION = os.environ.get("GOOGLE_MAPS_KEY")
    # Construct the API URL with the zip code and API key.
    API_URL = f"https://maps.googleapis.com/maps/api/geocode/json?address={zip_code}&key={API_KEY_LOCATION}"
    # Send a GET request to the Google Geocoding API.
    response = requests.get(API_URL)
    # Parse the JSON response content.
    data = json.loads(response.content)
    # Check if the API call was successful and if results were found.
    if response.status_code == 200 and data["status"] == "OK":
        # Extract the location data (latitude and longitude).
        location = data["results"][0]["geometry"]["location"]
        # Return the latitude and longitude as a tuple.
        return location["lat"], location["lng"]
    else:
        # Return None if the API call was unsuccessful or if no results were found.
        return None
    
# Used by the Freight Partial Calculator to get actual highway miles.
def get_road_distance(origin_zip, dest_zip):
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
                return exact_miles
    except Exception as e:
        print(f"Error fetching road distance: {e}")
        
    return None