import ssl
import socket
from OpenSSL import crypto
from urllib.parse import urlparse
from datetime import datetime
import requests
import json
from django.shortcuts import render
from django.http import HttpResponse
from bs4 import BeautifulSoup
import chardet
import csv
import gc
from concurrent.futures import ThreadPoolExecutor

# from reportlab.lib.pagesizes import letter
# from reportlab.pdfgen import canvas
# import plotly


def normalize_url(url):
    """
    Normalize a URL by adding missing schemes (e.g., https://) or www if necessary.

    Args:
        url (str): The input URL.

    Returns:
        str: The normalized URL in a valid format.
    """
    parsed_url = urlparse(url)

    # Add scheme (https://) if missing.
    if not parsed_url.scheme:
        url = f"https://{url}"

    # # Re-parse after adding the scheme to ensure netloc is valid.
    parsed_url = urlparse(url)

    # Add www if netloc is missing but path looks like a domain.
    if not parsed_url.netloc and parsed_url.path:
        url = f"https://www.{parsed_url.path}"

    return url


def fetch_head_section(url):
    """
    Fetch and return the <head> section of a webpage.

    Args:
        url (str): The URL to fetch.

    Returns:
        BeautifulSoup.Tag or None: The parsed <head> section or None if an error occurs.
    """
    try:
        # Use a persistent session for efficiency.
        with requests.Session() as session:
            response = session.get(url, stream=True, timeout=30)
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

            # Parse the <head> section.
            soup = BeautifulSoup(head_html, "html.parser")  # Use lightweight parser
            return soup.find("head")

    except Exception as e:
        print(f"Error fetching <head> for URL {url}: {e}")
        return None


def process_single_url(url):
    """
    Extract SEO elements from the <head> of a single URL.

    Args:
        url (str): The URL to process.

    Returns:
        dict: A dictionary with the URL, status, and SEO elements found.
    """
    head = fetch_head_section(url)
    if not head:
        return {"URL": url, "Status": "No head section"}

    # Extract and indicate the presence of various SEO elements.
    return {
        "URL": url,
        "Status": "Success",
        "Title Tag": "Present" if head.title else "Missing",
        "Meta Description": (
            "Present" if head.find("meta", attrs={"name": "description"}) else "Missing"
        ),
        "Canonical Tag": "Present" if head.find("link", rel="canonical") else "Missing",
        "Meta Robots Tag": (
            "Present" if head.find("meta", attrs={"name": "robots"}) else "Missing"
        ),
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
            "Present" if head.find("script", type="application/ld+json") else "Missing"
        ),
        "Charset Declaration": (
            "Present" if head.find("meta", charset=True) else "Missing"
        ),
        "Viewport Tag": (
            "Present" if head.find("meta", attrs={"name": "viewport"}) else "Missing"
        ),
        "Favicon": "Present" if head.find("link", rel="icon") else "Missing",
    }


def process_sitemap(sitemap_url):
    """
    Process a sitemap URL and generate a report in parallel.

    Args:
        sitemap_url (str): The sitemap URL to process.

    Returns:
        str: The path to the generated file.

    Raises:
        ValueError: If the sitemap cannot be processed.
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
        # Process URLs in parallel.
        with ThreadPoolExecutor(max_workers=10) as executor:
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
