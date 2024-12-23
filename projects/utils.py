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

# The following commented imports are placeholders for future functionalities:
# from reportlab.lib.pagesizes import letter
# from reportlab.pdfgen import canvas
# - Intended for PDF generation, possibly in the Freight Carrier Safety Reporter or similar apps.
# import plotly
# - Placeholder for potential data visualization features.


# Function to process the sitemap and return results via a queue.
def process_sitemap_task(sitemap_url, queue):
    """
    Process a sitemap URL, extracting SEO information for up to 500 URLs,
    and save the results to a CSV file.

    Args:
        sitemap_url (str): URL of the sitemap to process.
        queue (multiprocessing.Queue): Queue to return results or errors.

    Notes:
        - This function runs in a separate process to avoid blocking.
    """
    # Attempt to fetch the sitemap from the provided URL.
    try:
        # 10-second timeout for the request.
        response = requests.get(sitemap_url, timeout=10)
        # Raise an HTTPError for bad responses (4xx or 5xx).
        response.raise_for_status()

        # Parse the sitemap XML content.
        soup = BeautifulSoup(response.content, "lxml-xml")
        # Check for <sitemap> tags to identify sitemap indexes.  This app doesn't support sitemap indexes.
        if soup.find("sitemap"):
            queue.put(
                ValueError(
                    "Sitemap indexes are not supported. Please submit a standard sitemap containing URLs."
                )
            )
            return
        # Extract <loc> tags containing URLs.
        urls = [loc.text for loc in soup.find_all("loc")]

        # If no URLs are found in the sitemap, return an error via the queue.
        if not urls:
            queue.put(ValueError("No URLs found in the sitemap."))
            return

        # List to store results of URL processing.
        results = []

        # Process a subset of the URLs (up to 500 due to save server resources.)
        for url in urls[:500]:
            # Process each URL individually.
            result = process_single_url(url)
            results.append(result)

        # Save the processing results to a CSV file.
        output_file = "seo_report.csv"
        with open(output_file, "w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(
                file,
                fieldnames=[
                    "URL",
                    "Status",
                    "Title Tag",
                    "Meta Description",
                    "Canonical Tag",
                    "Meta Robots Tag",
                    "Open Graph Tags",
                    "Twitter Card Tags",
                    "Hreflang Tags",
                    "Structured Data",
                    "Charset Declaration",
                    "Viewport Tag",
                    "Favicon",
                ],
            )
            # Write column headers.
            writer.writeheader()
            # Write each processed URL's data.
            writer.writerows(results)

        # Send the path to the generated file back to the main process.
        queue.put(output_file)

    except Exception as e:
        # If an error occurs, send the exception back to the main process via the queue.
        queue.put(e)


# Function to process a sitemap with a 30 minute timeout.
def process_sitemap_with_timeout(sitemap_url, timeout=1800):
    """
    Process a sitemap URL with a timeout. The function spawns a subprocess
    to handle the processing and enforces a time limit.

    Args:
        sitemap_url (str): URL of the sitemap to process.
        timeout (int): Maximum time allowed (in seconds) for processing.

    Returns:
        str: Path to the generated report file.

    Raises:
        ValueError: If the process times out or encounters an error.
    """

    # Create a queue to facilitate communication between the main process and the worker process.
    queue = Queue()

    # Initialize a separate process to handle sitemap processing.
    process = Process(target=process_sitemap_task, args=(sitemap_url, queue))
    # Start the worker process.
    process.start()

    # Wait for the process to finish or timeout.
    process.join(timeout)

    if process.is_alive():
        # If the process exceeds the timeout, terminate it forcefully.
        process.terminate()
        # Ensure the process is fully stopped.
        process.join()
        raise ValueError(
            "Processing took too long and was stopped. Heroku limits me to 30 seconds. Please try a smaller sitemap."
        )

    # Retrieve the result from the queue.
    result = queue.get()
    if isinstance(result, Exception):
        # If an exception was raised in the worker process, propagate it as a ValueError.
        raise ValueError(
            "Failed to process sitemap.  Please make sure you've entered a valid sitemap URL."
        )
    # Return the file path of the successfully generated report.
    return result


# This allows the app to break down, manipulate, and reassemble URLs in a structured way.
from urllib.parse import urlparse, urlunparse


# Function to normalize URLs.
def normalize_url(url):
    """
    Normalize a URL by adding missing schemes (e.g., https://) or handling naked domains.

    Args:
        url (str): The input URL.

    Returns:
        str: The normalized URL in a valid format.

    Raises:
        ValueError: If the URL cannot be normalized.
    """
    parsed_url = urlparse(url)

    # Case 1: No scheme and no netloc, but path looks like a domain.
    if not parsed_url.scheme and not parsed_url.netloc:
        # Likely a domain.
        if "." in parsed_url.path:
            # Assume it's a naked domain.
            url = f"https://{parsed_url.path}"
            # Re-parse with the updated scheme.
            parsed_url = urlparse(url)

    # Case 2: No scheme but valid netloc.
    elif not parsed_url.scheme:
        # Add https:// as the default scheme.
        url = f"https://{url}"
        # Re-parse with the updated scheme.
        parsed_url = urlparse(url)

    # Case 3: Ensure the resulting URL has a netloc.
    if not parsed_url.netloc:
        raise ValueError(f"Invalid URL: {url}")

    # Return the fully normalized URL.
    return urlunparse(parsed_url)


# Create a persistent HTTP session with the requests library.
# Avoid the cost of establishing new connections for each request.
session = requests.Session()


# Function to fetch the <head> section of a webpage.
def fetch_head_section(url):
    """
    Fetch the <head> section of a webpage using streaming to minimize memory usage.

    Args:
        url (str): The URL to fetch.

    Returns:
        BeautifulSoup.Tag or None: Parsed <head> section, or None on failure.
    """
    try:
        # Use a persistent session for efficiency.
        with requests.Session() as session:
            # This identifies my app so website administrators know who is crawling their website.
            session.headers.update(
                {
                    "User-Agent": "SEO Head Checker by Ben Crittenden (https://www.bencritt.net)"
                }
            )
            response = session.get(url, stream=True, timeout=3000)
            response.raise_for_status()

            # Accumulate streamed content until </head> is found.
            head_content = b""
            for chunk in response.iter_content(chunk_size=1024):
                head_content += chunk
                if b"</head>" in head_content:
                    break

            # Detect encoding of the content.
            detected_encoding = chardet.detect(head_content)["encoding"]
            if not detected_encoding:
                raise ValueError(f"Encoding detection failed for URL: {url}")

            # Decode and extract the <head> section.
            decoded_content = head_content.decode(detected_encoding, errors="replace")
            head_html = decoded_content.split("</head>")[0] + "</head>"

            soup = BeautifulSoup(head_html, "lxml")
            return soup.find("head")

    except Exception as e:
        print(f"Error fetching <head> for URL {url}: {e}")
        return None


# Function to extract SEO elements from a single URL.
def process_single_url(url):
    """
    Extract SEO elements from the <head> of a single URL.

    Args:
        url (str): The URL to process.

    Returns:
        dict: A dictionary with the URL, status, and SEO elements found.
    """
    try:
        head = fetch_head_section(url)
    except Exception as e:
        return {"URL": url, "Status": f"Error: {str(e)}"}

    if not head:
        return {"URL": url, "Status": "No head section"}

    def is_present(tag_name, **attrs):
        return "Present" if head.find(tag_name, attrs=attrs) else "Missing"

    structured_data_count = len(head.find_all("script", type="application/ld+json"))

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


# Function to process a sitemap and generate a report.
def process_sitemap(sitemap_url):
    """
    Process a sitemap, analyze each URL, and generate a CSV report.

    Args:
        sitemap_url (str): The sitemap URL.

    Returns:
        str: Path to the generated CSV report.

    Raises:
        ValueError: If processing fails or the sitemap is invalid.
    """
    output_file = "seo_report.csv"
    try:
        # Fetch and parse the sitemap.
        with requests.get(sitemap_url, timeout=10) as response:
            response.raise_for_status()
            soup = BeautifulSoup(response.content, "lxml-xml")
            urls = [loc.text for loc in soup.find_all("loc")]

            if not urls:
                raise ValueError("No URLs found in the sitemap.")

        # Initialize an empty list, to be populated below.
        results = []
        # Process URLs in parallel.  With max_workers set to 5, this will process 10 URLs at once.
        with ThreadPoolExecutor(max_workers=5) as executor:
            results = list(executor.map(process_single_url, urls))

        # Write results to CSV.
        with open(output_file, mode="w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(
                file,
                fieldnames=[
                    "URL",
                    "Status",
                    "Title Tag",
                    "Meta Description",
                    "Canonical Tag",
                    "Meta Robots Tag",
                    "Open Graph Tags",
                    "Twitter Card Tags",
                    "Hreflang Tags",
                    "Structured Data",
                    "Charset Declaration",
                    "Viewport Tag",
                    "Favicon",
                ],
            )
            writer.writeheader()
            writer.writerows(results)

        return output_file

    except requests.exceptions.ConnectionError:
        raise ValueError(
            "Unable to connect to the provided URL. Please ensure it is valid and accessible."
        )
    except requests.exceptions.Timeout:
        raise ValueError(
            "The request timed out. Heroku limits me to 30 seconds per request."
        )
    except requests.exceptions.RequestException:
        raise ValueError(
            "An error occurred while fetching the sitemap. Please verify the URL and try again."
        )
    except Exception as e:
        raise ValueError(f"Failed to process sitemap: {e}")


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
