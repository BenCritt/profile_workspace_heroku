# Used in the SSL Verification Tool to create SSL contexts for secure communication and certificate verification.
import ssl

# Provides low-level network communication capabilities, used in the SSL Verification Tool to establish secure connections.
import socket

# Used in the SSL Verification Tool to parse and extract details from SSL certificates.
from OpenSSL import crypto

# urlparse: Breaks down URLs into components for validation and processing (e.g., in the SEO Head Checker and SSL Verification Tool).
# urlunparse: Reassembles parsed URLs into strings after modification.
from urllib.parse import urlparse

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

# Renders templates for various apps, such as displaying forms and results.
from django.shortcuts import render

# Sends raw data responses to users, such as file downloads and dynamically generated content.
from django.http import HttpResponse

# Parses HTML and XML content. Specifically used in the SEO Head Checker for extracting URLs from sitemap files.
from bs4 import BeautifulSoup

# Detects character encodings, ensuring accurate decoding of web page content in the SEO Head Checker.
import chardet

# Writes and reads CSV files. Used to generate reports in apps like the SEO Head Checker.
# Used in the SEO Head Checker to generate CSV reports summarizing the presence of SEO elements.
import csv

# Provides garbage collection functionality, potentially used to free memory during heavy processing tasks.
import gc

# Enables multi-threaded parallel execution of tasks, such as processing multiple URLs concurrently in the SEO Head Checker.
from concurrent.futures import ThreadPoolExecutor

# Process: Creates separate processes for tasks, such as time-limited sitemap processing in the SEO Head Checker.
# Queue: Facilitates inter-process communication, allowing results or errors to be passed back to the main process.
from multiprocessing import Process, Queue

# Provides time-related functions, such as enforcing delays or measuring execution time.
import time

# Dictionary to store task statuses.
from django.core.cache import cache

# The following commented imports are placeholders for future functionalities:
# from reportlab.lib.pagesizes import letter
# from reportlab.pdfgen import canvas
# - Intended for PDF generation, possibly in the Freight Carrier Safety Reporter or similar apps.
# import plotly
# - Placeholder for potential data visualization features.


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
        "User-Agent": "SEO Head Checker (+https://www.bencritt.net)",
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


def process_sitemap_urls(urls, sitemap_limit=100, max_workers=5, task_id=None):
    """
    Processes URLs from a sitemap in parallel, up to a specified limit.

    - Utilizes a thread pool to process URLs concurrently for improved efficiency.
    - Updates task progress in the cache if a task ID is provided.
    - Returns the results of processing each URL.

    Args:
        urls (list): List of URLs to process.
        sitemap_limit (int, optional): Maximum number of URLs to process. Defaults to 100.
        max_workers (int, optional): Number of threads to use for concurrent processing. Defaults to 5.
        task_id (str, optional): Unique identifier for tracking progress in the cache. Defaults to None.

    Returns:
        list: A list of results from processing each URL.
    """
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
                    # Cache entry expiration time (1 hour).
                    timeout=3600,
                )
    # Return the list of results after processing all URLs.
    return results


def process_single_url(url):
    """
    Processes a single URL to extract and check the presence of SEO-related elements in the <head> section.

    - Sends an HTTP GET request to fetch the content of the URL.
    - Parses the HTML content and extracts the <head> section.
    - Checks for the presence of various SEO elements (e.g., title, meta tags, structured data).
    - Returns a dictionary with the URL, status, and details about the presence of SEO elements.

    Args:
        url (str): The URL to process.

    Returns:
        dict: A dictionary containing the URL, status, and results for SEO element checks.
    """
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

        # Count the number of structured data scripts in the <head>.
        structured_data_count = len(head.find_all("script", type="application/ld+json"))

        # Return a dictionary with the presence status of various SEO elements.
        return {
            "URL": url,
            "Status": "Success",
            "Title Tag": "Present" if head.title else "Missing",
            "Meta Description": is_present("meta", name="description"),
            "Canonical Tag": is_present("link", rel="canonical"),
            "Meta Robots Tag": is_present("meta", name="robots"),
            "Open Graph Tags": (
                "Present"
                if head.find(
                    "meta", attrs={"property": lambda p: p and p.startswith("og:")}
                )
                else "Missing"
            ),
            "Twitter Card Tags": (
                "Present"
                if head.find(
                    "meta", attrs={"name": lambda p: p and p.startswith("twitter:")}
                )
                else "Missing"
            ),
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
https://mobile.fmcsa.dot.gov/QCDevsite/docs/qcApi
https://mobile.fmcsa.dot.gov/QCDevsite/docs/getStarted
https://mobile.fmcsa.dot.gov/QCDevsite/docs/apiElements
https://mobile.fmcsa.dot.gov/qc/services/carriers/264184?webKey=d4cf8cc419e2ba88e590a957140c86abe8b79f97
https://mobile.fmcsa.dot.gov/qc/services/carriers/2245945?webKey=d4cf8cc419e2ba88e590a957140c86abe8b79f97
"""

"""
I'm still working on a "Safety Score" feature for this app.

def calculate_safety_score(carrier_data):
    # Assign weightings to each metric (these can be adjusted as necessary)
    weights = {
        "crashTotal": 0.2,
        "driverOosRate": 0.2,
        "fatalCrash": 0.2,
        "vehicleOosRate": 0.2,
        "vehicleInsp": 0.1,
        "safetyRating": 0.1,  # This returns a letter, not a numner.  I need to figure this out.
    }

    # Calculate the safety score based on the available data, handling "N/A" as 0
    crash_total = (
        float(carrier_data.get("crashTotal", 0))
        if carrier_data.get("crashTotal") != "N/A"
        else 0
    )
    driver_oos_rate = (
        float(carrier_data.get("driverOosRate", 0))
        if carrier_data.get("driverOosRate") != "N/A"
        else 0
    )
    fatal_crash = (
        float(carrier_data.get("fatalCrash", 0))
        if carrier_data.get("fatalCrash") != "N/A"
        else 0
    )
    vehicle_oos_rate = (
        float(carrier_data.get("vehicleOosRate", 0))
        if carrier_data.get("vehicleOosRate") != "N/A"
        else 0
    )
    vehicle_insp = (
        float(carrier_data.get("vehicleInsp", 0))
        if carrier_data.get("vehicleInsp") != "N/A"
        else 0
    )
    safety_rating = (
        float(carrier_data.get("safetyRating", 0))
        if carrier_data.get("safetyRating") != "N/A"
        else 0
    )

    # Apply weights to each factor to calculate the total score
    safety_score = (
        crash_total * weights["crashTotal"]
        + driver_oos_rate * weights["driverOosRate"]
        + fatal_crash * weights["fatalCrash"]
        + vehicle_oos_rate * weights["vehicleOosRate"]
        + vehicle_insp * weights["vehicleInsp"]
        + safety_rating * weights["safetyRating"]
    )

    # Normalize the score to a scale (0-100 for example)
    max_possible_score = (
        sum(weights.values()) * 100
    )  # Assuming the max score is 100 per metric
    normalized_score = (safety_score / max_possible_score) * 100

    return round(normalized_score, 2)
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
        response.raise_for_status()  # Raise an exception for bad status codes

        response_data = response.json()
        print("Full Response Data:", response_data)

        # Ensure 'content' exists and contains 'carrier'
        content_data = response_data.get("content")
        if not content_data:
            return None  # 'content' missing, return None

        carrier_data = content_data.get("carrier")
        if not carrier_data:
            return None  # 'carrier' missing, return None

        # Apply the helper function to replace None values with "N/A"
        cleaned_carrier_data = replace_none_with_na(carrier_data)

        # Parse and clean relevant fields from the cleaned JSON data
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


"""
I'm still working on this feature.

def generate_pdf(carrier, safety_score):
    # Create the PDF response
    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = (
        f'attachment; filename="carrier_safety_report_{carrier["dotNumber"]}.pdf"'
    )

    # Create a PDF canvas
    p = canvas.Canvas(response, pagesize=letter)
    width, height = letter

    # Add content to the PDF
    p.setFont("Helvetica-Bold", 16)
    p.drawString(
        100, height - 50, f"Freight Carrier Safety Report for {carrier['name']}"
    )

    p.setFont("Helvetica", 12)
    p.drawString(50, height - 80, f"USDOT Number: {carrier['dotNumber']}")
    p.drawString(50, height - 100, f"MC Number: {carrier['mcNumber']}")
    p.drawString(50, height - 120, f"Allowed to Operate: {carrier['allowedToOperate']}")
    p.drawString(50, height - 140, f"Safety Score: {safety_score}")

    # Non-safety information section
    p.setFont("Helvetica-Bold", 14)
    p.drawString(50, height - 160, "Carrier Information")

    p.setFont("Helvetica", 12)
    p.drawString(
        50,
        height - 180,
        f"Physical Address: {carrier['phyStreet']}, {carrier['phyCity']}, {carrier['phyState']} {carrier['phyZipcode']}",
    )
    p.drawString(
        50, height - 200, f"Employer Identification Number (EIN): {carrier['ein']}"
    )
    p.drawString(50, height - 220, f"Total Drivers: {carrier['totalDrivers']}")
    p.drawString(50, height - 240, f"Total Power Units: {carrier['totalPowerUnits']}")

    # Safety information section
    p.setFont("Helvetica-Bold", 14)
    p.drawString(50, height - 260, "Safety Information")

    p.setFont("Helvetica", 12)
    p.drawString(50, height - 280, f"Total Crashes: {carrier['crashTotal']}")
    p.drawString(
        50, height - 300, f"Driver Out-of-Service Rate: {carrier['driverOosRate']}"
    )
    p.drawString(
        50, height - 320, f"Vehicle Out-of-Service Rate: {carrier['vehicleOosRate']}"
    )
    p.drawString(50, height - 340, f"Safety Rating: {carrier['safetyRating']}")
    p.drawString(50, height - 360, f"Safety Rating Date: {carrier['safetyRatingDate']}")

    # Finalize the PDF
    p.showPage()
    p.save()

    return response
"""


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
