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


# ---------------------------- Region detection ----------------------------

# Cache the region result for 30 seconds.  The ISS moves ~230 km in that
# window — enough to cross a coastline in the worst case, but totally
# acceptable for a live tracker UI.  This drops Nominatim calls from
# "every poll" to roughly 2/minute, well within OSM's usage policy.
_REGION_CACHE_KEY = "iss_current_region"
_REGION_CACHE_TTL = 30  # seconds


def _reverse_geocode(latitude: float, longitude: float) -> str | None:
    """
    Attempt Nominatim reverse geocode.  Returns a region name string
    on success, or None if no land result / service unavailable.
    """
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
    except GeocoderTimedOut:
        logger.debug("Nominatim timed out for (%s, %s); falling back to bounding boxes.", latitude, longitude)
    except GeocoderServiceError as e:
        logger.warning("Nominatim service error for (%s, %s): %s", latitude, longitude, e)
    except Exception as e:
        logger.warning("Unexpected geocoder error for (%s, %s): %s", latitude, longitude, e)

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
      1. Check the short-lived region cache (30 s TTL).  If the ISS
         hasn't moved far, reuse the previous result without hitting
         Nominatim at all.
      2. Nominatim reverse geocode (land result -> country/state/city).
      3. If Nominatim returns nothing or fails, fall through to the
         bounding-box water-body lookup.
      4. If neither matches, return 'Unrecognized Region'.

    Every successful result is cached so subsequent polls within the
    TTL window skip the network call entirely.
    """
    # Step 0: return cached result if still fresh
    cached = cache.get(_REGION_CACHE_KEY)
    if cached:
        return cached

    # Step 1: try Nominatim (returns None on any failure)
    region = _reverse_geocode(latitude, longitude)

    # Step 2: bounding-box water-body lookup
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
