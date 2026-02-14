# projects/satellite_pass_predictor_utils.py
from django.core.cache import cache
from skyfield.api import load, wgs84
from skyfield.sgp4lib import EarthSatellite
from zoneinfo import ZoneInfo
import requests
import datetime
import logging

logger = logging.getLogger(__name__)

# ---------------------------- Config ----------------------------

HEADERS = {
    'User-Agent': 'Satellite Pass Predictor by Ben Crittenden (+https://www.bencritt.net)',
    'Accept': 'text/plain,text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
}

# Map internal keys to Celestrak URLs
# "Special" satellites are fetched individually to avoid API parsing errors with lists.
SOURCES = {
    'stations': 'https://celestrak.org/NORAD/elements/stations.txt',
    'amateur': 'https://celestrak.org/NORAD/elements/amateur.txt',
    'weather': 'https://celestrak.org/NORAD/elements/weather.txt',
    'sarsat': 'https://celestrak.org/NORAD/elements/sarsat.txt',
    'science': 'https://celestrak.org/NORAD/elements/science.txt',
    
    # Individual fetch URLs for satellites missing from standard lists
    'noaa_15': 'https://celestrak.org/NORAD/elements/gp.php?CATNR=25338&FORMAT=tle',
    'noaa_18': 'https://celestrak.org/NORAD/elements/gp.php?CATNR=28654&FORMAT=tle',
    'noaa_19': 'https://celestrak.org/NORAD/elements/gp.php?CATNR=33591&FORMAT=tle',
    'aqua':    'https://celestrak.org/NORAD/elements/gp.php?CATNR=27424&FORMAT=tle',
    'landsat_8': 'https://celestrak.org/NORAD/elements/gp.php?CATNR=39084&FORMAT=tle',
    'landsat_9': 'https://celestrak.org/NORAD/elements/gp.php?CATNR=49260&FORMAT=tle',
    'sentinel_2a': 'https://celestrak.org/NORAD/elements/gp.php?CATNR=40697&FORMAT=tle',
    'ajisai': 'https://celestrak.org/NORAD/elements/gp.php?CATNR=16908&FORMAT=tle',
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
]

TLE_CACHE_TIMEOUT = 3600 * 4  # 4 hours

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

def _fetch_tle_for_group(group_key):
    if group_key not in SOURCES:
        raise ValueError(f"Unknown source group: {group_key}")
    
    url = SOURCES[group_key]
    cache_key = f"tle_source_{group_key}_v4" # Updated cache key to v4
    
    cached = cache.get(cache_key)
    if cached:
        return cached

    try:
        # Pass HEADERS to mimic a browser
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        text = resp.text.splitlines()
        text = [line.strip() for line in text if line.strip()]
        
        # Validation: Ensure we actually got TLE data
        if not text or not any(line.startswith("1 ") for line in text[:20]):
            snippet = text[0] if text else "Empty response"
            raise ValueError(f"Response from {url} does not look like TLE data. Content: '{snippet}'")

        cache.set(cache_key, text, TLE_CACHE_TIMEOUT)
        return text
    except requests.RequestException as e:
        raise ConnectionError(f"Failed to fetch TLE from {url}: {e}")

def _extract_tle(sat_name, norad_id, tle_lines):
    target_id = int(norad_id)
    
    # 1. Standard search for 2-line format
    for i, line in enumerate(tle_lines):
        if line.startswith("2 "):
            try:
                line_id = int(line[2:7].strip())
                if line_id == target_id:
                    if i > 0:
                        return tle_lines[i-1], line
            except (ValueError, IndexError):
                continue
                
    # 2. Fallback for Single-Sat fetch (where only 3 lines might exist: Name, Line1, Line2)
    # If the file is just one satellite, sometimes Line 1 is the first line.
    if len(tle_lines) >= 2 and tle_lines[0].startswith("1 ") and tle_lines[1].startswith("2 "):
        try:
             # Verify ID in line 2
             line_id = int(tle_lines[1][2:7].strip())
             if line_id == target_id:
                 return tle_lines[0], tle_lines[1]
        except ValueError:
            pass

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

        # 2. Fetch TLE
        tle_lines = _fetch_tle_for_group(sat_config['celestrak_group'])
        line1, line2 = _extract_tle(sat_config['name'], sat_config['norad_id'], tle_lines)
        
        # 3. Calculate
        ts = load.timescale()
        satellite = EarthSatellite(line1, line2, sat_config['name'], ts)
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