# views/views_space_tools.py
#
# ============================================================================
# Space & Astronomy Toolkit — View Layer
# ============================================================================
# Contains all Django view functions for the Space & Astronomy Toolkit category.
# All orbital mechanics, ephemeris calculations, and timezone resolution are
# delegated to per-utility modules; these views are thin HTTP adapters.
#
# Tools in this module:
#   space_and_astronomy      — Hub/landing page for the whole category
#   iss_tracker              — Real-time ISS position + next visible pass events
#   satellite_pass_predictor — TLE-based satellite rise/culminate/set predictor
#   lunar_phase_calendar     — Monthly lunar phase grid with optional rise/set times
#   night_sky_planner        — Comprehensive dark-window, planet, and satellite report
#
# Private helpers (not exported from __init__.py):
#   _format_local_times      — Converts UTC datetimes in night_sky_planner
#                              results to the observer's local timezone
#
# ============================================================================
# DEPENDENCY OVERVIEW
# ============================================================================
# These views use some of the heaviest scientific libraries on the site:
#
#   skyfield          — High-precision satellite and planet ephemeris
#   pyephem / ephem   — Lunar phase and rise/set calculations (lunar_phase_calendar)
#   timezonefinder    — Reverse-geocodes a lat/lon to an IANA timezone name
#   zoneinfo          — Stdlib timezone conversion (Python 3.9+)
#
# Because these imports are expensive (skyfield loads a timescale binary;
# timezonefinder optionally loads a shapefile), they are always deferred to
# inside the view function body rather than imported at module scope.  The
# ISS tracker documents this most explicitly — see its inline comments.
#
# ============================================================================
# NOTE ON _format_local_times
# ============================================================================
# This helper is defined at the bottom of this module and is called only by
# night_sky_planner.  It is NOT listed in __init__.py's re-exports because
# it is an implementation detail of one view function, not a public API.
# Prefixing it with `_` communicates this intent.
# ============================================================================

from django.shortcuts import render
from django.views.decorators.cache import cache_control
from django.views.decorators.csrf import ensure_csrf_cookie

from ..decorators import trim_memory_after


# ===========================================================================
# Space & Astronomy Toolkit Hub
# ===========================================================================
# Static landing page — card grid linking to each space/astronomy tool.
# @ensure_csrf_cookie primes the CSRF token for any JS-driven requests made
# from navigation or quick-action widgets on the hub page.
# ===========================================================================

@trim_memory_after
@ensure_csrf_cookie
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def space_and_astronomy(request):
    return render(request, "projects/space_and_astronomy.html")


# ===========================================================================
# ISS Tracker
# ===========================================================================
# Tracks the International Space Station and shows:
#   - Current position (latitude, longitude, altitude, speed)
#   - What region/ocean/country the ISS is currently over
#   - Next 24 hours of visible pass events (Rise, Culminate, Set) for the
#     observer's location, in local time
#
# ── ARCHITECTURE ────────────────────────────────────────────────────────────
# GET  → renders an empty WeatherForm (shared ZIP-code field) with no heavy
#        imports.  The page loads instantly; the user supplies a ZIP code and
#        submits the form to trigger the actual tracking calculation.
#
# POST → validates the ZIP code, geocodes it via the local ZIP dataset,
#        fetches TLE data from Celestrak (with 1-hour caching), runs the
#        Skyfield orbital mechanics, converts event times to local timezone,
#        and renders the results.
#
# ── MEMORY MANAGEMENT ───────────────────────────────────────────────────────
# This view manages memory very explicitly because skyfield's EarthSatellite
# and timescale objects hold significant RAM.  After the response is assembled:
#   1. `del` is called on the large objects individually
#   2. gc.collect() runs a full collection pass
#   3. malloc_trim(0) asks libc to return freed pages to the OS
#
# These steps are all wrapped in separate try/except blocks so a failure in
# cleanup (e.g. on a non-Linux platform where libc.so.6 isn't available) does
# not suppress the actual response.
#
# ── TLE CACHING ─────────────────────────────────────────────────────────────
# TLE (Two-Line Element) data from Celestrak is cached for 3600 seconds (1 hr)
# using Django's cache framework.  TLEs are good for several days, so 1 hour
# is conservative.  The ISS (ZARYA) element set is extracted by name from the
# stations.txt file, which contains multiple satellites.
#
# ── HEAVY IMPORT STRATEGY ───────────────────────────────────────────────────
# All heavy imports (skyfield, timezonefinder, zoneinfo, requests, gc, ctypes)
# are deferred inside the POST branch.  The GET path has zero heavy-library
# imports; worker fork memory stays lean.
#
# ── TIMEZONE RESOLUTION ─────────────────────────────────────────────────────
# TimezoneFinder is instantiated with in_memory=False ("lite mode") to keep
# shapefiles on disk rather than loading them into RAM.  This trades a small
# amount of lookup latency for significantly lower peak memory usage per request.
#
# ── CONTEXT KEYS on success ──────────────────────────────────────────────────
#   form           — bound WeatherForm (for re-rendering the ZIP input)
#   current_data   — dict: latitude, longitude, altitude, velocity, region
#   iss_pass_times — list of dicts: event, date (local), time (local), position
# ===========================================================================

@trim_memory_after
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def iss_tracker(request):
    from ..iss_utils import detect_region
    from ..zip_data import local_get_coordinates as get_coordinates
    from django.core.cache import cache
    from datetime import timedelta
    # WeatherForm is reused here because it's a simple single-field ZIP form;
    # the ISS tracker doesn't need a dedicated form class.
    from ..forms import WeatherForm

    form           = WeatherForm(request.POST or None)
    current_data   = {}
    iss_pass_times = []

    if request.method == "POST" and form.is_valid():
        # ── Heavy imports — deferred to POST path only ──────────────────────
        from zoneinfo import ZoneInfo
        from timezonefinder import TimezoneFinder
        from skyfield.api import load, Topos
        from skyfield.sgp4lib import EarthSatellite
        import requests, gc, ctypes

        zip_code = form.cleaned_data["zip_code"]
        coords   = get_coordinates(zip_code)
        if not coords:
            return render(
                request,
                "projects/iss_tracker.html",
                {"form": form, "error": "Could not determine coordinates."},
            )

        lat, lon = coords

        # ── Fetch (or retrieve cached) TLE text ─────────────────────────────
        # cache.get_or_set() returns the cached value if the key exists, or
        # calls the lambda, stores its result, and returns it.  TTL = 3600s.
        def _fetch_tle_text():
            r = requests.get(
                "https://celestrak.org/NORAD/elements/stations.txt", timeout=10
            )
            r.raise_for_status()
            return r.text

        tle_text = cache.get_or_set("tle_data_text", _fetch_tle_text, 3600)

        # ── Extract ISS (ZARYA) TLE lines from the multi-satellite file ──────
        # stations.txt contains many objects; the ISS entry is identified by
        # its canonical name "ISS (ZARYA)" followed by the two TLE data lines.
        line1 = line2 = None
        lines = tle_text.splitlines()
        for i, line in enumerate(lines):
            if line.strip() == "ISS (ZARYA)":
                line1, line2 = lines[i + 1], lines[i + 2]
                break

        if not line1 or not line2:
            # This would only happen if Celestrak changed the station name.
            return render(
                request,
                "projects/iss_tracker.html",
                {"form": form, "error": "ISS TLE not found."},
            )

        # ── Skyfield orbital mechanics ───────────────────────────────────────
        ts        = load.timescale()
        satellite = EarthSatellite(line1, line2, "ISS (ZARYA)", ts)
        observer  = Topos(latitude_degrees=lat, longitude_degrees=lon)

        now      = ts.now()
        end_time = ts.utc(now.utc_datetime() + timedelta(days=1))

        # find_events() returns parallel arrays: times[] and events[].
        # event codes: 0=Rise above horizon, 1=Culminate (max elevation), 2=Set
        times, events = satellite.find_events(
            observer, now, end_time, altitude_degrees=10.0
        )

        # ── Current ISS position ─────────────────────────────────────────────
        geocentric = satellite.at(now)
        subpoint   = geocentric.subpoint()

        # Compute scalar speed from the 3D velocity vector (km/s components).
        v     = geocentric.velocity.km_per_s
        speed = (v[0] * v[0] + v[1] * v[1] + v[2] * v[2]) ** 0.5

        region = detect_region(
            subpoint.latitude.degrees, subpoint.longitude.degrees
        )

        current_data = {
            "latitude":  f"{subpoint.latitude.degrees:.2f}°",
            "longitude": f"{subpoint.longitude.degrees:.2f}°",
            "altitude":  f"{subpoint.elevation.km:.2f} km",
            "velocity":  f"{speed:.2f} km/s",
            "region":    region,
        }

        # ── Timezone resolution for pass event times ─────────────────────────
        # in_memory=False = lite mode: keeps shapefiles on disk, lower RSS.
        tf       = TimezoneFinder(in_memory=False)
        tzname   = tf.timezone_at(lat=lat, lng=lon) or "UTC"
        local_tz = ZoneInfo(tzname)

        for t, event in zip(times, events):
            name       = ("Rise", "Culminate", "Set")[event]  # decode event code
            local_time = t.utc_datetime().astimezone(local_tz)
            iss_pass_times.append({
                "event": name,
                "date":  local_time.strftime("%A, %B %d"),
                "time":  local_time.strftime("%I:%M %p %Z"),
                # Rough compass bearing: if ISS ground track is north of observer,
                # it's approaching from the south and the pass is "North".
                "position": (
                    "North"
                    if satellite.at(t).subpoint().latitude.degrees > lat
                    else "South"
                ),
            })

        # ── Explicit memory cleanup ───────────────────────────────────────────
        # Delete the largest objects individually before gc runs so the
        # reference counts drop and cyclic garbage is minimised.
        try:
            del satellite, geocentric, subpoint, lines, tle_text, ts, tf
        except Exception:
            pass
        try:
            gc.collect()
            ctypes.CDLL("libc.so.6").malloc_trim(0)
        except Exception:
            pass

        return render(
            request,
            "projects/iss_tracker.html",
            {
                "form":           form,
                "current_data":   current_data,
                "iss_pass_times": iss_pass_times,
            },
        )

    # GET — render the empty form; no heavy libraries loaded.
    return render(
        request,
        "projects/iss_tracker.html",
        {"form": form, "current_data": current_data},
    )


# ===========================================================================
# Satellite Pass Predictor
# ===========================================================================
# Predicts when a named satellite (ISS, Hubble, NOAA-15, Starlink chains, etc.)
# will be visible from a given location over the next several days.
#
# The satellite catalog lives in satellite_pass_predictor_utils.  Each entry
# maps a human-readable name to a NORAD catalog number used to fetch the
# correct TLE from Celestrak.
#
# `get_satellite_groups()` returns the catalog grouped by category (Space
# Stations, Earth Observation, Navigation, etc.) for the template to render
# as an <optgroup> select menu.
#
# GEOCODING:
#   ZIP → (lat, lon) via the local ZIP dataset (same as ISS tracker and weather).
#   If geocoding fails, an error is shown and no prediction is attempted.
#
# RESULT STRUCTURE (on success):
#   result["passes"] — list of pass dicts: rise, culminate, set times (UTC),
#                      max elevation, and start/end azimuth.
#   result["error"]  — present if the TLE fetch or prediction failed.
#
# GET  → empty SatellitePassForm + satellite_groups for the select menu.
# POST → validates; geocodes ZIP; calls predict_passes(); renders results or error.
# ===========================================================================

@trim_memory_after
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def satellite_pass_predictor(request):
    from ..forms import SatellitePassForm
    from ..satellite_pass_predictor_utils import predict_passes, get_satellite_groups
    from ..zip_data import local_get_coordinates as get_coordinates

    form   = SatellitePassForm()
    result = None
    error  = None

    if request.method == "POST":
        form = SatellitePassForm(request.POST)
        if form.is_valid():
            satellite_name = form.cleaned_data["satellite"]
            zip_code       = form.cleaned_data["zip_code"]

            coords = get_coordinates(zip_code)
            if not coords:
                error = (
                    "Could not determine coordinates for that ZIP code. "
                    "This is a Google Maps Platform API error."
                )
            else:
                lat, lon = coords
                result = predict_passes(satellite_name, lat, lon)
                # predict_passes() returns an error key when TLE fetch or
                # skyfield propagation fails; surface it as the top-level error.
                if result.get("error"):
                    error = result["error"]

    context = {
        "form":             form,
        "result":           result,
        "error":            error,
        "satellite_groups": get_satellite_groups(),  # always loaded for select menu
    }
    return render(request, "projects/satellite_pass_predictor.html", context)


# ===========================================================================
# Lunar Phase Calendar
# ===========================================================================
# Renders a month-view calendar grid where each day cell shows:
#   - The moon's illumination percentage
#   - The named phase (New Moon, Waxing Crescent, First Quarter, etc.)
#   - An emoji/icon representing the phase
#   - Optionally: moonrise and moonset times for the observer's location
#
# Rise/set times require a known lat/lon and timezone, so they are only
# calculated when the user provides a ZIP code.  Phase data (illumination,
# phase name) is always calculated; it doesn't depend on location.
#
# GEOCODING (optional):
#   geocode_zip() in lunar_phase_calendar_utils wraps the local ZIP dataset
#   and returns (lat, lon, city, state, tz_name) or None.
#   If the ZIP fails, the calendar still renders with phase data only and
#   a non-fatal warning message is shown.
#
# GET  → current month, phase data only, no ZIP needed, no location label.
# POST → user-selected month/year; optional ZIP for rise/set times.
#        If ZIP geocoding fails: error message, phase-only calendar.
#        If calendar calculation fails: error message, no calendar.
#
# CONTEXT KEYS:
#   form           — LunarPhaseCalendarForm
#   calendar_data  — list of week lists of day dicts (from build_month_calendar)
#   location_label — "City, ST (ZIP)" string or None
#   error          — non-fatal warning or fatal error string, or None
# ===========================================================================

@trim_memory_after
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def lunar_phase_calendar(request):
    from datetime import date
    from ..forms import LunarPhaseCalendarForm
    from ..lunar_phase_calendar_utils import build_month_calendar, geocode_zip

    today = date.today()

    # Pre-populate the form with the current month/year for the GET case.
    form = LunarPhaseCalendarForm(
        request.POST or None,
        initial={"month": today.month, "year": today.year},
    )

    context = {
        "form":           form,
        "calendar_data":  None,
        "location_label": None,
        "error":          None,
    }

    if request.method == "POST" and form.is_valid():
        month    = form.cleaned_data["month"]
        year     = form.cleaned_data["year"]
        zip_code = form.cleaned_data["zip_code"]

        lat = lon = tz_name = None
        location_label = None

        # Attempt geocoding only if the user provided a ZIP code.
        if zip_code:
            geo = geocode_zip(zip_code)
            if geo:
                lat, lon, city, state, tz_name = geo
                location_label = f"{city}, {state} ({zip_code})"
            else:
                # Geocoding failed — still render the calendar without times.
                # This is a non-fatal warning, not a hard error.
                context["error"] = (
                    f'ZIP code "{zip_code}" could not be located. '
                    "Showing phase data without rise/set times."
                )

        try:
            context["calendar_data"] = build_month_calendar(
                year=year, month=month,
                lat=lat, lon=lon,
                # Fall back to UTC if timezone wasn't resolved.
                tz_name=tz_name or "UTC",
            )
            context["location_label"] = location_label
        except Exception as exc:
            context["error"] = f"Calendar calculation failed: {exc}"

    else:
        # GET (or invalid POST) — render the current month with phase data only.
        try:
            context["calendar_data"] = build_month_calendar(
                year=today.year, month=today.month,
                # No lat/lon → no rise/set times.
            )
        except Exception as exc:
            context["error"] = f"Could not load calendar: {exc}"

    return render(request, "projects/lunar_phase_calendar.html", context)


# ===========================================================================
# Night Sky Planner
# ===========================================================================
# Provides a comprehensive observing session report for a given ZIP code and
# date (defaulting to tonight), including:
#   - Sunset, astronomical twilight end/start, sunrise times
#   - Dark-window duration (the period of truly dark sky)
#   - Golden hour times for photography
#   - Moon phase, moonrise, and moonset
#   - Visible planet positions and rise/set times
#   - Upcoming bright satellite passes (ISS, etc.)
#
# All of the above comes from get_night_sky_report() in night_sky_utils.
# The datetimes in the report are UTC.  _format_local_times() (defined below)
# converts them to the observer's local timezone for display.
#
# DUAL INPUT METHOD:
#   This view supports both POST and GET with query parameters:
#     POST ?zip_code=XXXXX → standard HTML form submission
#     GET  ?zip_code=XXXXX → shareable/bookmarkable URL
#   The same form class (NightSkyPlannerForm) validates both.  If neither
#   provides a valid zip_code, the empty form is rendered.
#
# CONTEXT KEYS on success:
#   form        — NightSkyPlannerForm (bound)
#   report      — raw report dict from night_sky_utils (contains UTC datetimes)
#   local_times — dict of formatted local-time strings from _format_local_times()
#                 (note: _format_local_times also mutates report["satellites"]
#                  in-place, adding local_rise_time / local_max_alt_time / local_set_time)
#   error       — None on success, or an error string
# ===========================================================================

@trim_memory_after
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def night_sky_planner(request):
    from ..forms import NightSkyPlannerForm
    from ..night_sky_utils import get_night_sky_report

    form        = NightSkyPlannerForm()
    report      = None
    error       = None
    local_times = {}

    # Resolve zip_code from either POST body or GET query string.
    zip_code = None
    if request.method == "POST":
        form = NightSkyPlannerForm(request.POST)
        if form.is_valid():
            zip_code = form.cleaned_data["zip_code"]
    elif request.method == "GET" and "zip_code" in request.GET:
        # Shareable URL support: GET /night-sky/?zip_code=53563
        form = NightSkyPlannerForm(request.GET)
        if form.is_valid():
            zip_code = form.cleaned_data["zip_code"]

    if zip_code:
        report = get_night_sky_report(zip_code)
        if not report.get("success"):
            # The util signals failure via success=False + an "error" key.
            error  = report.get("error", "An unexpected error occurred.")
            report = None  # don't pass a failed report to the template
        else:
            # Convert all UTC datetimes to local-time display strings.
            local_times = _format_local_times(report)

    context = {
        "form":        form,
        "report":      report,
        "error":       error,
        "local_times": local_times,
    }
    return render(request, "projects/night_sky_planner.html", context)


# ============================================================================
# Private Helper — _format_local_times
# ============================================================================
# Called only by night_sky_planner.  Converts UTC datetime objects in the
# report dict to formatted local-time strings in the observer's timezone.
#
# MUTATES REPORT IN PLACE:
#   For each dict in report["satellites"], three keys are added:
#     "local_rise_time"    — formatted rise time string
#     "local_max_alt_time" — formatted culmination time string
#     "local_set_time"     — formatted set time string
#   This avoids a separate template iteration to resolve satellite times.
#
# RETURN VALUE:
#   A flat dict mapping time-slot names to formatted strings, consumed by
#   the template to populate the event timeline.  Keys are:
#     sunset, sunrise, civil_twilight_end/start, nautical_twilight_end/start,
#     astro_twilight_end/start, dark_window_start/end,
#     golden_hour_evening_start/end, golden_hour_morning_start/end,
#     moonrise, moonset
#
# FORMAT STRINGS:
#   time_fmt = "%I:%M %p"      → e.g. "07:42 PM"  (leading zero stripped)
#   full_fmt  = "%I:%M %p %Z"  → e.g. "07:42 PM CST" (for key sunset/sunrise)
#   lstrip("0") removes the leading zero so "07:42" displays as "7:42".
#
# TIMEZONE RESOLUTION:
#   The timezone name is stored in report["timezone"] (set by night_sky_utils).
#   ZoneInfo is used for conversion.  An unknown timezone name falls back to UTC.
# ============================================================================

def _format_local_times(report):
    """
    Convert UTC datetimes in the night-sky report to the location's local tz.
    Returns a dict of formatted time strings consumed by the template.
    Also mutates each satellite-pass dict in report["satellites"] in place.
    """
    import zoneinfo
    from datetime import timezone

    tz_name = report.get("timezone", "UTC")
    try:
        tz = zoneinfo.ZoneInfo(tz_name)
    except zoneinfo.ZoneInfoNotFoundError:
        # Fallback to UTC if the timezone name from the utils is unrecognised.
        tz = timezone.utc

    time_fmt = "%I:%M %p"      # e.g. "07:42 PM"
    full_fmt  = "%I:%M %p %Z"  # e.g. "07:42 PM CST" — used for sunset/sunrise

    def fmt(dt, use_full=False):
        """
        Format a single UTC datetime as a local time string.
        Returns "N/A" if dt is None (event doesn't occur on this date,
        e.g. midnight sun or polar night situations for moonrise/set).
        """
        if dt is None:
            return "N/A"
        local_dt = dt.astimezone(tz)
        try:
            formatted = local_dt.strftime(full_fmt if use_full else time_fmt)
            return formatted.lstrip("0")  # "07:42 PM" → "7:42 PM"
        except ValueError:
            # strftime fails on some platforms for out-of-range years;
            # fall back to ISO format as a safe display value.
            return local_dt.isoformat()

    twilight = report.get("twilight", {})
    moon     = report.get("moon", {})

    times = {
        # ── Sunset / Sunrise (shown with timezone abbreviation) ────────────
        "sunset":  fmt(twilight.get("sunset"),  use_full=True),
        "sunrise": fmt(twilight.get("sunrise"), use_full=True),

        # ── Twilight boundaries (no tz label needed — all same session) ────
        "civil_twilight_end":      fmt(twilight.get("civil_twilight_end")),
        "civil_twilight_start":    fmt(twilight.get("civil_twilight_start")),
        "nautical_twilight_end":   fmt(twilight.get("nautical_twilight_end")),
        "nautical_twilight_start": fmt(twilight.get("nautical_twilight_start")),
        "astro_twilight_end":      fmt(twilight.get("astro_twilight_end")),
        "astro_twilight_start":    fmt(twilight.get("astro_twilight_start")),

        # ── Truly dark window (astro twilight end → start) ─────────────────
        "dark_window_start": fmt(twilight.get("dark_window_start"), use_full=True),
        "dark_window_end":   fmt(twilight.get("dark_window_end"),   use_full=True),

        # ── Golden hour — photography / landscape windows ──────────────────
        "golden_hour_evening_start":  fmt(twilight.get("golden_hour_evening_start")),
        "golden_hour_evening_end":    fmt(twilight.get("golden_hour_evening_end")),
        "golden_hour_morning_start":  fmt(twilight.get("golden_hour_morning_start")),
        "golden_hour_morning_end":    fmt(twilight.get("golden_hour_morning_end")),

        # ── Moon ──────────────────────────────────────────────────────────
        "moonrise": fmt(moon.get("moonrise")),
        "moonset":  fmt(moon.get("moonset")),
    }

    # Mutate each satellite pass dict to add local formatted times in place.
    # This avoids a second pass in the template and keeps all time formatting
    # logic in one place.
    for sat_pass in report.get("satellites", []):
        sat_pass["local_rise_time"]    = fmt(sat_pass.get("rise_time"))
        sat_pass["local_max_alt_time"] = fmt(sat_pass.get("max_alt_time"))
        sat_pass["local_set_time"]     = fmt(sat_pass.get("set_time"))

    return times