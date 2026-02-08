"""
Repeater Finder — Route-based VHF/UHF repeater search utilities.

Workflow:
  1. Google Maps Directions API → encoded polyline for the driving route.
  2. Decode polyline → list of (lat, lon) waypoints.
  3. Sample waypoints at a configurable interval.
  4. Query RepeaterBook proximity API at each sample point (with backoff).
  5. Deduplicate, filter, and sort repeaters by position along route.

Includes Async Task Management to prevent Heroku H12 Timeouts.
"""

import math
import time
import logging
import requests
import os
import uuid
import threading
from django.core.cache import cache

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
#  Constants
# ---------------------------------------------------------------------------

# API Key retrieved from environment variables (Production standard)
# GOOGLE_MAPS_API_KEY = os.environ.get("GOOGLE_MAPS_KEY")
GOOGLE_MAPS_API_KEY = "AIzaSyD0xBXRANSgMPe8HvaE2rSmm7u8E8QYAyM"  # Placeholder for development/testing. Replace with env var in production.

GOOGLE_DIRECTIONS_URL = "https://maps.googleapis.com/maps/api/directions/json"

# CHANGED: Use prox.php for location-based searches. export.php ignores lat/lon.
REPEATERBOOK_API_URL = "https://www.repeaterbook.com/api/export.php"

# RepeaterBook asks for a descriptive User-Agent with contact info.
REPEATERBOOK_HEADERS = {
    "User-Agent": "Repeater Finder by Ben Crittenden (+https://www.bencritt.net/)",
}

# CHANGED: Increased delay to 5.0s to mimic human browsing and avoid 429 blocks.
REPEATERBOOK_NORMAL_DELAY = 5.0 

# CHANGED: Increased backoff to 60s (max recommended) to clear penalty box.
REPEATERBOOK_BACKOFF_DELAY = 60.0

# Earth radius in miles (for Haversine calculations).
EARTH_RADIUS_MI = 3958.8

# Band ranges in MHz for filtering.
BAND_RANGES = {
    "6m":     (50.0, 54.0),
    "2m":     (144.0, 148.0),
    "1.25m":  (222.0, 225.0),
    "70cm":   (420.0, 450.0),
}

DEFAULT_BANDS = ["2m", "70cm"]

# Default search radius in miles from the route centerline.
DEFAULT_SEARCH_RADIUS_MI = 30

# CHANGED: Increased interval to 55 miles.
# Since search radius is 30mi, 55mi spacing still ensures good coverage 
# (30+30=60mi diameter) but reduces total API calls by ~20%.
DEFAULT_SAMPLE_INTERVAL_MI = 55

# Maximum sample points (safety cap for very long routes).
MAX_SAMPLE_POINTS = 30

# Cache timeout for task results (1 hour)
CACHE_TIMEOUT = 3600


# ---------------------------------------------------------------------------
#  Async Task Management (Thread + Cache)
# ---------------------------------------------------------------------------

def start_search_task(origin_zip, dest_zip, search_radius, bands):
    """
    Starts a background thread to perform the search.
    Returns: task_id (str)
    """
    task_id = str(uuid.uuid4())
    
    # Initialize task state in cache
    initial_state = {
        "status": "processing",
        "progress": "Initializing route...",
        "result": None,
        "error": None
    }
    cache.set(f"repeater_task_{task_id}", initial_state, CACHE_TIMEOUT)

    # Define the worker function
    def worker():
        try:
            # Update progress: Route Fetching
            _update_task(task_id, status="processing", progress="Calculating driving route...")
            
            # Run the heavy synchronous logic
            result = find_repeaters_along_route(
                origin_zip, 
                dest_zip, 
                search_radius_mi=search_radius,
                bands=bands,
                task_id_for_progress=task_id 
            )
            
            # Save final result
            if result.get("error"):
                _update_task(task_id, status="error", error=result["error"])
            else:
                _update_task(task_id, status="done", result=result)
            
        except Exception as e:
            logger.error(f"Task {task_id} failed: {e}")
            _update_task(task_id, status="error", error=f"Internal Server Error: {str(e)}")

    # Start thread (Daemon=True ensures it doesn't block server shutdown)
    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    
    return task_id

def get_task_status(task_id):
    """Retrieves the current status of a task from the cache."""
    return cache.get(f"repeater_task_{task_id}")

def _update_task(task_id, **kwargs):
    """Helper to update specific fields of the task in cache."""
    key = f"repeater_task_{task_id}"
    data = cache.get(key) or {}
    data.update(kwargs)
    cache.set(key, data, CACHE_TIMEOUT)


# ---------------------------------------------------------------------------
#  Google Maps Directions — get route polyline
# ---------------------------------------------------------------------------

def get_route_polyline(origin_zip, dest_zip, timeout=10):
    """
    Fetch the driving route between two US ZIP codes or addresses.
    """
    params = {
        "origin": origin_zip,
        "destination": dest_zip,
        "mode": "driving",
        "units": "imperial",
        "key": GOOGLE_MAPS_API_KEY, 
    }
    try:
        resp = requests.get(GOOGLE_DIRECTIONS_URL, params=params, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as exc:
        raise ValueError(f"Directions API request failed: {exc}")

    if data.get("status") != "OK":
        status = data.get("status", "UNKNOWN")
        error_msg = data.get("error_message", "No details provided.")
        raise ValueError(f"Google Maps API Error ({status}): {error_msg}")

    if not data.get("routes"):
        raise ValueError(f"Could not find a driving route between {origin_zip} and {dest_zip}.")

    route = data["routes"][0]
    leg = route["legs"][0]

    return {
        "polyline": route["overview_polyline"]["points"],
        "distance_miles": round(leg["distance"]["value"] / 1609.344, 1),
        "duration_text": leg["duration"]["text"],
        "summary": route.get("summary", ""),
        "origin_addr": leg.get("start_address", origin_zip),
        "dest_addr": leg.get("end_address", dest_zip),
    }


# ---------------------------------------------------------------------------
#  Polyline decoding
# ---------------------------------------------------------------------------

def decode_polyline(encoded):
    points = []
    index = 0
    lat = 0
    lng = 0
    length = len(encoded)

    while index < length:
        shift = 0
        result = 0
        while True:
            b = ord(encoded[index]) - 63
            index += 1
            result |= (b & 0x1F) << shift
            shift += 5
            if b < 0x20:
                break
        lat += (~(result >> 1) if (result & 1) else (result >> 1))

        shift = 0
        result = 0
        while True:
            b = ord(encoded[index]) - 63
            index += 1
            result |= (b & 0x1F) << shift
            shift += 5
            if b < 0x20:
                break
        lng += (~(result >> 1) if (result & 1) else (result >> 1))

        points.append((lat / 1e5, lng / 1e5))

    return points


# ---------------------------------------------------------------------------
#  Haversine distance
# ---------------------------------------------------------------------------

def haversine_miles(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return EARTH_RADIUS_MI * 2 * math.asin(math.sqrt(a))


# ---------------------------------------------------------------------------
#  Route sampling
# ---------------------------------------------------------------------------

def sample_route(polyline_points, interval_mi=DEFAULT_SAMPLE_INTERVAL_MI):
    if not polyline_points:
        return []

    samples = []
    cumulative = 0.0
    next_sample_at = 0.0

    prev_lat, prev_lon = polyline_points[0]
    samples.append((prev_lat, prev_lon, 0.0))
    next_sample_at = interval_mi

    for lat, lon in polyline_points[1:]:
        seg_dist = haversine_miles(prev_lat, prev_lon, lat, lon)
        cumulative += seg_dist

        if cumulative >= next_sample_at:
            samples.append((lat, lon, round(cumulative, 1)))
            next_sample_at = cumulative + interval_mi

        prev_lat, prev_lon = lat, lon

        if len(samples) >= MAX_SAMPLE_POINTS:
            break

    # Ensure endpoint is included if needed
    last_lat, last_lon = polyline_points[-1]
    last_sample_lat, last_sample_lon, _ = samples[-1]
    if haversine_miles(last_sample_lat, last_sample_lon, last_lat, last_lon) > 2.0:
        samples.append((last_lat, last_lon, round(cumulative, 1)))

    return samples


# ---------------------------------------------------------------------------
#  RepeaterBook API query (With Retry Logic)
# ---------------------------------------------------------------------------

def query_repeaterbook(lat, lon, radius_mi=DEFAULT_SEARCH_RADIUS_MI, timeout=15):
    """
    Query RepeaterBook proximity API using export.php with qtype=prox.
    """
    params = {
        "qtype": "prox",       # This triggers the proximity mode
        "lat": lat,
        "lng": lon,            # Note: 'lng' instead of 'lon' for this endpoint
        "dist": radius_mi,     # Note: 'dist' instead of 'distance'
        "dunit": "m",          # 'm' for miles, 'km' for kilometers
        "band": "14,4",        # 2m and 70cm
    }
    
    max_retries = 2
    
    for attempt in range(max_retries + 1):
        try:
            resp = requests.get(
                REPEATERBOOK_API_URL,
                params=params,
                headers=REPEATERBOOK_HEADERS,
                timeout=timeout,
            )
            
            # Check specifically for Rate Limit (429)
            if resp.status_code == 429:
                logger.warning(f"RepeaterBook 429 Rate Limit at attempt {attempt+1}. Sleeping {REPEATERBOOK_BACKOFF_DELAY}s...")
                time.sleep(REPEATERBOOK_BACKOFF_DELAY)
                continue # Retry loop
            
            resp.raise_for_status()
            
            if not resp.text.strip():
                return []
                
            data = resp.json()
            
            if isinstance(data, list):
                return data
            elif isinstance(data, dict):
                # prox.php typically returns a list, but handle wrapper dicts just in case
                return data.get("results", [])
            return []
            
        except (requests.RequestException, ValueError) as exc:
            if attempt == max_retries:
                logger.warning("RepeaterBook query failed at (%.4f, %.4f): %s", lat, lon, exc)
                return []
            time.sleep(1.0)
            
    return []


# ---------------------------------------------------------------------------
#  Repeater normalization and filtering
# ---------------------------------------------------------------------------

def _parse_frequency(freq_str):
    try:
        return float(freq_str)
    except (TypeError, ValueError):
        return None

def _classify_band(freq):
    if freq is None:
        return None
    for band_label, (low, high) in BAND_RANGES.items():
        if low <= freq <= high:
            return band_label
    return None

def normalize_repeater(raw, sample_lat, sample_lon, cumulative_mi):
    freq = _parse_frequency(raw.get("Frequency"))
    if freq is None:
        return None

    band = _classify_band(freq)

    try:
        rpt_lat = float(raw.get("Lat", 0))
        rpt_lon = float(raw.get("Long", 0))
    except (TypeError, ValueError):
        rpt_lat, rpt_lon = 0.0, 0.0

    if rpt_lat and rpt_lon:
        dist_from_route = round(haversine_miles(sample_lat, sample_lon, rpt_lat, rpt_lon), 1)
    else:
        dist_from_route = None

    input_freq = _parse_frequency(raw.get("Input Freq"))
    if input_freq and freq:
        offset_mhz = round(input_freq - freq, 4)
        if offset_mhz > 0:
            offset_display = f"+{abs(offset_mhz):.3f} MHz"
        elif offset_mhz < 0:
            offset_display = f"−{abs(offset_mhz):.3f} MHz"
        else:
            offset_display = "Simplex"
    else:
        offset_display = raw.get("Offset", "Unknown")

    return {
        "frequency": freq,
        "frequency_display": f"{freq:.4f}" if freq else "",
        "input_freq": input_freq,
        "offset_display": offset_display,
        "band": band,
        "band_display": band.upper().replace("M", "m").replace("CM", "cm") if band else "Other",
        "pl_tone": raw.get("PL", raw.get("Encode", "")).strip() or "None",
        "callsign": raw.get("Callsign", "").strip().upper(),
        "city": raw.get("Nearest City", raw.get("City", "")).strip(),
        "state": raw.get("State", raw.get("Operational Status", "")).strip(),
        "use": raw.get("Use", "OPEN").strip().upper(),
        "latitude": rpt_lat,
        "longitude": rpt_lon,
        "dist_from_route_mi": dist_from_route,
        "approx_route_mile": cumulative_mi,
    }

def filter_and_deduplicate(repeaters, bands=None):
    """
    Filter by band and usage (removing CLOSED/PRIVATE), then deduplicate.
    """
    if bands:
        repeaters = [r for r in repeaters if r["band"] in bands]

    # Filter out CLOSED/PRIVATE systems
    filtered_repeaters = []
    for r in repeaters:
        use_status = r["use"]
        if "CLOSED" in use_status or "PRIVATE" in use_status:
            continue
        filtered_repeaters.append(r)

    # Deduplicate by (callsign, frequency)
    seen = set()
    unique = []
    for r in filtered_repeaters:
        key = (r["callsign"], r["frequency"])
        if key not in seen:
            seen.add(key)
            unique.append(r)

    # Sort by position along route
    unique.sort(key=lambda r: (r["approx_route_mile"] or 0, r["frequency"]))
    return unique


# ---------------------------------------------------------------------------
#  Main orchestrator
# ---------------------------------------------------------------------------

def find_repeaters_along_route(
    origin_zip,
    dest_zip,
    search_radius_mi=DEFAULT_SEARCH_RADIUS_MI,
    sample_interval_mi=DEFAULT_SAMPLE_INTERVAL_MI,
    bands=None,
    task_id_for_progress=None,
):
    """
    End-to-end: finds repeaters along a route. 
    Can update a cache task with progress if task_id_for_progress is provided.
    """
    result = {
        "route": None,
        "repeaters": [],
        "sample_count": 0,
        "error": None,
    }

    # 1. Fetch Route
    try:
        route_info = get_route_polyline(origin_zip, dest_zip)
    except ValueError as exc:
        result["error"] = str(exc)
        return result

    result["route"] = route_info

    # 2. Decode Polyline
    polyline_points = decode_polyline(route_info["polyline"])
    if not polyline_points:
        result["error"] = "Route returned an empty polyline."
        return result

    # 3. Sample Points
    samples = sample_route(polyline_points, interval_mi=sample_interval_mi)
    result["sample_count"] = len(samples)

    if task_id_for_progress:
        _update_task(task_id_for_progress, progress=f"Route found ({result['route']['distance_miles']} mi). Scanning {len(samples)} zones...")

    # 4. Query Points
    all_repeaters = []
    for i, (lat, lon, cum_mi) in enumerate(samples):
        # Update progress bar
        if task_id_for_progress:
            percent = int((i / len(samples)) * 100)
            _update_task(task_id_for_progress, progress=f"Scanning mile {int(cum_mi)}... ({percent}%)")

        raw_results = query_repeaterbook(lat, lon, radius_mi=search_radius_mi)
        
        for raw in raw_results:
            normalized = normalize_repeater(raw, lat, lon, cum_mi)
            if normalized:
                all_repeaters.append(normalized)

        # Rate-limit delay (skip after last request)
        if i < len(samples) - 1:
            time.sleep(REPEATERBOOK_NORMAL_DELAY)

    # 5. Filter & Sort
    if bands is None:
        bands = DEFAULT_BANDS

    if task_id_for_progress:
        _update_task(task_id_for_progress, progress="Finalizing results...")

    result["repeaters"] = filter_and_deduplicate(all_repeaters, bands=bands)
    return result