# views/views_radio_tools.py
#
# ============================================================================
# Radio Hobbyist Toolkit — View Layer
# ============================================================================
# Contains all Django view functions for the Radio Hobbyist Toolkit category.
# All domain logic (band lookups, antenna math, RF exposure calculations, etc.)
# is delegated to per-utility modules; these views are thin HTTP adapters.
#
# Tools in this module:
#   radio_tools               — Hub/landing page for the whole category
#   ham_radio_call_sign_lookup— Callsign → licensee data via callook.info / HamDB
#   band_plan_checker         — Frequency → US amateur band + per-license privileges
#   repeater_finder           — 3-endpoint async repeater search along a route
#   antenna_calculator        — Element lengths for common antenna types
#   grid_square_converter     — Maidenhead locator ↔ lat/lon ↔ ZIP code
#   rf_exposure_calculator    — FCC OET-65 MPE compliance tool
#   coax_cable_loss_calculator— Matched-line loss by cable type, frequency, length
#
# ============================================================================
# ENDPOINT PATTERNS
# ============================================================================
#
# Most tools follow the standard two-state pattern:
#   GET  → render an empty form (+ optional reference data in context)
#   POST → validate the form, run the calculation, render results
#
# Three tools deviate from this:
#
#   CALLSIGN LOOKUP — single view, two external API sources with fallback:
#     Primary: callook.info (returns structured XML parsed to a dict)
#     Fallback: hamdb.org (used if callook returns INVALID status)
#     The view decides which data source's payload is "data" in context.
#
#   BAND PLAN CHECKER — adds `bands_summary` to every GET and POST response
#     so the quick-reference table is always visible regardless of whether
#     the user has submitted a frequency query.
#
#   REPEATER FINDER — three-endpoint async pipeline:
#     repeater_finder        (GET)  → renders form; no search initiated
#     repeater_finder_start  (POST) → AJAX; validates form, starts background
#                                     task, returns {"task_id": "..."} JSON
#     repeater_finder_status (GET)  → AJAX; polls task by ID, returns progress
#                                     and results JSON
#     This pattern avoids long HTTP timeouts on repeater database queries that
#     may take several seconds to resolve.
#
# ============================================================================
# IMPORT NOTE
# ============================================================================
# `requests` is imported at module scope under the alias `_requests` to avoid
# shadowing any local variable named `requests` inside view functions.  This
# is a convention used across several view modules in the project.
# ============================================================================

import requests as _requests  # aliased to avoid conflict with local vars

from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.cache import cache_control
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import ensure_csrf_cookie

from ..decorators import trim_memory_after


# ===========================================================================
# Radio Hobbyist Toolkit Hub
# ===========================================================================
# Static landing page — renders a card grid linking to each tool.
# @ensure_csrf_cookie ensures the CSRF cookie is set for any subsequent JS
# fetch() calls made from hub-level navigation widgets.
# ===========================================================================

@trim_memory_after
@ensure_csrf_cookie
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def radio_tools(request):
    return render(request, "projects/radio_tools.html")


# ===========================================================================
# Ham Radio Call Sign Lookup
# ===========================================================================
# Looks up an FCC-licensed amateur radio callsign against two public APIs:
#
#   1. callook.info (primary)
#      Returns structured licensee data (name, address, license class, grant
#      and expiry dates, Trustee info for club calls).  A "VALID" status means
#      the call was found in the FCC ULS database.
#
#   2. hamdb.org (fallback)
#      Used when callook returns a non-VALID status (expired, cancelled, or
#      not found).  HamDB sometimes has records for recently expired calls
#      that callook has already purged.  A "NOT_FOUND" messages.status means
#      the call genuinely doesn't exist in either source.
#
# Both query functions live in ham_utils.py.  This view handles the cascade
# logic and error messaging.
#
# GET  → empty CallsignLookupForm.
# POST → validates (callsign format check in the form), attempts callook,
#        falls back to HamDB if needed, sets either `data` or `error` in context.
#
# CONTEXT KEYS:
#   form   — the bound/unbound form
#   data   — dict of licensee data (None if not found or error)
#   error  — human-readable error string (None on success)
# ===========================================================================

@trim_memory_after
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def ham_radio_call_sign_lookup(request):
    from ..ham_utils import query_callook, query_hamdb
    from ..forms import CallsignLookupForm

    data  = None
    error = None
    form  = CallsignLookupForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        cs = form.cleaned_data["callsign"]
        try:
            payload = query_callook(cs)
            if payload.get("status") == "VALID":
                # callook found a valid licensee — use its data.
                data = payload
            else:
                # callook returned INVALID (expired, cancelled, etc.).
                # Try HamDB as a secondary source before giving up.
                alt = query_hamdb(cs)
                if alt.get("messages", {}).get("status") != "NOT_FOUND":
                    data = alt
                else:
                    # Neither source found the callsign.
                    # \u201c / \u201d = left/right curly quotes for display.
                    error = f"\u201c{cs}\u201d is not a valid amateur-radio call sign."
        except (_requests.Timeout, _requests.ConnectionError) as e:
            # Network-level failures (DNS, connection refused, read timeout).
            error = f"Lookup service error: {e}"

    return render(
        request,
        "projects/ham_radio_call_sign_lookup.html",
        {"form": form, "data": data, "error": error},
    )


# ===========================================================================
# Band Plan Checker
# ===========================================================================
# Determines which US amateur radio band a given frequency (in MHz) falls
# into, what operating modes are permitted in that segment, and whether a
# specific license class (Technician, General, Amateur Extra) has transmit
# privileges there.
#
# The band data lives in band_plan_utils.py and is sourced from the ARRL/FCC
# Part 97 band plan.
#
# GET  → empty BandPlanForm + full bands_summary reference table.
# POST → validates form (frequency range check), calls lookup_frequency(),
#        injects `result` dict into context.  bands_summary is always present
#        so the quick-reference table shows on both GET and POST responses.
#
# CONTEXT KEYS:
#   form          — bound/unbound BandPlanForm
#   result        — lookup result dict (None on GET or invalid POST)
#   bands_summary — list of all band dicts for the reference table
#   page_title    — SEO / <title> tag string
#   page_description — meta description string
# ===========================================================================

@trim_memory_after
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def band_plan_checker(request):
    from ..forms import BandPlanForm
    from ..band_plan_utils import lookup_frequency, get_all_bands_summary

    form          = BandPlanForm()
    result        = None
    bands_summary = get_all_bands_summary()  # always loaded; shown as reference table

    if request.method == "POST":
        form = BandPlanForm(request.POST)
        if form.is_valid():
            freq = form.cleaned_data["frequency"]
            # license_class is optional; None means "show all classes"
            lc   = form.cleaned_data.get("license_class") or None
            result = lookup_frequency(freq, license_class=lc)

    context = {
        "form":          form,
        "result":        result,
        "bands_summary": bands_summary,
        "page_title": (
            "Band Plan Checker — US Amateur Radio Frequency Privileges"
        ),
        "page_description": (
            "Enter any frequency to instantly see which US amateur band it "
            "falls in, what modes are permitted, and whether your license "
            "class grants transmit privileges."
        ),
    }
    return render(request, "projects/band_plan_checker.html", context)


# ===========================================================================
# Repeater Finder  (3 endpoints)
# ===========================================================================
# Finds amateur radio repeaters along a route between two US ZIP codes.
# Because the repeater database query can take several seconds (geocoding +
# remote API calls + filtering), it is handled asynchronously:
#
#   ENDPOINT 1 — repeater_finder (GET)
#     Renders the main form page with an empty RepeaterFinderForm.
#     The form collects origin ZIP, destination ZIP, search radius (miles),
#     and one or more band selections (2m, 70cm, etc.).
#     No search is initiated here; the JS on the page handles that via AJAX.
#
#   ENDPOINT 2 — repeater_finder_start (POST, AJAX)
#     Receives the serialized form data via AJAX.
#     Validates the form server-side.
#     If valid: calls repeater_finder_utils.start_search_task() which spins
#       up a background task (threading/Celery) and returns a task_id UUID.
#       Returns {"status": "ok", "task_id": "<uuid>"} JSON.
#     If invalid: returns {"status": "error", "errors": {...}} JSON with
#       HTTP 400 so the JS can surface field-level validation messages.
#
#   ENDPOINT 3 — repeater_finder_status (GET, AJAX)
#     Polls the status of a running task by task_id.
#     Returns the task's current state dict from repeater_finder_utils,
#     which includes a "status" field ("pending" / "complete" / "error")
#     and, when complete, the repeater results list.
#     Returns HTTP 404 if the task_id is unknown or expired.
# ===========================================================================

@trim_memory_after
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def repeater_finder(request):
    """Renders the main Repeater Finder page with an empty form."""
    from ..forms import RepeaterFinderForm

    form = RepeaterFinderForm()
    return render(request, "projects/repeater_finder.html", {"form": form})


@require_POST  # Hard-enforces POST-only; returns 405 for any other method.
def repeater_finder_start(request):
    """
    AJAX endpoint: validates the form and starts the background search task.

    Returns JSON — the caller (JS) should check `response.status` before
    reading `task_id`.  HTTP 400 is returned on form validation failure;
    HTTP 500 on an unexpected server error.
    """
    from ..forms import RepeaterFinderForm
    from .. import repeater_finder_utils

    form = RepeaterFinderForm(request.POST)

    if form.is_valid():
        try:
            origin  = form.cleaned_data["origin_zip"]
            dest    = form.cleaned_data["dest_zip"]
            radius  = form.cleaned_data["search_radius"]
            bands   = form.cleaned_data["bands"]   # list of strings, e.g. ["2m", "70cm"]

            task_id = repeater_finder_utils.start_search_task(
                origin, dest, radius, bands
            )
            return JsonResponse({"status": "ok", "task_id": task_id})
        except Exception as e:
            return JsonResponse(
                {"status": "error", "message": str(e)}, status=500
            )
    else:
        # Return field-level validation errors so JS can annotate the form.
        return JsonResponse(
            {"status": "error", "errors": form.errors}, status=400
        )


def repeater_finder_status(request, task_id):
    """
    AJAX polling endpoint: returns the current state of a search task.

    task_id is captured from the URL pattern, e.g.:
        path("repeater-finder/status/<str:task_id>/", views.repeater_finder_status)

    The returned dict always contains a "status" key.  When status is
    "complete" it also contains the repeater results list.
    """
    from .. import repeater_finder_utils

    status = repeater_finder_utils.get_task_status(task_id)
    if not status:
        return JsonResponse(
            {"status": "error", "message": "Task not found"}, status=404
        )
    return JsonResponse(status)


# ===========================================================================
# Antenna Length Calculator
# ===========================================================================
# Calculates the physical element lengths for common amateur antenna designs
# given an operating frequency and antenna type.  Supported types typically
# include half-wave dipole, quarter-wave vertical, 5/8-wave vertical, and
# Yagi-Uda elements.  A velocity factor can be specified for wire-in-coax or
# mobile whip calculations.
#
# `QUICK_PICK_FREQUENCIES` is a list of common amateur frequencies (with band
# labels) imported from antenna_calculator_utils and injected into context so
# the template can render a one-click frequency selector.
#
# GET  → empty AntennaCalculatorForm + quick_picks reference.
# POST → validates; calls antenna_calculator_utils.calculate_antenna();
#        result dict contains element lengths in inches, feet, and centimeters.
# ===========================================================================

@trim_memory_after
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def antenna_calculator(request):
    from ..forms import AntennaCalculatorForm
    from ..antenna_calculator_utils import calculate_antenna, QUICK_PICK_FREQUENCIES

    form   = AntennaCalculatorForm()
    result = None

    if request.method == "POST":
        form = AntennaCalculatorForm(request.POST)
        if form.is_valid():
            result = calculate_antenna(
                frequency_mhz=form.cleaned_data["frequency"],
                antenna_type=form.cleaned_data["antenna_type"],
                # velocity_factor is optional; None tells the util to use
                # the default free-space value of 1.0 (or antenna-specific default).
                velocity_factor=form.cleaned_data.get("velocity_factor"),
            )

    context = {
        "form":        form,
        "result":      result,
        "quick_picks": QUICK_PICK_FREQUENCIES,  # pre-defined list for UI buttons
    }
    return render(request, "projects/antenna_calculator.html", context)


# ===========================================================================
# Grid Square Converter
# ===========================================================================
# Converts between three representations of a geographic location used in
# amateur radio:
#
#   MODE 1 — grid_to_coords:
#     Maidenhead locator (e.g. "EN52") → decimal lat/lon center point.
#     Precision determines how many character pairs are decoded (2=field,
#     4=square, 6=subsquare, 8=extended).
#
#   MODE 2 — coords_to_grid:
#     Decimal lat/lon → Maidenhead locator at the requested precision.
#
#   MODE 3 — zip_to_grid:
#     US ZIP code → geocoded lat/lon (via local dataset) → Maidenhead locator.
#     Uses the same local ZIP dataset as the weather and ISS tracker tools.
#
# The conversion mode is selected via a radio/select field on the form.
# Because all three modes share the same form page, the template conditionally
# shows/hides input groups with JS based on the selected mode.
#
# `PRECISION_TABLE` is a reference list (characters → area coverage → use case)
# injected into context so the template can render a precision guide table.
#
# GET  → empty GridSquareForm + precision_table reference.
# POST → validates; dispatches to the appropriate converter; injects result.
#
# CONTEXT KEYS:
#   form            — bound/unbound form
#   result          — conversion result dict (None on GET)
#   conversion_mode — echoed back to template to drive result section rendering
#   precision_table — reference table data from grid_square_utils
# ===========================================================================

@trim_memory_after
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def grid_square_converter(request):
    from ..forms import GridSquareForm
    from ..grid_square_utils import (
        grid_to_coordinates,
        coordinates_to_grid,
        zip_to_grid,
        PRECISION_TABLE,
    )
    # local_get_coordinates returns (lat, lon) tuple or None for a ZIP code.
    from ..zip_data import local_get_coordinates as get_coordinates

    form            = GridSquareForm()
    result          = None
    conversion_mode = None

    if request.method == "POST":
        form = GridSquareForm(request.POST)
        if form.is_valid():
            conversion_mode = form.cleaned_data["conversion_mode"]
            precision       = form.cleaned_data["precision"]

            if conversion_mode == "grid_to_coords":
                grid   = form.cleaned_data["grid_square"].strip()
                result = grid_to_coordinates(grid)

            elif conversion_mode == "coords_to_grid":
                lat    = form.cleaned_data["latitude"]
                lon    = form.cleaned_data["longitude"]
                result = coordinates_to_grid(lat, lon, precision=precision)

            elif conversion_mode == "zip_to_grid":
                zip_code = form.cleaned_data["zip_code"].strip()
                # zip_to_grid takes the geocoder function as a parameter so it
                # can be swapped out in tests without monkeypatching.
                result   = zip_to_grid(zip_code, get_coordinates)

    context = {
        "form":            form,
        "result":          result,
        "conversion_mode": conversion_mode,
        "precision_table": PRECISION_TABLE,
    }
    return render(request, "projects/grid_square_converter.html", context)


# ===========================================================================
# RF Exposure Calculator
# ===========================================================================
# Evaluates FCC Part 97 / OET Bulletin 65 RF exposure compliance for an
# amateur station.  Calculates:
#   - Maximum Permissible Exposure (MPE) power density limit (mW/cm²)
#     at a given distance and frequency.
#   - Actual power density from the station's ERP (effective radiated power),
#     accounting for transmitter power, antenna gain, feed line loss, and
#     transmit duty cycle.
#   - Whether the station is within the Controlled (occupational) and
#     Uncontrolled (general public) MPE zones.
#   - Minimum safe distance for each zone if the station exceeds the limit.
#
# GAIN REFERENCE:
#   Antenna gain can be specified in dBi (isotropic) or dBd (relative to a
#   dipole, where 1 dBd ≈ 2.15 dBi).  The form collects both the value and
#   the reference standard; rf_exposure_utils handles the conversion.
#
# DUTY CYCLE:
#   Mode selections (CW, SSB, FM, FT8, etc.) map to pre-defined duty cycle
#   percentages.  The "custom" mode exposes an additional field for arbitrary
#   duty cycle input.
#
# `EXAMPLE_SCENARIOS` is a list of pre-configured station profiles (100W FM
# on 2m, 1500W HF dipole, etc.) injected into context for the reference table.
#
# GET  → empty RFExposureForm + examples reference.
# POST → validates; calls rf_exposure_utils.calculate_rf_exposure(); result
#        contains MPE limits, actual power density, compliance status, and
#        minimum safe distances.
# ===========================================================================

@trim_memory_after
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def rf_exposure_calculator(request):
    from ..forms import RFExposureForm
    from ..rf_exposure_utils import calculate_rf_exposure, EXAMPLE_SCENARIOS

    form   = RFExposureForm()
    result = None

    if request.method == "POST":
        form = RFExposureForm(request.POST)
        if form.is_valid():
            result = calculate_rf_exposure(
                power_watts=form.cleaned_data["power_watts"],
                gain_value=form.cleaned_data["gain_value"],
                gain_reference=form.cleaned_data["gain_reference"],  # "dBi" or "dBd"
                frequency_mhz=form.cleaned_data["frequency_mhz"],
                distance_value=form.cleaned_data["distance_value"],
                distance_unit=form.cleaned_data["distance_unit"],    # "ft" or "m"
                mode=form.cleaned_data["mode"],                      # "FM", "SSB", etc.
                # custom_duty_cycle is only set when mode == "custom"
                custom_duty_cycle=form.cleaned_data.get("custom_duty_cycle"),
                # feed_line_loss_db defaults to 0 (lossless feedline) if omitted
                feed_line_loss_db=form.cleaned_data.get("feed_line_loss_db") or 0.0,
            )

    context = {
        "form":     form,
        "result":   result,
        "examples": EXAMPLE_SCENARIOS,
    }
    return render(request, "projects/rf_exposure_calculator.html", context)


# ===========================================================================
# Coax Cable Loss Calculator
# ===========================================================================
# Calculates the matched-line (no-SWR) insertion loss for a run of coaxial
# cable at a given frequency, and optionally the additional loss introduced
# by a mismatch (SWR > 1).
#
# Cable types are defined in coax_calculator_utils with per-cable attenuation
# data (dB/100ft at standard test frequencies); the util interpolates between
# tabulated frequencies.
#
# OPTIONAL INPUTS:
#   power_watts — if provided, the util also calculates power delivered to the
#                 antenna vs. power lost as heat in the feedline.
#   swr         — if provided, total loss including mismatch loss is calculated.
#
# `EXAMPLE_SCENARIOS` is a list of representative coax runs (LMR-400 at HF,
# RG-58 at 2m, etc.) injected into context for the reference table.
#
# GET  → empty CoaxCableLossForm + examples reference.
# POST → validates; calls coax_calculator_utils.calculate_coax_loss(); result
#        contains matched-line loss, mismatch loss (if SWR given), and power
#        budget (if power given).
# ===========================================================================

@trim_memory_after
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def coax_cable_loss_calculator(request):
    from ..forms import CoaxCableLossForm
    from ..coax_calculator_utils import calculate_coax_loss, EXAMPLE_SCENARIOS

    form   = CoaxCableLossForm()
    result = None

    if request.method == "POST":
        form = CoaxCableLossForm(request.POST)
        if form.is_valid():
            result = calculate_coax_loss(
                cable_type=form.cleaned_data["cable_type"],
                frequency_mhz=form.cleaned_data["frequency_mhz"],
                length_value=form.cleaned_data["length_value"],
                length_unit=form.cleaned_data["length_unit"],    # "ft" or "m"
                # Optional; None means "skip power budget calculation"
                power_watts=form.cleaned_data.get("power_watts"),
                # Optional; None means "skip mismatch loss calculation"
                swr=form.cleaned_data.get("swr"),
            )

    context = {
        "form":     form,
        "result":   result,
        "examples": EXAMPLE_SCENARIOS,
    }
    return render(request, "projects/coax_cable_loss_calculator.html", context)