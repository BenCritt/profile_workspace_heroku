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

# This variable is used to limit the number of URLs processed by SEO Head Checker.
sitemap_limit = 25

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

# Used in the XML Splitter
import io, re, zipfile, xml.etree.ElementTree as ET

_XML_DECL = b'<?xml version="1.0" encoding="utf-8"?>\n'

def _safe_filename(text: str | None) -> str:
    """
    Sanitise the ID value so it is safe for a filename.
    Returns 'unnamed' if the value is missing or blank.
    """
    if not text:                     # catches None and empty string
        return "unnamed"
    cleaned = re.sub(r"[^\w\-\.]", "_", text.strip())
    return cleaned or "unnamed"

def split_xml_to_zip(uploaded_file) -> io.BytesIO:
    raw = uploaded_file.read()
    xml_text = re.sub(
        rb'encoding="[^"]+"', b'encoding="utf-8"', raw, count=1, flags=re.I
    ).decode("utf-8", "replace")

    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        # Bad XML – e.g. missing tag, unescaped ampersand, etc.
        raise ValueError("The uploaded file is not well‑formed XML.") from exc

    if not list(root):
        # Root exists but contains no child objects
        raise ValueError("The XML contains no <Order>, <Product>, or similar objects.")

    zip_io = io.BytesIO()
    with zipfile.ZipFile(zip_io, "w", zipfile.ZIP_DEFLATED) as zf:
        for obj in root:
            first_child = next(iter(obj), None)
            file_id = _safe_filename(first_child.text if first_child is not None else None)
            xml_bytes = _XML_DECL + ET.tostring(obj, encoding="utf-8")
            zf.writestr(f"{file_id}.xml", xml_bytes)

    zip_io.seek(0)
    return zip_io


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

        # Step 1: Check if the coordinates match any known water body.
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

        # Step 2: Check for land regions using reverse geocoding.
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


def fetch_sitemap_urls(sitemap_url):
    """
    Fetches all URLs listed in a sitemap or processes a single webpage URL.

    - Sends an HTTP GET request to the sitemap URL or webpage URL.
    - If the URL points to a sitemap, parses the sitemap content to extract all <loc> tags.
    - If the URL points to a webpage, validates whether it has a valid <head> section.

    Args:
        sitemap_url (str): The URL of the sitemap or webpage to fetch.

    Returns:
        list: A list of URLs (str) extracted from the sitemap or containing the single webpage URL.

    Raises:
        ValueError: If the URL is invalid, inaccessible, or cannot be processed.
        Exception: If the sitemap content cannot be parsed.
    """
    headers = {
        # Identifies my app so admins know who is crawling their website.
        "User-Agent": "SEO Head Checker by Ben Crittenden (+https://www.bencritt.net)",
        # Tells websites what the app is looking for.
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    }
    try:
        # Send an HTTP GET request to fetch the sitemap or webpage content with a custom User-Agent.
        response = requests.get(sitemap_url, headers=headers, timeout=10)
        response.raise_for_status()  # Check for HTTP errors (e.g., 404, 500).
    except requests.exceptions.Timeout:
        raise ValueError("The request timed out. Please try again later.")
    except requests.exceptions.ConnectionError:
        raise ValueError("Failed to connect to the URL. Please check the URL.")
    except requests.exceptions.HTTPError as e:
        raise ValueError(f"HTTP error occurred: {e}")
    except requests.exceptions.RequestException as e:
        raise ValueError(f"An error occurred while fetching the URL: {e}")

    # Check the content type of the response to determine if it's a sitemap
    content_type = response.headers.get("Content-Type", "")
    if "xml" in content_type or sitemap_url.endswith(".xml"):
        try:
            # Parse the sitemap content as XML using BeautifulSoup.
            soup = BeautifulSoup(response.content, "lxml-xml")
            # Extract and return all URLs found in <loc> tags.
            urls = [loc.text for loc in soup.find_all("loc")]
            if not urls:
                raise ValueError("The provided sitemap is empty or invalid.")
            return urls
        except Exception as e:
            raise ValueError(
                f"Failed to parse the sitemap. Ensure it's a valid XML file. Error: {e}"
            )
    else:
        # If not a sitemap, assume it's a single webpage URL
        return [sitemap_url]


def process_sitemap_urls(urls, max_workers=1, task_id=None):
    """
    Processes URLs from a sitemap in parallel, up to a specified limit.

    - Utilizes a thread pool to process URLs concurrently for improved efficiency.
    - Updates task progress in the cache if a task ID is provided.
    - Returns the results of processing each URL.

    Args:
        urls (list): List of URLs to process.
        max_workers (int, optional): Number of threads to use for concurrent processing. Defaults to 5.
        task_id (str, optional): Unique identifier for tracking progress in the cache. Defaults to None.

    Returns:
        list: A list of results from processing each URL.
    """
    # Ensure the global sitemap_limit variable is accessible.
    global sitemap_limit

    # Initialize an empty list to store the results.
    results = []

    # Determine the actual number of URLs to process (limited by sitemap_limit).
    total_urls = min(len(urls), sitemap_limit)

    # Use a thread pool to process URLs concurrently.
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Process URLs in parallel and enumerate results to track progress.
        for i, result in enumerate(
            executor.map(process_single_url, urls[:sitemap_limit])
        ):
            # Append the result of processing each URL to the results list.
            results.append(result)

            # If a task ID is provided, update the progress in the cache.
            if task_id:
                cache.set(
                    task_id,
                    {
                        # Indicate that the task is still processing.
                        "status": "processing",
                        # Calculate progress percentage.
                        "progress": int((i + 1) / total_urls * 100),
                    },
                    # Cache entry expiration time (30 minutes).
                    timeout=1800,
                )
    # Explicit cleanup.
    del urls
    gc.collect()

    # Return the list of results after processing all URLs.
    return results


def process_single_url(url):
    """
    Processes a single URL to extract and check the presence of SEO-related elements in the <head> section.

    Args:
        url (str): The URL to process.

    Returns:
        dict: A dictionary containing the URL, status, and results for SEO element checks.
    """
    soup = None  # Initialize soup to avoid uninitialized reference in finally block

    try:
        # Send an HTTP GET request to the URL with a 10-second timeout.
        response = requests.get(url, timeout=10)
        response.raise_for_status()  # Check for HTTP errors (e.g., 404, 500).
    except requests.exceptions.Timeout:
        return {"URL": url, "Status": "Error: Request timed out"}
    except requests.exceptions.ConnectionError:
        return {"URL": url, "Status": "Error: Failed to connect to the URL"}
    except requests.exceptions.HTTPError as e:
        return {"URL": url, "Status": f"HTTP error occurred: {e}"}
    except requests.exceptions.RequestException as e:
        return {"URL": url, "Status": f"Request error: {e}"}

    try:
        # Parse the HTML content of the response using BeautifulSoup.
        soup = BeautifulSoup(response.text, "html.parser")
        # Extract the <head> section from the parsed HTML.
        head = soup.find("head")
        if not head:
            return {"URL": url, "Status": "No <head> section"}

        # Helper function to check for the presence of specific tags in the <head>.
        def is_present(tag_name, **attrs):
            return "Present" if head.find(tag_name, attrs=attrs) else "Missing"

        # Count structured data scripts in the <head>.
        structured_data_scripts = head.find_all("script", type="application/ld+json")
        structured_data_count = (
            len(structured_data_scripts) if structured_data_scripts else 0
        )

        # Open Graph and Twitter Tags
        open_graph_present = bool(
            head.find("meta", attrs={"property": lambda p: p and p.startswith("og:")})
        )
        twitter_card_present = bool(
            head.find("meta", attrs={"name": lambda p: p and p.startswith("twitter:")})
        )

        # Return the results dictionary.
        return {
            "URL": url,
            "Status": "Success",
            "Title Tag": "Present" if head.title else "Missing",
            "Meta Description": is_present("meta", name="description"),
            "Canonical Tag": is_present("link", rel="canonical"),
            "Meta Robots Tag": is_present("meta", name="robots"),
            "Open Graph Tags": "Present" if open_graph_present else "Missing",
            "Twitter Card Tags": "Present" if twitter_card_present else "Missing",
            "Hreflang Tags": (
                "Present"
                if head.find("link", rel="alternate", hreflang=True)
                else "Missing"
            ),
            "Structured Data": (
                f"Present ({structured_data_count} scripts)"
                if structured_data_count > 0
                else "Missing"
            ),
            "Charset Declaration": is_present("meta", charset=True),
            "Viewport Tag": is_present("meta", name="viewport"),
            "Favicon": is_present("link", rel="icon"),
        }
    except Exception as e:
        # Return a dictionary indicating an error occurred and include the exception message.
        return {"URL": url, "Status": f"Error while processing content: {e}"}
    finally:
        # Safely release memory for the parsed HTML.
        if soup:
            del soup
        gc.collect()  # Force garbage collection


def save_results_to_csv(results, task_id):
    """
    Saves the results of sitemap processing to a CSV file.

    - Creates a CSV file named using the task ID to ensure uniqueness.
    - Writes the results, including headers and data rows, to the CSV file.
    - Returns the file path for further use (e.g., download or cleanup).

    Args:
        results (list): A list of dictionaries containing the processing results for each URL.
        task_id (str): A unique identifier for the task, used to name the CSV file.

    Returns:
        str: The file path of the generated CSV file.
    """
    # Define the file path using the task ID for uniqueness.
    file_path = f"seo_report_{task_id}.csv"

    # Open the file in write mode with UTF-8 encoding.
    with open(file_path, "w", newline="", encoding="utf-8") as csvfile:

        # Define the field names (column headers) for the CSV file.
        writer = csv.DictWriter(
            csvfile,
            fieldnames=[
                # The URL of the processed page.
                "URL",
                # The processing status (e.g., Success, Error).
                "Status",
                # Presence of the <title> tag.
                "Title Tag",
                # Presence of the meta description.
                "Meta Description",
                # Presence of the canonical link tag.
                "Canonical Tag",
                # Presence of the meta robots tag.
                "Meta Robots Tag",
                # Presence of Open Graph meta tags.
                "Open Graph Tags",
                # Presence of Twitter card meta tags.
                "Twitter Card Tags",
                # Presence of hreflang link tags.
                "Hreflang Tags",
                # Presence of structured data (JSON-LD scripts).
                "Structured Data",
                # Presence of the charset declaration.
                "Charset Declaration",
                # Presence of the viewport meta tag.
                "Viewport Tag",
                # Presence of the favicon link tag.
                "Favicon",
            ],
        )

        # Write the column headers to the CSV file.
        writer.writeheader()

        # Write the rows of data to the CSV file.
        writer.writerows(results)

    # Return the file path of the generated CSV file.
    return file_path


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
