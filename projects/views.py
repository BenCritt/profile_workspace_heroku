# Used to render templates for various views (e.g., forms, results) and handle redirects to other views/pages.
from django.shortcuts import render, redirect

# Custom forms used across different views.
from .forms import (
    # QRForm is used in the QR Code Generator.
    QRForm,
    # MonteCarloForm is used in the Monte Carlo Simulator.
    MonteCarloForm,
    # WeatherForm is used in the Weather Forecast app.
    WeatherForm,
    # TextForm is used in the Grade Level Analyzer.
    TextForm,
    # IPForm is used in the IP Address Lookup Tool.
    IPForm,
    # DomainForm is used in the DNS Lookup Tool.
    DomainForm,
    # SSLCheckForm is used in the SSL Verification Tool.
    SSLCheckForm,
    # CarrierSearchForm is used in the Freight Carrier Safety Reporter.
    CarrierSearchForm,
    # SitemapForm is used in the SEO Head Checker.
    SitemapForm,
    # XMLUploadForm is used in the XML Splitter.
    XMLUploadForm,
)

# Provides operating system-dependent functionality, such as file path handling and directory management.
import os

# Used in the QR Code Generator app to create QR codes from user-provided data.
import qrcode

# HttpResponse: Sends raw data back to the user (e.g., for file downloads).
# JsonResponse: Sends JSON responses for AJAX requests, such as progress tracking in SEO Head Checker.
# HttpResponseNotFound: Returns a 404 error for static files or invalid paths.
from django.http import HttpResponse, JsonResponse, HttpResponseNotFound

# Used for making HTTP requests in apps such as:
# - Fetching weather data for the Weather Forecast app.
# - Performing API calls for geolocation in the IP Address Lookup Tool.
# - Retrieving carrier data in the Freight Carrier Safety Reporter.
# - Fetching sitemap URLs in the SEO Head Checker.
# - Fetching TLE data from CelesTrak in the ISS Tracker.
import requests

# Handles date and time operations, such as formatting timestamps in the Weather Forecast app.
import datetime

# Used in the Monte Carlo Simulator for generating random simulations and numerical calculations.
import numpy as np

# Used in the Monte Carlo Simulator for creating visualizations (e.g., histograms).
import matplotlib.pyplot as plt

# Accesses project-wide settings, such as the base directory, used in file path construction (e.g., robots.txt, requirements.txt).
from django.conf import settings

# Used in the Grade Level Analyzer to calculate various readability scores.
import textstat

# Performs DNS queries, such as resolving A, MX, and other record types in the DNS Lookup Tool.
import dns.resolver

# Converts IP addresses to reverse DNS names, used in the IP Address Lookup Tool for PTR lookups.
import dns.reversename

# Sets caching policies for views, ensuring dynamic content is always up-to-date (e.g., no-cache for tools and results pages).
from django.views.decorators.cache import cache_control

# Imports utility functions shared across apps.
from .utils import (
    # verify_ssl: Verifies SSL certificates in the SSL Verification Tool.
    verify_ssl,
    # get_coordinates, get_city_and_state: Geocoding utilities for the Weather Forecast app.
    get_coordinates,
    get_city_and_state,
    # get_fmcsa_carrier_data_by_usdot: Retrieves carrier data for the Freight Carrier Safety Reporter.
    get_fmcsa_carrier_data_by_usdot,
    # normalize_url: Ensures submitted URLs are properly formatted (e.g., add "https://" if missing).
    normalize_url,
    # fetch_sitemap_urls: Extracts all <loc> tags (URLs) from a sitemap.
    fetch_sitemap_urls,
    # save_results_to_csv: Saves processed SEO results to a CSV file for download.
    save_results_to_csv,
    # sitemap_limit: Limits the number of URLs processed from a sitemap. This is a variable, not a library.
    sitemap_limit,
    # process_sitemap_urls: Processes multiple URLs concurrently, updating progress and returning results.
    process_sitemap_urls,
    detect_region,
    # split_xml_to_zip is used in the XML Splitter.
    split_xml_to_zip,
)

# Generates unique task IDs for tracking background tasks, such as sitemap processing in the SEO Head Checker.
import uuid

# Dictionary to store task statuses.
from django.core.cache import cache

# Garbage Collection helps prevent the wasting of memory.
import gc

# render: Used to render templates with context data, enabling dynamic HTML generation for views.
from django.shortcuts import render

# json: Used to parse incoming JSON requests and generate JSON responses for AJAX interactions.
import json

# ThreadPoolExecutor: Used to execute tasks (e.g., URL processing) concurrently, improving performance for processing large sitemaps.
from concurrent.futures import ThreadPoolExecutor

# Used to calculate time intervals for predictions, such as 1-day time ranges.
from datetime import timedelta

# Topos: Represents an observer's location on Earth.
# load: Loads data such as TLE and ephemeris.
from skyfield.api import Topos, load

# Provides tools for working with satellites using Two-Line Element (TLE) data.
from skyfield.sgp4lib import EarthSatellite

# Caches data (e.g., TLE) to reduce redundant API calls and improve performance.
from django.core.cache import cache

# Determines the time zone based on geographic coordinates (latitude and longitude).
from timezonefinder import TimezoneFinder

# Handles time zones for converting UTC times to the observer's local time zone.
import pytz

# Used in the XML Splitter
from django.http import StreamingHttpResponse

# XML Splitter
# Disallow caching to prevent CSRF token errors.
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def xml_splitter(request):
    # Load the form for the user to upload their XML file.
    form = XMLUploadForm(request.POST or None, request.FILES or None)

    # If the user submitted an XML file.
    if request.method == "POST" and form.is_valid():
        # Attempt to split the XML file into multiple XML files.
        try:
            # Use the split_xml_to_zip function from utils.py to parse the user's file and create their new files.
            # form.cleaned_data is a stock Django utility.  The file captured by the form is what's being parsed by split_xml_to_zip.
            # The results of this are captured by zip_io.
            zip_io = split_xml_to_zip(form.cleaned_data["file"])
        # Catch errors so the app doesn't crash.
        except ValueError as err:
            # Show the problem to the user instead of crashing.
            form.add_error("file", str(err))
        # If everything worked, it's time to give the user their ZIP folder containing their new files.
        else:
            # This is the naming convention for the ZIP folder.
            # Splits from the rightmost dot in the source filename and takes the first of the two portions made from that split.
            # Concatenate the first portion with _split.zip.
            download_name = form.cleaned_data["file"].name.rsplit(".", 1)[0] + "_split.zip"
            response = StreamingHttpResponse(zip_io, content_type="application/zip")
            response["Content-Disposition"] = f'attachment; filename="{download_name}"'
            return response

    # Load the web page.
    return render(request, "projects/xml_splitter.html", {"form": form})

# ISS Tracker
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def iss_tracker(request):
    """
    View function to track the International Space Station (ISS) and provide
    real-time location data and visibility events for a given location.

    Args:
        request: HTTP request object.

    Returns:
        Rendered HTML page with ISS current data and visibility events.
    """

    # Initialize the form that takes in the ZIP code.  This is the same form used by the Weather Forecast app.
    form = WeatherForm(request.POST or None)
    # Initialize the library that will store current ISS data.
    current_data = {}
    # Initialize the array that will store upcoming ISS pass events.
    iss_pass_times = []

    # Check if the request method is POST and the form is valid.
    if request.method == "POST" and form.is_valid():
        # Get the ZIP code from the form and convert it to coordinates.
        zip_code = form.cleaned_data["zip_code"]
        coordinates = get_coordinates(zip_code)

        if coordinates:
            # Extract latitude and longitude from the coordinates.
            lat, lon = coordinates

            try:
                # Attempt to retrieve cached TLE data (Two-Line Element sets).
                tle_data = cache.get("tle_data")
                if not tle_data:
                    # If TLE data is not cached, fetch it from CelesTrak.
                    tle_url = "https://celestrak.org/NORAD/elements/stations.txt"
                    # Timeout after 10 seconds.
                    response = requests.get(tle_url, timeout=10)
                    # Raise an exception for HTTP errors.
                    response.raise_for_status()
                    # Split TLE data into lines.
                    tle_data = response.text.splitlines()
                    # Cache TLE data for 1 hour.
                    cache.set("tle_data", tle_data, timeout=3600)

                # Locate the ISS entry in the TLE data.
                # Identifier for the ISS in the TLE file.
                iss_name = "ISS (ZARYA)"
                iss_index = next(
                    i for i, line in enumerate(tle_data) if line.strip() == iss_name
                )
                # First line of the TLE for the ISS.
                line1 = tle_data[iss_index + 1]
                # Second line of the TLE for the ISS.
                line2 = tle_data[iss_index + 2]

                # Create an EarthSatellite object for the ISS.
                satellite = EarthSatellite(line1, line2, iss_name, load.timescale())

                # Define the observer's location based on latitude and longitude.
                observer = Topos(latitude_degrees=lat, longitude_degrees=lon)
                # Load the timescale for Skyfield.
                ts = load.timescale()
                # Get the current time.
                now = ts.now()
                # End time for visibility calculations.
                end_time = ts.utc(now.utc_datetime() + timedelta(days=1))

                # Calculate ISS visibility events for the observer's location.
                times, events = satellite.find_events(
                    observer, now, end_time, altitude_degrees=10.0
                )

                # Calculate the ISS's current geocentric position.
                geocentric = satellite.at(now)
                # Subpoint (latitude, longitude, altitude).
                subpoint = geocentric.subpoint()
                # Latitude in degrees.
                latitude = subpoint.latitude.degrees
                # Longitude in degrees.
                longitude = subpoint.longitude.degrees
                # Velocity in km/s.
                velocity = geocentric.velocity.km_per_s

                # Detect the region (land or body of water) over which the ISS is currently located.
                region = detect_region(latitude, longitude)

                # Store the current ISS data.
                current_data = {
                    "latitude": f"{latitude:.2f}°",
                    "longitude": f"{longitude:.2f}°",
                    "altitude": f"{subpoint.elevation.km:.2f} km",
                    "velocity": f"{(velocity[0]**2 + velocity[1]**2 + velocity[2]**2)**0.5:.2f} km/s",
                    "region": region,
                }

                # Determine the local timezone based on the observer's location.
                tf = TimezoneFinder()
                timezone_name = tf.timezone_at(lat=lat, lng=lon) or "UTC"
                local_timezone = pytz.timezone(timezone_name)

                # Format the visibility events for display.
                for t, event in zip(times, events):
                    # Event name.
                    name = ("Rise", "Culminate", "Set")[event]
                    # Event time in UTC.
                    utc_time = t.utc_datetime()
                    # Convert UTC time to time zone local to the ZIP code.
                    local_time = utc_time.astimezone(local_timezone)
                    iss_pass_times.append(
                        {
                            "event": name,
                            # "date": local_time.strftime("%A, %B %d, %Y"), ~ I'm removin year for now.
                            "date": local_time.strftime("%A, %B %d"),
                            "time": local_time.strftime("%I:%M %p %Z"),
                            "position": (
                                "North"
                                if satellite.at(t).subpoint().latitude.degrees > lat
                                else "South"
                            ),
                        }
                    )

                return render(
                    request,
                    "projects/iss_tracker.html",
                    {
                        "form": form,
                        "current_data": current_data,
                        "iss_pass_times": iss_pass_times,
                    },
                )
            except Exception as e:
                # Handle any errors and display an error message.
                error = f"An error occurred: {e}"
                return render(
                    request, "projects/iss_tracker.html", {"form": form, "error": error}
                )

    # Render the page initially with the form and no data.
    return render(
        request,
        "projects/iss_tracker.html",
        {"form": form, "current_data": current_data},
    )


@cache_control(no_cache=True, must_revalidate=True, no_store=True)
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


@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def seo_head_checker(request):
    """
    Renders the SEO Head Checker form and handles POST requests to initiate processing.

    - For GET requests: Displays the form for the user to input a sitemap URL.
    - For POST requests: Validates the submitted form and initiates sitemap processing.
    - Provides user feedback on errors or the status of the initiated process.
    """
    # Handle form submission via POST.
    if request.method == "POST":
        # Bind the submitted data to the form for validation.
        form = SitemapForm(request.POST)
        # Check if the form data is valid
        if form.is_valid():
            # Extract the cleaned sitemap URL from the form.
            sitemap_url = form.cleaned_data["sitemap_url"]
            try:
                # Start processing the sitemap and get the response.
                response = start_sitemap_processing(request)
                # Task successfully started.
                if response.status_code == 202:
                    # Retrieve the task ID for tracking the status.
                    task_id = response.json().get("task_id")
                    # Pass form and task_id to template.
                    return render(
                        request,
                        "projects/seo_head_checker.html",
                        {"form": form, "task_id": task_id},
                    )
                # If the response indicates an error.
                else:
                    # Extract the error message or provide a generic error.
                    error_message = response.json().get("error", "Unexpected error.")
                    # Pass error to template.
                    return render(
                        request,
                        "projects/seo_head_checker.html",
                        {"form": form, "error": error_message},
                    )
            # Catch any unexpected errors during processing.
            except Exception as e:
                # Render the form with an error message.
                return render(
                    request,
                    "projects/seo_head_checker.html",
                    {"form": form, "error": str(e)},
                )
    # Handle GET requests by displaying an empty form.
    else:
        form = SitemapForm()

    # Render the form for both GET and unsuccessful POST requests.
    return render(request, "projects/seo_head_checker.html", {"form": form})


def start_sitemap_processing(request):
    """
    Handles the initiation of sitemap processing.

    - Accepts a POST request with a sitemap URL in the request body.
    - Starts a background task to fetch and process the sitemap URLs.
    - Returns a JSON response containing a unique task ID for progress tracking.
    """
    # Ensure the request method is POST.
    if request.method == "POST":
        try:
            # Parse the request body as JSON.
            data = json.loads(request.body)
            # Normalize and validate the sitemap URL.
            sitemap_url = normalize_url(data.get("sitemap_url"))

            # Generate a unique task ID for this processing job.
            task_id = str(uuid.uuid4())
            # Initialize the cache for tracking task status and progress.
            cache.set(task_id, {"status": "pending", "progress": 0}, timeout=1800)

            # Define the background task for sitemap processing.
            def process_task():
                try:
                    # Fetch all URLs from the sitemap.
                    urls = fetch_sitemap_urls(sitemap_url)
                    # Process the fetched URLs, updating progress in cache.
                    results = process_sitemap_urls(urls, max_workers=5, task_id=task_id)
                    # Save the processed results to a CSV file.
                    file_path = save_results_to_csv(results, task_id)
                    # Update cache to mark task as completed and store the file path.
                    cache.set(
                        task_id,
                        {"status": "completed", "file": file_path},
                        timeout=1800,
                    )
                except Exception as e:
                    # Update cache to indicate an error occurred.
                    cache.set(
                        task_id, {"status": "error", "error": str(e)}, timeout=1800
                    )
                finally:
                    # Explicit cleanup.
                    del urls, results
                    # Perform garbage collection to free up memory.
                    gc.collect()

            # Submit the processing task to a thread pool for background execution.
            ThreadPoolExecutor().submit(process_task)

            # Return a response with the task ID for the client to track progress.
            return JsonResponse({"task_id": task_id}, status=202)
        except Exception as e:
            # Handle any exceptions during processing and return an error response.
            return JsonResponse({"error": str(e)}, status=400)

    # Return an error response if the request method is not POST.
    return JsonResponse({"error": "Invalid request method"}, status=405)


def get_task_status(request, task_id):
    """
    Retrieves the status of a background task by its task ID.

    - Checks the cache for the task information associated with the given task ID.
    - Returns the current status of the task, including progress or errors, if available.

    Args:
        request (HttpRequest): The HTTP request object.
        task_id (str): The unique identifier for the task.

    Returns:
        JsonResponse: A JSON response containing the task status or an error message.
    """
    # Attempt to retrieve the task information from the cache.
    task = cache.get(task_id)
    # If the task is not found in the cache.
    if not task:
        # Return an error response indicating the task was not found.
        return JsonResponse({"error": "Task not found"}, status=404)
    # Return the task details as a JSON response.
    return JsonResponse(task)


def download_task_file(request, task_id):
    """
    Handles the download of a completed task's output file.

    - Checks the cache for the task information and ensures the task is completed.
    - Validates the existence of the output file associated with the task.
    - Serves the file for download and cleans up the file and cache entry after serving.

    Args:
        request (HttpRequest): The HTTP request object.
        task_id (str): The unique identifier for the task.

    Returns:
        HttpResponse: A response containing the file for download.
        JsonResponse: An error response if the file or task is not found.
    """
    # Retrieve task details from the cache.
    task = cache.get(task_id)
    # Ensure the task exists and is marked as "completed".
    if not task or task.get("status") != "completed":
        return JsonResponse({"error": "File not ready or task not found"}, status=404)

    # Get the file path from the task details.
    file_path = task.get("file")

    # Verify that the file path exists and is accessible.
    if not file_path or not os.path.exists(file_path):
        return JsonResponse({"error": "File not found"}, status=404)

    # Open the file in binary mode and prepare the response for download.
    with open(file_path, "rb") as file:
        response = HttpResponse(file, content_type="application/octet-stream")

        # Set the Content-Disposition header to prompt a download with the file's name.
        response["Content-Disposition"] = (
            f'attachment; filename="{os.path.basename(file_path)}"'
        )

        # Remove the file from the server after it is served.
        os.remove(file_path)
        # Delete the task entry from the cache.
        cache.delete(task_id)
        # Trigger garbage collection to free memory.
        gc.collect()

        # Return the file as an HTTP response.
        return response


# This is code for generating favicons on Android devices.
# This dynamically creates a web.manifest JSON file, similar to how my sitemap is dynamically generated.
def manifest(request):
    manifest_json = {
        "short_name": "BenCritt",
        "name": "Ben Crittenden's PWA",
        "icons": [
            {
                "src": "https://www.bencritt.net/static/img/pwa/pwa-192.png",
                "sizes": "192x192",
                "type": "image/png",
            },
            {
                "src": "https://www.bencritt.net/static/img/pwa/pwa-512.png",
                "sizes": "512x512",
                "type": "image/png",
            },
        ],
        "start_url": "/",
        "display": "standalone",
        "theme_color": "#000000",
        "background_color": "#000000",
    }
    return JsonResponse(manifest_json)


# This is the code for the Freight Carrier Safety Reporter
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def freight_safety(request):
    form = CarrierSearchForm(request.POST or None)
    carrier = None
    error = None
    # safety_score = None ~ I'm still working on this feature.

    if request.method == "POST" and form.is_valid():
        search_value = form.cleaned_data["search_value"]

        try:

            # Ensure the search is conducted only with a DOT number
            carrier = get_fmcsa_carrier_data_by_usdot(search_value)

            if not carrier:
                error = "Carrier not found in FMCSA.  Please verify you're submitting a valid DOT Number."

            """
            I'm still working on this feature.
            
            if carrier:
                safety_score = calculate_safety_score(carrier)  # Calculate the safety score
                
                # Check if the user clicked the 'Download PDF' button
                if 'download_pdf' in request.POST:
                    return generate_pdf(carrier, safety_score)  # Trigger the PDF generation
            else:
                error = "Carrier not found in FMCSA."
            """
        except requests.exceptions.RequestException as e:
            # Catch any errors related to the API request
            error = f"There was an issue retrieving the carrier data. Please try again later. Error: {str(e)}"

    return render(
        request,
        "projects/freight_safety.html",
        {
            "form": form,
            "carrier": carrier,
            "error": error,
        },  # "safety_score": safety_score
    )


# This is the code for the Grade Level Analyzer.
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def grade_level_analyzer(request):
    # Check if the request method is POST.
    if request.method == "POST":
        # Initialize the form with data from the request.
        form = TextForm(request.POST)
        # Validate the form.
        if form.is_valid():
            # Extract the input text from the form.
            input_text = form.cleaned_data["text"]
            # Calculate readability scores using different indices.
            results = {
                "flesch_kincaid_grade": textstat.flesch_kincaid_grade(input_text),
                "gunning_fog": textstat.gunning_fog(input_text),
                "coleman_liau_index": textstat.coleman_liau_index(input_text),
            }
            # Calculate the weighted average of the scores.
            average_score = round(
                (0.5 * results["flesch_kincaid_grade"])
                + (0.3 * results["gunning_fog"])
                + (0.2 * results["coleman_liau_index"]),
                1,
            )
            # Calculate the uniform average of the scores.
            uniform_average_score = round(
                (
                    results["flesch_kincaid_grade"]
                    + results["gunning_fog"]
                    + results["coleman_liau_index"]
                )
                / 3,
                1,
            )
            # Add the calculated scores to the results dictionary.
            results["average_score"] = average_score
            results["uniform_average_score"] = uniform_average_score
            # Prepare the context with the form and results for rendering.
            context = {"form": form, "results": results}
            # Render the results page with the context.
            return render(request, "projects/grade_level_results.html", context)
        else:
            # If the form is invalid, re-render the page with the form.
            return render(request, "projects/grade_level_analyzer.html", {"form": form})
    else:
        # If the request is not POST, create a new form and render the page.
        form = TextForm()
        return render(request, "projects/grade_level_analyzer.html", {"form": form})


# This is the code for the view for my website's robots.txt file.
def robots_txt(request):
    # Construct the absolute path to the robots.txt file.
    robots_txt_path = os.path.join(settings.BASE_DIR, "robots.txt")
    # Open and read the content of the robots.txt file.
    with open(robots_txt_path, "r") as f:
        robots_txt_content = f.read()
    # Return the content as HttpResponse with content type 'text/plain'
    return HttpResponse(robots_txt_content, content_type="text/plain")


# This is the code for the view for the txt file containing my website's required Python libraries.
def requirements_txt(request):
    # Construct the absolute path to the requirements.txt file.
    requirements_txt_path = os.path.join(settings.BASE_DIR, "requirements.txt")
    # Open and read the content of the requirements.txt file.
    with open(requirements_txt_path, "r") as f:
        requirements_txt_content = f.read()
    # Return the content as HttpResponse with content type 'text/plain'
    return HttpResponse(requirements_txt_content, content_type="text/plain")


# This is the code for the view for the view for the txt file containing my website's runtime.
def runtime_txt(request):
    # Construct the absolute path to the runtime.txt file.
    runtime_txt_path = os.path.join(settings.BASE_DIR, "runtime.txt")
    # Open and read the content of the runtime.txt file.
    with open(runtime_txt_path, "r") as f:
        runtime_txt_content = f.read()
    # Return the content as HttpResponse with content type 'text/plain'.
    return HttpResponse(runtime_txt_content, content_type="text/plain")


# This is the code for my 404 catcher.  It returns the root, or homepage, of my website.
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def view_404(request, exception):
    return render(request, "404.html", status=404)


# This is the code for my homepage.  It's set in URL paths to the root of my website.
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def home(request):
    return render(request, "projects/home.html")


# This is the code for the page holding links to my résumé.
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def resume(request):
    return render(request, "projects/resume.html")


# This is the code for the QR Code Generator.
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def qr_code_generator(request):
    # Check if the request method is POST.
    if request.method == "POST":
        # Initialize the form with data from the request.
        form = QRForm(request.POST)
        # Validate the form.
        if form.is_valid():
            # Extract the data to be encoded in the QR code.
            data = form.cleaned_data["qr_text"]
            # Initialize a QR Code generator.
            qr = qrcode.QRCode(version=1, box_size=10, border=5)
            # Add the data to the QR Code.
            qr.add_data(data)
            # Optimize the QR code layout.
            qr.make(fit=True)
            # Create an image from the QR Code instance.
            img = qr.make_image(fill_color="black", back_color="white")
            # Determine the directory to save the QR code image.
            home_dir = os.path.expanduser("~")
            save_dir = os.path.join(home_dir, "Downloads")
            # Create the directory if it doesn't exist.
            if not os.path.exists(save_dir):
                os.makedirs(save_dir)
            # Define the filename and full path for the QR code image.
            filename = "qrcode.png"
            full_path = os.path.join(save_dir, filename)
            # Save the QR code image to the specified path.
            img.save(full_path)

            # Serve the QR code image as a downloadable file in the response.
            with open(full_path, "rb") as f:
                response = HttpResponse(f.read(), content_type="image/png")
                response["Content-Disposition"] = 'attachment; filename="qrcode.png"'
                return response
    # Handle non-POST requests by initializing an empty form.
    else:
        form = QRForm
    # Render the QR code generator page with the form.
    return render(request, "projects/qr_code_generator.html", context={"form": form})


# This is the code for the page containing methods of contacting me.
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def contact(request):
    return render(request, "projects/contact.html")


# This is the code for the Monte Carlo Simulator.
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def monte_carlo_simulator(request):
    # Check if the request method is POST.
    if request.method == "POST":
        # Initialize the form with data from the request.
        form = MonteCarloForm(request.POST)
        # Validate the form
        if form.is_valid():
            # This determines where to save the PDF file that will eventually be created.
            home_dir = os.path.expanduser("~")
            save_dir = os.path.join(home_dir, "Downloads")
            # Create the directory if it doesn't exist.
            if not os.path.exists(save_dir):
                os.makedirs(save_dir)
            # Create a filename and define the full path of the directory on the user's computer.
            filename = "probability_graph.pdf"
            full_path = os.path.join(save_dir, filename)

            # This pulls the data from the first HTML form to prepare for the graph generation.
            sim_quantity = form.cleaned_data["sim_quantity"]
            min_val = form.cleaned_data["min_val"]
            max_val = form.cleaned_data["max_val"]
            target_val = form.cleaned_data["target_val"]

            # Generate random data for the first simulation.
            sim_result = np.random.uniform(min_val, max_val, sim_quantity)

            # Check for a second simulation.
            second_sim_quantity = form.cleaned_data["second_sim_quantity"]

            # Begin second data range, if there is one.
            if form.cleaned_data["second_sim_quantity"] is not None:
                second_min_val = form.cleaned_data["second_min_val"]
                second_max_val = form.cleaned_data["second_max_val"]
                second_target_val = form.cleaned_data["second_target_val"]

                # Generate data for the second range.
                second_sim_result = np.random.uniform(
                    second_min_val, second_max_val, second_sim_quantity
                )

                # Create the visual graph.
                plt.figure()
                plt.hist(sim_result, density=True, edgecolor="white")
                plt.axvline(target_val, color="r")
                if second_target_val != None:
                    plt.hist(
                        second_sim_result, density=True, edgecolor="white", alpha=0.5
                    )
                    plt.axvline(second_target_val, color="b")
                else:
                    plt.hist(
                        second_sim_result, density=True, edgecolor="white", alpha=0.5
                    )
                plt.savefig(full_path, format="pdf")

                # Generate a response with the generated PDF.
                with open(full_path, "rb") as f:
                    response = HttpResponse(f.read(), content_type="pdf")
                    response["Content-Disposition"] = (
                        'attachment; filename="probability_graph.pdf"'
                    )
                    return response
            # Handle the case where there is only one simulation.
            elif form.cleaned_data["second_sim_quantity"] is None:
                plt.figure()
                plt.hist(sim_result, density=True, edgecolor="white")
                plt.axvline(target_val, color="r")
                plt.savefig(full_path, format="pdf")

                # Generate a response with the generated PDF.
                with open(full_path, "rb") as f:
                    response = HttpResponse(f.read(), content_type="pdf")
                    response["Content-Disposition"] = (
                        'attachment; filename="probability_graph.pdf"'
                    )
                    return response

    # Create an empty form for GET request.
    else:
        form = MonteCarloForm()

    # Render the Monte Carlo simulator page with the form.
    return render(
        request, "projects/monte_carlo_simulator.html", context={"form": form}
    )


# This is the code for the Weather Forecast app.
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def weather(request):
    # Initialize the weather form, allowing for POST or None (for GET requests).
    form = WeatherForm(request.POST or None)

    # Retrieve the zip code from the POST request, if present.
    if request.method == "POST":
        zip_code = request.POST["zip_code"]

    # If the form is valid, process the form data and render the weather forecast.
    if form.is_valid():
        # Obtain the coordinates for the given zip code.
        coordinates = get_coordinates(zip_code)
        # Handle cases where coordinates cannot be found.
        if coordinates == None:
            context = {
                "form": form,
                "error_message": "The ZIP code you entered is valid, but the server was unable to find coordinates for it.  This is a Google Maps Platform API error and not a problem with my code.",
            }
            return render(request, "projects/weather.html", context)
        else:
            # Retrieve city and state names based on the zip code.
            city_name, state_name = get_city_and_state(zip_code)
            latitude, longitude = coordinates
        # API key for accessing the weather information.
        API_KEY_WEATHER = "7e805bf42d5f1713e20456904be7155c"
        # Construct the API URL with coordinates and API key.
        API_URL = f"https://api.openweathermap.org/data/3.0/onecall?lat={latitude}&lon={longitude}&appid={API_KEY_WEATHER}&units=imperial"
        # Send a GET request to the weather API.
        response = requests.get(API_URL)
        data = json.loads(response.content)
        # Parse and extract current weather information.
        icon_code_current = data["current"]["weather"][0]["icon"]
        icon_url_current = f"https://openweathermap.org/img/wn/{icon_code_current}.png"
        current_weather = data["current"]
        day = data["daily"]
        current_weather_report = []
        current_weather_report.append(
            {
                "icon_url_current": icon_url_current,
                "current_temperature": int(current_weather["temp"]),
                "current_description": data["current"]["weather"][0]["description"],
                "current_humidity": current_weather.get("humidity", "N/A"),
                "current_rain": current_weather.get("rain", "No Rain"),
                "current_snow": current_weather.get("snow", "No Snow"),
                "current_wind_gust": current_weather.get("wind_gust", "N/A"),
                "current_wind_speed": current_weather.get("wind_speed", "N/A"),
                "current_wind_direction": current_weather.get("wind_deg", "N/A"),
                "current_cloud": current_weather.get("clouds", "N/A"),
                "current_uv": current_weather.get("uvi", "N/A"),
                "current_dew": int(current_weather["dew_point"]),
                # Temporarily commenting out current visibility because an API error is causing a server error.
                # "current_visibility": int((current_weather["visibility"]) * 0.00062137),
                "current_sunrise": datetime.datetime.fromtimestamp(
                    current_weather["sunrise"]
                ),
                "current_sunset": datetime.datetime.fromtimestamp(
                    current_weather["sunset"]
                ),
            }
        )
        # Parse and extract daily weather forecast information.
        daily_forecast = []
        for day in data["daily"]:
            daily_forecast.append(
                {
                    "day_of_week": datetime.datetime.fromtimestamp(day["dt"]).strftime(
                        "%A"
                    ),
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
                    "summary": day["summary"],
                    "sunrise": datetime.datetime.fromtimestamp(day["sunrise"]),
                    "sunset": datetime.datetime.fromtimestamp(day["sunset"]),
                    "dew_point": day["dew_point"],
                    "humidity": day["humidity"],
                    "precipitation_chance": round(day["pop"] * 100),
                }
            )

        # Prepare context with weather and location data for rendering.
        context = {
            "form": form,
            "daily_forecast": daily_forecast,
            "city_name": city_name,
            "state_name": state_name,
            "current_weather_report": current_weather_report,
        }
        # Render the page with weather results.
        return render(request, "projects/weather.html", context)

    # If the form is not valid or it's a GET request, render the form again.
    else:
        context = {
            "form": form,
        }
        return render(request, "projects/weather.html", context)


# This is the code for the page containing information on all of my projects.
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def all_projects(request):
    return render(request, "projects/all_projects.html")


# This is the code for the DNS Lookup Tool app.
# Decorator to set cache control headers to prevent caching of the page
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def dns_tool(request):
    # Initialize an empty dictionary to store DNS results
    results = {}
    # Initialize error message as None
    error_message = None
    # Create an instance of the DomainForm
    form = DomainForm()

    # Check if the request method is POST
    if request.method == "POST":
        # Populate form with POST data
        form = DomainForm(request.POST)
        # Validate the form input
        if form.is_valid():
            # Retrieve the cleaned domain name
            domain = form.cleaned_data["domain"]
            # List of DNS record types to query
            record_types = [
                "A",
                "AAAA",
                "MX",
                "NS",
                "CNAME",
                "TXT",
                "SOA",
                "SRV",
                "CAA",
            ]

            # Loop through each record type to perform DNS queries
            for record_type in record_types:
                try:
                    # Resolve the DNS records for the given domain and record type
                    answers = dns.resolver.resolve(domain, record_type)
                    # Store the results in the dictionary with the record type as key
                    results[record_type] = [r.to_text() for r in answers]
                except dns.resolver.NoAnswer:
                    # Handle cases where no records are found for the given type
                    results[record_type] = ["No records found"]
                except dns.resolver.NXDOMAIN:
                    # Handle cases where the domain does not exist
                    results[record_type] = ["Domain does not exist"]
                except dns.resolver.Timeout:
                    # Handle cases where the DNS query times out
                    results[record_type] = ["DNS query timed out"]
                except Exception as e:
                    # Handle any other exceptions that may occur
                    results[record_type] = [
                        f"Error retrieving {record_type} records: {str(e)}"
                    ]
                    # Set a general error message for unexpected errors
                    error_message = (
                        "An unexpected error occurred while retrieving DNS records."
                    )

    # Render the template with form, results, and error message
    response = render(
        request,
        "projects/dns_tool.html",
        {"form": form, "results": results, "error_message": error_message},
    )

    # Sets additional anti-caching headers directly on the response object
    response["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response["Pragma"] = "no-cache"
    response["Expires"] = "0"

    # Return the HTTP response
    return response


# This is the code for the IP Address Lookup Tool app.
# Decorator to set cache control headers to prevent caching of the page
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def ip_tool(request):
    # Initialize an empty dictionary to store results
    results = {}
    # Initialize error message as None
    error_message = None
    # Create an instance of the IPForm

    form = IPForm()

    # Check if the request method is POST
    if request.method == "POST":
        # Populate form with POST data
        form = IPForm(request.POST)
        # Validate the form input
        if form.is_valid():
            # Retrieve the cleaned IP address
            ip_address = form.cleaned_data["ip_address"]
            # PTR Record Lookup
            try:
                # Perform reverse DNS lookup to find PTR records
                rev_name = dns.reversename.from_address(ip_address)
                # Resolve PTR records for the reverse name
                ptr_records = dns.resolver.resolve(rev_name, "PTR")
                # Store PTR records in the results dictionary
                results["PTR"] = [r.to_text() for r in ptr_records]
            except Exception as e:
                # Handle any exceptions during PTR lookup
                results["PTR"] = [f"Error retrieving PTR records: {str(e)}"]
                # error_message = "An error occurred while retrieving PTR records."

            # Geolocation and ISP Information (Example using ip-api.com)
            try:
                # Make a request to the IP geolocation API
                response = requests.get(f"http://ip-api.com/json/{ip_address}")
                # Parse the response as JSON
                geo_data = response.json()
                if geo_data["status"] == "success":
                    # If the API request is successful, store geolocation data in the results dictionary
                    results["Geolocation"] = {
                        "Country": geo_data.get("country"),
                        "Region": geo_data.get("regionName"),
                        "City": geo_data.get("city"),
                        "Latitude": geo_data.get("lat"),
                        "Longitude": geo_data.get("lon"),
                        "ISP": geo_data.get("isp"),
                        "Organization": geo_data.get("org"),
                        "AS": geo_data.get("as"),
                    }
                else:
                    # Handle failure to retrieve geolocation data
                    results["Geolocation"] = ["Failed to retrieve geolocation data."]
            except Exception as e:
                # Handle any exceptions during geolocation lookup
                results["Geolocation"] = [
                    f"Error retrieving geolocation data: {str(e)}"
                ]

            # Blacklist Check (Example using DNS-based blacklist lookup)
            try:
                # Reverse the IP address to check against DNS-based blacklists
                reversed_ip = ".".join(reversed(ip_address.split(".")))
                # List of DNS blacklist servers
                blacklist_servers = ["zen.spamhaus.org", "bl.spamcop.net"]
                # Initialize a list to store blacklist check results
                blacklist_results = []
                for server in blacklist_servers:
                    # Formulate the query for the blacklist server
                    query = f"{reversed_ip}.{server}"
                    try:
                        # Perform DNS resolution for the blacklist query
                        dns.resolver.resolve(query, "A")
                        # If successful, IP is listed on the blacklist server
                        blacklist_results.append(f"Listed on {server}")
                    except dns.resolver.NXDOMAIN:
                        # If NXDOMAIN, IP is not listed on the blacklist server
                        blacklist_results.append(f"Not listed on {server}")
                    except Exception as e:
                        # Handle any exceptions during blacklist checking
                        blacklist_results.append(f"Error checking {server}: {str(e)}")
                # Store blacklist results in the results dictionary
                results["Blacklist"] = blacklist_results
            except Exception as e:
                # Handle any exceptions during the overall blacklist checking process
                results["Blacklist"] = [f"Error checking blacklists: {str(e)}"]

    # Render the template with form, results, and error message
    response = render(
        request,
        "projects/ip_tool.html",
        {"form": form, "results": results, "error_message": error_message},
    )

    # Sets additional anti-caching headers directly on the response object
    response["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response["Pragma"] = "no-cache"
    response["Expires"] = "0"

    # Return the HTTP response
    return response


# This is the code for the SSL Verification Tool app.
# Decorator to set cache control headers to prevent caching of the page
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def ssl_check(request):
    # Initialize the form and result variables
    form = SSLCheckForm()
    result = None
    url = None

    # Check if the request method is POST
    if request.method == "POST":
        # Bind the form with POST data
        form = SSLCheckForm(request.POST)
        # Validate the form
        if form.is_valid():
            # Extract the URL from the form data
            url = form.cleaned_data["url"]
            # Verify the SSL certificate for the given URL
            result = verify_ssl(url)

    # Render the template with form, results, and error message
    response = render(
        request,
        "projects/ssl_check.html",
        {"form": form, "result": result, "url": url},
    )
    # Sets additional anti-caching headers directly on the response object
    response["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response["Pragma"] = "no-cache"
    response["Expires"] = "0"

    # Return the HTTP response
    return response


# This is the view for the IT Tools page.
# Decorator to set cache control headers to prevent caching of the page
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def it_tools(request):
    return render(request, "projects/it_tools.html")
