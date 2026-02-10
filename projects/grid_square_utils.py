"""
Grid Square Converter — Maidenhead Locator System utilities.

The Maidenhead Locator System encodes geographic coordinates into a
compact alphanumeric string used worldwide by amateur radio operators.

Structure (each pair adds precision):
    Field      : 2 uppercase letters  (A–R)  → 18×18 grid  (20° lon × 10° lat)
    Square     : 2 digits             (0–9)  → 10×10 sub   (2° lon  × 1° lat)
    Subsquare  : 2 lowercase letters  (a–x)  → 24×24 sub   (5' lon  × 2.5' lat)
    Extended   : 2 digits             (0–9)  → 10×10 sub   (30" lon × 15" lat)

Valid lengths: 4, 6, or 8 characters (always in pairs).

Reference: https://en.wikipedia.org/wiki/Maidenhead_Locator_System

No external dependencies — pure Python math.
"""

import re

# ---------------------------------------------------------------------------
#  Validation
# ---------------------------------------------------------------------------

# Regex patterns for valid grid squares.
GRID_4_RE = re.compile(r"^[A-Ra-r]{2}[0-9]{2}$")
GRID_6_RE = re.compile(r"^[A-Ra-r]{2}[0-9]{2}[A-Xa-x]{2}$")
GRID_8_RE = re.compile(r"^[A-Ra-r]{2}[0-9]{2}[A-Xa-x]{2}[0-9]{2}$")


def validate_grid_square(grid):
    """
    Validate a Maidenhead grid square string.

    Args:
        grid: str — grid square to validate.

    Returns:
        tuple: (normalized_grid: str, error: str or None).
               normalized_grid has uppercase field, digits, lowercase subsquare.
    """
    if not grid or not isinstance(grid, str):
        return None, "Please enter a grid square."

    grid = grid.strip()

    if len(grid) not in (4, 6, 8):
        return None, (
            "Grid square must be 4, 6, or 8 characters "
            "(e.g. EN53, EN53dj, EN53dj27)."
        )

    if len(grid) == 4 and not GRID_4_RE.match(grid):
        return None, (
            "Invalid 4-character grid square. Format: 2 letters (A–R) "
            "followed by 2 digits (e.g. EN53)."
        )
    elif len(grid) == 6 and not GRID_6_RE.match(grid):
        return None, (
            "Invalid 6-character grid square. Format: 2 letters (A–R), "
            "2 digits, 2 letters (A–X) (e.g. EN53dj)."
        )
    elif len(grid) == 8 and not GRID_8_RE.match(grid):
        return None, (
            "Invalid 8-character grid square. Format: 2 letters (A–R), "
            "2 digits, 2 letters (A–X), 2 digits (e.g. EN53dj27)."
        )

    # Normalize: field uppercase, subsquare lowercase.
    normalized = grid[0:2].upper() + grid[2:4]
    if len(grid) >= 6:
        normalized += grid[4:6].lower()
    if len(grid) == 8:
        normalized += grid[6:8]

    return normalized, None


def validate_coordinates(lat, lon):
    """
    Validate latitude and longitude values.

    Returns:
        str or None — error message, or None if valid.
    """
    if lat is None or lon is None:
        return "Please enter both latitude and longitude."

    if not (-90.0 <= lat <= 90.0):
        return "Latitude must be between −90 and 90."

    if not (-180.0 <= lon <= 180.0):
        return "Longitude must be between −180 and 180."

    return None


# ---------------------------------------------------------------------------
#  Grid Square → Coordinates (decode)
# ---------------------------------------------------------------------------

def grid_to_coordinates(grid):
    """
    Convert a Maidenhead grid square to geographic coordinates.

    Returns the center point of the grid square at the given precision,
    plus the bounding box corners.

    Args:
        grid: str — validated/normalized grid square (4, 6, or 8 chars).

    Returns:
        dict with keys:
            "latitude"       : float — center latitude.
            "longitude"      : float — center longitude.
            "lat_display"    : str   — formatted latitude string.
            "lon_display"    : str   — formatted longitude string.
            "precision"      : str   — "Field + Square", "Subsquare", or "Extended".
            "precision_desc" : str   — human-readable area description.
            "bbox"           : dict  — bounding box {lat_min, lat_max, lon_min, lon_max}.
            "grid"           : str   — the normalized input grid.
            "error"          : str or None.
    """
    grid, error = validate_grid_square(grid)
    if error:
        return {"error": error}

    # Decode field (letters A–R → 0–17).
    lon = (ord(grid[0]) - ord("A")) * 20.0 - 180.0
    lat = (ord(grid[1]) - ord("A")) * 10.0 - 90.0

    # Decode square (digits 0–9).
    lon += int(grid[2]) * 2.0
    lat += int(grid[3]) * 1.0

    # Width/height at this precision level.
    lon_width = 2.0
    lat_height = 1.0
    precision = "Field + Square"
    precision_desc = "~111 km × 111 km (2° × 1°)"

    if len(grid) >= 6:
        # Decode subsquare (letters a–x → 0–23).
        lon += (ord(grid[4]) - ord("a")) * (2.0 / 24.0)
        lat += (ord(grid[5]) - ord("a")) * (1.0 / 24.0)
        lon_width = 2.0 / 24.0       # 5 minutes of longitude
        lat_height = 1.0 / 24.0      # 2.5 minutes of latitude
        precision = "Subsquare"
        precision_desc = "~4.6 km × 4.6 km (5' × 2.5')"

    if len(grid) == 8:
        # Decode extended (digits 0–9).
        lon += int(grid[6]) * (2.0 / 240.0)
        lat += int(grid[7]) * (1.0 / 240.0)
        lon_width = 2.0 / 240.0      # 30 seconds of longitude
        lat_height = 1.0 / 240.0     # 15 seconds of latitude
        precision = "Extended"
        precision_desc = "~460 m × 460 m (30\" × 15\")"

    # Center of the grid square.
    center_lat = lat + lat_height / 2.0
    center_lon = lon + lon_width / 2.0

    return {
        "latitude": round(center_lat, 6),
        "longitude": round(center_lon, 6),
        "lat_display": _format_coordinate(center_lat, "lat"),
        "lon_display": _format_coordinate(center_lon, "lon"),
        "precision": precision,
        "precision_desc": precision_desc,
        "bbox": {
            "lat_min": round(lat, 6),
            "lat_max": round(lat + lat_height, 6),
            "lon_min": round(lon, 6),
            "lon_max": round(lon + lon_width, 6),
        },
        "grid": grid,
        "error": None,
    }


# ---------------------------------------------------------------------------
#  Coordinates → Grid Square (encode)
# ---------------------------------------------------------------------------

def coordinates_to_grid(lat, lon, precision=6):
    """
    Convert geographic coordinates to a Maidenhead grid square.

    Args:
        lat: float — latitude (−90 to 90).
        lon: float — longitude (−180 to 180).
        precision: int — 4, 6, or 8 characters of output.

    Returns:
        dict with keys:
            "grid"           : str   — the computed grid square.
            "grid_4"         : str   — 4-character field+square.
            "grid_6"         : str   — 6-character subsquare (if precision >= 6).
            "grid_8"         : str   — 8-character extended (if precision == 8).
            "latitude"       : float — the input latitude.
            "longitude"      : float — the input longitude.
            "lat_display"    : str   — formatted latitude.
            "lon_display"    : str   — formatted longitude.
            "error"          : str or None.
    """
    error = validate_coordinates(lat, lon)
    if error:
        return {"error": error}

    if precision not in (4, 6, 8):
        precision = 6

    # Shift origin to (0, 0) at the southwest corner of AA00.
    adjusted_lon = lon + 180.0
    adjusted_lat = lat + 90.0

    grid = ""

    # Field: 2 uppercase letters (A–R).
    lon_field = int(adjusted_lon / 20.0)
    lat_field = int(adjusted_lat / 10.0)
    # Clamp to valid range (handles edge case of exactly 180 / 90).
    lon_field = min(lon_field, 17)
    lat_field = min(lat_field, 17)
    grid += chr(ord("A") + lon_field)
    grid += chr(ord("A") + lat_field)

    # Remainder within the field.
    rem_lon = adjusted_lon - lon_field * 20.0
    rem_lat = adjusted_lat - lat_field * 10.0

    # Square: 2 digits (0–9).
    lon_sq = int(rem_lon / 2.0)
    lat_sq = int(rem_lat / 1.0)
    lon_sq = min(lon_sq, 9)
    lat_sq = min(lat_sq, 9)
    grid += str(lon_sq)
    grid += str(lat_sq)

    grid_4 = grid

    grid_6 = ""
    grid_8 = ""

    if precision >= 6:
        rem_lon -= lon_sq * 2.0
        rem_lat -= lat_sq * 1.0

        # Subsquare: 2 lowercase letters (a–x).
        lon_sub = int(rem_lon / (2.0 / 24.0))
        lat_sub = int(rem_lat / (1.0 / 24.0))
        lon_sub = min(lon_sub, 23)
        lat_sub = min(lat_sub, 23)
        grid += chr(ord("a") + lon_sub)
        grid += chr(ord("a") + lat_sub)

        grid_6 = grid

        if precision == 8:
            rem_lon -= lon_sub * (2.0 / 24.0)
            rem_lat -= lat_sub * (1.0 / 24.0)

            # Extended: 2 digits (0–9).
            lon_ext = int(rem_lon / (2.0 / 240.0))
            lat_ext = int(rem_lat / (1.0 / 240.0))
            lon_ext = min(lon_ext, 9)
            lat_ext = min(lat_ext, 9)
            grid += str(lon_ext)
            grid += str(lat_ext)

            grid_8 = grid

    return {
        "grid": grid,
        "grid_4": grid_4,
        "grid_6": grid_6,
        "grid_8": grid_8,
        "latitude": round(lat, 6),
        "longitude": round(lon, 6),
        "lat_display": _format_coordinate(lat, "lat"),
        "lon_display": _format_coordinate(lon, "lon"),
        "error": None,
    }


# ---------------------------------------------------------------------------
#  ZIP Code → Grid Square (convenience wrapper)
# ---------------------------------------------------------------------------

def zip_to_grid(zip_code, get_coordinates_fn):
    """
    Convert a US ZIP code to a Maidenhead grid square by geocoding first.

    Args:
        zip_code: str — 5-digit US ZIP code.
        get_coordinates_fn: callable — the shared get_coordinates(zip_code)
                            function from utils.py.  Returns (lat, lon)
                            or None.

    Returns:
        dict — same structure as coordinates_to_grid(), plus:
            "zip_code"  : str — the input ZIP.
            "zip_error" : str or None — geocoding error message.
    """
    if not zip_code or not zip_code.strip().isdigit() or len(zip_code.strip()) != 5:
        return {"error": "Enter a valid 5-digit US ZIP code.", "zip_error": True}

    coords = get_coordinates_fn(zip_code.strip())
    if coords is None:
        return {
            "error": f"Could not geocode ZIP code '{zip_code}'.",
            "zip_error": True,
        }

    lat, lon = coords
    result = coordinates_to_grid(lat, lon, precision=8)
    result["zip_code"] = zip_code.strip()
    result["zip_error"] = None
    return result


# ---------------------------------------------------------------------------
#  Coordinate formatting helpers
# ---------------------------------------------------------------------------

def _format_coordinate(value, axis):
    """
    Format a decimal degree value as a human-readable string.
    Example: 43.073100 → "43.0731° N"
    """
    if axis == "lat":
        direction = "N" if value >= 0 else "S"
    else:
        direction = "E" if value >= 0 else "W"

    return f"{abs(value):.4f}° {direction}"


def _format_dms(value, axis):
    """
    Format a decimal degree value as degrees, minutes, seconds.
    Example: 43.073100 → "43° 4' 23.2\" N"
    """
    if axis == "lat":
        direction = "N" if value >= 0 else "S"
    else:
        direction = "E" if value >= 0 else "W"

    value = abs(value)
    degrees = int(value)
    minutes_float = (value - degrees) * 60
    minutes = int(minutes_float)
    seconds = (minutes_float - minutes) * 60

    return f'{degrees}° {minutes}\' {seconds:.1f}" {direction}'


# ---------------------------------------------------------------------------
#  Grid square metadata (for educational content)
# ---------------------------------------------------------------------------

PRECISION_TABLE = [
    {
        "characters": "4 (Field + Square)",
        "example": "EN53",
        "lon_resolution": "2°",
        "lat_resolution": "1°",
        "approx_area": "~111 km × 111 km",
    },
    {
        "characters": "6 (Subsquare)",
        "example": "EN53dj",
        "lon_resolution": "5'",
        "lat_resolution": "2.5'",
        "approx_area": "~4.6 km × 4.6 km",
    },
    {
        "characters": "8 (Extended)",
        "example": "EN53dj27",
        "lon_resolution": "30\"",
        "lat_resolution": "15\"",
        "approx_area": "~460 m × 460 m",
    },
]
