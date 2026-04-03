# views/views_misc.py
#
# ============================================================================
# Miscellaneous Standalone Tool Views
# ============================================================================
# Contains view functions for tools that don't belong to any larger thematic
# category (freight, glass, radio, etc.) and that are light enough to live
# in a single shared module rather than their own package.
#
# Tools in this module:
#   qr_code_generator    — Converts any text or URL to a downloadable QR PNG
#   monte_carlo_simulator— Runs a probability distribution simulation and
#                          returns a rendered PDF chart
#   weather              — ZIP-code current conditions + 7-day forecast
#                          via the OpenWeatherMap One Call 3.0 API
#   ai_api_cost_estimator— Estimates token count and per-provider API cost
#                          for a given input text + task type
#
# All views follow the same decorator conventions used throughout the project:
#   @trim_memory_after          — gc.collect() + malloc_trim() post-response
#   @cache_control(no_cache=…)  — prevents browser/CDN result caching
#
# See views_glass_tools.py for a full explanation of the decorator rationale
# and the lazy-import pattern.
# ============================================================================

import os

from django.shortcuts import render
from django.http import HttpResponse
from django.views.decorators.cache import cache_control

from ..decorators import trim_memory_after


# ===========================================================================
# QR Code Generator
# ===========================================================================
# Accepts arbitrary text or a URL and returns a PNG image of the corresponding
# QR code as a file download (not a page render).
#
# GET  → renders the input form (QRForm).
# POST → validates the form; if valid, calls qr_utils.generate_qr_code_image()
#        which returns a BytesIO buffer.  The buffer is streamed directly as an
#        image/png response with a Content-Disposition attachment header so the
#        browser triggers a Save dialog rather than trying to display the PNG
#        inline.  No template is rendered on a successful POST.
#
# On an invalid POST the form is re-rendered with validation errors as usual.
# ===========================================================================

@trim_memory_after
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def qr_code_generator(request):
    from .. import qr_utils
    from ..forms import QRForm

    if request.method == "POST":
        form = QRForm(request.POST)
        if form.is_valid():
            data      = form.cleaned_data["qr_text"]
            qr_buffer = qr_utils.generate_qr_code_image(data)

            # Stream the PNG bytes directly — no template involved.
            response  = HttpResponse(qr_buffer, content_type="image/png")
            # "attachment" triggers a browser download dialog; "inline" would
            # try to display the image in-tab.
            response["Content-Disposition"] = 'attachment; filename="qrcode.png"'
            return response
    else:
        form = QRForm()

    # GET, or invalid POST — render the form page.
    return render(
        request, "projects/qr_code_generator.html", context={"form": form}
    )


# ===========================================================================
# Monte Carlo Probability Simulator
# ===========================================================================
# Runs one or two Monte Carlo probability distribution simulations and returns
# a rendered PDF chart as a file download.  The chart shows the distribution
# histogram, probability density curve, and the target-value percentile marker.
#
# This is the heaviest tool on the site in terms of CPU + memory: it uses
# NumPy/SciPy for simulation and Matplotlib for rendering.  Three strategies
# are in place to manage resource usage:
#
#   1. SUBPROCESS ISOLATION (preferred):
#      monte_carlo_utils.render_probability_pdf_isolated() forks a child
#      process to do the heavy lifting, enforces a 20-second timeout, and
#      ensures that Matplotlib's memory is fully released when the child exits.
#      If that import is unavailable (e.g. the multiprocessing-based module
#      hasn't been installed), the code falls back to the in-process renderer.
#
#   2. FALLBACK IN-PROCESS RENDERER:
#      monte_carlo_utils.render_probability_pdf() runs directly in the Gunicorn
#      worker.  Memory is not as cleanly reclaimed, but it still works.
#
#   3. EXPLICIT MEMORY TRIM (_trim_memory_safely):
#      After rendering (or even after an exception), gc.collect() + malloc_trim()
#      are called via the nested helper to encourage the OS to reclaim freed
#      heap pages.  This runs in a finally block so it fires regardless of
#      whether the render succeeded or raised.
#
# GET  → renders the form page (MonteCarloForm with primary + optional secondary
#        simulation inputs).
# POST → validates form; runs the simulation; returns a PDF binary response.
#        The finally block always runs the memory trim.
#
# SECOND SIMULATION:
#   If second_sim_quantity is provided, the form also collects a second
#   distribution's min/max/target/n.  These are bundled into a `second_params`
#   dict and passed to the renderer, which overlays the second distribution on
#   the same chart for comparison.
# ===========================================================================

@trim_memory_after
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def monte_carlo_simulator(request):
    from ..forms import MonteCarloForm

    def _trim_memory_safely():
        """
        Encourage the OS to reclaim freed memory after simulation completes.

        gc.collect() returns reference-cycle garbage to Python's allocator.
        malloc_trim(0) then asks libc to release free pages back to the OS —
        critical on Heroku where resident set size (RSS) is tightly monitored.
        Both calls are wrapped in a try/except so a missing libc (Windows dev
        environment, musl libc, etc.) doesn't break the response.
        """
        try:
            import gc, ctypes
            gc.collect()
            ctypes.CDLL("libc.so.6").malloc_trim(0)
        except Exception:
            pass

    if request.method == "POST":
        form = MonteCarloForm(request.POST)
        if form.is_valid():
            sim_quantity = form.cleaned_data["sim_quantity"]
            min_val      = form.cleaned_data["min_val"]
            max_val      = form.cleaned_data["max_val"]
            target_val   = form.cleaned_data["target_val"]

            # Second simulation is optional.  Only assemble second_params if
            # the user filled in second_sim_quantity; the other second_* fields
            # are conditional on that field being present.
            second_sim_quantity = form.cleaned_data["second_sim_quantity"]
            second_params = None
            if second_sim_quantity is not None:
                second_params = {
                    "min":    form.cleaned_data["second_min_val"],
                    "max":    form.cleaned_data["second_max_val"],
                    "n":      second_sim_quantity,
                    "target": form.cleaned_data["second_target_val"],
                }

            # Prefer the subprocess-isolated renderer; fall back to in-process.
            # The `use_timeout` flag signals whether the isolated renderer's
            # `timeout` kwarg is supported.
            try:
                from ..monte_carlo_utils import (
                    render_probability_pdf_isolated as render_pdf,
                )
                use_timeout = True
            except ImportError:
                from ..monte_carlo_utils import render_probability_pdf as render_pdf
                use_timeout = False

            try:
                if use_timeout:
                    pdf_bytes = render_pdf(
                        min_val, max_val, sim_quantity, target_val,
                        second=second_params, timeout=20,
                    )
                else:
                    pdf_bytes = render_pdf(
                        min_val, max_val, sim_quantity, target_val,
                        second=second_params,
                    )

                # Stream the rendered PDF bytes directly to the browser.
                response = HttpResponse(pdf_bytes, content_type="application/pdf")
                response["Content-Disposition"] = (
                    'attachment; filename="probability_graph.pdf"'
                )
                # Prevent MIME-type sniffing; we know exactly what this is.
                response["X-Content-Type-Options"] = "nosniff"
                return response
            finally:
                # Always trim memory, even if the render raised an exception.
                _trim_memory_safely()
    else:
        form = MonteCarloForm()

    return render(
        request,
        "projects/monte_carlo_simulator.html",
        context={"form": form},
    )


# ===========================================================================
# Weather Forecast
# ===========================================================================
# Provides current conditions and a 7-day daily forecast for a US ZIP code
# using the OpenWeatherMap One Call 3.0 API (imperial units).
#
# GEOCODING:
#   ZIP → lat/lon is resolved locally via zip_data.local_get_location_data(),
#   which reads a bundled ZIP-code dataset rather than calling the Google Maps
#   Geocoding API.  This avoids a per-request Maps API charge and is faster.
#   The function also returns city and state names so we can display
#   "Chicago, IL" without a second lookup.
#
# GET  → renders an empty WeatherForm (single ZIP code field).
# POST → geocodes the ZIP, calls OpenWeatherMap, parses the response via
#        weather_utils.parse_weather_data(), and injects the parsed data into
#        context.  Two distinct error paths:
#          - Geocoding failure  → "error_message" (coordinates not found)
#          - API/network error  → "error_message" (service unavailable)
#
# CONTEXT KEYS on success:
#   city_name, state_name       — display location
#   current_weather_report      — today's conditions dict
#   daily_forecast              — list of 7 daily forecast dicts
#   (all injected via **weather_data unpacking from parse_weather_data())
#
# NOTE: The API key is currently hardcoded as a fallback while the env var
# comment is preserved.  In production, set OPEN_WEATHER_MAP_KEY in Heroku
# Config Vars and uncomment the os.environ.get() line.
# ===========================================================================

@trim_memory_after
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def weather(request):
    import requests
    from ..forms import WeatherForm
    from ..zip_data import local_get_location_data as get_location_data
    from ..weather_utils import parse_weather_data

    form    = WeatherForm(request.POST or None)
    context = {"form": form}

    if request.method == "POST" and form.is_valid():
        zip_code = form.cleaned_data["zip_code"]

        # Single call returns lat, lon, city, and state together.
        # Returns None if the ZIP is not in the local dataset.
        location = get_location_data(zip_code)

        if not location:
            # Geocoding failed — not a network issue, just an unknown ZIP.
            context["error_message"] = (
                "The ZIP code you entered is valid, but the server was unable to "
                "find coordinates for it. This is a Google Maps Platform API error "
                "and not a problem with my code."
            )
            return render(request, "projects/weather.html", context)

        latitude   = location["lat"]
        longitude  = location["lng"]
        city_name  = location["city"]  or "Unknown City"
        state_name = location["state"] or ""

        API_KEY_WEATHER = os.environ.get("OPEN_WEATHER_MAP_KEY")
        API_URL = (
            f"https://api.openweathermap.org/data/3.0/onecall"
            f"?lat={latitude}&lon={longitude}"
            f"&appid={API_KEY_WEATHER}&units=imperial"
        )

        try:
            response = requests.get(API_URL, timeout=5)
            response.raise_for_status()  # raises HTTPError for 4xx/5xx responses

            # parse_weather_data() normalises the raw OWM JSON into two
            # template-friendly dicts: current_weather_report and daily_forecast.
            weather_data = parse_weather_data(response.json())

            context.update({
                "city_name":  city_name,
                "state_name": state_name,
                **weather_data,   # spreads current_weather_report + daily_forecast
            })

        except requests.RequestException:
            # Covers connection errors, timeouts, and HTTP error status codes.
            context["error_message"] = (
                "Weather service is currently unavailable. Please try again later."
            )
        except Exception as e:
            # Catch-all for unexpected parse errors; log for diagnostics.
            print(f"Weather App Error: {e}")
            context["error_message"] = (
                "An unexpected error occurred while processing weather data."
            )

    return render(request, "projects/weather.html", context)


# ===========================================================================
# AI Token & API Cost Estimator
# ===========================================================================
# Estimates the number of tokens in a given text and projects the API cost
# across multiple AI providers (OpenAI, Anthropic, Google, etc.) for a
# specified task type (chat, completion, embedding, etc.).
#
# Token counting uses a heuristic (chars/4 approximation or tiktoken if
# available) implemented in ai_api_cost_estimator_utils.  Per-provider pricing
# tables are maintained in that same utils module and should be updated when
# providers change their rates.
#
# GET  → renders an empty AITokenCostForm (textarea + task_type dropdown).
# POST → validates form; calls estimate_tokens_and_cost(); injects the
#        results dict into context.  The results dict contains:
#          token_count        — estimated input token count
#          provider_estimates — list of {provider, model, input_cost, output_cost}
# ===========================================================================

@trim_memory_after
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def ai_api_cost_estimator(request):
    from ..forms import AITokenCostForm
    from ..ai_api_cost_estimator_utils import estimate_tokens_and_cost

    form    = AITokenCostForm(request.POST or None)
    context = {"form": form}

    if request.method == "POST" and form.is_valid():
        input_text = form.cleaned_data["input_text"]
        task_type  = form.cleaned_data["task_type"]
        context["results"] = estimate_tokens_and_cost(input_text, task_type)

    return render(request, "projects/ai_api_cost_estimator.html", context)

# ===========================================================================
# Job Fit Analyzer
# ===========================================================================
# Two-phase async pattern to avoid Heroku's 30-second request timeout:
#
#   Phase 1 — POST /job-fit-analyzer/
#     Validates the form, writes a "pending" cache entry, spawns a daemon
#     thread to call Gemini, and immediately returns a JSON {job_id}.
#     Response time: ~50ms.
#
#   Phase 2 — GET /job-fit-analyzer/status/<job_id>/
#     Lightweight polling endpoint. Returns JSON {status} or {status, html}.
#     Each response completes in milliseconds — well under Heroku's 30-second
#     ceiling — while the background thread runs freely with no timeout.
#
# Cache keys: "jfa:<job_id>" — TTL 10 minutes. Uses the "jobfit"
# FileBasedCache backend (/tmp/django_cache_jfa). No createcachetable
# required. See CACHES in settings.py.
# ===========================================================================

@trim_memory_after
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def job_fit_analyzer(request):
    from ..forms import JobFitForm

    form    = JobFitForm(request.POST or None)
    context = {"form": form}

    if request.method == "POST" and form.is_valid():
        import uuid
        import threading
        from django.core.cache import caches
        from django.http import JsonResponse
        from django_ratelimit.core import is_ratelimited
        from ..job_fit_analyzer_utils import run_gemini_job

        # Rate limit: 5 POSTs per hour per IP
        '''
        When testing locally, these are the PowerShell commands to clear cache:
        Remove-Item -Recurse -Force "$env:TEMP\django_cache_jfa"
        Remove-Item -Recurse -Force "$env:TEMP\django_cache_default"
        '''
        if is_ratelimited(request, group="job_fit_analyzer", key="ip", rate="5/h", method="POST", increment=True):
            return JsonResponse(
                {"error": "Thank you for your interest in my profile. This tool is rate-limited to 5 requests per hour per IP address due to API costs. Please try again shortly."},
                status=429,
            )

        # Honeypot check
        if form.cleaned_data.get("company_website"):
            print(f"Honeypot triggered — IP: {request.META.get('REMOTE_ADDR', 'unknown')}")
            return JsonResponse({"job_id": str(uuid.uuid4())})

        job_desc   = form.cleaned_data["job_description"]
        gemini_key = os.environ.get("GEMINI_API_KEY")

        if not gemini_key:
            return JsonResponse(
                {"error": "The AI analysis service is temporarily unavailable. Please try again later."},
                status=503,
            )

        job_id    = str(uuid.uuid4())
        cache_key = f"jfa:{job_id}"
        cache     = caches["jobfit"]
        cache.set(cache_key, {"status": "pending"}, timeout=600)

        thread = threading.Thread(
            target=run_gemini_job,
            args=(job_id, job_desc, gemini_key),
            daemon=True,
        )
        thread.start()

        return JsonResponse({"job_id": job_id})

    return render(request, "job_fit_analyzer.html", context)


@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def job_fit_analyzer_status(request, job_id):
    """
    Polling endpoint called by the client every 3 seconds.
    Each GET completes in ~10ms, resetting Heroku's timeout clock on
    every call while the background thread runs without restriction.
    """
    from django.core.cache import caches
    cache = caches["jobfit"]
    from django.http import JsonResponse

    cache_key = f"jfa:{job_id}"
    job       = cache.get(cache_key)

    if job is None:
        return JsonResponse(
            {"status": "error", "message": "Job expired or not found. Please submit the form again."},
            status=404,
        )

    if job["status"] == "complete":
        # Single-use: evict from cache immediately after delivery.
        cache.delete(cache_key)
        return JsonResponse({"status": "complete", "html": job["html"]})

    if job["status"] == "error":
        cache.delete(cache_key)
        return JsonResponse({"status": "error", "message": job.get("message", "An error occurred.")})

    # Still pending — client will poll again in 3 seconds.
    return JsonResponse({"status": "pending"})