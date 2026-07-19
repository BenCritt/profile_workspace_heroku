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

# Cache the region result for a short TTL.  The ISS moves ~75 km in 10
# seconds — acceptable drift for a live tracker UI.  This drops Nominatim
# calls from "every poll" to at most 6/minute (and in practice far fewer,
# since ~70% of the orbit is over water and skips Nominatim entirely),
# well within OSM's usage policy.
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
      1. Check the short-lived region cache.
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


# ---------------------------- Orbital data (CelesTrak GP API) ----------------------------
#
# WHY THIS SECTION CHANGED (2026-07):
#
#   The previous implementation fetched the legacy static file
#   https://celestrak.org/NORAD/elements/stations.txt and parsed TLE lines.
#   CelesTrak removed ALL legacy static .txt element files (final removal
#   2024-12-24; see https://celestrak.org/NORAD/documentation/gp-data-formats.php)
#   and, on 2026-07-11, the SATCAT ran out of 5-digit catalog numbers —
#   newly cataloged objects (100000+) cannot be expressed in TLE format
#   at all.  The supported interface is the GP query API:
#
#       https://celestrak.org/NORAD/elements/gp.php?CATNR=<id>&FORMAT=<fmt>
#
#   We request FORMAT=json (the OMM record format CelesTrak is urging
#   everyone toward) and build the Skyfield satellite with
#   EarthSatellite.from_omm() — available in Skyfield >= 1.43.
#
#   CelesTrak usage policy (https://celestrak.org/usage-policy.php):
#   GP data updates at most every 2 hours; never re-download more often
#   than that, identify your client with a User-Agent, and stop querying
#   entirely when the server is erroring.  The three-tier cache below
#   (fresh / backup / backoff) implements exactly that.

_ISS_NORAD_ID = 25544
_GP_URL = (
    "https://celestrak.org/NORAD/elements/gp.php"
    f"?CATNR={_ISS_NORAD_ID}&FORMAT=json"
)

_GP_HEADERS = {
    "User-Agent": "ISS Tracker by Ben Crittenden (+https://www.bencritt.net)",
    "Accept": "application/json,text/plain;q=0.9,*/*;q=0.8",
}

# Cache strategy — NOTE the "_v2" suffix: the old keys may hold stale or
# invalid content cached by the previous implementation, so we deliberately
# use new key names instead of requiring a cache flush at deploy time.
#
#   fresh copy   : 6 h TTL  -> normal operation (~4 fetches/day per worker)
#   backup copy  : 14 d TTL -> served if a refresh fails (stale-if-error;
#                              a days-old ISS element set still yields a
#                              usable position for a live map display)
#   backoff flag : 15 min   -> after any failure, skip upstream entirely
_GP_FRESH_KEY = "iss_omm_fresh_v2"
_GP_BACKUP_KEY = "iss_omm_backup_v2"
_GP_BACKOFF_KEY = "iss_omm_backoff_v2"
_GP_FRESH_TTL = 6 * 60 * 60        # 6 hours
_GP_BACKUP_TTL = 14 * 24 * 60 * 60  # 14 days
_GP_BACKOFF_TTL = 15 * 60           # 15 minutes

# Fields every usable CelesTrak OMM record must carry.
_OMM_REQUIRED_FIELDS = (
    "EPOCH", "MEAN_MOTION", "ECCENTRICITY", "INCLINATION",
    "RA_OF_ASC_NODE", "ARG_OF_PERICENTER", "MEAN_ANOMALY", "NORAD_CAT_ID",
)


def _validate_omm_record(record) -> bool:
    """True if `record` looks like a complete CelesTrak OMM element set."""
    return isinstance(record, dict) and all(k in record for k in _OMM_REQUIRED_FIELDS)


def _fetch_iss_omm() -> dict:
    """
    Return the current ISS OMM record (dict of orbital elements).

    Order of preference:
      1. Fresh cached copy (<= 6 h old).
      2. Live fetch from the CelesTrak GP API — the body is validated
         BEFORE caching, so a bad response (HTML notice page, plain-text
         "No GP data found", Cloudflare challenge, etc.) can never poison
         the cache the way the old .txt implementation could.
      3. Stale backup copy (<= 14 d old) if the live fetch fails.

    Raises RuntimeError only when all three fail.
    """
    fresh = cache.get(_GP_FRESH_KEY)
    if fresh:
        return fresh

    # During a backoff window, skip upstream entirely (the usage policy
    # asks clients to stop querying while the service is erroring) and
    # rely on the backup copy below.
    if not cache.get(_GP_BACKOFF_KEY):
        import requests  # heavy-ish import deferred until actually needed
        try:
            resp = requests.get(_GP_URL, headers=_GP_HEADERS, timeout=10)
            resp.raise_for_status()

            # A non-JSON body (e.g. "No GP data found") raises ValueError here.
            data = resp.json()
            record = data[0] if isinstance(data, list) and data else None
            if not _validate_omm_record(record):
                raise ValueError(
                    f"GP response did not contain a valid OMM record: {str(data)[:120]!r}"
                )

            # Validation passed — safe to cache.
            cache.set(_GP_FRESH_KEY, record, timeout=_GP_FRESH_TTL)
            cache.set(_GP_BACKUP_KEY, record, timeout=_GP_BACKUP_TTL)
            return record

        except Exception as e:
            logger.warning(
                "CelesTrak GP fetch failed (%s). Backing off for 15 minutes.", e
            )
            cache.set(_GP_BACKOFF_KEY, True, timeout=_GP_BACKOFF_TTL)

    backup = cache.get(_GP_BACKUP_KEY)
    if backup:
        return backup

    raise RuntimeError("ISS orbital data is temporarily unavailable from CelesTrak.")


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

    Error responses use {"error": "..."} with a 5xx status.  The frontend
    poller in iss_tracker.html treats any non-OK response as "keep showing
    the last good values", so a transient upstream outage degrades quietly
    instead of blanking the table.
    """
    # Heavy imports only when this endpoint is called
    from skyfield.api import load, wgs84, EarthSatellite

    try:
        record = _fetch_iss_omm()

        ts = load.timescale()
        sat = EarthSatellite.from_omm(ts, record)
        now = ts.now()
        geo = sat.at(now)

        # Subpoint and velocity.
        # wgs84.geographic_position_of() replaces the deprecated
        # geo.subpoint() — same latitude/longitude/elevation attributes,
        # without the DeprecationWarning on modern Skyfield.
        sub = wgs84.geographic_position_of(geo)
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

    except RuntimeError as e:
        # Upstream data unavailable (all three cache tiers exhausted).
        # 503 is the semantically correct status for "dependency down".
        logger.error("current_iss_data unavailable: %s", e)
        return JsonResponse({"error": str(e)}, status=503)

    except Exception:
        # Unexpected failure — log the full traceback server-side, but
        # return a clean message instead of leaking internals to a
        # public, unauthenticated endpoint.
        logger.exception("Unexpected error in current_iss_data")
        return JsonResponse({"error": "Unable to compute current ISS data."}, status=500)

    finally:
        _trim_memory_safely()