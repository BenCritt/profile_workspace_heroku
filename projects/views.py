from django.shortcuts import render
from django.http import HttpResponse, JsonResponse, HttpResponseNotFound, FileResponse, HttpRequest
from django.conf import settings
from django.views.decorators.cache import cache_control
from django.views.decorators.http import require_POST, require_GET
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

# NEW Beginning
@trim_memory_after
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
@require_POST
def cookie_audit_start(request):
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
# NEW END

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

# NEW BEGIN
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
# NEW END
# Font Inspector
# Force memory trim after work.
@trim_memory_after
# Disallow caching to prevent CSRF token errors.
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def font_inspector(request):
    from django.http import FileResponse
    from .font_utils import make_report, report_to_csv
    from .forms import FontInspectorForm
    from .utils import normalize_url
    import re
    form = FontInspectorForm(request.POST or None)
    rows = None

    if request.method == "POST" and form.is_valid():
        url = form.cleaned_data["url"]
        try:
            url = normalize_url(url)
        except Exception:
            if not re.match(r"^https?://", url, flags=re.I):
                rows = make_report(url)
            url = "https://" + url
            if not rows:
                form.add_error("url", "No fonts detected on that page.")
        except Exception as exc:
            form.add_error("url", str(exc))

        # optional CSV download
        if "download" in request.POST and rows:
            return FileResponse(
                report_to_csv(rows),
                as_attachment=True,
                filename="font_report.csv",
                content_type="text/csv",
            )

    return render(request, "projects/font_inspector.html",
                  {"form": form, "rows": rows})

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


# Grade Level Text Analyzer.
# Force memory trim after work.
@trim_memory_after
# Disallow caching to prevent CSRF token errors.
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def grade_level_analyzer(request):
    import textstat
    from .forms import TextForm
    # Check if the request method is POST.
    if request.method == "POST":
        # Initialize the form with data from the request.
        form = TextForm(request.POST)
        # Validate the form.
        if form.is_valid():
            # Extract the input text from the form.
            input_text = form.cleaned_data["text"]

            # --- Hardening & helpers (self-contained) ---
            import re
            # If available, ensure English rules for textstat
            if hasattr(textstat, "set_lang"):
                try:
                    textstat.set_lang("en_US")
                except Exception:
                    pass

            def _sanitize_for_readability(s: str) -> str:
                # Normalize punctuation that can confuse tokenizers
                s = s.replace("—", " ").replace("–", " ").replace("…", ". ")
                s = s.translate(str.maketrans({"’": "'", "‘": "'", "“": '"', "”": '"'}))
                # Remove standalone numbers/ordinals that can trip syllable tokenizers
                s = re.sub(r"\b\d+(?:[.,]\d+)?(?:st|nd|rd|th)?\b", " ", s)
                # Collapse whitespace
                return re.sub(r"\s{2,}", " ", s).strip()

            # Naive, dependency-free readability estimators (no CMU dict lookups)
            def _sentences(s: str):
                return [x for x in re.split(r"[.!?]+", s) if x.strip()]

            def _words(s: str):
                # keep contractions as a single token
                return re.findall(r"[A-Za-z]+(?:'[A-Za-z]+)?", s)

            _vowels = set("aeiouy")

            def _syllables(word: str) -> int:
                w = word.lower()
                count, prev_vowel = 0, False
                for ch in w:
                    is_vowel = ch in _vowels
                    if is_vowel and not prev_vowel:
                        count += 1
                    prev_vowel = is_vowel
                # Drop a trailing silent 'e' when plausible
                if w.endswith("e") and count > 1:
                    count -= 1
                return max(count, 1)

            def _metrics(s: str):
                # Keep letters, digits, basic punctuation; normalize whitespace
                s2 = re.sub(r"[^A-Za-z0-9\.\!\?,;:\s']", " ", s)
                s2 = re.sub(r"\s{2,}", " ", s2).strip()
                sents = _sentences(s2) or [s2]
                words = _words(s2)
                n_w = max(len(words), 1)
                n_s = max(len(sents), 1)
                n_letters = sum(len(re.findall(r"[A-Za-z]", w)) for w in words)
                syl_per_word = (sum(_syllables(w) for w in words) / n_w) if n_w else 0.0
                words_per_sent = n_w / n_s
                # Flesch–Kincaid Grade
                fk = 0.39 * words_per_sent + 11.8 * syl_per_word - 15.59
                # Coleman–Liau Index
                L = (n_letters / n_w) * 100.0
                S = (n_s / n_w) * 100.0
                cli = 0.0588 * L - 0.296 * S - 15.8
                # Gunning Fog
                complex_words = sum(1 for w in words if _syllables(w) >= 3)
                fog = 0.4 * (words_per_sent + 100.0 * (complex_words / n_w))
                return fk, fog, cli

            clean_text = _sanitize_for_readability(input_text)

            # Calculate readability scores using different indices.
            try:
                results = {
                    "flesch_kincaid_grade": textstat.flesch_kincaid_grade(clean_text),
                    "gunning_fog":          textstat.gunning_fog(clean_text),
                    "coleman_liau_index":   textstat.coleman_liau_index(clean_text),
                }
            except KeyError:
                # Dictionary miss (numbers, brand names, OOV words): use safe estimators
                fk, fog, cli = _metrics(clean_text)
                results = {
                    "flesch_kincaid_grade": fk,
                    "gunning_fog":          fog,
                    "coleman_liau_index":   cli,
                }
            except Exception:
                # Last-ditch: aggressively strip non-letters and compute safe estimators
                safer_text = re.sub(r"[^A-Za-z\.\!\?,;:\s']", " ", clean_text)
                fk, fog, cli = _metrics(safer_text)
                results = {
                    "flesch_kincaid_grade": fk,
                    "gunning_fog":          fog,
                    "coleman_liau_index":   cli,
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

# QR Code Generator.
# Force memory trim after work.
@trim_memory_after
# Disallow caching to prevent CSRF token errors.
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def qr_code_generator(request):
    import qrcode
    from .forms import QRForm
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
        form = QRForm()
    # Render the QR code generator page with the form.
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
    import json, datetime
    from .weather_utils import get_city_and_state
    from .utils import get_coordinates
    from .forms import WeatherForm
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
        API_KEY_WEATHER = os.environ["OPEN_WEATHER_MAP_KEY"]
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
# Force memory trim after work.
@trim_memory_after
# Disallow caching to prevent CSRF token errors.
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def all_projects(request):
    return render(request, "projects/all_projects.html")


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
# Disallow caching to prevent CSRF token errors.
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def it_tools(request):
    return render(request, "projects/it_tools.html")

# This is the view for the SEO Professional Toolkit page.
# Force memory trim after work.
@trim_memory_after
# Disallow caching to prevent CSRF token errors.
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def seo_tools(request):
    return render(request, "projects/seo_tools.html")
