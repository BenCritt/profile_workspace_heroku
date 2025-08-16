from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut
from datetime import timedelta
from skyfield.api import load, Topos
from skyfield.sgp4lib import EarthSatellite
from django.http import JsonResponse
from django.core.cache import cache
import requests

def detect_region(latitude, longitude):
    """
    Detect the region (land or water) based on latitude and longitude.
    Recognizes smaller bodies of water like seas, lakes, and gulfs.
    """
    try:
        # Custom mapping for known water bodies.
        # This is better than using the Google Maps API for rate limit considerations.
        # This doesn't work without "as water_bodies" included, and I don't know why.  But it works, so whatever.
        from .water_bodies import water_bodies as water_bodies

        # Initialize the geolocator. This is using an API through the library.
        geolocator = Nominatim(
            user_agent="ISS Tracker by Ben Crittenden (+https://www.bencritt.net)"
        )

        # Step 1: Check for land regions using reverse geocoding.
        location = geolocator.reverse(
            (latitude, longitude), exactly_one=True, language="en", timeout=10
        )

        if location:
            # Extract relevant details from the geocoded response.
            address = location.raw.get("address", {})
            if "country" in address:
                return address["country"]
            elif "state" in address:
                return address["state"]
            elif "city" in address:
                return address["city"]
            
        # Step 2: Check if the coordinates match any known water body.
        for water_body in water_bodies:
            if (
                water_body["latitude_range"][0]
                <= latitude
                <= water_body["latitude_range"][1]
                and water_body["longitude_range"][0]
                <= longitude
                <= water_body["longitude_range"][1]
            ):
                return water_body["name"]

        # Fallback for unknown regions.
        return "Unrecognized Region"
    except GeocoderTimedOut:
        # Handle geocoder timeout.
        return "Geolocation Timeout"
    except Exception as e:
        # Handle unexpected errors.
        return f"Error: {e}"
    
def current_iss_data(request):
    """
    API endpoint to provide real-time information about the International Space Station (ISS).
    Returns the current latitude, longitude, altitude, velocity, and region over which the ISS is located.

    Args:
        request: HTTP request object.

    Returns:
        JsonResponse: A JSON object containing the ISS's current data or an error message.
    """
    try:
        # Attempt to retrieve the TLE (Two-Line Element) data from cache.
        tle_data = cache.get("tle_data")

        # If the TLE data is not cached, fetch it from the external source.
        if not tle_data:
            # URL for TLE data.
            tle_url = "https://celestrak.org/NORAD/elements/stations.txt"
            # Fetch data with a timeout of 10 seconds.
            response = requests.get(tle_url, timeout=10)
            # Raise an error if the response contains an HTTP error status.
            response.raise_for_status()
            # Split the fetched text into lines.
            tle_data = response.text.splitlines()
            # Cache the TLE data for 1 hour.
            cache.set("tle_data", tle_data, timeout=3600)

        # Dynamically locate the ISS entry ("ISS (ZARYA)") in the TLE data.
        # The unique name for the ISS in the TLE data.
        iss_name = "ISS (ZARYA)"
        # Find the line index matching the ISS name.
        iss_index = next(
            i for i, line in enumerate(tle_data) if line.strip() == iss_name
        )
        # First line of the TLE data for the ISS.
        line1 = tle_data[iss_index + 1]
        # Second line of the TLE data for the ISS.
        line2 = tle_data[iss_index + 2]

        # Create an EarthSatellite object for the ISS using the TLE data.
        satellite = EarthSatellite(line1, line2, iss_name, load.timescale())

        # Determine the ISS's current position based on the current time.
        # Get the ISS's geocentric position.
        geocentric = satellite.at(load.timescale().now())
        # Extract the subpoint (latitude, longitude, altitude).
        subpoint = geocentric.subpoint()

        # Extract the ISS's latitude and longitude.
        latitude = subpoint.latitude.degrees
        longitude = subpoint.longitude.degrees

        # Calculate the ISS's velocity in km/s using the velocity vector components.
        velocity = geocentric.velocity.km_per_s

        # Determine the region (land or body of water) over which the ISS is located.
        region = detect_region(latitude, longitude)

        # Return the current ISS data as a JSON response.
        return JsonResponse(
            {
                # Latitude in degrees with 2 decimal places.
                "latitude": f"{latitude:.2f}°",
                # Longitude in degrees with 2 decimal places.
                "longitude": f"{longitude:.2f}°",
                # Altitude in kilometers with 2 decimal places.
                "altitude": f"{subpoint.elevation.km:.2f} km",
                # Velocity magnitude.
                "velocity": f"{(velocity[0]**2 + velocity[1]**2 + velocity[2]**2)**0.5:.2f} km/s",
                # Detected region (land or water body).
                "region": region,
            }
        )
    except Exception as e:
        # Handle any exceptions that occur during processing and return an error response.
        return JsonResponse({"error": str(e)}, status=500)
