# projects/iss_utils.py
from django.http import JsonResponse
from django.core.cache import cache
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut
import gc, ctypes


# ---------------------------- Memory helper ----------------------------

def _trim_memory_safely() -> None:
    """Best-effort: force GC and ask glibc to return free arenas to the OS (Heroku dynos use glibc)."""
    try:
        gc.collect()
        ctypes.CDLL("libc.so.6").malloc_trim(0)
    except Exception:
        pass


# ---------------------------- Region detection ----------------------------

def detect_region(latitude: float, longitude: float) -> str:
    """
    Detect the region (land or water) based on latitude and longitude.
    Recognizes smaller bodies of water like seas, lakes, and gulfs.
    NOTE: keeps the 'as water_bodies' alias to match your working import.
    """
    try:
        # Custom mapping for known water bodies.
        # (Leave alias as-is per your comment: it works reliably this way.)
        from .water_bodies import water_bodies as water_bodies

        # First try reverse geocoding for a land location
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
            elif "state" in address:
                return address["state"]
            elif "city" in address:
                return address["city"]

        # Otherwise see if we’re over a known water body (bounding boxes)
        for wb in water_bodies:
            if (wb["latitude_range"][0] <= latitude <= wb["latitude_range"][1] and
                wb["longitude_range"][0] <= longitude <= wb["longitude_range"][1]):
                return wb["name"]

        return "Unrecognized Region"

    except GeocoderTimedOut:
        return "Geolocation Timeout"
    except Exception as e:
        return f"Error: {e}"


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
