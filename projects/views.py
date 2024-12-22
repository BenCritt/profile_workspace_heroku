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
import requests

# Used for parsing and generating JSON data, such as handling request bodies or responses in AJAX calls.
import json

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
    # process_sitemap_with_timeout: Handles sitemap processing in the SEO Head Checker with a timeout.
    process_sitemap_with_timeout,
    # process_single_url: Processes individual URLs for SEO analysis.
    process_single_url,
)

# Generates unique task IDs for tracking background tasks, such as sitemap processing in the SEO Head Checker.
import uuid

# Writes results to CSV files, such as SEO analysis reports in the SEO Head Checker.
import csv

# Runs background tasks in parallel to the main thread, such as sitemap processing in the SEO Head Checker.
from threading import Thread

# Validates and parses URLs (e.g., normalizing sitemap URLs in the SEO Head Checker).
from urllib.parse import urlparse

# Parses XML/HTML content, such as extracting <loc> tags from sitemaps in the SEO Head Checker.
from bs4 import BeautifulSoup

# Dictionary to store task statuses. In production, use a persistent database.
from django.core.cache import cache


def normalize_url(url):
    """
    Normalize a URL by adding missing schemes (e.g., https://) or handling naked domains.
    I have code in forms.py that should be doing this, but it doesn't work.

    Args:
        url (str): The input URL.

    Returns:
        str: The normalized URL in a valid format.
    """
    if not url.startswith(("http://", "https://")):
        # Prepend https:// if missing.
        url = f"https://{url}"
    return url


def start_sitemap_processing(request):
    """
    Handles sitemap processing requests, manages task lifecycle, and starts background processing.

    Args:
        request: Django HTTP request.
    Returns:
        JsonResponse: Status of the request or task.
    """
    if request.method == "POST":
        try:
            # Parse JSON body to extract the sitemap URL.
            data = json.loads(request.body)
            sitemap_url = data.get("sitemap_url", "").strip()  # Remove extra spaces.
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON input."}, status=400)

        # Check if sitemap URL is provided.
        if not sitemap_url:
            return JsonResponse({"error": "Sitemap URL is required."}, status=400)

        # Normalize the URL.
        sitemap_url = normalize_url(sitemap_url)

        # Validate the normalized URL.
        parsed_url = urlparse(sitemap_url)
        if not parsed_url.scheme or not parsed_url.netloc:
            return JsonResponse({"error": "Invalid Sitemap URL."}, status=400)

        # Generate a unique task ID for tracking.
        task_id = str(uuid.uuid4())
        cache.set(
            task_id, {"status": "pending", "progress": 0}, timeout=60 * 60
        )  # 1 hour timeout

        # Function to process sitemap URLs in the background.
        def process_task(task_id, sitemap_url):
            try:
                # Initialize task progress.
                task = cache.get(task_id)
                if task:
                    task["status"] = "processing"
                    task["progress"] = 0
                    cache.set(task_id, task, timeout=60 * 60)

                # Fetch and parse the sitemap XML to extract URLs.
                response = requests.get(sitemap_url, timeout=10)
                response.raise_for_status()  # Raise an error for HTTP failures.
                soup = BeautifulSoup(response.content, "lxml-xml")
                urls = [
                    loc.text for loc in soup.find_all("loc")
                ]  # Extract all <loc> tags.

                total_urls = len(urls)
                task = cache.get(task_id)
                if task:
                    task["total_urls"] = total_urls
                    cache.set(task_id, task, timeout=60 * 60)

                results = []

                # Process each URL and track progress.
                for i, url in enumerate(urls, start=1):
                    result = process_single_url(
                        url
                    )  # Analyze URL (function defined elsewhere).
                    results.append(result)

                    # Update progress in cache.
                    task = cache.get(task_id)
                    if task:
                        task["progress"] = int(
                            (i / total_urls) * 100
                        )  # Calculate progress.
                        cache.set(task_id, task, timeout=60 * 60)

                # Write results to a file.
                output_file = f"seo_report_{task_id}.csv"
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
                    writer.writeheader()
                    writer.writerows(results)

                # Mark task as completed and save file path.
                task = cache.get(task_id)
                if task:
                    task["status"] = "completed"
                    task["file"] = output_file
                    cache.set(task_id, task, timeout=60 * 60)

            except Exception as e:
                # Mark task as failed and log the error.
                task = cache.get(task_id)
                if task:
                    task["status"] = "error"
                    task["error"] = str(e)
                    cache.set(task_id, task, timeout=60 * 60)

        # Start the background thread for processing.
        Thread(target=process_task, args=(task_id, sitemap_url)).start()

        # Return the task ID to the client for tracking.
        return JsonResponse({"task_id": task_id}, status=202)

    # Return an error if the request method is not POST.
    return JsonResponse({"error": "Invalid request method."}, status=405)


def get_task_status(request, task_id):
    """
    Returns the current status of a task.

    Args:
        request: Django HTTP request.
        task_id (str): Unique task ID.
    Returns:
        JsonResponse: Task status or error if task not found.
    """
    task = cache.get(task_id)
    if not task:
        return JsonResponse({"error": "Task not found."}, status=404)
    return JsonResponse(
        {
            "status": task["status"],
            "progress": task.get("progress", 0),  # Only return the percentage
            "error": task.get("error"),
        }
    )


# I don't know why, but I have to have these repeated for download_task_file to run properly.
import os
from django.http import HttpResponse, JsonResponse


def download_task_file(request, task_id):
    """
    Handles file downloads and deletes the file from the server after serving it to the user.

    Args:
        request: Django HTTP request object containing metadata about the request.
        task_id (str): Unique identifier for the task whose file is being downloaded.

    Returns:
        HttpResponse: A response containing the file data for the user to download.
        JsonResponse: An error response if the file is not found, not ready, or if an exception occurs.
    """

    # Retrieve the task details from the TASKS dictionary using the task_id.
    # The TASKS dictionary is assumed to store task statuses and associated file paths.
    task = cache.get(task_id)

    # Check if the task exists and if its status is "completed".
    # If not, return a 404 error indicating that the file is not ready or the task does not exist.
    if not task or task.get("status") != "completed":
        return JsonResponse({"error": "File not ready or task not found."}, status=404)

    # Extract the file path from the task details.
    file_path = task.get("file")

    # Check if the file path exists and if the file is physically present on the server.
    # If not, return a 404 error indicating that the file is missing.
    if not file_path or not os.path.exists(file_path):
        return JsonResponse({"error": "File not found on the server."}, status=404)

    try:
        # Open the file in binary mode ("rb") to prepare it for download.
        with open(file_path, "rb") as file:
            # Create an HTTP response containing the file content.
            response = HttpResponse(file, content_type="application/octet-stream")
            # Add a "Content-Disposition" header to the response to prompt the user to download the file.
            # The filename is extracted from the file path and included in the header.
            response["Content-Disposition"] = (
                f'attachment; filename="{os.path.basename(file_path)}"'
            )

        # Delete the file from the server after successfully serving it to the user.
        # This ensures that temporary files do not accumulate on the server.
        os.remove(file_path)

        # Return the HTTP response to the client, triggering the file download.
        return response
    except Exception as e:
        # Catch any unexpected errors that occur during file handling or response creation.
        # Return a JSON error response with a 500 status code and a description of the error.
        return JsonResponse({"error": f"An error occurred: {str(e)}"}, status=500)


# This is the code for the SEO Head Checker
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def seo_head_checker(request):
    if request.method == "POST":
        # Instantiate the form with the submitted POST data.
        form = SitemapForm(request.POST)

        # Validate the form input.
        if form.is_valid():
            # Extract the cleaned sitemap URL and desired output format from the form.
            sitemap_url = form.cleaned_data["sitemap_url"]
            # User-selected output format.
            # file_type = form.cleaned_data["file_type"]
            # Fix filetype to CSV. Support for Excel coming in the future.
            file_type = "csv"

            try:
                # Call a function to process the sitemap with a hard 5 minute timeout.
                output_file = process_sitemap_with_timeout(sitemap_url, timeout=3000)

                # Serve the generated report file based on the user's selected format.
                # This will eventually work. For now, there is no option for the user to select.
                if file_type == "excel":
                    # If the user selects Excel, use pandas to convert the CSV to Excel format.
                    import pandas as pd

                    # Read the generated CSV file into a pandas DataFrame.
                    df = pd.read_csv(output_file)

                    # Create an HTTP response with the appropriate content type for Excel.
                    response = HttpResponse(
                        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                    # Set the Content-Disposition header to trigger a download with the specified filename.
                    response["Content-Disposition"] = (
                        'attachment; filename="seo_report.xlsx"'
                    )
                    # Write the DataFrame to the response as an Excel file.
                    df.to_excel(response, index=False, engine="openpyxl")
                    return response

                elif file_type == "csv":
                    # If the user selects CSV, serve the file directly as a response.
                    with open(output_file, "r", encoding="utf-8") as csv_file:
                        response = HttpResponse(csv_file, content_type="text/csv")
                        # Set the Content-Disposition header for downloading the CSV.
                        response["Content-Disposition"] = (
                            'attachment; filename="seo_report.csv"'
                        )
                        return response

            except ValueError as e:
                # Handle errors during sitemap processing, such as timeouts or invalid input.
                # Render the form page with the error message displayed to the user.
                return render(
                    request,
                    "projects/seo_head_checker.html",
                    {"error": str(e), "form": form},
                )
    else:
        # If the request is not a POST request (e.g., GET), display the empty form to the user.
        form = SitemapForm()

    # Render the HTML template with the form (and any error messages, if present.)
    return render(request, "projects/seo_head_checker.html", {"form": form})


# This is code for generating favicons on Android devices.
# This dynamically creates a web.manifest JSON file, similar to how my sitemap is dynamically generated.
def manifest(request):
    manifest_json = {
        "short_name": "BenCritt",
        "name": "Ben Crittenden's PWA",
        "icons": [
            {
                "src": "https://i.imgur.com/o7ZaHGO.png",
                "sizes": "192x192",
                "type": "image/png",
            },
            {
                "src": "https://i.imgur.com/TEf3wAa.png",
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
def view_404(request, exception):
    # If the request is for a static file (including the service worker)
    if (
        request.path.startswith(settings.STATIC_URL)
        or request.path == "/service-worker.js"
    ):
        # Return the default 404 response for static files
        return HttpResponseNotFound("File not found")

    # Otherwise, redirect to the homepage
    return redirect("/")


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
                "current_visibility": int((current_weather["visibility"]) * 0.00062137),
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
                    # "precipitation_chance": day["pop"],
                    "precipitation_chance": round(day["pop"] * 100),
                }
            )

        # Prepare context with weather and location data for rendering.
        context = {
            "daily_forecast": daily_forecast,
            "city_name": city_name,
            "state_name": state_name,
            "current_weather_report": current_weather_report,
        }
        # Render the page with weather results.
        return render(request, "projects/weather_results.html", context)

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
