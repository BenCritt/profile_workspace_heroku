from django.shortcuts import render
from django.http import HttpResponse, JsonResponse, HttpResponseNotFound, FileResponse, HttpRequest
from django.conf import settings
from django.views.decorators.cache import cache_control
from django.views.decorators.http import require_POST, require_GET
from django.views.decorators.csrf import ensure_csrf_cookie
from django.urls import reverse
from .decorators import trim_memory_after
import os
import requests


# Cookie Audit
@trim_memory_after
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
@require_GET
def cookie_audit_view(request):
    from .forms import CookieAuditForm
    from . import cookie_scan_utils
    """
    Renders a clean page (URL input only). No session-stored task_id.
    Results/progress are driven entirely by JS calling start/status/results endpoints.
    """
    form = CookieAuditForm()
    # If your form still has extra fields, make them optional so user submits URL only.
    for field_name in (
        "max_pages",
        "max_depth",
        "wait_ms",
        "timeout_ms",
        "headless",
        "ignore_https_errors",
    ):
        if field_name in form.fields:
            form.fields[field_name].required = False

    ctx = {"form": form}
    return render(request, "projects/cookie_audit.html", ctx)

@trim_memory_after
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
@require_POST
def cookie_audit_start(request):
    # Maintenance Mode pending hosting migration.
    return JsonResponse(
        {"error": "This tool is temporarily suspended."}, 
        status=503
    )
    from .forms import CookieAuditForm
    from . import cookie_scan_utils

    """
    Starts a scan and returns immediately with a task id (JSON).
    Does NOT store task_id in session (prevents tab/user overwrite).
    """
    form = CookieAuditForm(request.POST)
    for field_name in (
        "max_pages",
        "max_depth",
        "wait_ms",
        "timeout_ms",
        "headless",
        "ignore_https_errors",
    ):
        if field_name in form.fields:
            form.fields[field_name].required = False

    if not form.is_valid():
        return JsonResponse(
            {"error": "Please enter a valid website URL.", "form_errors": form.errors},
            status=400,
        )

    url = form.cleaned_data["url"]
    task_id = cookie_scan_utils.start_cookie_audit_task(url)

    return JsonResponse(
        {
            "task_id": task_id,
            "status_url": reverse("projects:cookie_audit_status", args=[task_id]),
            "results_url": reverse("projects:cookie_audit_results", args=[task_id]),
            "download_url": reverse("projects:cookie_audit_download", args=[task_id]),
        }
    )

@trim_memory_after
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
@require_GET
def cookie_audit_status(request, task_id):
    from .forms import CookieAuditForm
    from . import cookie_scan_utils
    """
    Polling endpoint for progress/status.
    Always returns JSON (even on server-side errors) so the frontend never crashes
    trying to parse HTML as JSON.
    """
    try:
        task = cookie_scan_utils.get_cookie_audit_task(str(task_id))

        if not task:
            return JsonResponse({"state": "unknown"}, status=404)

        if not isinstance(task, dict):
            # Defensive: if cache ever returns something unexpected
            return JsonResponse(
                {"state": "error", "error": "Task data corrupted (non-dict)."},
                status=500,
            )

        payload = {
            "state": task.get("state", "unknown"),
            "progress": task.get("progress") or {},
        }

        if payload["state"] == "error":
            payload["error"] = task.get("error") or "Unknown error"

        # Include queue position if present (useful for UI)
        if "queue_position" in task:
            payload["queue_position"] = task.get("queue_position")

        return JsonResponse(payload)

    except Exception as exc:
        # IMPORTANT: still return JSON
        return JsonResponse(
            {"state": "error", "error": f"{type(exc).__name__}: {exc}"},
            status=500,
        )

@trim_memory_after
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
@require_GET
def cookie_audit_results(request, task_id):
    from . import cookie_scan_utils

    """
    Returns results JSON once done. JS calls this after status says 'done'.
    Defensive: always returns JSON, even if task data is corrupted or an exception occurs.

    IMPORTANT:
    We do NOT pop/remove results here because the CSV download endpoint needs them.
    """
    try:
        task = cookie_scan_utils.get_cookie_audit_task(str(task_id))

        if not task:
            return JsonResponse({"state": "unknown"}, status=404)

        if not isinstance(task, dict):
            return JsonResponse(
                {"state": "error", "error": "Task data corrupted (non-dict)."},
                status=500,
            )

        state = task.get("state", "unknown")
        payload = {"state": state}

        if state == "done":
            payload["results"] = task.get("results") or {}

        elif state == "error":
            payload["error"] = task.get("error") or "Unknown error"

        else:
            payload["progress"] = task.get("progress") or {}
            payload["queue_position"] = task.get("queue_position", None)

        return JsonResponse(payload)

    except Exception as exc:
        return JsonResponse(
            {"state": "error", "error": f"{type(exc).__name__}: {exc}"},
            status=500,
        )
@trim_memory_after
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
@require_GET
def cookie_audit_download(request, task_id):
    import os
    import time
    from . import cookie_scan_utils
    from . import csv_utils

    # Best-effort cleanup of stale exports (30 min)
    csv_utils.cleanup_old_files(export_subdir="cookie_audit", max_age_seconds=30 * 60)

    task_id_str = str(task_id)
    task = cookie_scan_utils.get_cookie_audit_task(task_id_str)
    if not task or not isinstance(task, dict):
        return HttpResponseNotFound("Task not found.")

    if task.get("state") != "done":
        return HttpResponseNotFound("Results not ready yet.")

    csv_meta = task.get("csv") or {}
    path = (csv_meta.get("path") or "").strip()
    filename = (csv_meta.get("filename") or "cookie_audit.csv").strip()
    created_at = float(csv_meta.get("created_at") or 0.0)

    # Expire after 30 minutes even if never downloaded
    if created_at and (time.time() - created_at) >= 30 * 60:
        # If it's expired, delete it and behave like it doesn't exist
        try:
            if path:
                os.remove(path)
        except Exception:
            pass
        path = ""

    if not path or not os.path.exists(path):
        return HttpResponseNotFound("CSV file expired or missing. Please run the scan again.")

    # IMPORTANT: mark it as consumed so it can't be downloaded multiple times
    task["csv"] = None
    task["csv_downloaded_at"] = time.time()
    cookie_scan_utils.set_cookie_audit_task(task_id_str, task)

    return csv_utils.file_response_with_cleanup(
        path=path,
        download_filename=filename,
        content_type="text/csv",
    )

# Font Inspector
# Disallow caching to prevent CSRF token errors.
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def font_inspector(request):
    from .forms import FontInspectorForm
    form = FontInspectorForm()
    return render(request, "projects/font_inspector.html", {"form": form})

# Ham Radio Call Sign Lookup
# Force memory trim after work.
@trim_memory_after
# Disallow caching to prevent CSRF token errors.
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def ham_radio_call_sign_lookup(request):
    from .ham_utils import query_callook, query_hamdb
    from .forms import CallsignLookupForm
    data = None
    error = None
    form = CallsignLookupForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        cs = form.cleaned_data["callsign"]
        try:
            # Callook first
            payload = query_callook(cs)

            if payload.get("status") == "VALID":
                data = payload
            else:
                # Fallback to HamDB
                alt = query_hamdb(cs)
                if alt.get("messages", {}).get("status") != "NOT_FOUND":
                    data = alt
                else:
                    error = f"“{cs}” is not a valid amateur-radio call sign."
        except (requests.Timeout, requests.ConnectionError) as e:
            error = f"Lookup service error: {e}"
    return render(request, "projects/ham_radio_call_sign_lookup.html", {"form": form, "data": data, "error": error})

# XML Splitter
# Force memory trim after work.
@trim_memory_after
# Disallow caching to prevent CSRF token errors.
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def xml_splitter(request):
    from .forms import XMLUploadForm
    from .xml_splitter_utils import split_xml_to_zip
    from django.http import StreamingHttpResponse
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
# Force memory trim after work.
@trim_memory_after
# Disallow caching to prevent CSRF token errors.
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def iss_tracker(request):
    """
    Track ISS and show current location + next visible events.
    Memory-optimized: lazy heavy imports, lite TZ finder, cleanup.
    """
    from .iss_utils import detect_region
    from .utils import get_coordinates
    from django.core.cache import cache
    from datetime import timedelta
    from .forms import WeatherForm

    form = WeatherForm(request.POST or None)
    current_data = {}
    iss_pass_times = []

    if request.method == "POST" and form.is_valid():
        # --- heavy imports only when needed ---
        from zoneinfo import ZoneInfo
        from timezonefinder import TimezoneFinder
        from skyfield.api import load, Topos  # (Topos is fine; could also use wgs84.latlon)
        from skyfield.sgp4lib import EarthSatellite
        import requests, gc, ctypes

        zip_code = form.cleaned_data["zip_code"]
        coords = get_coordinates(zip_code)
        if not coords:
            return render(request, "projects/iss_tracker.html",
                          {"form": form, "error": "Could not determine coordinates."})

        lat, lon = coords

        # --- cache TLE text (1 hour) ---
        def _fetch_tle_text():
            r = requests.get("https://celestrak.org/NORAD/elements/stations.txt", timeout=10)
            r.raise_for_status()
            return r.text

        tle_text = cache.get_or_set("tle_data_text", _fetch_tle_text, 3600)

        # --- parse ISS (ZARYA) lines without holding extra structures ---
        line1 = line2 = None
        lines = tle_text.splitlines()
        for i, line in enumerate(lines):
            if line.strip() == "ISS (ZARYA)":
                line1, line2 = lines[i + 1], lines[i + 2]
                break
        if not line1 or not line2:
            return render(request, "projects/iss_tracker.html",
                          {"form": form, "error": "ISS TLE not found."})

        ts = load.timescale()
        satellite = EarthSatellite(line1, line2, "ISS (ZARYA)", ts)
        observer = Topos(latitude_degrees=lat, longitude_degrees=lon)

        now = ts.now()
        end_time = ts.utc(now.utc_datetime() + timedelta(days=1))

        times, events = satellite.find_events(observer, now, end_time, altitude_degrees=10.0)

        geocentric = satellite.at(now)
        subpoint = geocentric.subpoint()
        v = geocentric.velocity.km_per_s
        speed = (v[0]*v[0] + v[1]*v[1] + v[2]*v[2]) ** 0.5

        region = detect_region(subpoint.latitude.degrees, subpoint.longitude.degrees)

        current_data = {
            "latitude": f"{subpoint.latitude.degrees:.2f}°",
            "longitude": f"{subpoint.longitude.degrees:.2f}°",
            "altitude": f"{subpoint.elevation.km:.2f} km",
            "velocity": f"{speed:.2f} km/s",
            "region": region,
        }

        # Lite mode keeps shapefiles off-heap and on disk
        tf = TimezoneFinder(in_memory=False)
        tzname = tf.timezone_at(lat=lat, lng=lon) or "UTC"
        local_tz = ZoneInfo(tzname)

        for t, event in zip(times, events):
            name = ("Rise", "Culminate", "Set")[event]
            local_time = t.utc_datetime().astimezone(local_tz)
            iss_pass_times.append({
                "event": name,
                "date": local_time.strftime("%A, %B %d"),
                "time": local_time.strftime("%I:%M %p %Z"),
                "position": ("North" if satellite.at(t).subpoint().latitude.degrees > lat else "South"),
            })

        # --- cleanup to actually return memory to the OS ---
        try:
            del satellite, geocentric, subpoint, lines, tle_text, ts, tf
        except Exception:
            pass
        try:
            gc.collect()
            ctypes.CDLL("libc.so.6").malloc_trim(0)
        except Exception:
            pass

        return render(request, "projects/iss_tracker.html",
                      {"form": form, "current_data": current_data, "iss_pass_times": iss_pass_times})

    # GET: render empty form without loading heavy libs
    return render(request, "projects/iss_tracker.html", {"form": form, "current_data": current_data})


# SEO Head Checker
# Force memory trim after work.
@trim_memory_after
# Disallow caching to prevent CSRF token errors.
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def seo_head_checker(request):
    from .forms import SitemapForm
    return render(request, "projects/seo_head_checker.html", {"form": SitemapForm()})

# ---- Forwarders to the robust utils implementations ----
from .seo_head_checker_utils import (
    start_sitemap_processing as _start_sitemap_processing,
    get_task_status as _get_task_status,
    download_task_file as _download_task_file,
)

@require_POST
# Force memory trim after work.
@trim_memory_after
# Disallow caching to prevent CSRF token errors.
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def start_sitemap_processing(request):
    return _start_sitemap_processing(request=request)

# Force memory trim after work.
@trim_memory_after
# Disallow caching to prevent CSRF token errors.
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def get_task_status(request, task_id):
    return _get_task_status(request, task_id)

# Force memory trim after work.
@trim_memory_after
# Disallow caching to prevent CSRF token errors.
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def download_task_file(request, task_id):
    return _download_task_file(request, task_id)

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

# Grade Level Text Analyzer
# Force memory trim after work.
@trim_memory_after
# Disallow caching to prevent CSRF token errors.
@trim_memory_after
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def grade_level_analyzer(request):
    from .forms import TextForm
    from .grade_level_utils import calculate_grade_levels

    # Default: Initialize an empty form
    form = TextForm()
    context = {} # Initialize context
    
    if request.method == "POST":
        # Bind data to the form
        form = TextForm(request.POST)
        
        if form.is_valid():
            # SUCCESS CASE
            input_text = form.cleaned_data["text"]
            context['text'] = input_text
            
            # Calculate and add results
            results = calculate_grade_levels(input_text)
            context["results"] = results
        else:
            # FAILURE CASE - IMPORTANT
            # If valid fails, we must ensure 'text' is passed back 
            # so the user doesn't lose their input.
            context['text'] = request.POST.get('text', '')

    # ALWAYS pass the form to the context.
    # If it was invalid, this 'form' object contains the errors.
    context["form"] = form

    return render(request, "projects/grade_level_analyzer.html", context)


# This is the code for the view for my website's llms.txt file.
def llms_txt(request):
    llms_path = os.path.join(settings.BASE_DIR, "llms.txt")
    try:
        with open(llms_path, "r", encoding="utf-8") as f:
            return HttpResponse(f.read(), content_type="text/plain; charset=utf-8")
    except FileNotFoundError:
        return HttpResponseNotFound("llms.txt not found")


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

# This is the code for my 404 catcher.  It returns the root, or homepage, of my website.
# Disallow caching to prevent CSRF token errors.
@trim_memory_after
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def view_404(request, exception):
    return render(request, "404.html", status=404)


# This is the code for my homepage.  It's set in URL paths to the root of my website.
# Force memory trim after work.
@trim_memory_after
# Disallow caching to prevent CSRF token errors.
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def home(request):
    return render(request, "projects/home.html")

# QR Code Generator
@trim_memory_after
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def qr_code_generator(request):
    from . import qr_utils
    from .forms import QRForm
    from django.http import HttpResponse

    if request.method == "POST":
        form = QRForm(request.POST)
        if form.is_valid():
            # 1. Get data
            data = form.cleaned_data["qr_text"]
            
            # 2. Offload image generation to utils
            qr_buffer = qr_utils.generate_qr_code_image(data)
            
            # 3. Return the response directly from memory
            response = HttpResponse(qr_buffer, content_type="image/png")
            response["Content-Disposition"] = 'attachment; filename="qrcode.png"'
            return response
    else:
        form = QRForm()

    return render(request, "projects/qr_code_generator.html", context={"form": form})

# Monte Carlo Simulator
# Force memory trim after work.
@trim_memory_after
# Disallow caching to prevent CSRF token errors.
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def monte_carlo_simulator(request):
    from .forms import MonteCarloForm
    from django.http import HttpResponse
    from django.shortcuts import render

    # Helper to encourage the OS to reclaim freed memory after heavy work
    def _trim_memory_safely():
        try:
            import gc, ctypes
            gc.collect()
            ctypes.CDLL("libc.so.6").malloc_trim(0)
        except Exception:
            pass

    if request.method == "POST":
        form = MonteCarloForm(request.POST)
        if form.is_valid():
            # First simulation inputs
            sim_quantity = form.cleaned_data["sim_quantity"]
            min_val = form.cleaned_data["min_val"]
            max_val = form.cleaned_data["max_val"]
            target_val = form.cleaned_data["target_val"]

            # Optional second simulation
            second_sim_quantity = form.cleaned_data["second_sim_quantity"]
            second_params = None
            if second_sim_quantity is not None:
                second_params = {
                    "min": form.cleaned_data["second_min_val"],
                    "max": form.cleaned_data["second_max_val"],
                    "n": second_sim_quantity,
                    "target": form.cleaned_data["second_target_val"],
                }

            # Prefer isolated child-process renderer; fall back to in-process if unavailable
            try:
                from .monte_carlo_utils import render_probability_pdf_isolated as render_pdf
                use_timeout = True
            except ImportError:
                from .monte_carlo_utils import render_probability_pdf as render_pdf
                use_timeout = False

            try:
                if use_timeout:
                    pdf_bytes = render_pdf(
                        min_val, max_val, sim_quantity, target_val,
                        second=second_params, timeout=20
                    )
                else:
                    pdf_bytes = render_pdf(
                        min_val, max_val, sim_quantity, target_val,
                        second=second_params
                    )

                response = HttpResponse(pdf_bytes, content_type="application/pdf")
                response["Content-Disposition"] = 'attachment; filename="probability_graph.pdf"'
                response["X-Content-Type-Options"] = "nosniff"
                return response
            finally:
                _trim_memory_safely()
    else:
        form = MonteCarloForm()

    return render(request, "projects/monte_carlo_simulator.html", context={"form": form})



# Weather Forecast
# Force memory trim after work.
@trim_memory_after
# Disallow caching to prevent CSRF token errors.
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def weather(request):
    import requests
    from .forms import WeatherForm
    from .utils import get_coordinates
    from .weather_utils import get_city_and_state, parse_weather_data

    # Initialize form
    form = WeatherForm(request.POST or None)
    context = {"form": form}

    # Only process if POST and Valid
    if request.method == "POST" and form.is_valid():
        # use cleaned_data for safety
        zip_code = form.cleaned_data["zip_code"]

        # 1. Get Coordinates
        coordinates = get_coordinates(zip_code)
        
        if not coordinates:
            context["error_message"] = (
                "The ZIP code you entered is valid, but the server was unable to find coordinates for it. "
                "This is a Google Maps Platform API error and not a problem with my code."
            )
            return render(request, "projects/weather.html", context)

        # 2. Get Location Names
        city_name, state_name = get_city_and_state(zip_code)
        latitude, longitude = coordinates
        
        # 3. Fetch Weather Data safely
        API_KEY_WEATHER = os.environ.get("OPEN_WEATHER_MAP_KEY")
        API_URL = f"https://api.openweathermap.org/data/3.0/onecall?lat={latitude}&lon={longitude}&appid={API_KEY_WEATHER}&units=imperial"

        try:
            response = requests.get(API_URL, timeout=5)
            response.raise_for_status() # Raises error for 404/500 codes
            
            # Offload parsing logic to utils
            weather_data = parse_weather_data(response.json())
            
            # Merge results into context
            context.update({
                "city_name": city_name,
                "state_name": state_name,
                **weather_data # Unpacks 'current_weather_report' and 'daily_forecast'
            })

        except requests.RequestException:
            context["error_message"] = "Weather service is currently unavailable. Please try again later."
        except Exception as e:
            # Catch parsing errors or other issues
            print(f"Weather App Error: {e}")
            context["error_message"] = "An unexpected error occurred while processing weather data."

    # Render (Same template for GET and POST)
    return render(request, "projects/weather.html", context)

# This is the code for the page containing information on all of my projects.
# Force memory trim after work.
@trim_memory_after
# Disallow caching to prevent CSRF token errors.
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def all_projects(request):
    projects_data = [
        {
            "title": "QR Code Generator",
            "url_name": "projects:qr_code_generator",
            "image": "qr-code-generator.webp",
            "description": "Easily generate QR codes with the user-friendly QR Code Generator. Whether you need a QR code for a website link, contact information, or any text, this app provides a fast and efficient solution. Simply enter your desired data, and with one click, you'll have a high-quality QR code ready to download and use. Perfect for teachers, businesses, marketers, event organizers, and individuals."
        },
        {
            "title": "Monte Carlo Simulator",
            "url_name": "projects:monte_carlo_simulator",
            "image": "monte-carlo-simulator.webp",
            "description": "Run quick what-if simulations. Set your ranges (single or dual) and an optional target, then export an easy-to-read probability chart to PDF for stakeholders."
        },
        {
            "title": "Weather Forecast App",
            "url_name": "projects:weather",
            "image": "weather.webp",
            "description": "Stay prepared with the Weather Forecast App, which provides precise and up-to-date weather information tailored to your location. By simply entering your ZIP code, you can receive detailed weather forecasts, including current conditions, daily highs and lows, humidity levels, wind speeds, and more."
        },
        {
            "title": "Grade Level Text Analyzer",
            "url_name": "projects:grade_level_analyzer",
            "image": "grade-level-text-analyzer.webp",
            "description": "Improve the readability of your content with the Grade Level Text Analyzer. This intuitive tool evaluates your text using the Flesch-Kincaid Grade Level, Gunning Fog Index, and Coleman-Liau Index, providing insights into how easily your writing can be understood by different audiences."
        },
        {
            "title": "DNS Lookup Tool",
            "url_name": "projects:dns_tool",
            "image": "dns-lookup.webp",
            "description": "Perform comprehensive DNS lookups with the DNS Lookup Tool, designed to provide quick access to vital DNS records for any domain. This tool is ideal for webmasters, network administrators, and SEO professionals who need detailed DNS information for troubleshooting, optimization, or security purposes."
        },
        {
            "title": "IP Address Lookup Tool",
            "url_name": "projects:ip_tool",
            "image": "ip-tool.webp",
            "description": "Uncover vital details about any IP address with the IP Address Lookup Tool, designed for IT professionals seeking in-depth information, including PTR (reverse DNS) records, geolocation data, ISP details, and organization information. This useful app also conducts DNS-based blacklist checks."
        },
        {
            "title": "SSL Verification Tool",
            "url_name": "projects:ssl_check",
            "image": "ssl-check.webp",
            "description": "Ensure the security and validity of your website's SSL certificate with the SSL Verification Tool. This app provides detailed information about SSL certificates, including the certificate’s issuer, expiration dates, and validity period. Whether you're a website owner, developer, or security professional, this tool helps you maintain a secure online presence."
        },
        {
            "title": "Freight Carrier Safety Reporter",
            "url_name": "projects:freight_safety",
            "image": "freight-safety.webp",
            "description": "Gain critical insights into freight carrier safety and compliance with the Freight Carrier Safety Reporter. Designed for freight brokers, safety managers, and logistics professionals, this app provides essential details about motor carriers using their USDOT numbers. The tool leverages FMCSA’s QCMobile API to retrieve vital safety data."
        },
        {
            "title": "SEO Head Checker",
            "url_name": "projects:seo_head_checker",
            "image": "seo-head-checker.webp",
            "description": "Uncover opportunities to enhance your website's search engine performance with the SEO Head Checker. This tool analyzes the head section of webpages, identifying the presence or absence of essential SEO elements such as title tags, meta descriptions, canonical tags, Open Graph tags, Twitter Card tags, and more."
        },
        {
            "title": "ISS Tracker",
            "url_name": "projects:iss_tracker",
            "image": "iss-tracker.webp",
            "description": "Monitor the International Space Station (ISS) in real-time with the ISS Tracker. This web-based app provides dynamic tracking of the ISS, including its current latitude, longitude, altitude, velocity, and regional position. Users can also project upcoming pass times over their location with precise timing and geolocation."
        },
        {
            "title": "XML Splitter",
            "url_name": "projects:xml_splitter",
            "image": "xml-splitter.webp",
            "description": "Convert a single, nested XML export into a clean ZIP of one-file-per-record. Many e-commerce platforms bundle orders, products, and customers into one large XML, while ERPs prefer individual XML files. Upload your source XML and the app splits it into well-formed, per-entry XML documents."
        },
        {
            "title": "Ham Radio Call Sign Lookup",
            "url_name": "projects:ham_radio_call_sign_lookup",
            "image": "ham-radio-call-sign-lookup.webp",
            "description": "Look up any U.S. amateur (ham) radio call sign to verify license status and view key details such as licensee name, class, and expiration. Designed for operators, clubs, and event coordinators, this tool provides quick identity checks before on-air contacts or during registration and logging."
        },
        {
            "title": "Font Inspector",
            "url_name": "projects:font_inspector",
            "image": "font-inspector.webp",
            "description": "Identify the fonts used on any website and where they’re loaded from. The Font Inspector scans page HTML and linked stylesheets to detect local and web-hosted fonts (e.g. Google Fonts, Adobe Fonts, Font Awesome), and offers licensing guidance. Export results to CSV for design audits."
        },
        {
            "title": "Cookie Audit",
            "url_name": "projects:cookie_audit",
            "image": "cookie-audit.webp",
            "description": "Scan any public webpage to identify cookies in use and review key attributes such as domain, expiration, HttpOnly, Secure, and SameSite flags. The Cookie Audit tool distinguishes between first-party and third-party cookies, identifies how cookies are set, and displays results in a clear, audit-ready table."
        },
        {
            "title": "Stained Glass Materials Calculator",
            "url_name": "projects:stained_glass_materials",
            "image": "glass-materials.webp",
            "description": "Estimate exactly how much copper foil, lead came, solder, and flux is needed for a stained glass project based on dimensions and piece count."
        },
        {
            "title": "Glass Volume & Weight Calculator",
            "url_name": "projects:glass_volume_calculator",
            "image": "glass-calc.webp",
            "description": "Calculate the exact amount of glass needed for pot melts, casting molds, or thick fused slabs using standard glass density."
        },
        {
            "title": "Kiln Firing Schedule Generator",
            "url_name": "projects:kiln_schedule_generator",
            "image": "kiln-schedule.webp", 
            "description": "Generate safe firing schedules for fused glass projects (COE 90, 96, 104, 33). Automatically adjusts ramp rates for Borosilicate, Soft Glass, and Standard fusing."
        },
        {
            "title": "Kiln Controller Utilities",
            "url_name": "projects:kiln_controller_utils",
            "image": "kiln-utils.webp",
            "description": "Quick math helpers for programming digital kiln controllers, including temperature conversion (F/C) and ramp segment duration calculations."
        },
        {
            "title": "Stained Glass Cost Estimator",
            "url_name": "projects:stained_glass_cost_estimator",
            "image": "stained-glass-calc.webp",
            "description": "Calculate a fair price for stained glass art by factoring in hidden costs like waste glass, solder, foil, and labor time."
        },
        {
            "title": "Lampwork Glass Calculator",
            "url_name": "projects:lampwork_materials",
            "image": "lampwork-glass-calculator.webp",
            "description": "Calculate the precise weight of glass stock needed for your next project. This calculator supports Borosilicate (COE 33), Soft Glass (COE 104), Satake, and Lead Crystal. Simply input the dimensions of your solid rods or hollow tubing to instantly get the required weight in grams or pounds. Essential for lampworkers, glassblowers, and inventory planning."
        },
        {
            "title": "Freight Class Calculator",
            "url_name": "projects:freight_class_calculator",
            "image": "freight-class-calculator.webp",
            "description": "Avoid costly re-bills by accurately estimating the NMFC Freight Class for LTL shipments. Simply input dimensions and weight to calculate density (PCF) and determine the correct class based on the standard density scale."
        },
        {
            "title": "Fuel Surcharge Calculator",
            "url_name": "projects:fuel_surcharge_calculator",
            "image": "fuel-surcharge-calculator.webp",
            "description": "Instantly calculate the Fuel Surcharge (FSC) for truckload shipments. Input your trip miles, current diesel price, and base peg to generate the exact surcharge amount per mile and total trip cost. Essential for freight brokers and owner-operators negotiating rates."
        },
        {
            "title": "HOS Trip Planner",
            "url_name": "projects:hos_trip_planner",
            "image": "hos-trip-planner.webp",
            "description": "Plan realistic truck trips compliant with FMCSA Hours of Service (HOS) rules. Input your miles and start time to generate a step-by-step itinerary that automatically calculates mandatory 30-minute breaks and 10-hour daily resets."
        },
        {
            "title": "Glass Reaction Checker",
            "url_name": "projects:glass_reaction_checker",
            "image": "glass-reaction-checker.webp",
            "description": "Prevent accidental discoloration and dark lines in your fused glass projects. This tool checks for chemical reactions between different glass families (Sulfur, Copper, Lead, and Silver) so you can plan your glass combinations safely."
        },
        {
            "title": "Enamel & Frit Mixing Calculator",
            "url_name": "projects:frit_mixing_calculator",
            "image": "frit-mixing-calculator.webp",
            "description": "Stop guessing your mix. Calculate the exact amount of liquid medium needed for your glass powders and enamels based on your application style (brush painting, screen printing, palette knife, or airbrush)."
        }
    ]
    
    context = {
        'projects': projects_data
    }
    
    return render(request, 'projects/all_projects.html', context)

# DNS Lookup Tool
# Force memory trim after work.
@trim_memory_after
# Disallow caching to prevent CSRF token errors.
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def dns_tool(request):
    from .forms import DomainForm
    from .dns_tool_utils import (
    fetch_dns_records,
    normalize_domain,
)
    results = {}
    error_message = None
    form = DomainForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        domain = normalize_domain(form.cleaned_data["domain"])
        results, error_message = fetch_dns_records(domain)

    response = render(
        request,
        "projects/dns_tool.html",
        {"form": form, "results": results, "error_message": error_message},
    )

    # Optional: the decorator already sets modern Cache-Control headers.
    # Only keep the manual headers if you have a strict legacy requirement.
    # response = add_no_cache_headers(response)

    return response

# IP Address Lookup Tool
# Force memory trim after work.
@trim_memory_after
# Disallow caching to prevent CSRF token errors.
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def ip_tool(request):
    from .forms import IPForm
    from .ip_tool_utils import lookup_ptr, geolocate_ip, check_blacklists

    results = {}
    error_message = None
    form = IPForm()

    if request.method == "POST":
        form = IPForm(request.POST)
        if form.is_valid():
            ip_address = form.cleaned_data["ip_address"]

            # Each helper already returns a user-facing payload and never raises.
            results["PTR"] = lookup_ptr(ip_address)
            results["Geolocation"] = geolocate_ip(ip_address)
            results["Blacklist"] = check_blacklists(ip_address)

    response = render(
        request,
        "projects/ip_tool.html",
        {"form": form, "results": results, "error_message": error_message},
    )

    # Extra anti-caching headers
    response["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response["Pragma"] = "no-cache"
    response["Expires"] = "0"
    return response



# SSL Verification Tool
# Force memory trim after work.
@trim_memory_after
# Disallow caching to prevent CSRF token errors.
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def ssl_check(request):
    from .forms import SSLCheckForm
    from .ssl_utils import verify_ssl
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


# This is the view for the IT Professional Toolkit page.
# Force memory trim after work.
@trim_memory_after
# Prevents CSRF token issues in iframes.
@ensure_csrf_cookie
# Disallow caching to prevent CSRF token errors.
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def it_tools(request):
    return render(request, "projects/it_tools.html")

# This is the view for the SEO Professional Toolkit page.
# Force memory trim after work.
@trim_memory_after
# Prevents CSRF token issues in iframes.
@ensure_csrf_cookie
# Disallow caching to prevent CSRF token errors.
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def seo_tools(request):
    return render(request, "projects/seo_tools.html")

# This is the view for the Privacy & Cookies page.
# Force memory trim after work.
@trim_memory_after
# Disallow caching to prevent CSRF token errors.
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def privacy_cookies(request):
    return render(request, "privacy_cookies.html")

# Glass Artist Toolkit Page
@trim_memory_after
# Prevents CSRF token issues in iframes.
@ensure_csrf_cookie
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def glass_artist_toolkit(request):
    return render(request, "projects/glass_artist_toolkit.html")

# Glass Volume Calculator
@trim_memory_after
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def glass_volume_calculator(request):
    from . import glass_utils
    from .forms import GlassVolumeForm
    form = GlassVolumeForm(request.POST or None)
    context = {"form": form}

    if request.method == "POST" and form.is_valid():
        # Delegate math to utils with new dynamic arguments
        context["results"] = glass_utils.calculate_glass_volume_weight(
            shape=form.cleaned_data["shape"],
            glass_type=form.cleaned_data["glass_type"],
            waste_factor=form.cleaned_data["waste_factor"],
            data=form.cleaned_data
        )

    return render(request, "projects/glass_volume_calculator.html", context)


# Kiln Schedule Generator
@trim_memory_after
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def kiln_schedule_generator(request):
    from . import glass_utils
    from .forms import KilnScheduleForm
    form = KilnScheduleForm(request.POST or None)
    context = {"form": form}

    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        # Delegate schedule generation to utils
        result = glass_utils.generate_kiln_schedule(
            brand=data["brand"],
            project=data["project_type"],
            thickness=data["thickness"]
        )
        context.update(result) # Merges "schedule" and "total_time"
        
        # Format the title for display
        context["project_name"] = f"{data['brand'].title()} - {data['project_type'].replace('_', ' ').title()}"

    return render(request, "projects/kiln_schedule_generator.html", context)

# Stained Glass Cost Estimator
@trim_memory_after
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def stained_glass_cost_estimator(request):
    from . import glass_utils
    from .forms import StainedGlassCostForm
    form = StainedGlassCostForm(request.POST or None)
    context = {"form": form}

    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        context["results"] = glass_utils.estimate_stained_glass_cost(
            w=d["width"], h=d["height"], pieces=d["pieces"],
            glass_price=d["glass_price"], rate=d["labor_rate"],
            user_hours=d["estimated_hours"], markup=d["markup"]
        )

    return render(request, "projects/stained_glass_cost_estimator.html", context)

# Kiln Controller Utilities
@trim_memory_after
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def kiln_controller_utils(request):
    from . import glass_utils
    from .forms import TempConverterForm, RampCalculatorForm
    
    convert_form = TempConverterForm(initial={"action": "convert"})
    ramp_form = RampCalculatorForm(initial={"action": "ramp"})
    context = {"convert_form": convert_form, "ramp_form": ramp_form}

    if request.method == "POST":
        action = request.POST.get("action")

        if action == "convert":
            convert_form = TempConverterForm(request.POST)
            if convert_form.is_valid():
                res = glass_utils.convert_temperature(
                    convert_form.cleaned_data["temperature"],
                    convert_form.cleaned_data["from_unit"]
                )
                context["convert_result"] = {
                    "input": f"{convert_form.cleaned_data['temperature']}{res['orig']}",
                    "output": f"{round(res['val'], 1)}{res['unit']}"
                }
                context["convert_form"] = convert_form

        elif action == "ramp":
            ramp_form = RampCalculatorForm(request.POST)
            if ramp_form.is_valid():
                res = glass_utils.calculate_ramp_details(
                    ramp_form.cleaned_data["start_temp"],
                    ramp_form.cleaned_data["target_temp"],
                    ramp_form.cleaned_data["rate"]
                )
                if res:
                    context["ramp_result"] = res
                else:
                    ramp_form.add_error("rate", "Rate must be greater than 0.")
                
                context["ramp_form"] = ramp_form

    return render(request, "projects/kiln_controller_utils.html", context)


# Stained Glass Materials Calculator
@trim_memory_after
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def stained_glass_materials(request):
    from . import glass_utils
    from .forms import StainedGlassMaterialsForm
    form = StainedGlassMaterialsForm(request.POST or None)
    context = {"form": form}

    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        context["results"] = glass_utils.estimate_stained_glass_materials(
            w=d["width"], h=d["height"], pieces=d["pieces"],
            method=d["method"], waste_factor=d["waste_factor"]
        )
        context["method_display"] = dict(form.fields['method'].choices)[d["method"]]

    return render(request, "projects/stained_glass_materials.html", context)


# Lampwork Material Calculator
@trim_memory_after
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def lampwork_materials(request):
    from . import glass_utils
    from .forms import LampworkMaterialForm
    form = LampworkMaterialForm(request.POST or None)
    context = {"form": form}

    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        results = glass_utils.calculate_lampwork_weight(
            glass_type=d["glass_type"], shape=d["form_factor"],
            dia_mm=d["diameter_mm"], length_in=d["length_inches"],
            qty=d["quantity"], wall_mm=d.get("wall_mm", 0)
        )
        # Add display names for template
        results["glass_name"] = dict(form.fields['glass_type'].choices)[d["glass_type"]]
        results["shape_name"] = dict(form.fields['form_factor'].choices)[d["form_factor"]]
        
        context["results"] = results

    return render(request, "projects/lampwork_materials.html", context)

# Freight Class Calculator
@trim_memory_after
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def freight_class_calculator(request):
    from . import freight_calculator_utils
    from .forms import FreightClassForm
    form = FreightClassForm(request.POST or None)
    context = {"form": form}

    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        context["results"] = freight_calculator_utils.calculate_freight_class(
            length=d["length"], width=d["width"], height=d["height"],
            weight_per_unit=d["weight"], quantity=d["quantity"]
        )

    return render(request, "projects/freight_class_calculator.html", context)


# Fuel Surcharge Calculator
@trim_memory_after
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def fuel_surcharge_calculator(request):
    from . import freight_calculator_utils
    from .forms import FuelSurchargeForm
    form = FuelSurchargeForm(request.POST or None)
    context = {"form": form}

    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        context["results"] = freight_calculator_utils.calculate_fuel_surcharge(
            miles=d["trip_miles"], current_price=d["current_price"],
            base_price=d["base_price"], mpg=d["mpg"]
        )

    return render(request, "projects/fuel_surcharge_calculator.html", context)


# Truck Driver HOS Trip Planner
@trim_memory_after
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def hos_trip_planner(request):
    from . import freight_calculator_utils
    from .forms import HOSTripPlannerForm
    from datetime import datetime
    
    form = HOSTripPlannerForm(request.POST or None)
    context = {"form": form}

    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        start_datetime = datetime.combine(d["start_date"], d["start_time"])
        
        # Run HOS Simulation
        simulation_results = freight_calculator_utils.generate_hos_itinerary(
            miles_remaining=d["total_miles"],
            speed=d["avg_speed"],
            start_datetime=start_datetime
        )
        
        context.update(simulation_results) # Merges 'itinerary' and 'arrival_time'
        context["total_trip_miles"] = d["total_miles"]

    return render(request, "projects/hos_trip_planner.html", context)

# Freight Carrier Safety Reporter
@trim_memory_after
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def freight_safety(request):
    from .freight_calculator_utils import get_fmcsa_carrier_data_by_usdot
    from .forms import CarrierSearchForm
    
    form = CarrierSearchForm(request.POST or None)
    carrier = None
    error = None

    if request.method == "POST" and form.is_valid():
        search_value = form.cleaned_data["search_value"]

        try:
            # Ensure the search is conducted only with a DOT number
            carrier = get_fmcsa_carrier_data_by_usdot(search_value)

            if not carrier:
                error = "Carrier not found in FMCSA. Please verify you're submitting a valid DOT Number."

        except requests.exceptions.RequestException as e:
            error = f"There was an issue retrieving the carrier data. Please try again later. Error: {str(e)}"

    return render(
        request,
        "projects/freight_safety.html",
        {
            "form": form,
            "carrier": carrier,
            "error": error,
        }
    )

# Freight Professional Toolkit Page
@trim_memory_after
@ensure_csrf_cookie
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def freight_tools(request):
    return render(request, "projects/freight_tools.html")

# Freight Professional Toolkit Page
@trim_memory_after
@ensure_csrf_cookie
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def freight_tools(request):
    return render(request, "projects/freight_tools.html")

# Glass Reaction Checker
@trim_memory_after
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def glass_reaction_checker(request):
    from . import glass_utils
    from .forms import GlassReactionForm

    form = GlassReactionForm(request.POST or None)
    context = {"form": form}

    if request.method == "POST" and form.is_valid():
        type_a = form.cleaned_data["glass_a"]
        type_b = form.cleaned_data["glass_b"]

        # Delegate logic to utils
        context["results"] = glass_utils.check_glass_reaction(type_a, type_b)

    return render(request, "projects/glass_reaction_checker.html", context)

# Enamel/Frit Mixing Calculator
@trim_memory_after
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def frit_mixing_calculator(request):
    from . import glass_utils
    from .forms import FritMixingForm

    form = FritMixingForm(request.POST or None)
    context = {"form": form}

    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        context["results"] = glass_utils.calculate_frit_medium_ratio(
            powder_weight=d["powder_weight"],
            application_style=d["application_style"]
        )

    return render(request, "projects/frit_mixing_calculator.html", context)

# Circle/Oval Cutter Calculator
@trim_memory_after
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def circle_cutter_calculator(request):
    from . import glass_utils
    from .forms import CircleCutterForm

    form = CircleCutterForm(request.POST or None)
    context = {"form": form}

    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        
        # Determine display name for the shape
        shape_map = dict(form.fields['shape_type'].choices)
        shape_name = shape_map[d["shape_type"]]

        context["results"] = glass_utils.calculate_circle_cutter_settings(
            target_dim=d["target_diameter"],
            shape=shape_name,
            cutter_offset=d["cutter_offset"], # New argument
            grind_allowance=float(d["grind_allowance"])
        )

    return render(request, "projects/circle_cutter_calculator.html", context)