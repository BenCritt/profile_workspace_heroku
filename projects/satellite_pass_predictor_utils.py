# projects/satellite_pass_predictor_utils.py
from django.core.cache import cache
from skyfield.api import load, wgs84, EarthSatellite
from zoneinfo import ZoneInfo
import requests
import datetime
import logging

logger = logging.getLogger(__name__)

# ---------------------------- Config ----------------------------
#
# WHY THE SOURCES CHANGED (2026-07):
#
#   The previous implementation fetched five legacy static files
#   (stations.txt, amateur.txt, weather.txt, sarsat.txt, science.txt).
#   CelesTrak removed ALL legacy static .txt element files (final removal
#   2024-12-24; see https://celestrak.org/NORAD/documentation/gp-data-formats.php)
#   and, on 2026-07-11, the SATCAT ran out of 5-digit catalog numbers —
#   newly cataloged objects (100000+) cannot be expressed in TLE format
#   at all.  The supported interface is the GP query API (gp.php), and
#   CelesTrak is urging everyone onto the OMM formats (JSON/CSV) instead
#   of TLE.  Every source below now requests FORMAT=json, and satellites
#   are built with EarthSatellite.from_omm() (Skyfield >= 1.43).
#
#   Legacy-to-GP group mapping is 1:1 for the groups we use:
#       stations.txt -> gp.php?GROUP=stations
#       amateur.txt  -> gp.php?GROUP=amateur
#       weather.txt  -> gp.php?GROUP=weather
#       sarsat.txt   -> gp.php?GROUP=sarsat
#       science.txt  -> gp.php?GROUP=science

HEADERS = {
    'User-Agent': 'Satellite Pass Predictor by Ben Crittenden (+https://www.bencritt.net)',
    'Accept': 'application/json,text/plain;q=0.9,*/*;q=0.8',
}

_GP_BASE = "https://celestrak.org/NORAD/elements/gp.php"

# Map internal keys to CelesTrak GP API URLs (all OMM JSON).
# "Special" satellites are fetched individually because they are not
# carried in the group sets above.
SOURCES = {
    'stations': f'{_GP_BASE}?GROUP=stations&FORMAT=json',
    'amateur':  f'{_GP_BASE}?GROUP=amateur&FORMAT=json',
    'weather':  f'{_GP_BASE}?GROUP=weather&FORMAT=json',
    'sarsat':   f'{_GP_BASE}?GROUP=sarsat&FORMAT=json',
    'science':  f'{_GP_BASE}?GROUP=science&FORMAT=json',

    # Individual fetch URLs for satellites missing from the group sets
    'noaa_15':     f'{_GP_BASE}?CATNR=25338&FORMAT=json',
    'noaa_18':     f'{_GP_BASE}?CATNR=28654&FORMAT=json',
    'noaa_19':     f'{_GP_BASE}?CATNR=33591&FORMAT=json',
    'aqua':        f'{_GP_BASE}?CATNR=27424&FORMAT=json',
    'landsat_8':   f'{_GP_BASE}?CATNR=39084&FORMAT=json',
    'landsat_9':   f'{_GP_BASE}?CATNR=49260&FORMAT=json',
    'sentinel_2a': f'{_GP_BASE}?CATNR=40697&FORMAT=json',
    'ajisai':      f'{_GP_BASE}?CATNR=16908&FORMAT=json',
}

# The definitive catalog of supported satellites
SATELLITE_CATALOG = [
    # ── Space Stations ────────────────────────────────────────────────
    {
        "name": "ISS (ZARYA)",
        "norad_id": 25544,
        "celestrak_group": "stations",
        "group": "Space Stations",
        "description": "International Space Station.",
    },
    {
        "name": "CSS (TIANHE)",
        "norad_id": 48274,
        "celestrak_group": "stations",
        "group": "Space Stations",
        "description": "China Space Station (Tiangong).",
    },
    # ── Educational Satellites ────────────────────────────────────────
    {
        "name": "FUNCUBE-1 (AO-73)",
        "norad_id": 39444,
        "celestrak_group": "amateur",
        "group": "Educational",
        "description": "Designed for schools to receive telemetry.",
    },
    {
        "name": "UOSAT 2 (UO-11)",
        "norad_id": 14781,
        "celestrak_group": "amateur",
        "group": "Educational",
        "description": "Oldest digital satellite still monitored (launched 1984).",
    },
    {
        "name": "TEVEL-2",
        "norad_id": 63217,
        "celestrak_group": "amateur",
        "group": "Educational",
        "description": "Israeli student-built satellite.",
    },
    {
        "name": "TEVEL-3",
        "norad_id": 63219,
        "celestrak_group": "amateur",
        "group": "Educational",
        "description": "Israeli student-built satellite.",
    },
    {
        "name": "GEOSCAN-2",
        "norad_id": 64890,
        "celestrak_group": "amateur",
        "group": "Educational",
        "description": "Russian educational CubeSat.",
    },
    # ── Amateur Radio (DX & Repeaters) ────────────────────────────────
    {
        "name": "RS-44 (DOSAAF-85)",
        "norad_id": 44909,
        "celestrak_group": "amateur",
        "group": "Amateur Radio",
        "description": "High-altitude linear transponder (SSB/CW).",
    },
    {
        "name": "SO-50 (SaudiSat-1C)",
        "norad_id": 27607,
        "celestrak_group": "amateur",
        "group": "Amateur Radio",
        "description": "FM repeater. 145.850 MHz up / 436.795 MHz down.",
    },
    {
        "name": "AO-91 (RadFxSat)",
        "norad_id": 43017,
        "celestrak_group": "amateur",
        "group": "Amateur Radio",
        "description": "FM repeater. 145.960 MHz up / 435.250 MHz down.",
    },
    {
        "name": "IO-117 (GreenCube)",
        "norad_id": 53109,
        "celestrak_group": "amateur",
        "group": "Amateur Radio",
        "description": "MEO Digipeater. Allows contacts between Europe and USA.",
    },
    {
        "name": "AO-7 (OSCAR 7)",
        "norad_id": 7530,
        "celestrak_group": "amateur",
        "group": "Amateur Radio",
        "description": "Launched 1974. Semi-operational linear transponder.",
    },
    {
        "name": "JY1SAT (JO-97)",
        "norad_id": 43803,
        "celestrak_group": "amateur",
        "group": "Amateur Radio",
        "description": "Jordanian FM transponder satellite. 145.855 MHz up / 435.170 MHz down.",
    },
    # ── Weather Satellites ────────────────────────────────────────────
    {
        "name": "NOAA 15",
        "norad_id": 25338,
        "celestrak_group": "noaa_15",  # Individual Source
        "group": "Weather",
        "description": "Analog APT images (137.620 MHz).",
    },
    {
        "name": "NOAA 18",
        "norad_id": 28654,
        "celestrak_group": "noaa_18",  # Individual Source
        "group": "Weather",
        "description": "Analog APT images (137.9125 MHz).",
    },
    {
        "name": "NOAA 19",
        "norad_id": 33591,
        "celestrak_group": "noaa_19",  # Individual Source
        "group": "Weather",
        "description": "Analog APT images (137.100 MHz).",
    },
    {
        "name": "NOAA 20 (JPSS-1)",
        "norad_id": 43013,
        "celestrak_group": "weather",
        "group": "Weather",
        "description": "Next-gen digital weather satellite.",
    },
    {
        "name": "NOAA 21 (JPSS-2)",
        "norad_id": 54234,
        "celestrak_group": "weather",
        "group": "Weather",
        "description": "Latest JPSS series weather satellite.",
    },
    {
        "name": "METEOR-M2 3",
        "norad_id": 57166,
        "celestrak_group": "sarsat",
        "group": "Weather",
        "description": "High-res LRPT digital images (137.900 MHz).",
    },
    {
        "name": "METEOR-M2 4",
        "norad_id": 59051,
        "celestrak_group": "sarsat",
        "group": "Weather",
        "description": "Newest Russian weather satellite.",
    },
    # ── Search & Rescue ───────────────────────────────────────────────
    {
        "name": "SARSAT 13 (METOP-B)",
        "norad_id": 38771,
        "celestrak_group": "sarsat",
        "group": "Search & Rescue",
        "description": "Monitors 406 MHz emergency distress beacons.",
    },
    {
        "name": "SARSAT 16 (METOP-C)",
        "norad_id": 43689,
        "celestrak_group": "weather",
        "group": "Search & Rescue",
        "description": "Monitors 406 MHz emergency distress beacons.",
    },
    # ── Science & Earth Observation ───────────────────────────────────
    {
        "name": "HST (Hubble)",
        "norad_id": 20580,
        "celestrak_group": "science",
        "group": "Science",
        "description": "Hubble Space Telescope.",
    },
    {
        "name": "TERRA",
        "norad_id": 25994,
        "celestrak_group": "science",
        "group": "Science",
        "description": "NASA flagship EOS satellite.",
    },
    {
        "name": "AQUA",
        "norad_id": 27424,
        "celestrak_group": "aqua",  # Individual Source
        "group": "Science",
        "description": "NASA EOS PM-1 (Water Cycle).",
    },
    {
        "name": "LANDSAT 8",
        "norad_id": 39084,
        "celestrak_group": "landsat_8",  # Individual Source
        "group": "Science",
        "description": "USGS Earth observation.",
    },
    {
        "name": "LANDSAT 9",
        "norad_id": 49260,
        "celestrak_group": "landsat_9",  # Individual Source
        "group": "Science",
        "description": "USGS Earth observation.",
    },
    {
        "name": "SENTINEL-2A",
        "norad_id": 40697,
        "celestrak_group": "sentinel_2a",  # Individual Source
        "group": "Science",
        "description": "Copernicus Optical Earth Imaging (ESA).",
    },
    {
        "name": "AJISAI (EGS)",
        "norad_id": 16908,
        "celestrak_group": "ajisai",  # Individual Source
        "group": "Science",
        "description": "Experimental Geodetic Satellite.",
    },
    {
        "name": "IXPE",
        "norad_id": 49954,
        "celestrak_group": "science",
        "group": "Science",
        "description": "NASA X-ray Polarimetry Explorer (launched 2021).",
    },
]

# Cache strategy (CelesTrak usage policy: GP data updates at most every
# 2 hours; never re-download more often than that, and stop querying
# entirely while the service is erroring):
#
#   fresh copy   : 12 h TTL -> matches the "refreshes its orbital data
#                              every 12 hours" copy on the tool page, and
#                              a <=12 h-old element set is well within
#                              accuracy limits for 24 h pass prediction
#   backup copy  : 14 d TTL -> served if a refresh fails (stale-if-error)
#   backoff flag : 15 min   -> after a failure, skip upstream entirely
OMM_CACHE_TIMEOUT = 3600 * 12       # 12 hours (fresh)
OMM_BACKUP_TIMEOUT = 3600 * 24 * 14  # 14 days (stale-if-error)
OMM_BACKOFF_TIMEOUT = 60 * 15        # 15 minutes

# Fields every usable CelesTrak OMM record must carry.
_OMM_REQUIRED_FIELDS = (
    "EPOCH", "MEAN_MOTION", "ECCENTRICITY", "INCLINATION",
    "RA_OF_ASC_NODE", "ARG_OF_PERICENTER", "MEAN_ANOMALY", "NORAD_CAT_ID",
)

# ---------------------------- Helpers ----------------------------

# Lazy Singleton for TimezoneFinder
_tf_instance = None

def _get_timezone_finder():
    global _tf_instance
    if _tf_instance is None:
        from timezonefinder import TimezoneFinder
        _tf_instance = TimezoneFinder(in_memory=False)
    return _tf_instance

def get_satellite_groups():
    groups = {}
    for sat in SATELLITE_CATALOG:
        g = sat['group']
        if g not in groups:
            groups[g] = []
        groups[g].append(sat)
    return groups

def get_satellite_choices():
    groups = get_satellite_groups()
    choices = []
    GROUP_ORDER = ["Space Stations", "Educational", "Amateur Radio", "Weather", "Science", "Search & Rescue"]

    for group_name in GROUP_ORDER:
        if group_name in groups:
            sats = groups[group_name]
            group_choices = [(sat['name'], sat['name']) for sat in sats]
            choices.append((group_name, group_choices))

    for group_name, sats in groups.items():
        if group_name not in GROUP_ORDER:
            group_choices = [(sat['name'], sat['name']) for sat in sats]
            choices.append((group_name, group_choices))

    return choices

# EXPORTED FOR FORMS.PY
SATELLITE_CHOICES = get_satellite_choices()


def _valid_omm_record(record) -> bool:
    """True if `record` looks like a complete CelesTrak OMM element set."""
    return isinstance(record, dict) and all(k in record for k in _OMM_REQUIRED_FIELDS)


def _fetch_omm_for_group(group_key):
    """
    Return a list of OMM record dicts for a source key.

    Order of preference:
      1. Fresh cached copy (<= 12 h old).
      2. Live fetch from the CelesTrak GP API — records are validated
         BEFORE caching, so a bad response body (HTML notice page,
         plain-text "No GP data found", Cloudflare challenge, etc.)
         can never poison the cache.
      3. Stale backup copy (<= 14 d old) if the live fetch fails.

    Raises ConnectionError only when all three fail.
    """
    if group_key not in SOURCES:
        raise ValueError(f"Unknown source group: {group_key}")

    url = SOURCES[group_key]
    # v5 key generation: the v4 keys may hold TLE-format content cached
    # by the previous implementation, so we deliberately use new key
    # names instead of requiring a cache flush at deploy time.
    fresh_key = f"omm_source_{group_key}_v5"
    backup_key = f"omm_backup_{group_key}_v5"
    backoff_key = f"omm_backoff_{group_key}_v5"

    cached = cache.get(fresh_key)
    if cached:
        return cached

    # During a backoff window, skip upstream entirely (the usage policy
    # asks clients to stop querying while the service is erroring) and
    # rely on the backup copy below.
    if not cache.get(backoff_key):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            resp.raise_for_status()

            # A non-JSON body (e.g. "No GP data found") raises ValueError here.
            data = resp.json()
            if not isinstance(data, list):
                raise ValueError(
                    f"Response from {url} is not a JSON array: {str(data)[:120]!r}"
                )

            # Keep only structurally valid records; require at least one so a
            # single malformed entry can't take down the whole group.
            records = [r for r in data if _valid_omm_record(r)]
            if not records:
                raise ValueError(f"Response from {url} contained no valid OMM records.")

            # Validation passed — safe to cache.
            cache.set(fresh_key, records, OMM_CACHE_TIMEOUT)
            cache.set(backup_key, records, OMM_BACKUP_TIMEOUT)
            return records

        except (requests.RequestException, ValueError) as e:
            logger.warning(
                "CelesTrak GP fetch failed for '%s' (%s). Backing off for 15 minutes.",
                group_key, e,
            )
            cache.set(backoff_key, True, OMM_BACKOFF_TIMEOUT)

    backup = cache.get(backup_key)
    if backup:
        return backup

    raise ConnectionError(
        f"Orbital data for source '{group_key}' is temporarily unavailable from CelesTrak."
    )


def _extract_omm(sat_name, norad_id, records):
    """
    Find the OMM record matching a NORAD catalog ID.

    Matching on NORAD_CAT_ID replaces the old TLE line-2 column parsing —
    no fixed-width slicing, no name-line lookups, and it keeps working
    when CelesTrak reorders or renames entries within a group.
    """
    target_id = int(norad_id)

    for record in records:
        try:
            if int(record.get("NORAD_CAT_ID", -1)) == target_id:
                return record
        except (TypeError, ValueError):
            continue

    raise ValueError(f"Satellite '{sat_name}' (ID {norad_id}) not found in source.")


def az_direction(degrees):
    dirs = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW']
    ix = round(degrees / 45)
    return dirs[ix % 8]

# ---------------------------- Logic ----------------------------

def predict_passes(satellite_name, lat, lon):
    sat_config = next((s for s in SATELLITE_CATALOG if s['name'] == satellite_name), None)
    if not sat_config:
        return {"error": f"Satellite '{satellite_name}' not found in catalog."}

    try:
        # 1. Determine Timezone
        tf = _get_timezone_finder()
        tz_name = tf.timezone_at(lng=lon, lat=lat)
        local_tz = ZoneInfo(tz_name) if tz_name else datetime.timezone.utc

        # 2. Fetch orbital elements (OMM JSON) and pick this satellite's record
        records = _fetch_omm_for_group(sat_config['celestrak_group'])
        record = _extract_omm(sat_config['name'], sat_config['norad_id'], records)

        # 3. Calculate
        ts = load.timescale()
        satellite = EarthSatellite.from_omm(ts, record)
        observer = wgs84.latlon(lat, lon)

        t0 = ts.now()
        t1 = ts.from_datetime(t0.utc_datetime() + datetime.timedelta(hours=24))

        times, events = satellite.find_events(observer, t0, t1, altitude_degrees=10.0)

        pass_list = []
        current_pass = {}

        for t, event in zip(times, events):
            utc_dt = t.utc_datetime()
            local_dt = utc_dt.astimezone(local_tz)

            if event == 0:  # Rise
                current_pass['rise_time'] = local_dt
                az, alt, dist = (satellite - observer).at(t).altaz()
                current_pass['rise_az'] = f"{az.degrees:.0f}° {az_direction(az.degrees)}"

            elif event == 1:  # Culminate
                current_pass['max_time'] = local_dt
                az, alt, dist = (satellite - observer).at(t).altaz()
                current_pass['max_alt'] = f"{alt.degrees:.0f}°"

            elif event == 2:  # Set
                current_pass['set_time'] = local_dt
                az, alt, dist = (satellite - observer).at(t).altaz()
                current_pass['set_az'] = f"{az.degrees:.0f}° {az_direction(az.degrees)}"

                if 'rise_time' in current_pass:
                    duration = current_pass['set_time'] - current_pass['rise_time']
                    mins, secs = divmod(duration.total_seconds(), 60)

                    pass_data = {
                        "event": f"Pass ({int(mins)}m)",
                        "date": current_pass['rise_time'].strftime("%a, %b %d"),
                        "time": f"{current_pass['rise_time'].strftime('%I:%M %p')} - {current_pass['set_time'].strftime('%I:%M %p %Z')}",
                        "position": f"Max: {current_pass.get('max_alt', '?')} ({current_pass.get('rise_az')} -> {current_pass.get('set_az')})"
                    }
                    pass_list.append(pass_data)

                current_pass = {}

        return {
            "satellite": sat_config,
            "passes": pass_list
        }

    except Exception as e:
        logger.error(f"Error calculating passes for {satellite_name}: {e}")
        return {"error": f"Calculation error: {str(e)}"}

# ---------------------------- Legacy Compatibility ----------------------------

def get_next_passes(lat, lon, sat_key, hours=24):
    LEGACY_MAP = {
        'ISS': 'ISS (ZARYA)',
        'HST': 'HST (Hubble)',
        'SO-50': 'SO-50 (SaudiSat-1C)',
        'AO-91': 'AO-91 (RadFxSat)',
        'NOAA-19': 'NOAA 19',
        'NOAA-15': 'NOAA 15',
        'NOAA-18': 'NOAA 18',
    }

    new_name = LEGACY_MAP.get(sat_key, sat_key)
    result = predict_passes(new_name, lat, lon)

    if "error" in result:
        logger.warning(f"Legacy get_next_passes failed for {sat_key}: {result['error']}")
        return []

    return result.get('passes', [])