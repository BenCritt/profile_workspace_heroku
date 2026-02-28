"""
lunar_phase_calendar_utils.py
─────────────────────────────
All astronomical calculations for the Lunar Phase Calendar app.
Uses PyEphem (ephem package) — self-contained, no ephemeris file download.

Key public functions
────────────────────
  build_month_calendar(year, month, lat, lon, tz_name)
      Returns full calendar data: weeks, next phases, rise/set.

  geocode_zip(zip_code)
      Returns (lat, lon, city, state, tz_name) or None.
"""

import math
import logging
import calendar
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import ephem

logger = logging.getLogger(__name__)


# ── Phase metadata ────────────────────────────────────────────────────────────

# (upper_bound_degrees, display_name, emoji)
_PHASE_BANDS = [
    (22.5,  "New Moon",         "🌑"),
    (67.5,  "Waxing Crescent",  "🌒"),
    (112.5, "First Quarter",    "🌓"),
    (157.5, "Waxing Gibbous",   "🌔"),
    (202.5, "Full Moon",        "🌕"),
    (247.5, "Waning Gibbous",   "🌖"),
    (292.5, "Last Quarter",     "🌗"),
    (337.5, "Waning Crescent",  "🌘"),
]

_MAJOR_PHASE_FUNCS = [
    ("New Moon",      "🌑", ephem.next_new_moon),
    ("First Quarter", "🌓", ephem.next_first_quarter_moon),
    ("Full Moon",     "🌕", ephem.next_full_moon),
    ("Last Quarter",  "🌗", ephem.next_last_quarter_moon),
]

_ALL_NEXT_FUNCS = [
    ("New Moon",      "🌑", ephem.next_new_moon),
    ("First Quarter", "🌓", ephem.next_first_quarter_moon),
    ("Full Moon",     "🌕", ephem.next_full_moon),
    ("Last Quarter",  "🌗", ephem.next_last_quarter_moon),
]


def _phase_from_angle(angle_deg: float) -> tuple[str, str]:
    """Return (name, emoji) for a phase angle 0–360°."""
    for upper, name, emoji in _PHASE_BANDS:
        if angle_deg < upper:
            return name, emoji
    return "New Moon", "🌑"   # 337.5–360° wraps back


# ── Per-day phase computation ─────────────────────────────────────────────────

def _compute_day_phase(year: int, month: int, day: int) -> dict:
    """
    Compute moon phase angle and illumination at solar noon UTC.
    Using noon avoids timezone-related date boundary ambiguity.
    """
    # ephem.Date is a Dublin Julian Day float; pass a UTC tuple
    dt_noon = ephem.Date(f"{year}/{month}/{day} 12:00:00")

    moon = ephem.Moon(dt_noon)
    sun  = ephem.Sun(dt_noon)

    # Moon phase angle = angular separation between moon and sun ecliptic longitudes
    # ephem provides moon.moon_phase (0–1 illumination fraction) directly,
    # but we also want the directional angle to determine waxing vs waning.
    moon_ra = math.degrees(float(moon.ra))   # Use geocentric Right Ascension
    sun_ra  = math.degrees(float(sun.ra))

    phase_angle = (moon_ra - sun_ra) % 360.0

    # ephem.Moon.moon_phase is the illuminated fraction (0.0–1.0); multiply by 100
    illumination = round(moon.moon_phase * 100.0, 1)

    name, emoji = _phase_from_angle(phase_angle)

    return {
        "day":           day,
        "date":          date(year, month, day),
        "phase_angle":   round(phase_angle, 1),
        "illumination":  illumination,
        "phase_name":    name,
        "phase_emoji":   emoji,
        "is_today":      date(year, month, day) == date.today(),
        # Filled later if this day has an exact major phase
        "major_phase_name":  None,
        "major_phase_emoji": None,
        "major_phase_time":  None,
    }


# ── Exact major phase events within a month ───────────────────────────────────

def _find_major_phases_in_month(year: int, month: int) -> dict[int, tuple[str, str, str]]:
    """
    Return {day_of_month: (name, emoji, utc_time_str)} for each exact major
    phase that falls within the given month.
    If two phases fall on the same day (very rare) the later one wins.
    """
    num_days  = calendar.monthrange(year, month)[1]
    month_start = date(year, month, 1)
    month_end   = date(year, month, num_days)

    # Search window: start from ~30 days before month start to catch phases
    # that might be near the beginning of the month.
    search_from = ephem.Date(f"{year}/{month}/01 00:00:00") - 30

    result: dict[int, tuple[str, str, str]] = {}

    for name, emoji, func in _MAJOR_PHASE_FUNCS:
        cursor = search_from
        # Walk forward through all occurrences of this phase type that might
        # land within the target month (~2 occurrences per month max).
        for _ in range(3):
            phase_ephem_date = func(cursor)
            # Convert to a Python UTC datetime
            phase_dt = ephem.Date(phase_ephem_date).datetime()   # naive UTC
            phase_date = phase_dt.date()

            if phase_date > month_end:
                break

            if month_start <= phase_date <= month_end:
                result[phase_date.day] = (
                    name,
                    emoji,
                    phase_dt.strftime("%H:%M UTC"),
                )

            # Advance past this event by 1 day so next_*() finds the next one
            cursor = ephem.Date(phase_ephem_date) + 1

    return result


# ── Next major phases from now ────────────────────────────────────────────────

def get_next_major_phases(n: int = 4) -> list[dict]:
    """
    Return the next `n` major moon phase events from now (UTC).
    Each dict has: name, emoji, dt_utc, date_str, time_str, days_away.
    """
    now_ephem = ephem.Date(datetime.now(timezone.utc).strftime("%Y/%m/%d %H:%M:%S"))
    today     = date.today()

    candidates: list[dict] = []

    # Pull 2 occurrences of each of the 4 phase types to ensure we have enough
    for name, emoji, func in _ALL_NEXT_FUNCS:
        cursor = now_ephem
        for _ in range(2):
            phase_ephem_date = func(cursor)
            dt_utc = ephem.Date(phase_ephem_date).datetime()   # naive UTC
            candidates.append({
                "name":      name,
                "emoji":     emoji,
                "dt_utc":    dt_utc,
                "date_str":  dt_utc.strftime("%B %d, %Y"),
                "time_str":  dt_utc.strftime("%H:%M UTC"),
                "days_away": (dt_utc.date() - today).days,
            })
            cursor = ephem.Date(phase_ephem_date) + 1

    # Sort chronologically, return the nearest n
    candidates.sort(key=lambda x: x["dt_utc"])
    return candidates[:n]


# ── Moon rise / set times ─────────────────────────────────────────────────────

def _get_moon_rise_set(year: int, month: int,
                       lat: float, lon: float,
                       tz_name: str) -> dict[int, dict]:
    """
    Compute moon rise and set times for every day in the given month.
    Returns {day: {'rise': 'HH:MM', 'set': 'HH:MM', 'up_all_day': bool, 'down_all_day': bool}}.
    Times are expressed in the local timezone given by tz_name.
    Days with no event are flagged with up_all_day / down_all_day booleans.
    """
    local_tz = ZoneInfo(tz_name)
    num_days = calendar.monthrange(year, month)[1]

    # Build an ephem.Observer for this location
    observer = ephem.Observer()
    observer.lat  = str(lat)
    observer.lon  = str(lon)
    observer.elevation = 0
    # Use the standard ~34′ atmospheric refraction horizon
    observer.horizon  = "-0:34"
    observer.pressure = 1013.25   # mbar, standard atmosphere

    moon = ephem.Moon()

    result: dict[int, dict] = {}

    for day in range(1, num_days + 1):
        # Set observer to local midnight (expressed as UTC) for this day
        # We use UTC midnight then let ephem compute local events
        midnight_utc = datetime(year, month, day, 0, 0, 0, tzinfo=timezone.utc)
        observer.date = ephem.Date(midnight_utc.strftime("%Y/%m/%d %H:%M:%S"))

        rise_str = "—"
        set_str  = "—"
        up_all   = False
        down_all = False

        try:
            rise_utc = observer.next_rising(moon).datetime()   # naive UTC
            rise_local = rise_utc.replace(tzinfo=timezone.utc).astimezone(local_tz)
            # Only record if it falls on this calendar day in local time
            if rise_local.month == month and rise_local.day == day:
                rise_str = rise_local.strftime("%H:%M")
        except ephem.AlwaysUpError:
            up_all = True
        except ephem.NeverUpError:
            down_all = True
        except Exception:
            pass   # leave as "—"

        if not up_all and not down_all:
            # Reset observer to midnight to get the set time from same reference point
            observer.date = ephem.Date(midnight_utc.strftime("%Y/%m/%d %H:%M:%S"))
            try:
                set_utc = observer.next_setting(moon).datetime()   # naive UTC
                set_local = set_utc.replace(tzinfo=timezone.utc).astimezone(local_tz)
                if set_local.month == month and set_local.day == day:
                    set_str = set_local.strftime("%H:%M")
            except (ephem.AlwaysUpError, ephem.NeverUpError, Exception):
                pass

        result[day] = {
            "rise":         rise_str,
            "set":          set_str,
            "up_all_day":   up_all,
            "down_all_day": down_all,
        }

    return result



# ── Lazy singletons ───────────────────────────────────────────────────────────
# Matches the satellite_pass_predictor_utils.py pattern.

_tf_instance = None

def _get_timezone_finder():
    global _tf_instance
    if _tf_instance is None:
        from timezonefinder import TimezoneFinder
        _tf_instance = TimezoneFinder(in_memory=False)
    return _tf_instance


def geocode_zip(zip_code: str) -> tuple | None:
    """
    Return (lat, lng, city, state, tz_name) for a US ZIP code, or None on failure.
    Delegates to get_location_data() from projects.utils — same Google Geocoding
    API call (with 30-day Django cache) used by the Weather and ISS Tracker apps.
    TimezoneFinder resolves the IANA timezone from coordinates.
    """
    try:
        from projects.zip_data import local_get_location_data

        data = local_get_location_data(zip_code.strip())
        if not data:
            logger.warning("ZIP code %s could not be geocoded", zip_code)
            return None

        lat   = float(data["lat"])
        lng   = float(data["lng"])
        city  = str(data.get("city") or "").strip() or "Unknown"
        state = str(data.get("state") or "").strip() or ""

        tf      = _get_timezone_finder()
        tz_name = tf.timezone_at(lat=lat, lng=lng) or "America/Chicago"

        return lat, lng, city, state, tz_name

    except Exception:
        logger.exception("ZIP geocoding failed for %s", zip_code)
        return None


# ── Main calendar builder ─────────────────────────────────────────────────────

def build_month_calendar(year: int, month: int,
                          lat: float  = None,
                          lon: float  = None,
                          tz_name: str = "UTC") -> dict:
    """
    Build a complete month of lunar calendar data.

    Parameters
    ──────────
    year, month  : target calendar month
    lat, lon     : observer coordinates (optional; enables rise/set times)
    tz_name      : IANA timezone string for rise/set local times

    Returns
    ───────
    dict with keys:
      weeks        — list[list[day_dict | None]]  (7 columns, Sun–Sat)
      month_name   — "Month YYYY"
      next_phases  — list of next 4 major phase dicts from today
      has_location — bool; True when rise/set data is present
      tz_name      — echoed back for template display
      year, month  — echoed back for template nav links
      prev_year, prev_month, next_year, next_month — for prev/next navigation
    """
    num_days   = calendar.monthrange(year, month)[1]
    month_name = datetime(year, month, 1).strftime("%B %Y")

    # ── Exact major phase events within this month ────────────────────────────
    major_phases_this_month = _find_major_phases_in_month(year, month)

    # ── Per-day phase data ────────────────────────────────────────────────────
    days_data = []
    for day in range(1, num_days + 1):
        info = _compute_day_phase(year, month, day)

        if day in major_phases_this_month:
            info["major_phase_name"],  \
            info["major_phase_emoji"], \
            info["major_phase_time"]  = major_phases_this_month[day]

        days_data.append(info)

    # ── Rise / set (only if coordinates provided) ─────────────────────────────
    rise_set     = {}
    has_location = False
    if lat is not None and lon is not None:
        try:
            rise_set     = _get_moon_rise_set(year, month, lat, lon, tz_name)
            has_location = True
        except Exception:
            logger.exception("Rise/set calculation failed for %s/%s", year, month)

    # ── Next 4 major phases from today ────────────────────────────────────────
    next_phases = get_next_major_phases(n=4)

    # ── Merge rise/set into each day dict (avoids custom template filters) ────
    for day_info in days_data:
        d  = day_info["day"]
        rs = rise_set.get(d, {})
        day_info["moon_rise"]    = rs.get("rise",         "—")
        day_info["moon_set"]     = rs.get("set",          "—")
        day_info["up_all_day"]   = rs.get("up_all_day",   False)
        day_info["down_all_day"] = rs.get("down_all_day", False)

    # ── Sunday-first calendar grid with None padding ──────────────────────────
    # calendar.monthrange weekday: Mon=0 … Sun=6
    # Target column: Sun=0, Mon=1, … Sat=6  →  offset = (weekday + 1) % 7
    first_weekday = calendar.monthrange(year, month)[0]
    first_col     = (first_weekday + 1) % 7

    cells = [None] * first_col + days_data
    while len(cells) % 7 != 0:
        cells.append(None)
    weeks = [cells[i : i + 7] for i in range(0, len(cells), 7)]

    # ── Prev / next month navigation ─────────────────────────────────────────
    prev_dt = datetime(year, month, 1) - timedelta(days=1)
    next_dt = datetime(year, month, num_days) + timedelta(days=1)

    return {
        "weeks":        weeks,
        "month_name":   month_name,
        "next_phases":  next_phases,
        "has_location": has_location,
        "tz_name":      tz_name,
        "year":         year,
        "month":        month,
        "prev_year":    prev_dt.year,
        "prev_month":   prev_dt.month,
        "next_year":    next_dt.year,
        "next_month":   next_dt.month,
    }