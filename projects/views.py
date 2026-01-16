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

# Freight Carrier Safety Reporter
# Force memory trim after work.
@trim_memory_after
# Disallow caching to prevent CSRF token errors.
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def freight_safety(request):
    from .freight_utils import get_fmcsa_carrier_data_by_usdot
    from .forms import CarrierSearchForm
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
# Force memory trim after work.
@trim_memory_after
# Disallow caching to prevent CSRF token errors.
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def qr_code_generator(request):
    import qrcode
    import io
    from .forms import QRForm
    """
    Generates a QR code from user input and serves it directly as a download
    without saving files to the server's filesystem.
    """
    if request.method == "POST":
        form = QRForm(request.POST)
        if form.is_valid():
            # 1. Get data
            data = form.cleaned_data["qr_text"]
            
            # 2. Generate QR Object
            qr = qrcode.QRCode(
                version=1, 
                box_size=10, 
                border=5
            )
            qr.add_data(data)
            qr.make(fit=True)
            
            # 3. Create Image in Memory (No Disk I/O)
            img = qr.make_image(fill_color="black", back_color="white")
            
            # Use BytesIO to hold the image data in RAM
            buffer = io.BytesIO()
            img.save(buffer, format="PNG")
            
            # Rewind the buffer to the beginning so it can be read
            buffer.seek(0)
            
            # 4. Return the response directly from memory
            response = HttpResponse(buffer, content_type="image/png")
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
        # NEW 2 BEGIN
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
        }
        # NEW 2 END
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

# NEW BEGIN

# Glass Volume Calculator
@trim_memory_after
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def glass_volume_calculator(request):
    from .forms import GlassVolumeForm
    import math

    # Standard density for soda-lime fusing glass (Bullseye/System 96) is approx 2.5 g/cm³
    GLASS_DENSITY = 2.5 

    form = GlassVolumeForm(request.POST or None)
    context = {"form": form}

    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        shape = data["shape"]
        units = data["units"]
        depth = data["depth"]
        
        volume_cm3 = 0.0

        # 1. Normalize inputs to Centimeters for calculation
        # Conversion factor: 1 inch = 2.54 cm
        scale = 2.54 if units == "inches" else 1.0
        
        depth_cm = depth * scale

        if shape == "cylinder":
            diameter = data["diameter"] * scale
            radius = diameter / 2
            # V = π * r² * h
            volume_cm3 = math.pi * (radius ** 2) * depth_cm
            
        elif shape == "rectangle":
            length = data["length"] * scale
            width = data["width"] * scale
            # V = l * w * h
            volume_cm3 = length * width * depth_cm

        # 2. Calculate Weight
        weight_grams = volume_cm3 * GLASS_DENSITY
        
        # 3. Format Results
        context["results"] = {
            "volume_cc": round(volume_cm3, 2),
            "weight_g": round(weight_grams, 1),
            "weight_oz": round(weight_grams / 28.3495, 2), # Grams to Ounces
            "weight_kg": round(weight_grams / 1000, 3),
            "glass_needed": round(weight_grams * 1.05, 1) # Including 5% waste buffer
        }

    return render(request, "projects/glass_volume_calculator.html", context)

# Kiln Schedule Generator
@trim_memory_after
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def kiln_schedule_generator(request):
    from .forms import KilnScheduleForm

    form = KilnScheduleForm(request.POST or None)
    context = {"form": form}

    if request.method == "POST" and form.is_valid():
        brand = form.cleaned_data["brand"]
        project = form.cleaned_data["project_type"]
        thickness = form.cleaned_data["thickness"]

        # 1. Define Base Temperatures (Fahrenheit)
        # Dictionary maps brand to (Anneal Temp, Strain Point)
        glass_specs = {
            "bullseye": {"anneal": 900, "strain": 800},
            "verre":    {"anneal": 900, "strain": 800},     # Treating Verre as standard COE 90
            "system96": {"anneal": 950, "strain": 850},
            "soft":     {"anneal": 960, "strain": 840},     # Typical Effetre/Moretti values
            "boro":     {"anneal": 1050, "strain": 950},    # Hard glass requires high heat
        }
        
        # Get specs with safety default to Bullseye 90
        specs = glass_specs.get(brand, glass_specs["bullseye"])
        anneal_temp = specs["anneal"]
        strain_point = specs["strain"]
        
        # Process Temps: Define standard vs Boro (High Temp)
        if brand == "boro":
            # Borosilicate needs significantly higher temps
            process_temps = {
                "full_fuse": 1650,  # Warning: High for some hobby kilns
                "tack_fuse": 1500,
                "slump": 1300,
                "fire_polish": 1375,
            }
        else:
            # Standard Soft/90/96/104 Temps
            process_temps = {
                "full_fuse": 1490,
                "tack_fuse": 1350,
                "slump": 1225,
                "fire_polish": 1325,
            }
            
        top_temp = process_temps.get(project, 1490)

        # 2. Define Rates based on Thickness (Safety Logic)
        # Structure: (Ramp 1 Speed, Bubble Squeeze Hold, Ramp 2 Speed, Anneal Cool Speed, Cool Down Speed)
        if thickness == "extra_thick":
            rate_1 = 150  # Very slow initial heat
            squeeze_hold = 45
            rate_2 = 250
            anneal_cool = 50 # Very slow cool through anneal
            cool_down = 100
        elif thickness == "thick":
            rate_1 = 250
            squeeze_hold = 30
            rate_2 = 400
            anneal_cool = 80
            cool_down = 150
        else: # Standard (6mm)
            rate_1 = 400
            squeeze_hold = 20
            rate_2 = 600
            anneal_cool = 150 # Standard cool
            cool_down = 300

        # 3. Construct the Schedule Segments
        # Segment format: [Segment Name, Rate (°F/hr), Target Temp (°F), Hold Time (min)]
        segments = []
        
        # Seg 1: Initial Heat (Bubble Squeeze)
        segments.append({
            "step": 1, "name": "Initial Heat", 
            "rate": rate_1, "temp": 1225, "hold": squeeze_hold
        })
        
        # Seg 2: Process Heat (The Fuse/Slump)
        segments.append({
            "step": 2, "name": "Process Heat", 
            "rate": rate_2, "temp": top_temp, "hold": 10 if project == "full_fuse" else 20
        })
        
        # Seg 3: Rapid Cool (Crash to Anneal)
        segments.append({
            "step": 3, "name": "Rapid Cool", 
            "rate": 9999, "temp": anneal_temp, "hold": 60 if thickness == "extra_thick" else 30
        })
        
        # Seg 4: Anneal Soak (Critical for strength)
        segments.append({
            "step": 4, "name": "Anneal Cool", 
            "rate": anneal_cool, "temp": strain_point, "hold": 0
        })
        
        # Seg 5: Cool to Room Temp
        segments.append({
            "step": 5, "name": "Final Cool", 
            "rate": cool_down, "temp": 70, "hold": 0
        })

        # Calculate Total Estimated Time
        total_minutes = 0
        current_temp = 70
        for seg in segments:
            # Time = Distance / Rate
            dist = abs(seg["temp"] - current_temp)
            if seg["rate"] == 9999: # AFAP (As Fast As Possible)
                hours = 0.25 # Estimate 15 mins for crash cool
            else:
                hours = dist / seg["rate"]
            
            total_minutes += (hours * 60) + seg["hold"]
            current_temp = seg["temp"]

        hours = int(total_minutes // 60)
        mins = int(total_minutes % 60)

        context["schedule"] = segments
        context["total_time"] = f"{hours} hours, {mins} minutes"
        context["project_name"] = f"{form.cleaned_data['brand'].title()} - {form.cleaned_data['project_type'].replace('_', ' ').title()}"

    return render(request, "projects/kiln_schedule_generator.html", context)

# Stained Glass Cost Estimator
@trim_memory_after
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def stained_glass_cost_estimator(request):
    from .forms import StainedGlassCostForm
    
    form = StainedGlassCostForm(request.POST or None)
    context = {"form": form}

    if request.method == "POST" and form.is_valid():
        w = form.cleaned_data["width"]
        h = form.cleaned_data["height"]
        pieces = form.cleaned_data["pieces"]
        glass_price = form.cleaned_data["glass_price"]
        rate = form.cleaned_data["labor_rate"]
        user_hours = form.cleaned_data["estimated_hours"]

        # 1. Calculate Area & Glass Cost
        area_sqft = (w * h) / 144.0
        # Add 35% waste factor for cuts/breaks
        glass_cost = area_sqft * glass_price * 1.35

        # 2. Calculate Consumables (Solder, Foil, Flux, Patina)
        # Rule of thumb: Approx $0.60 - $0.75 per piece in consumables
        consumables_cost = pieces * 0.65

        # 3. Calculate Labor
        if user_hours:
            hours = user_hours
            labor_method = "User Input"
        else:
            # Estimate 15 mins (0.25 hrs) per piece for end-to-end construction
            hours = pieces * 0.25
            labor_method = "Auto-Estimated (15m/piece)"
        
        labor_cost = hours * rate

        # 4. Totals
        total_cost = glass_cost + consumables_cost + labor_cost
        retail_price = total_cost * 2.0  # Standard Keystone markup (100% markup)

        context["results"] = {
            "area_sqft": round(area_sqft, 2),
            "glass_cost": round(glass_cost, 2),
            "consumables_cost": round(consumables_cost, 2),
            "labor_hours": round(hours, 1),
            "labor_cost": round(labor_cost, 2),
            "labor_method": labor_method,
            "total_base_cost": round(total_cost, 2),
            "retail_price": round(retail_price, 2)
        }

    return render(request, "projects/stained_glass_cost_estimator.html", context)

# Kiln Controller Utilities
@trim_memory_after
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def kiln_controller_utils(request):
    from .forms import TempConverterForm, RampCalculatorForm
    
    # Initialize both forms
    convert_form = TempConverterForm(initial={"action": "convert"})
    ramp_form = RampCalculatorForm(initial={"action": "ramp"})
    
    context = {
        "convert_form": convert_form,
        "ramp_form": ramp_form
    }

    if request.method == "POST":
        # Determine which form was submitted based on the hidden 'action' field
        action = request.POST.get("action")

        if action == "convert":
            convert_form = TempConverterForm(request.POST)
            if convert_form.is_valid():
                temp = convert_form.cleaned_data["temperature"]
                unit = convert_form.cleaned_data["from_unit"]
                
                if unit == "F":
                    # F to C: (32°F − 32) × 5/9 = 0°C
                    result_val = (temp - 32) * 5/9
                    result_unit = "°C"
                    input_unit = "°F"
                else:
                    # C to F: (0°C × 9/5) + 32 = 32°F
                    result_val = (temp * 9/5) + 32
                    result_unit = "°F"
                    input_unit = "°C"

                context["convert_result"] = {
                    "input": f"{temp}{input_unit}",
                    "output": f"{round(result_val, 1)}{result_unit}"
                }
                context["convert_form"] = convert_form

        elif action == "ramp":
            ramp_form = RampCalculatorForm(request.POST)
            if ramp_form.is_valid():
                start = ramp_form.cleaned_data["start_temp"]
                target = ramp_form.cleaned_data["target_temp"]
                rate = ramp_form.cleaned_data["rate"]

                if rate > 0:
                    # Logic: Time = Distance / Speed
                    diff = abs(target - start)
                    hours_decimal = diff / rate
                    
                    # Convert decimal hours to Hours:Minutes
                    hours_int = int(hours_decimal)
                    minutes_int = int((hours_decimal - hours_int) * 60)
                    
                    context["ramp_result"] = {
                        "delta": round(diff, 1),
                        "duration": f"{hours_int} hr {minutes_int} min",
                        "total_decimal": round(hours_decimal, 2)
                    }
                else:
                    ramp_form.add_error("rate", "Rate must be greater than 0.")
                
                context["ramp_form"] = ramp_form

    return render(request, "projects/kiln_controller_utils.html", context)

# Stained Glass Materials Calculator
@trim_memory_after
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def stained_glass_materials(request):
    from .forms import StainedGlassMaterialsForm
    import math

    form = StainedGlassMaterialsForm(request.POST or None)
    context = {"form": form}

    if request.method == "POST" and form.is_valid():
        w = form.cleaned_data["width"]
        h = form.cleaned_data["height"]
        pieces = form.cleaned_data["pieces"]
        method = form.cleaned_data["method"]
        waste_percent = 1 + (form.cleaned_data["waste_factor"] / 100.0)

        area = w * h
        perimeter = 2 * (w + h)

        # Geometric estimation of total pattern line length (internal + external)
        # Based on a tiling approximation: Line_Length approx 2 * sqrt(Area * Pieces)
        estimated_line_length = 2.0 * math.sqrt(area * pieces)

        results = {}

        if method == "foil":
            # Foil covers every edge of every piece.
            # Internal lines have 2 edges (one for each piece), border has 1.
            # Approximation: Total Perimeter of all pieces = 2 * Line_Length
            raw_foil_inches = estimated_line_length * 2.0
            total_foil_inches = raw_foil_inches * waste_percent
            
            # Solder (Foil): Beads on both sides (x2 length)
            # Standard estimate: 1lb solder per ~1500 linear inches of 1/4" bead
            solder_needed_lbs = (estimated_line_length * 2) / 1500.0

            results = {
                "material_name": "Copper Foil",
                "length_feet": round(total_foil_inches / 12, 1),
                "rolls_needed": math.ceil(total_foil_inches / (36 * 12)), # Standard 36 yard roll
                "solder_lbs": round(solder_needed_lbs, 2),
                "flux_oz": round(solder_needed_lbs * 2, 1), # Rough estimate
            }
        
        else: # Lead Came
            # Came covers the lines exactly once.
            total_came_inches = estimated_line_length * waste_percent
            
            # Solder (Came): Joints only. Approx 0.01 lbs per piece/joint.
            solder_needed_lbs = pieces * 0.01

            results = {
                "material_name": "Lead Came",
                "length_feet": round(total_came_inches / 12, 1),
                "sticks_needed": math.ceil(total_came_inches / 72), # Standard 6ft (72") stick
                "solder_lbs": round(solder_needed_lbs, 2),
                "putty_lbs": round(area / 144.0 * 0.5, 1), # Approx 0.5 lb putty per sq ft
            }

        context["results"] = results
        context["method_display"] = dict(form.fields['method'].choices)[method]

    return render(request, "projects/stained_glass_materials.html", context)

# Lampwork Material Calculator
@trim_memory_after
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def lampwork_materials(request):
    from .forms import LampworkMaterialForm
    import math

    form = LampworkMaterialForm(request.POST or None)
    context = {"form": form}

    # Density Mapping (g/cm³)
    DENSITIES = {
        "boro": 2.23,    # Standard Borosilicate
        "soft": 2.50,    # Standard Soda Lime (Effetre)
        "satake": 2.55,  # Satake Glass (Lead)
        "coe90": 2.50,   # Bullseye (approx standard soda lime)
        "coe96": 2.50,   # System 96 (approx standard soda lime)
        "crystal": 3.10, # Generic Full Lead Crystal
        "quartz": 2.20,  # Fused Silica
    }

    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        
        # 1. Inputs
        g_type = data["glass_type"]
        shape = data["form_factor"]
        dia_mm = data["diameter_mm"]
        length_in = data["length_inches"]
        qty = data["quantity"]
        
        # 2. Conversions (mm -> cm, inches -> cm)
        radius_cm = (dia_mm / 2) / 10.0
        length_cm = length_in * 2.54
        
        # 3. Volume Calculation (cm³)
        if shape == "rod":
            # V = π * r² * h
            vol_per_piece = math.pi * (radius_cm ** 2) * length_cm
        else:
            # Tubing: V = π * (r_out² - r_in²) * h
            wall_mm = data["wall_mm"]
            inner_radius_cm = ((dia_mm - (2 * wall_mm)) / 2) / 10.0
            vol_per_piece = math.pi * (radius_cm**2 - inner_radius_cm**2) * length_cm

        total_vol = vol_per_piece * qty

        # 4. Weight Calculation
        density = DENSITIES.get(g_type, 2.50) # Default to 2.5 if unknown
        total_weight_g = total_vol * density
        total_weight_lb = total_weight_g / 453.592

        context["results"] = {
            "weight_g": round(total_weight_g, 1),
            "weight_lb": round(total_weight_lb, 3),
            "total_len_in": round(length_in * qty, 1),
            "glass_name": dict(form.fields['glass_type'].choices)[g_type],
            "shape_name": dict(form.fields['form_factor'].choices)[shape],
            "density": density,
        }

    return render(request, "projects/lampwork_materials.html", context)

# Glass Artist Toolkit Page
@trim_memory_after
# Prevents CSRF token issues in iframes.
@ensure_csrf_cookie
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def glass_artist_toolkit(request):
    return render(request, "projects/glass_artist_toolkit.html")

# NEW END

# NEW 2 BEGIN

# Freight Class Calculator
@trim_memory_after
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def freight_class_calculator(request):
    from .forms import FreightClassForm

    form = FreightClassForm(request.POST or None)
    context = {"form": form}

    if request.method == "POST" and form.is_valid():
        l = form.cleaned_data["length"]
        w = form.cleaned_data["width"]
        h = form.cleaned_data["height"]
        weight_per = form.cleaned_data["weight"]
        qty = form.cleaned_data["quantity"]

        # 1. Calculate Totals
        # Volume of one unit in cubic inches
        vol_cubic_inches = l * w * h
        # Volume of one unit in cubic feet (1728 cubic inches = 1 cubic foot)
        vol_cubic_feet = vol_cubic_inches / 1728.0
        
        total_cubic_feet = vol_cubic_feet * qty
        total_weight = weight_per * qty
        
        # 2. Calculate Density (PCF: Pounds per Cubic Foot)
        if total_cubic_feet > 0:
            density = total_weight / total_cubic_feet
        else:
            density = 0

        # 3. Determine Estimated Freight Class (Standard NMFC Density Scale)
        if density < 1:
            est_class = 400
        elif density < 2:
            est_class = 300
        elif density < 4:
            est_class = 250
        elif density < 6:
            est_class = 150
        elif density < 8:
            est_class = 125
        elif density < 10:
            est_class = 100
        elif density < 12:
            est_class = 92.5
        elif density < 15:
            est_class = 85
        elif density < 22.5:
            est_class = 70
        elif density < 30:
            est_class = 65
        elif density < 35:
            est_class = 60
        elif density < 50:
            est_class = 55
        else:
            est_class = 50

        context["results"] = {
            "density": round(density, 2),
            "estimated_class": est_class,
            "total_weight": round(total_weight, 2),
            "total_cubic_feet": round(total_cubic_feet, 2),
            "qty": qty
        }

    return render(request, "projects/freight_class_calculator.html", context)

# Fuel Surcharge Calculator
@trim_memory_after
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def fuel_surcharge_calculator(request):
    from .forms import FuelSurchargeForm

    form = FuelSurchargeForm(request.POST or None)
    context = {"form": form}

    if request.method == "POST" and form.is_valid():
        miles = form.cleaned_data["trip_miles"]
        current = form.cleaned_data["current_price"]
        base = form.cleaned_data["base_price"]
        mpg = form.cleaned_data["mpg"]

        # 1. Calculate the difference
        # If current price is below base, surcharge is technically zero (or negative/credit).
        # We calculate the raw diff but handle display logic in the template or here.
        price_diff = current - base
        
        # 2. Calculate Surcharge Per Mile
        # Formula: (Current - Base) / MPG
        if mpg > 0:
            fsc_per_mile = price_diff / mpg
        else:
            fsc_per_mile = 0.0

        # 3. Calculate Total Surcharge
        total_fsc = fsc_per_mile * miles

        context["results"] = {
            "fsc_per_mile": round(fsc_per_mile, 3),  # Standard 3 decimal places for rate/mile
            "total_fsc": round(total_fsc, 2),
            "price_diff": round(price_diff, 2),
            "is_negative": price_diff < 0
        }

    return render(request, "projects/fuel_surcharge_calculator.html", context)

# Truck Driver HOS Trip Planner
@trim_memory_after
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def hos_trip_planner(request):
    from .forms import HOSTripPlannerForm
    from datetime import datetime, timedelta

    form = HOSTripPlannerForm(request.POST or None)
    context = {"form": form}

    if request.method == "POST" and form.is_valid():
        # Inputs
        miles_remaining = form.cleaned_data["total_miles"]
        speed = form.cleaned_data["avg_speed"]
        s_date = form.cleaned_data["start_date"]
        s_time = form.cleaned_data["start_time"]

        # Initialize Simulation Clock
        current_time = datetime.combine(s_date, s_time)
        itinerary = []
        
        # HOS Counters
        shift_drive_time = 0.0
        continuous_drive_time = 0.0
        
        # Safety catch for infinite loops
        iterations = 0
        max_iterations = 50 

        while miles_remaining > 0 and iterations < max_iterations:
            iterations += 1
            
            # 1. Determine constraints for this leg
            # How much time is left on the 11-hour shift limit?
            time_left_in_shift = 11.0 - shift_drive_time
            # How much time is left before mandatory 30-min break (8 hr limit)?
            time_left_continuous = 8.0 - continuous_drive_time
            # How much time to finish the trip?
            time_to_finish = miles_remaining / speed

            # The actual drive time is the smallest of these constraints
            leg_duration = min(time_to_finish, time_left_in_shift, time_left_continuous)
            
            # Avoid tiny floating point fragments (less than 1 min)
            if leg_duration < 0.01:
                leg_duration = 0

            # 2. "Drive" this leg
            dist_covered = leg_duration * speed
            start_leg_time = current_time
            current_time += timedelta(hours=leg_duration)
            
            miles_remaining -= dist_covered
            shift_drive_time += leg_duration
            continuous_drive_time += leg_duration

            # Add Drive Event
            if leg_duration > 0:
                itinerary.append({
                    "event": "Drive",
                    "start": start_leg_time,
                    "end": current_time,
                    "duration": f"{int(leg_duration)}h {int((leg_duration*60)%60)}m",
                    "note": f"Covered {round(dist_covered, 1)} miles"
                })

            # 3. Check Logic for Breaks/Resets
            
            # A) Trip Finished?
            if miles_remaining <= 0.1: # float tolerance
                itinerary.append({
                    "event": "Arrived",
                    "start": current_time,
                    "end": "",
                    "duration": "",
                    "note": "Destination Reached",
                    "is_highlight": True
                })
                break

            # B) 11-Hour Limit Hit? -> 10 Hour Reset
            if shift_drive_time >= 11.0:
                start_break = current_time
                current_time += timedelta(hours=10)
                itinerary.append({
                    "event": "10-Hour Reset",
                    "start": start_break,
                    "end": current_time,
                    "duration": "10h 00m",
                    "note": "Mandatory Daily Reset (11hr limit reached)",
                    "is_break": True
                })
                # Reset clocks
                shift_drive_time = 0
                continuous_drive_time = 0
                continue # Skip checking 30min break if we just took a 10hr reset

            # C) 8-Hour Limit Hit? -> 30 Minute Break
            if continuous_drive_time >= 8.0:
                start_break = current_time
                current_time += timedelta(minutes=30)
                itinerary.append({
                    "event": "30-Min Break",
                    "start": start_break,
                    "end": current_time,
                    "duration": "0h 30m",
                    "note": "Mandatory FMCSA Break (8hr continuous limit)",
                    "is_break": True
                })
                # Reset continuous clock only
                continuous_drive_time = 0

        context["itinerary"] = itinerary
        context["arrival_time"] = current_time
        context["total_trip_miles"] = form.cleaned_data["total_miles"]

    return render(request, "projects/hos_trip_planner.html", context)

# Freight Professional Toolkit Page
@trim_memory_after
@ensure_csrf_cookie
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def freight_tools(request):
    return render(request, "projects/freight_tools.html")

# NEW 2 END