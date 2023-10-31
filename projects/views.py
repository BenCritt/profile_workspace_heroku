from django.shortcuts import render
from .forms import QRForm
import os
import qrcode
from django.http import HttpResponse
from .forms import WeatherForm
import requests
import json
import datetime
from pyzipcode import ZipCodeDatabase
import numpy as np
import matplotlib.pyplot as plt
from .forms import MonteCarloForm


def home(request):
    return render(request, "projects/home.html")


def resume(request):
    return render(request, "projects/resume.html")


def qr_code_generator(request):
    if request.method == "POST":
        form = QRForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data["qr_text"]
            qr = qrcode.QRCode(version=1, box_size=10, border=5)
            qr.add_data(data)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")
            home_dir = os.path.expanduser("~")
            save_dir = os.path.join(home_dir, "Downloads")
            if not os.path.exists(save_dir):
                os.makedirs(save_dir)
            filename = "qrcode.png"
            full_path = os.path.join(save_dir, filename)
            img.save(full_path)

            with open(full_path, "rb") as f:
                response = HttpResponse(f.read(), content_type="image/png")
                response["Content-Disposition"] = 'attachment; filename="qrcode.png"'
                return response
    else:
        form = QRForm
    return render(request, "projects/qr_code_generator.html", context={"form": form})


def contact(request):
    return render(request, "projects/contact.html")


def monte_carlo_simulator(request):
    if request.method == "POST":
        form = MonteCarloForm(request.POST)
        if form.is_valid():
            # This determines where to save the PDF file that will eventually be created.
            home_dir = os.path.expanduser("~")
            save_dir = os.path.join(home_dir, "Downloads")
            if not os.path.exists(save_dir):
                os.makedirs(save_dir)
            filename = "probability_graph.pdf"
            full_path = os.path.join(save_dir, filename)

            # This pulls the data from the HTML to prepare for the graph generation.
            sim_quantity = form.cleaned_data["sim_quantity"]
            min_val = form.cleaned_data["min_val"]
            max_val = form.cleaned_data["max_val"]
            target_val = form.cleaned_data["target_val"]

            sim_result = np.random.uniform(min_val, max_val, sim_quantity)
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

                with open(full_path, "rb") as f:
                    response = HttpResponse(f.read(), content_type="pdf")
                    response[
                        "Content-Disposition"
                    ] = 'attachment; filename="probability_graph.pdf"'
                    return response

            elif form.cleaned_data["second_sim_quantity"] is None:
                plt.figure()
                plt.hist(sim_result, density=True, edgecolor="white")
                plt.axvline(target_val, color="r")
                plt.savefig(full_path, format="pdf")

                with open(full_path, "rb") as f:
                    response = HttpResponse(f.read(), content_type="pdf")
                    response[
                        "Content-Disposition"
                    ] = 'attachment; filename="probability_graph.pdf"'
                    return response

    else:
        form = MonteCarloForm()

    return render(
        request, "projects/monte_carlo_simulator.html", context={"form": form}
    )


def get_coordinates(zip_code):
    API_KEY_LOCATION = "AIzaSyDgTeYWJgkaaINk79nGU3zCMbqCGTiqwNk"
    API_URL = f"https://maps.googleapis.com/maps/api/geocode/json?address={zip_code}&key={API_KEY_LOCATION}"
    response = requests.get(API_URL)
    data = json.loads(response.content)
    if response.status_code == 200 and data["status"] == "OK":
        location = data["results"][0]["geometry"]["location"]
        return location["lat"], location["lng"]
    else:
        return None


def get_city_and_state(zip_code):
    API_KEY_CITY = "AIzaSyDgTeYWJgkaaINk79nGU3zCMbqCGTiqwNk"
    url = f"https://maps.googleapis.com/maps/api/geocode/json?address={zip_code}&key={API_KEY_CITY}"
    response = requests.get(url)
    data = json.loads(response.content)
    if response.status_code == 200 and data["status"] == "OK":
        city_name = data["results"][0]["address_components"][1]["long_name"]
        state_name = data["results"][0]["address_components"][3]["long_name"]
        return city_name, state_name
    else:
        return None


zdb = ZipCodeDatabase()


def weather(request):
    # Create a new form instance.
    form = WeatherForm(request.POST or None)

    # Get the coordinates, even if the form is not valid.
    if request.method == "POST":
        zip_code = request.POST["zip_code"]

    # If the form is valid, process the form data and render the weather forecast.
    if form.is_valid():
        coordinates = get_coordinates(zip_code)
        if coordinates == None:
            context = {
                "form": form,
                "error_message": "The ZIP code you entered is valid, but the server was unable to find coordinates for it.  This is a Google Maps Platform API error and not a problem with my code.",
            }
            return render(request, "projects/weather.html", context)
        else:
            city_name, state_name = get_city_and_state(zip_code)
            latitude, longitude = coordinates
        API_KEY_WEATHER = "7e805bf42d5f1713e20456904be7155c"
        API_URL = f"https://api.openweathermap.org/data/3.0/onecall?lat={latitude}&lon={longitude}&appid={API_KEY_WEATHER}&units=imperial"
        response = requests.get(API_URL)
        data = json.loads(response.content)
        icon_code_current = data["current"]["weather"][0]["icon"]
        icon_url_current = f"https://openweathermap.org/img/wn/{icon_code_current}.png"
        """
        # I can currently only get icons working with current weather.
        # This fix will be on my to-do list.
        icon_codes_daily = []
        for day in data["daily"]:
            icon_codes_daily.append(day["weather"][0]["icon"])
        icon_url_daily = f"https://openweathermap.org/img/wn/{icon_codes_daily}.png"
        """
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
        """
        # I want to eventually add a Moon phase feature.
        # I can do this by reporting phase numbers.
        # I want to report descriptive strings instead of numbers.
        # This will take some time.
        # I will likely devote this feature to it's own app, since it's outside the scope of "weather."
        moon_phase = data["daily"][0]["moon_phase"]

        if moon_phase == 1 or moon_phase == 0:
            moon_phase = "New Moon"
        elif moon_phase == 0.25:
            moon_phase = "First Quarter Moon"
        elif moon_phase == 0.50:
            moon_phase = "Full Moon"
        elif moon_phase == 0.75:
            moon_phase = "Last Quarter Moon"
        elif moon_phase < 0.25:
            moon_phase = "Waxing Crescent Moon"
        elif 0.25 < moon_phase < 0.5:
            moon_phase = "Waxing Gibbous Moon"
        elif 0.5 < moon_phase < 0.75:
            moon_phase = "Waning Gibbous Moon"
        elif 0.75 < moon_phase < 1:
            moon_phase = "Waning Crescent Moon"
        """
        daily_forecast = []
        for day in data["daily"]:
            daily_forecast.append(
                {
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
                    "precipitation_chance": day["pop"],
                    # "icon_url_daily": icon_url_daily,
                    # "moon:phase": moon_phase,
                    # "moon_phase": day["moon_phase"],
                    # "moonrise": datetime.datetime.fromtimestamp(day["moonrise"]),
                    # "moonset": datetime.datetime.fromtimestamp(day["moonset"]),
                }
            )

        context = {
            "daily_forecast": daily_forecast,
            "city_name": city_name,
            "state_name": state_name,
            "current_weather_report": current_weather_report,
        }

        return render(request, "projects/weather_results.html", context)

    # If the form is not valid, render the form again.
    else:
        context = {
            "form": form,
        }
        return render(request, "projects/weather.html", context)
