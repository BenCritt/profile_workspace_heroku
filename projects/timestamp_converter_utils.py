"""
timestamp_converter_utils.py — Unix Timestamp Converter
Business logic and helpers extracted from views.py.
Pure stdlib — no external dependencies required.
"""

import datetime
import time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


# ── Constants ─────────────────────────────────────────────────────────────────

COMMON_TIMEZONES = [
    "UTC",
    "Pacific/Honolulu",    # UTC-10
    "America/Anchorage",   # UTC-9
    "America/Los_Angeles", # UTC-8
    "America/Denver",      # UTC-7
    "America/Phoenix",     # UTC-7 (no DST)
    "America/Chicago",     # UTC-6
    "America/New_York",    # UTC-5
    "America/Sao_Paulo",   # UTC-3
    "Europe/London",       # UTC+0/+1
    "Europe/Paris",        # UTC+1/+2
    "Europe/Berlin",       # UTC+1/+2
    "Europe/Moscow",       # UTC+3
    "Asia/Dubai",          # UTC+4
    "Asia/Kolkata",        # UTC+5:30
    "Asia/Bangkok",        # UTC+7
    "Asia/Shanghai",       # UTC+8
    "Asia/Tokyo",          # UTC+9
    "Australia/Sydney",    # UTC+10/+11
]

# Millisecond auto-detection threshold: any epoch value above this number is
# implausibly large for seconds (it would be past year 3000), so treat as ms.
_MS_THRESHOLD = 32_503_680_000  # seconds equivalent of year 3000-01-01


# ── Helpers ───────────────────────────────────────────────────────────────────

def safe_epoch_to_dt(raw: str) -> tuple:
    """
    Parse a raw epoch string into a UTC-aware datetime.

    Handles both seconds (10-digit) and milliseconds (13-digit) automatically.
    Returns (dt_utc: datetime, epoch_seconds: float).
    Raises ValueError with a user-friendly message on bad input.
    """
    try:
        epoch = float(raw)
    except ValueError:
        raise ValueError(f"'{raw}' is not a valid number.")

    # Auto-detect milliseconds.
    if epoch > _MS_THRESHOLD:
        epoch = epoch / 1000.0

    try:
        dt_utc = datetime.datetime.fromtimestamp(epoch, tz=ZoneInfo("UTC"))
    except (OSError, OverflowError, ValueError):
        raise ValueError(
            "Timestamp is out of the supported range "
            "(roughly 1970–2038 on 32-bit systems, up to year 9999 on 64-bit)."
        )

    return dt_utc, epoch


def build_tz_table(dt_utc: datetime.datetime, tz_list: list) -> list:
    """
    Return a list of dicts — one per timezone — showing the local representation
    of the given UTC datetime.  Invalid / unknown timezone names are skipped silently.
    """
    rows = []
    for tz_name in tz_list:
        try:
            tz = ZoneInfo(tz_name)
            dt_local = dt_utc.astimezone(tz)
            offset_str = dt_local.strftime("%z")  # e.g. -0500
            # Insert colon for readability: -0500 → -05:00
            if len(offset_str) == 5:
                offset_str = f"{offset_str[:3]}:{offset_str[3:]}"
            rows.append({
                "timezone":     tz_name,
                "datetime_str": dt_local.strftime("%Y-%m-%d %H:%M:%S"),
                "day_of_week":  dt_local.strftime("%A"),
                "abbr":         dt_local.strftime("%Z"),
                "utc_offset":   offset_str,
            })
        except (ZoneInfoNotFoundError, Exception):
            continue  # skip unknown zones; never crash the whole page
    return rows


def relative_time(epoch: float) -> str:
    """
    Return a human-friendly relative time string.
    Examples: 'just now', '3 hours ago', 'in 2 days'.
    """
    now = time.time()
    diff = epoch - now          # positive = future, negative = past
    abs_diff = abs(diff)

    def _plural(n: float, unit: str) -> str:
        n_int = int(n)
        return f"{n_int} {unit}{'s' if n_int != 1 else ''}"

    if abs_diff < 10:
        return "just now"
    elif abs_diff < 60:
        label = _plural(abs_diff, "second")
    elif abs_diff < 3_600:
        label = _plural(abs_diff / 60, "minute")
    elif abs_diff < 86_400:
        label = _plural(abs_diff / 3_600, "hour")
    elif abs_diff < 86_400 * 30:
        label = _plural(abs_diff / 86_400, "day")
    elif abs_diff < 86_400 * 365:
        label = _plural(abs_diff / (86_400 * 30), "month")
    else:
        label = _plural(abs_diff / (86_400 * 365), "year")

    return f"in {label}" if diff > 10 else f"{label} ago"


def get_current_epoch() -> tuple[int, int]:
    """Return (epoch_seconds, epoch_milliseconds) as integers."""
    now = time.time()
    return int(now), int(now * 1000)
