# projects/iss_utils.py
from django.http import JsonResponse
from django.core.cache import cache
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError
import gc, ctypes
import logging

logger = logging.getLogger(__name__)


# ---------------------------- Memory helper ----------------------------

def _trim_memory_safely() -> None:
    """Best-effort: force GC and ask glibc to return free arenas to the OS (Heroku dynos use glibc)."""
    try:
        gc.collect()
        ctypes.CDLL("libc.so.6").malloc_trim(0)
    except Exception:
        pass


# ---------------------------- TimezoneFinder singleton -----------------

# Constructed once at first use, then reused for every subsequent call.
# in_memory=False keeps the data files on disk, avoiding a ~54 MB heap
# cost from the full timezones-with-oceans dataset in 8.x.
_tf_instance = None

def _get_timezone_finder():
    """Return a cached TimezoneFinder instance (lazy singleton)."""
    global _tf_instance
    if _tf_instance is None:
        from timezonefinder import TimezoneFinder
        _tf_instance = TimezoneFinder(in_memory=False)
    return _tf_instance


# ---------------------------- Region detection ----------------------------

# Cache the region result for 30 seconds.  The ISS moves ~230 km in that
# window — enough to cross a coastline in the worst case, but totally
# acceptable for a live tracker UI.  This drops Nominatim calls from
# "every poll" to roughly 2/minute, well within OSM's usage policy.
_REGION_CACHE_KEY = "iss_current_region"
_REGION_CACHE_TTL = 10  # seconds
_NOMINATIM_BACKOFF_KEY = "nominatim_backoff"


def _is_over_land(latitude: float, longitude: float) -> bool:
    """
    Fast, offline land/water check using timezonefinder 8.x.

    timezone_at_land() checks ONLY land timezone polygons:
      - Returns an IANA timezone string  -> coordinate is over land.
      - Returns None                     -> coordinate is over water.

    NOTE: timezone_at() (without '_land') uses the full ocean dataset
    in 8.x and will NEVER return None, making it useless as a
    land/water discriminator.
    """
    try:
        tf = _get_timezone_finder()
        return tf.timezone_at_land(lng=longitude, lat=latitude) is not None
    except Exception as e:
        # If timezonefinder fails for any reason, assume land so
        # Nominatim gets a chance to resolve it.  Worst case: one
        # extra Nominatim call that returns nothing, then we fall
        # through to water_bodies anyway.
        logger.warning("timezonefinder error for (%s, %s): %s", latitude, longitude, e)
        return True


def _reverse_geocode(latitude: float, longitude: float) -> str | None:
    """
    Attempt Nominatim reverse geocode.  Returns a region name string
    on success, or None if no land result / service unavailable.
    """
    # Skip Nominatim entirely during a backoff window
    if cache.get(_NOMINATIM_BACKOFF_KEY):
        return None

    try:
        geolocator = Nominatim(
            user_agent="ISS Tracker by Ben Crittenden (+https://www.bencritt.net)"
        )
        location = geolocator.reverse(
            (latitude, longitude), exactly_one=True, language="en", timeout=10
        )
        if location:
            address = location.raw.get("address", {})
            if "country" in address:
                return address["country"]
            if "state" in address:
                return address["state"]
            if "city" in address:
                return address["city"]

    except (GeocoderTimedOut, GeocoderServiceError) as e:
        logger.warning("Nominatim error for (%s, %s): %s. Backing off for 5 mins.", latitude, longitude, e)
        cache.set(_NOMINATIM_BACKOFF_KEY, True, timeout=300)
        return None

    except Exception as e:
        logger.warning("Unexpected geocoder error for (%s, %s): %s", latitude, longitude, e)
        return None

    return None


def _match_water_body(latitude: float, longitude: float) -> str | None:
    """
    Walk the bounding-box list (sorted smallest-area-first) and return
    the first matching water body name, or None.
    """
    from .water_bodies import water_bodies

    for wb in water_bodies:
        if (wb["latitude_range"][0] <= latitude <= wb["latitude_range"][1] and
                wb["longitude_range"][0] <= longitude <= wb["longitude_range"][1]):
            return wb["name"]

    return None


def detect_region(latitude: float, longitude: float) -> str:
    """
    Detect the region (land or water) for a lat/lon coordinate.

    Strategy:
      1. Check the short-lived region cache (30 s TTL).
      2. Use timezonefinder's timezone_at_land() as a fast, offline
         land/water discriminator (~microseconds, no network).
         - Over water (~70% of ISS orbit): skip Nominatim entirely,
           resolve via water_bodies bounding boxes.
         - Over land (~30%): call Nominatim for country/state/city,
           with water_bodies as a fallback if Nominatim fails.
      3. Cache the result so subsequent polls within the TTL window
         skip all lookups entirely.
    """
    # Step 0: return cached result if still fresh
    cached = cache.get(_REGION_CACHE_KEY)
    if cached:
        return cached

    region = None

    # Step 1: fast land/water gate
    if _is_over_land(latitude, longitude):
        # Over land — ask Nominatim for the country name
        region = _reverse_geocode(latitude, longitude)

    # Step 2: water_bodies fallback (handles ocean + Nominatim failures)
    if not region:
        region = _match_water_body(latitude, longitude)

    # Step 3: nothing matched
    if not region:
        region = "Unrecognized Region"

    # Cache the result regardless of source
    cache.set(_REGION_CACHE_KEY, region, timeout=_REGION_CACHE_TTL)

    return region


# ---------------------------- TLE helper ----------------------------

_TLE_CACHE_KEY = "tle_data"
_TLE_TTL_SECONDS = 3600  # 1 hour; ISS TLEs update multiple times per day

def _fetch_tle_lines() -> tuple[str, str]:
    tle_data = cache.get(_TLE_CACHE_KEY)
    if not tle_data:
        import requests
        url = "https://celestrak.org/NORAD/elements/stations.txt"
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        tle_data = resp.text.splitlines()
        cache.set(_TLE_CACHE_KEY, tle_data, timeout=_TLE_TTL_SECONDS)

    iss_name = "ISS (ZARYA)"
    try:
        idx = next(i for i, line in enumerate(tle_data) if line.strip() == iss_name)
        return tle_data[idx + 1], tle_data[idx + 2]
    except (StopIteration, IndexError) as e:
        raise RuntimeError("Unable to parse ISS TLE from Celestrak.") from e


# ---------------------------- Formatting ----------------------------

def _fmt(v: float, places=2, unit: str | None = None) -> str:
    s = f"{v:.{places}f}"
    return f"{s} {unit}" if unit else s


# ---------------------------- Public endpoint ----------------------------

def current_iss_data(request):
    """
    Returns the current ISS subpoint and speed.

    JSON:
    {
        "latitude": "43.12 °",
        "longitude": "-87.65 °",
        "altitude": "419.23 km",
        "velocity": "7.66 km/s",
        "region": "North Atlantic Ocean" | "United States" | ...
    }
    """
    # Heavy imports only when this endpoint is called
    from skyfield.api import load
    from skyfield.sgp4lib import EarthSatellite

    try:
        line1, line2 = _fetch_tle_lines()

        ts = load.timescale()
        sat = EarthSatellite(line1, line2, "ISS (ZARYA)", ts)
        now = ts.now()
        geo = sat.at(now)

        # Subpoint and velocity
        sub = geo.subpoint()
        lat = sub.latitude.degrees
        lon = sub.longitude.degrees
        alt_km = sub.elevation.km
        vx, vy, vz = geo.velocity.km_per_s
        speed_kms = (vx * vx + vy * vy + vz * vz) ** 0.5

        region = detect_region(lat, lon)

        payload = {
            "latitude":  _fmt(lat, 2, "°"),
            "longitude": _fmt(lon, 2, "°"),
            "altitude":  _fmt(alt_km, 2, "km"),
            "velocity":  _fmt(speed_kms, 2, "km/s"),
            "region":    region,
        }
        return JsonResponse(payload)

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)

    finally:
        _trim_memory_safely()