# Used in the SSL Verification Tool to create SSL contexts for secure communication and certificate verification.
import ssl

# Provides low-level network communication capabilities, used in the SSL Verification Tool to establish secure connections.
import socket

# Used in the SSL Verification Tool to parse and extract details from SSL certificates.
from OpenSSL import crypto

# Handles date and time operations, such as parsing and formatting certificate expiration dates in the SSL Verification Tool.
from datetime import datetime

# Used for making HTTP requests across multiple apps:
# - Fetching weather data for the Weather Forecast app.
# - Performing API calls in the IP Address Lookup Tool and DNS Lookup Tool.
# - Retrieving and processing sitemap data in the SEO Head Checker.
# - Accessing the FMCMSA API in the Freight Carrier Safety Reporter.
import requests

# Used for parsing and generating JSON data, such as handling API responses and request bodies.
import json

# Parses HTML and XML content. Specifically used in the SEO Head Checker for extracting URLs from sitemap files.
from bs4 import BeautifulSoup

# Writes and reads CSV files. Used to generate reports in apps like the SEO Head Checker.
import csv

# Enables multi-threaded parallel execution of tasks, such as processing multiple URLs concurrently in the SEO Head Checker.
from concurrent.futures import ThreadPoolExecutor

# Dictionary to store task statuses.
from django.core.cache import cache

# urlparse: Parses URLs into components (e.g., scheme, hostname, path).
# urlunparse: Reassembles parsed URL components into a full URL.
# Used in utilities like `normalize_url` for validating and modifying URLs.
from urllib.parse import urlparse, urlunparse

# Garbage Collection helps with memory management.
import gc

# Geocoding library used to reverse lookup latitude/longitude into human-readable locations.
from geopy.geocoders import Nominatim

# Importing the GeocoderTimedOut exception from geopy.
# This exception is raised when a geocoding request to the Nominatim API exceeds the allowed timeout duration.
from geopy.exc import GeocoderTimedOut


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





"""
Freight Carrier Safety Reporter API Documentation
https://mobile.fmcsa.dot.gov/QCDevsite/docs/qcApi
https://mobile.fmcsa.dot.gov/QCDevsite/docs/getStarted
https://mobile.fmcsa.dot.gov/QCDevsite/docs/apiElements
https://mobile.fmcsa.dot.gov/qc/services/carriers/264184?webKey=d4cf8cc419e2ba88e590a957140c86abe8b79f97
https://mobile.fmcsa.dot.gov/qc/services/carriers/2245945?webKey=d4cf8cc419e2ba88e590a957140c86abe8b79f97
"""


def replace_none_with_na(data):
    if isinstance(data, dict):
        return {key: replace_none_with_na(value) for key, value in data.items()}
    elif isinstance(data, list):
        return [replace_none_with_na(item) for item in data]
    elif data is None:
        return "N/A"
    else:
        return data


def get_fmcsa_carrier_data_by_usdot(usdot_number):
    fcsr_webkey = "d4cf8cc419e2ba88e590a957140c86abe8b79f97"
    url = f"https://mobile.fmcsa.dot.gov/qc/services/carriers/{usdot_number}?webKey={fcsr_webkey}"

    try:
        response = requests.get(url)
        # Raise an exception for bad status codes.
        response.raise_for_status()

        response_data = response.json()
        print("Full Response Data:", response_data)

        # Ensure 'content' exists and contains 'carrier'.
        content_data = response_data.get("content")
        if not content_data:
            return None  # 'content' missing, return None.

        carrier_data = content_data.get("carrier")
        if not carrier_data:
            return None  # 'carrier' missing, return None.

        # Apply the helper function to replace None values with "N/A."
        cleaned_carrier_data = replace_none_with_na(carrier_data)

        # Parse and clean relevant fields from the cleaned JSON data.
        carrier_info = {
            "name": cleaned_carrier_data.get("legalName", "N/A"),
            "dotNumber": cleaned_carrier_data.get("dotNumber", "N/A"),
            "mcNumber": cleaned_carrier_data.get("mcNumber", "N/A"),
            "allowedToOperate": cleaned_carrier_data.get("allowedToOperate", "N/A"),
            "bipdInsuranceOnFile": cleaned_carrier_data.get(
                "bipdInsuranceOnFile", "N/A"
            ),
            "bipdInsuranceRequired": cleaned_carrier_data.get(
                "bipdInsuranceRequired", "N/A"
            ),
            "bondInsuranceOnFile": cleaned_carrier_data.get(
                "bondInsuranceOnFile", "N/A"
            ),
            "brokerAuthorityStatus": cleaned_carrier_data.get(
                "brokerAuthorityStatus", "N/A"
            ),
            "cargoInsuranceOnFile": cleaned_carrier_data.get(
                "cargoInsuranceOnFile", "N/A"
            ),
            "carrierOperationCode": (
                cleaned_carrier_data.get("carrierOperation", {}).get(
                    "carrierOperationCode", "N/A"
                )
                if isinstance(cleaned_carrier_data.get("carrierOperation"), dict)
                else "N/A"
            ),
            "carrierOperationDesc": (
                cleaned_carrier_data.get("carrierOperation", {}).get(
                    "carrierOperationDesc", "N/A"
                )
                if isinstance(cleaned_carrier_data.get("carrierOperation"), dict)
                else "N/A"
            ),
            "commonAuthorityStatus": cleaned_carrier_data.get(
                "commonAuthorityStatus", "N/A"
            ),
            "contractAuthorityStatus": cleaned_carrier_data.get(
                "contractAuthorityStatus", "N/A"
            ),
            "crashTotal": cleaned_carrier_data.get("crashTotal", "N/A"),
            "driverInsp": cleaned_carrier_data.get("driverInsp", "N/A"),
            "driverOosInsp": cleaned_carrier_data.get("driverOosInsp", "N/A"),
            "driverOosRate": cleaned_carrier_data.get("driverOosRate", "N/A"),
            "ein": cleaned_carrier_data.get("ein", "N/A"),
            "fatalCrash": cleaned_carrier_data.get("fatalCrash", "N/A"),
            "hazmatInsp": cleaned_carrier_data.get("hazmatInsp", "N/A"),
            "hazmatOosInsp": cleaned_carrier_data.get("hazmatOosInsp", "N/A"),
            "hazmatOosRate": cleaned_carrier_data.get("hazmatOosRate", "N/A"),
            "injCrash": cleaned_carrier_data.get("injCrash", "N/A"),
            "phyCity": cleaned_carrier_data.get("phyCity", "N/A"),
            "phyState": cleaned_carrier_data.get("phyState", "N/A"),
            "phyStreet": cleaned_carrier_data.get("phyStreet", "N/A"),
            "phyZipcode": cleaned_carrier_data.get("phyZipcode", "N/A"),
            "reviewDate": cleaned_carrier_data.get("reviewDate", "N/A"),
            "safetyRating": cleaned_carrier_data.get("safetyRating", "N/A"),
            "safetyRatingDate": cleaned_carrier_data.get("safetyRatingDate", "N/A"),
            "totalDrivers": cleaned_carrier_data.get("totalDrivers", "N/A"),
            "totalPowerUnits": cleaned_carrier_data.get("totalPowerUnits", "N/A"),
            "towawayCrash": cleaned_carrier_data.get("towawayCrash", "N/A"),
            "vehicleInsp": cleaned_carrier_data.get("vehicleInsp", "N/A"),
            "vehicleOosInsp": cleaned_carrier_data.get("vehicleOosInsp", "N/A"),
            "vehicleOosRate": cleaned_carrier_data.get("vehicleOosRate", "N/A"),
        }

        return carrier_info

    except requests.exceptions.RequestException as e:
        # Handle any request-related exceptions
        print(f"There was an error fetching data for USDOT {usdot_number}: {e}")
        return None


# This is the code for the Weather Forecast app.
def get_coordinates(zip_code):
    # API key for accessing the Google Geocoding API.
    API_KEY_LOCATION = "AIzaSyD0xBXRANSgMPe8HvaE2rSmm7u8E8QYAyM"
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


# This is the code for the Weather Forecast app.
def get_city_and_state(zip_code):
    # API key for accessing the Google Geocoding API.
    API_KEY_CITY = "AIzaSyD0xBXRANSgMPe8HvaE2rSmm7u8E8QYAyM"
    # Construct the API URL with the zip code and API key.
    url = f"https://maps.googleapis.com/maps/api/geocode/json?address={zip_code}&key={API_KEY_CITY}"
    # Send a GET request to the Google Geocoding API.
    response = requests.get(url)
    # Parse the JSON response content.
    data = json.loads(response.content)
    # Check if the API call was successful and if results were found.
    if response.status_code == 200 and data["status"] == "OK":
        # Extract the city name from the response.
        city_name = data["results"][0]["address_components"][1]["long_name"]
        # Extract the state name from the response.
        state_name = data["results"][0]["address_components"][3]["long_name"]
        # Return the city and state names as a tuple.
        return city_name, state_name
    else:
        # Return None if the API call was unsuccessful or if no results were found.
        return None


"""
# This is the code for the SSL Verification Tool app.
def verify_ssl(url):
    try:
        # Parse URL to get the hostname
        parsed_url = urlparse(url)
        hostname = parsed_url.hostname

        # Create an SSL context and wrap a socket
        context = ssl.create_default_context()
        conn = context.wrap_socket(
            socket.socket(socket.AF_INET), server_hostname=hostname
        )

        # Set a timeout for the connection
        conn.settimeout(3.0)
        conn.connect((hostname, 443))

        # Retrieve the certificate from the server
        cert = conn.getpeercert(True)
        conn.close()

        # Load the certificate using pyOpenSSL
        x509 = crypto.load_certificate(crypto.FILETYPE_ASN1, cert)

        # Convert ASN.1 time format to datetime
        not_before = datetime.strptime(
            x509.get_notBefore().decode("utf-8"), "%Y%m%d%H%M%SZ"
        )
        not_after = datetime.strptime(
            x509.get_notAfter().decode("utf-8"), "%Y%m%d%H%M%SZ"
        )

        # Extract certificate details
        cert_info = {
            "subject": dict(x509.get_subject().get_components()),
            "issuer": dict(x509.get_issuer().get_components()),
            "serial_number": x509.get_serial_number(),
            "not_before": not_before,
            "not_after": not_after,
        }

        return cert_info

    except Exception as e:
        return {"error": str(e)}
"""


def verify_ssl(url):
    try:
        # Parse URL to get the hostname.
        parsed_url = urlparse(url)
        hostname = parsed_url.hostname

        # Check if hostname exists.
        if not hostname:
            return {
                "error": "Invalid URL. Please ensure the URL is correctly formatted."
            }

        # Create an SSL context and wrap a socket.
        context = ssl.create_default_context()
        conn = context.wrap_socket(
            socket.socket(socket.AF_INET), server_hostname=hostname
        )

        # Set a timeout for the connection.
        conn.settimeout(3.0)
        conn.connect((hostname, 443))

        # Retrieve the certificate from the server.
        cert = conn.getpeercert(True)

        # Always close the connection.
        conn.close()

        # Load the certificate using pyOpenSSL.
        x509 = crypto.load_certificate(crypto.FILETYPE_ASN1, cert)

        # Convert ASN.1 time format to datetime.
        not_before = datetime.strptime(
            x509.get_notBefore().decode("utf-8"), "%Y%m%d%H%M%SZ"
        )
        not_after = datetime.strptime(
            x509.get_notAfter().decode("utf-8"), "%Y%m%d%H%M%SZ"
        )

        # Extract certificate details.
        cert_info = {
            "subject": dict(x509.get_subject().get_components()),
            "issuer": dict(x509.get_issuer().get_components()),
            "serial_number": x509.get_serial_number(),
            "not_before": not_before,
            "not_after": not_after,
        }

        return cert_info

    # Error handling.
    except socket.timeout:
        return {"error": "Connection timed out. Please try again with a valid URL."}
    except ssl.SSLError as ssl_error:
        return {"error": f"SSL error: {str(ssl_error)}"}
    except Exception as e:
        return {"error": f"An unexpected error occurred: {str(e)}"}
    finally:
        # Ensure the connection is closed if it wasn't already.
        try:
            conn.close()
        except Exception:
            pass
