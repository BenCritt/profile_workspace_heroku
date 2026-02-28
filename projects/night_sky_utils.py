"""
Utility functions for the Night Sky Planner.

Provides astronomical calculations including twilight times, golden hour,
moon phase/illumination/rise/set, satellite pass predictions, and an
overall stargazing quality rating. Uses the ephem library for all
astronomical computations (Jean Meeus algorithms).

Geocoding reuses the existing Google Maps Geocoding API with Django's
cache framework to minimize API calls.
"""

import ephem
import math
import requests
import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from django.core.cache import cache

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Cache TTL values (seconds)
TLE_CACHE_TTL = 60 * 60 * 12           # 12 hours – TLEs update ~twice daily
RESULTS_CACHE_TTL = 60 * 15            # 15 minutes – same ZIP, same night

# CelesTrak TLE endpoints by satellite category
TLE_SOURCES = {
    "Space Stations": "https://celestrak.org/NORAD/elements/gp.php?GROUP=stations&FORMAT=tle",
    "Amateur Radio": "https://celestrak.org/NORAD/elements/gp.php?GROUP=amateur&FORMAT=tle",
    "Weather": "https://celestrak.org/NORAD/elements/gp.php?GROUP=weather&FORMAT=tle",
    "Science": "https://celestrak.org/NORAD/elements/gp.php?GROUP=science&FORMAT=tle",
}

# Well-known satellites to prioritize in results (NORAD catalog numbers)
PRIORITY_SATELLITES = {
    "ISS (ZARYA)": "Space Stations",
    "CSS (TIANHE)": "Space Stations",
    "HST": "Science",           # Hubble Space Telescope
    "NOAA 18": "Weather",
    "NOAA 19": "Weather",
    "NOAA 15": "Weather",
    "ISS DEB": None,            # Exclude ISS debris
}

# Minimum pass elevation (degrees) to consider "visible"
MIN_PASS_ELEVATION = 10.0

# Maximum number of satellite passes to return
MAX_PASSES_RETURNED = 20

# Satellites per category to check (limits computation time)
MAX_SATS_PER_CATEGORY = 25


# ---------------------------------------------------------------------------
# Geocoding (reuses existing Google Maps API pattern with caching)
# ---------------------------------------------------------------------------

def geocode_zip(zip_code):
    """
    Convert a US ZIP code to latitude, longitude, and locality name.

    Delegates to zip_data.local_get_location_data(), which uses a
    three-step fallback chain:
      1. Local JSON dataset (~41,000 US ZIPs — instant, free).
      2. Django cache (populated by a previous API call).
      3. Google Maps Geocoding API (live call, result cached for next time).

    Returns:
        dict with keys: lat, lon, locality, state, success, error
    """
    zip_code = str(zip_code).strip()

    try:
        from .zip_data import local_get_location_data
    except ImportError:
        logger.error("Could not import zip_data module.")
        return {
            "success": False,
            "error": "Internal configuration error (zip_data module not found).",
        }

    location = local_get_location_data(zip_code)

    if location is None:
        return {
            "success": False,
            "error": f"Could not find location for ZIP code {zip_code}.",
        }

    return {
        "success": True,
        "lat": location["lat"],
        "lon": location["lng"],  # zip_data uses "lng"; this file uses "lon"
        "locality": location.get("city", zip_code),
        "state": location.get("state", ""),
        "error": None,
    }


# ---------------------------------------------------------------------------
# Observer Setup
# ---------------------------------------------------------------------------

def _make_observer(lat, lon, date_utc=None):
    """
    Create an ephem.Observer for the given coordinates.

    Args:
        lat: Latitude in decimal degrees.
        lon: Longitude in decimal degrees.
        date_utc: A datetime in UTC. Defaults to now.

    Returns:
        ephem.Observer configured for the location and date.
    """
    observer = ephem.Observer()
    observer.lat = str(lat)
    observer.lon = str(lon)
    observer.elevation = 0  # Sea level default (adequate for stargazing calcs)
    observer.pressure = 0   # Disable atmospheric refraction for twilight accuracy

    if date_utc is not None:
        observer.date = ephem.Date(date_utc)
    else:
        observer.date = ephem.now()

    return observer


_tf_instance = None

def _get_timezone_finder():
    """Return a cached TimezoneFinder instance (lazy singleton)."""
    global _tf_instance
    if _tf_instance is None:
        from timezonefinder import TimezoneFinder
        _tf_instance = TimezoneFinder(in_memory=False)
    return _tf_instance

def _get_timezone_name(lat, lon):
    """Get the IANA timezone string for a given lat/lon."""
    tf = _get_timezone_finder()
    tz_name = tf.timezone_at(lng=lon, lat=lat)
    return tz_name if tz_name else "UTC"


def _ephem_date_to_datetime(ephem_date):
    """Convert an ephem.Date to a Python datetime (UTC)."""
    if ephem_date is None:
        return None
    return ephem.Date(ephem_date).datetime().replace(tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Twilight & Golden Hour Calculations
# ---------------------------------------------------------------------------

def calculate_twilight_times(lat, lon, target_date=None, tz_name="UTC"):
    """
    Calculate all twilight boundaries and golden hour windows...
    """
    local_tz = ZoneInfo(tz_name)

    if target_date is None:
        now_local = datetime.now(local_tz)
        target_date = now_local.date()

    # Set observer to local noon on the target date to find evening events
    local_noon = datetime(
        target_date.year, target_date.month, target_date.day,
        12, 0, 0, tzinfo=local_tz
    )
    noon_utc = local_noon.astimezone(timezone.utc).replace(tzinfo=None)

    result = {
        "date": target_date,
    }

    # --- Sunset / Sunrise ---
    observer = _make_observer(lat, lon, noon_utc)
    observer.pressure = 1013.25  # Standard pressure for sunset refraction

    try:
        result["sunset"] = _ephem_date_to_datetime(observer.next_setting(ephem.Sun()))
    except (ephem.AlwaysUpError, ephem.NeverUpError):
        result["sunset"] = None

    try:
        result["sunrise"] = _ephem_date_to_datetime(observer.next_rising(ephem.Sun()))
    except (ephem.AlwaysUpError, ephem.NeverUpError):
        result["sunrise"] = None

    # --- Civil Twilight (Sun at -6°) ---
    observer_twilight = _make_observer(lat, lon, noon_utc)
    observer_twilight.horizon = "-6"

    try:
        result["civil_twilight_end"] = _ephem_date_to_datetime(
            observer_twilight.next_setting(ephem.Sun(), use_center=True)
        )
    except (ephem.AlwaysUpError, ephem.NeverUpError):
        result["civil_twilight_end"] = None

    try:
        result["civil_twilight_start"] = _ephem_date_to_datetime(
            observer_twilight.next_rising(ephem.Sun(), use_center=True)
        )
    except (ephem.AlwaysUpError, ephem.NeverUpError):
        result["civil_twilight_start"] = None

    # --- Nautical Twilight (Sun at -12°) ---
    observer_nautical = _make_observer(lat, lon, noon_utc)
    observer_nautical.horizon = "-12"

    try:
        result["nautical_twilight_end"] = _ephem_date_to_datetime(
            observer_nautical.next_setting(ephem.Sun(), use_center=True)
        )
    except (ephem.AlwaysUpError, ephem.NeverUpError):
        result["nautical_twilight_end"] = None

    try:
        result["nautical_twilight_start"] = _ephem_date_to_datetime(
            observer_nautical.next_rising(ephem.Sun(), use_center=True)
        )
    except (ephem.AlwaysUpError, ephem.NeverUpError):
        result["nautical_twilight_start"] = None

    # --- Astronomical Twilight (Sun at -18°) ---
    observer_astro = _make_observer(lat, lon, noon_utc)
    observer_astro.horizon = "-18"

    try:
        result["astro_twilight_end"] = _ephem_date_to_datetime(
            observer_astro.next_setting(ephem.Sun(), use_center=True)
        )
    except (ephem.AlwaysUpError, ephem.NeverUpError):
        result["astro_twilight_end"] = None

    try:
        result["astro_twilight_start"] = _ephem_date_to_datetime(
            observer_astro.next_rising(ephem.Sun(), use_center=True)
        )
    except (ephem.AlwaysUpError, ephem.NeverUpError):
        result["astro_twilight_start"] = None

    # --- Dark Window (between astronomical twilight end and start) ---
    if result.get("astro_twilight_end") and result.get("astro_twilight_start"):
        dark_start = result["astro_twilight_end"]
        dark_end = result["astro_twilight_start"]
        result["dark_window_start"] = dark_start
        result["dark_window_end"] = dark_end
        result["dark_window_hours"] = (dark_end - dark_start).total_seconds() / 3600.0
    else:
        result["dark_window_start"] = None
        result["dark_window_end"] = None
        result["dark_window_hours"] = None

    # --- Golden Hour (Sun between +6° and -4°) ---
    # Evening golden hour
    observer_gh_upper = _make_observer(lat, lon, noon_utc)
    observer_gh_upper.horizon = "6"
    observer_gh_lower = _make_observer(lat, lon, noon_utc)
    observer_gh_lower.horizon = "-4"

    try:
        result["golden_hour_evening_start"] = _ephem_date_to_datetime(
            observer_gh_upper.next_setting(ephem.Sun(), use_center=True)
        )
    except (ephem.AlwaysUpError, ephem.NeverUpError):
        result["golden_hour_evening_start"] = None

    try:
        result["golden_hour_evening_end"] = _ephem_date_to_datetime(
            observer_gh_lower.next_setting(ephem.Sun(), use_center=True)
        )
    except (ephem.AlwaysUpError, ephem.NeverUpError):
        result["golden_hour_evening_end"] = None

    # Morning golden hour
    try:
        result["golden_hour_morning_start"] = _ephem_date_to_datetime(
            observer_gh_lower.next_rising(ephem.Sun(), use_center=True)
        )
    except (ephem.AlwaysUpError, ephem.NeverUpError):
        result["golden_hour_morning_start"] = None

    try:
        result["golden_hour_morning_end"] = _ephem_date_to_datetime(
            observer_gh_upper.next_rising(ephem.Sun(), use_center=True)
        )
    except (ephem.AlwaysUpError, ephem.NeverUpError):
        result["golden_hour_morning_end"] = None

    return result


# ---------------------------------------------------------------------------
# Moon Calculations
# ---------------------------------------------------------------------------

def calculate_moon_info(lat, lon, target_date=None, tz_name="UTC"):
    """
    Calculate moon phase, illumination, rise/set times, and altitude.
    """
    local_tz = ZoneInfo(tz_name)

    if target_date is None:
        now_local = datetime.now(local_tz)
        target_date = now_local.date()

    # Use local midnight for moonrise/moonset calculations
    local_midnight = datetime(
        target_date.year, target_date.month, target_date.day,
        0, 0, 0, tzinfo=local_tz
    )
    midnight_utc = local_midnight.astimezone(timezone.utc).replace(tzinfo=None)

    # Use local evening (9 PM) for phase/altitude snapshot
    local_evening = datetime(
        target_date.year, target_date.month, target_date.day,
        21, 0, 0, tzinfo=local_tz
    )
    evening_utc = local_evening.astimezone(timezone.utc).replace(tzinfo=None)

    moon = ephem.Moon()

    # Phase and illumination at evening time
    observer_evening = _make_observer(lat, lon, evening_utc)
    moon.compute(observer_evening)

    illumination = moon.phase  # 0–100%
    moon_alt_deg = math.degrees(moon.alt)
    moon_az_deg = math.degrees(moon.az)

    # Moon age (days since new moon) for phase naming
    # ephem provides moon.phase as illumination %, and we can compute
    # the elongation to determine waxing vs waning
    sun = ephem.Sun()
    sun.compute(observer_evening)

    # Elongation: positive = east of sun (waxing), negative = west (waning)
    # Use right ascension difference
    moon_ra = float(moon.ra)
    sun_ra = float(sun.ra)
    elongation = moon_ra - sun_ra
    # Normalize to [-pi, pi]
    while elongation > math.pi:
        elongation -= 2 * math.pi
    while elongation < -math.pi:
        elongation += 2 * math.pi

    is_waxing = elongation > 0

    phase_name = _get_phase_name(illumination, is_waxing)

    # Moonrise and moonset from midnight
    observer_rise = _make_observer(lat, lon, midnight_utc)
    observer_rise.pressure = 1013.25

    moonrise = None
    moonset = None

    try:
        moonrise = _ephem_date_to_datetime(observer_rise.next_rising(ephem.Moon()))
    except (ephem.AlwaysUpError, ephem.NeverUpError):
        pass

    try:
        moonset_observer = _make_observer(lat, lon, midnight_utc)
        moonset_observer.pressure = 1013.25
        moonset = _ephem_date_to_datetime(moonset_observer.next_setting(ephem.Moon()))
    except (ephem.AlwaysUpError, ephem.NeverUpError):
        pass

    # Determine if moon is up during the dark window
    moon_during_dark = moon_alt_deg > 0

    return {
        "phase_name": phase_name,
        "illumination": round(illumination, 1),
        "is_waxing": is_waxing,
        "altitude_deg": round(moon_alt_deg, 1),
        "azimuth_deg": round(moon_az_deg, 1),
        "moonrise": moonrise,
        "moonset": moonset,
        "moon_up_at_9pm": moon_during_dark,
        "phase_emoji": _get_phase_emoji(illumination, is_waxing),
    }


def _get_phase_name(illumination, is_waxing):
    """Return a human-readable moon phase name."""
    if illumination < 2:
        return "New Moon"
    elif illumination < 35:
        return "Waxing Crescent" if is_waxing else "Waning Crescent"
    elif illumination < 65:
        return "First Quarter" if is_waxing else "Last Quarter"
    elif illumination < 98:
        return "Waxing Gibbous" if is_waxing else "Waning Gibbous"
    else:
        return "Full Moon"


def _get_phase_emoji(illumination, is_waxing):
    """Return a moon phase emoji."""
    if illumination < 2:
        return "🌑"
    elif illumination < 35:
        return "🌒" if is_waxing else "🌘"
    elif illumination < 65:
        return "🌓" if is_waxing else "🌗"
    elif illumination < 98:
        return "🌔" if is_waxing else "🌖"
    else:
        return "🌕"


# ---------------------------------------------------------------------------
# Satellite Pass Predictions
# ---------------------------------------------------------------------------

def fetch_tle_data(category_name, tle_url):
    """
    Fetch TLE (Two-Line Element) data from CelesTrak with caching.

    TLE data is cached for 12 hours to limit API calls. CelesTrak
    updates TLEs roughly twice per day, so this is a reasonable interval.

    Args:
        category_name: Human-readable satellite category (for cache key).
        tle_url: CelesTrak URL to fetch TLE data from.

    Returns:
        list of tuples: [(name, tle_line1, tle_line2), ...]
        Returns empty list on failure.
    """
    cache_key = f"nightsky_tle_{category_name.replace(' ', '_').lower()}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        response = requests.get(tle_url, timeout=15)
        response.raise_for_status()
        lines = response.text.strip().splitlines()

        satellites = []
        i = 0
        while i + 2 < len(lines):
            name = lines[i].strip()
            line1 = lines[i + 1].strip()
            line2 = lines[i + 2].strip()

            # Basic TLE format validation
            if line1.startswith("1 ") and line2.startswith("2 "):
                satellites.append((name, line1, line2))
                i += 3
            else:
                # Skip malformed entries
                i += 1

        cache.set(cache_key, satellites, TLE_CACHE_TTL)
        return satellites

    except requests.exceptions.RequestException as e:
        logger.warning("Failed to fetch TLE data for %s: %s", category_name, e)
        return []


def predict_satellite_passes(lat, lon, target_date=None, tz_name="UTC", max_passes=MAX_PASSES_RETURNED):
    """
    Predict visible satellite passes for tonight.
    """
    local_tz = ZoneInfo(tz_name)

    if target_date is None:
        now_local = datetime.now(local_tz)
        target_date = now_local.date()

    # Define the observation window: sunset to sunrise
    local_sunset = datetime(
        target_date.year, target_date.month, target_date.day,
        18, 0, 0, tzinfo=local_tz
    )
    local_sunrise = local_sunset + timedelta(hours=14)  # Wide window

    window_start_utc = local_sunset.astimezone(timezone.utc).replace(tzinfo=None)
    window_end_utc = local_sunrise.astimezone(timezone.utc).replace(tzinfo=None)

    all_passes = []

    for category_name, tle_url in TLE_SOURCES.items():
        tle_data = fetch_tle_data(category_name, tle_url)

        # Limit satellites per category to control computation time
        sats_checked = 0
        for sat_name, line1, line2 in tle_data:
            if sats_checked >= MAX_SATS_PER_CATEGORY:
                break

            # Skip known debris entries
            if "DEB" in sat_name or "R/B" in sat_name:
                continue

            try:
                sat = ephem.readtle(sat_name, line1, line2)
            except ValueError:
                continue

            sats_checked += 1

            # Find passes within the window
            observer = _make_observer(lat, lon, window_start_utc)
            search_start = ephem.Date(window_start_utc)
            search_end = ephem.Date(window_end_utc)

            attempts = 0
            while observer.date < search_end and attempts < 15:
                attempts += 1
                try:
                    pass_info = observer.next_pass(sat)
                except Exception:
                    break

                if pass_info[0] is None:
                    break

                rise_time, rise_az, max_alt_time, max_alt, set_time, set_az = pass_info

                # Validate the pass is within our window
                if rise_time is None or rise_time > search_end:
                    break

                max_alt_deg = math.degrees(max_alt) if max_alt else 0

                # Only include passes with sufficient elevation
                if max_alt_deg >= MIN_PASS_ELEVATION:
                    # Check if satellite is sunlit at max altitude time
                    if max_alt_time is not None:
                        check_observer = _make_observer(lat, lon)
                        check_observer.date = max_alt_time
                        sat.compute(check_observer)

                        # Satellite is visible when it's above horizon and
                        # NOT in Earth's shadow (eclipsed = False means sunlit)
                        if not sat.eclipsed:
                            rise_dt = _ephem_date_to_datetime(rise_time)
                            max_dt = _ephem_date_to_datetime(max_alt_time)
                            set_dt = _ephem_date_to_datetime(set_time) if set_time else None

                            duration_sec = 0
                            if rise_time and set_time:
                                duration_sec = (
                                    set_time - rise_time
                                ) * 86400  # ephem days to seconds

                            all_passes.append({
                                "satellite_name": sat_name.strip(),
                                "category": category_name,
                                "rise_time": rise_dt,
                                "rise_azimuth": math.degrees(rise_az) if rise_az else None,
                                "max_alt_time": max_dt,
                                "max_altitude": round(max_alt_deg, 1),
                                "set_time": set_dt,
                                "set_azimuth": math.degrees(set_az) if set_az else None,
                                "duration_seconds": round(duration_sec),
                                "magnitude": round(float(sat.mag), 1) if hasattr(sat, "mag") else None,
                            })

                # Advance observer past this pass to find the next one
                if set_time is not None:
                    observer.date = set_time + ephem.minute
                else:
                    observer.date = rise_time + ephem.hour

    # Sort by rise time, limit results
    all_passes.sort(key=lambda p: p["rise_time"])
    return all_passes[:max_passes]


# ---------------------------------------------------------------------------
# Stargazing Quality Rating
# ---------------------------------------------------------------------------

def calculate_stargazing_quality(twilight_data, moon_data):
    """
    Calculate an overall stargazing quality rating from 1 to 5 stars.

    Factors considered:
        - Moon illumination (40% weight): Less light = better viewing
        - Moon position at 9 PM (25% weight): Below horizon = better
        - Dark window duration (25% weight): Longer = better
        - Twilight completeness (10% weight): Full astro twilight available

    Args:
        twilight_data: dict from calculate_twilight_times()
        moon_data: dict from calculate_moon_info()

    Returns:
        dict with rating (1-5), score (0-100), label, and breakdown.
    """
    scores = {}
    weights = {
        "moon_illumination": 0.40,
        "moon_position": 0.25,
        "dark_window": 0.25,
        "twilight_quality": 0.10,
    }

    # --- Moon Illumination Score (0-100) ---
    # New moon (0%) = 100, Full moon (100%) = 0
    illum = moon_data.get("illumination", 50)
    scores["moon_illumination"] = max(0, 100 - illum)

    # --- Moon Position Score (0-100) ---
    # Below horizon = 100, high in sky = 0
    alt = moon_data.get("altitude_deg", 0)
    if alt <= 0:
        scores["moon_position"] = 100
    elif alt >= 60:
        scores["moon_position"] = 0
    else:
        scores["moon_position"] = max(0, 100 - (alt / 60.0) * 100)

    # --- Dark Window Duration Score (0-100) ---
    # 8+ hours = 100, 0 hours = 0
    dark_hours = twilight_data.get("dark_window_hours")
    if dark_hours is None or dark_hours <= 0:
        scores["dark_window"] = 0
    elif dark_hours >= 8:
        scores["dark_window"] = 100
    else:
        scores["dark_window"] = (dark_hours / 8.0) * 100

    # --- Twilight Quality Score (0-100) ---
    # All twilight data present = 100
    has_astro = (
        twilight_data.get("astro_twilight_end") is not None
        and twilight_data.get("astro_twilight_start") is not None
    )
    scores["twilight_quality"] = 100 if has_astro else 30

    # Weighted total
    total_score = sum(
        scores[key] * weights[key] for key in weights
    )
    total_score = round(total_score, 1)

    # Convert to 1-5 star rating
    if total_score >= 85:
        stars = 5
        label = "Excellent"
        description = "Outstanding conditions for stargazing tonight."
    elif total_score >= 70:
        stars = 4
        label = "Very Good"
        description = "Great night for stargazing with minimal interference."
    elif total_score >= 50:
        stars = 3
        label = "Good"
        description = "Decent conditions — bright stars and planets will be visible."
    elif total_score >= 30:
        stars = 2
        label = "Fair"
        description = "Some viewing possible, but moonlight will wash out fainter objects."
    else:
        stars = 1
        label = "Poor"
        description = "Challenging conditions — only the brightest objects will be visible."

    return {
        "stars": stars,
        "score": total_score,
        "label": label,
        "description": description,
        "breakdown": {
            "moon_illumination": round(scores["moon_illumination"], 1),
            "moon_position": round(scores["moon_position"], 1),
            "dark_window": round(scores["dark_window"], 1),
            "twilight_quality": round(scores["twilight_quality"], 1),
        },
    }


# ---------------------------------------------------------------------------
# Main Orchestrator
# ---------------------------------------------------------------------------

def get_night_sky_report(zip_code):

    zip_code = str(zip_code).strip()

    # Check results cache
    cache_key = f"nightsky_report_{zip_code}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    # Step 1: Geocode
    geo = geocode_zip(zip_code)
    if not geo.get("success"):
        return {"success": False, "error": geo.get("error", "Geocoding failed.")}

    lat = geo["lat"]
    lon = geo["lon"]
    locality = geo["locality"]
    state = geo["state"]
    
    # 1. Get the actual timezone string
    tz_name = _get_timezone_name(lat, lon)

    # 2. Pass it to the calculators
    twilight = calculate_twilight_times(lat, lon, tz_name=tz_name)
    moon = calculate_moon_info(lat, lon, tz_name=tz_name)

    try:
        satellites = predict_satellite_passes(lat, lon, tz_name=tz_name)
    except Exception as e:
        logger.error("Satellite prediction error: %s", e)
        satellites = []

    quality = calculate_stargazing_quality(twilight, moon)

    moon["azimuth_compass"] = _degrees_to_compass(moon.get("azimuth_deg", 0))

    # Format satellite azimuths
    for sat_pass in satellites:
        if sat_pass.get("rise_azimuth") is not None:
            sat_pass["rise_compass"] = _degrees_to_compass(sat_pass["rise_azimuth"])
        if sat_pass.get("set_azimuth") is not None:
            sat_pass["set_compass"] = _degrees_to_compass(sat_pass["set_azimuth"])
        if sat_pass.get("duration_seconds"):
            minutes = sat_pass["duration_seconds"] // 60
            seconds = sat_pass["duration_seconds"] % 60
            sat_pass["duration_formatted"] = f"{minutes}m {seconds}s"

    report = {
        "success": True,
        "zip_code": zip_code,
        "locality": locality,
        "state": state,
        "lat": round(lat, 4),
        "lon": round(lon, 4),
        "timezone": tz_name,  # <-- Replaces offset_hours
        "twilight": twilight,
        "moon": moon,
        "satellites": satellites,
        "quality": quality,
        "generated_at": datetime.now(timezone.utc),
    }

    cache.set(cache_key, report, RESULTS_CACHE_TTL)

    return report


def _degrees_to_compass(degrees):
    """Convert degrees (0-360) to a 16-point compass direction."""
    if degrees is None:
        return "N/A"
    directions = [
        "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
        "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW",
    ]
    index = round(degrees / 22.5) % 16
    return directions[index]
