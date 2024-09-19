from django.shortcuts import render, redirect
from .forms import (
    QRForm,
    MonteCarloForm,
    WeatherForm,
    TextForm,
    IPForm,
    DomainForm,
    SSLCheckForm,
)
import os
import qrcode
from django.http import HttpResponse, JsonResponse
import requests
import json
import datetime
import numpy as np
import matplotlib.pyplot as plt
from django.conf import settings
import textstat
import dns.resolver
import dns.reversename
from django.views.decorators.cache import cache_control
from .utils import verify_ssl, get_coordinates, get_city_and_state


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
                error_message = "An error occurred while retrieving PTR records."

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
