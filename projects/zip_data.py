"""
zip_data.py — Local ZIP code lookup with API fallback.

Lookup chain (stops at first success):
  1. Local dataset  — instant, free, covers ~41,000 US ZIPs.
  2. Django cache    — free, populated by a previous API call.
  3. Google Maps API — live Geocoding call, result is cached for next time.

The JSON file is generated offline by generate_zip_dataset.py using
GeoNames data via pgeocode. The dataset covers ~41,000 active US ZIP
codes and is approximately 2–3 MB in memory.

Usage:
    from .zip_data import local_get_coordinates, local_get_location_data

    # Drop-in replacement for utils.get_coordinates()
    coords = local_get_coordinates("53190")
    # Returns: (42.8336, -88.7326) or None

    # Drop-in replacement for utils.get_location_data()
    location = local_get_location_data("53190")
    # Returns: {"lat": 42.8336, "lng": -88.7326, "city": "Whitewater", "state": "Wisconsin"} or None
"""

import json
import os
import logging

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
#  Lazy-loaded dataset (singleton)
# ---------------------------------------------------------------------------

_zip_dataset = None

# Path to the JSON file, relative to this module's directory.
# Expected location: projects/data/us_zip_data.json
_DATA_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "data",
    "us_zip_data.json",
)


def _load_dataset():
    """
    Load the ZIP code dataset from disk on first access.

    The file is read once and kept in module-level memory for the
    lifetime of the process. On a Heroku dyno this means it survives
    across requests until the dyno restarts (~24 h or deploy).
    """
    global _zip_dataset
    if _zip_dataset is not None:
        return _zip_dataset

    try:
        with open(_DATA_FILE, "r") as f:
            _zip_dataset = json.load(f)
        logger.info("Loaded %d ZIP codes from %s", len(_zip_dataset), _DATA_FILE)
    except FileNotFoundError:
        logger.error(
            "ZIP dataset not found at %s. "
            "Run generate_zip_dataset.py and copy the output to projects/data/.",
            _DATA_FILE,
        )
        _zip_dataset = {}
    except Exception as e:
        logger.error("Failed to load ZIP dataset: %s", e)
        _zip_dataset = {}

    return _zip_dataset


# ---------------------------------------------------------------------------
#  Public lookup functions (with fallback chain)
# ---------------------------------------------------------------------------

def local_get_coordinates(zip_code):
    """
    Look up coordinates for a US ZIP code.

    Fallback chain:
      1. Local dataset (instant, free)
      2. Django cache (free, from a previous API call)
      3. Google Geocoding API (live call, caches result for next time)

    Drop-in replacement for utils.get_coordinates().

    Args:
        zip_code (str): A US ZIP code (e.g., "53190").

    Returns:
        tuple: (lat, lng) or None if all sources fail.
    """
    # 1. Try local dataset first.
    dataset = _load_dataset()
    normalized = str(zip_code).strip().zfill(5)
    entry = dataset.get(normalized)

    if entry is not None:
        return (entry["lat"], entry["lng"])

    # 2–3. Fall back to the cached/API version in utils.py.
    # get_coordinates() already checks Django cache before making an API call.
    logger.info("ZIP %s not in local dataset, falling back to Google Geocoding API.", normalized)
    from .utils import get_coordinates
    return get_coordinates(zip_code)


def local_get_location_data(zip_code):
    """
    Look up coordinates, city, and state for a US ZIP code.

    Fallback chain:
      1. Local dataset (instant, free)
      2. Django cache (free, from a previous API call)
      3. Google Geocoding API (live call, caches result for next time)

    Drop-in replacement for utils.get_location_data().

    Args:
        zip_code (str): A US ZIP code (e.g., "53190").

    Returns:
        dict with keys: lat, lng, city, state — or None if all sources fail.
    """
    # 1. Try local dataset first.
    dataset = _load_dataset()
    normalized = str(zip_code).strip().zfill(5)
    entry = dataset.get(normalized)

    if entry is not None:
        # Return a copy to prevent accidental mutation of the cached dataset.
        return {
            "lat": entry["lat"],
            "lng": entry["lng"],
            "city": entry["city"],
            "state": entry["state"],
        }

    # 2–3. Fall back to the cached/API version in utils.py.
    # get_location_data() already checks Django cache before making an API call.
    logger.info("ZIP %s not in local dataset, falling back to Google Geocoding API.", normalized)
    from .utils import get_location_data
    return get_location_data(zip_code)
