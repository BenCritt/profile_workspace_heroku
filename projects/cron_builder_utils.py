"""
cron_builder_utils.py — Cron Expression Builder & Parser
Business logic, constants, and helpers extracted from views.py.

Dependencies (add to requirements.txt):
    croniter>=1.4.1
    cron-descriptor>=1.4.3
"""

import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


# ── Library availability flags ─────────────────────────────────────────────────
# Checked at module import time so views can gate UI without try/except clutter.

try:
    from croniter import croniter, CroniterBadCronError  # noqa: F401 (re-exported)
    CRONITER_AVAILABLE = True
except ImportError:
    croniter = None
    CroniterBadCronError = None
    CRONITER_AVAILABLE = False

try:
    from cron_descriptor import get_description, Options as CronDescOptions
    CRON_DESCRIPTOR_AVAILABLE = True
except ImportError:
    get_description = None
    CronDescOptions = None
    CRON_DESCRIPTOR_AVAILABLE = False


# ── Constants ─────────────────────────────────────────────────────────────────

COMMON_TIMEZONES = [
    "UTC",
    "Pacific/Honolulu",
    "America/Anchorage",
    "America/Los_Angeles",
    "America/Denver",
    "America/Phoenix",
    "America/Chicago",
    "America/New_York",
    "America/Sao_Paulo",
    "Europe/London",
    "Europe/Paris",
    "Europe/Berlin",
    "Europe/Moscow",
    "Asia/Dubai",
    "Asia/Kolkata",
    "Asia/Bangkok",
    "Asia/Shanghai",
    "Asia/Tokyo",
    "Australia/Sydney",
]

# Preset library shown beneath the form — label, expression, tooltip hint.
PRESETS = [
    {"label": "Every minute",                 "expr": "* * * * *",     "hint": "Runs every 60 seconds"},
    {"label": "Every 5 minutes",              "expr": "*/5 * * * *",   "hint": "E.g. health checks"},
    {"label": "Every 15 minutes",             "expr": "*/15 * * * *",  "hint": "Quarter-hour polling"},
    {"label": "Every 30 minutes",             "expr": "*/30 * * * *",  "hint": "Half-hour intervals"},
    {"label": "Every hour (top)",             "expr": "0 * * * *",     "hint": "Minute 0 of every hour"},
    {"label": "Every day at midnight",        "expr": "0 0 * * *",     "hint": "Daily batch jobs"},
    {"label": "Every day at noon",            "expr": "0 12 * * *",    "hint": "Lunchtime reports"},
    {"label": "Weekdays at 9 AM",             "expr": "0 9 * * 1-5",   "hint": "Mon–Fri, skip weekends"},
    {"label": "Every Monday at 8 AM",         "expr": "0 8 * * 1",     "hint": "Weekly kickoff"},
    {"label": "First of month, midnight",     "expr": "0 0 1 * *",     "hint": "Monthly billing/cleanup"},
    {"label": "First of month, 6 AM",         "expr": "0 6 1 * *",     "hint": "Monthly reports"},
    {"label": "Every Sunday at 2 AM",         "expr": "0 2 * * 0",     "hint": "Weekend maintenance"},
    {"label": "Twice daily (midnight & noon)","expr": "0 0,12 * * *",  "hint": "Bi-daily sync"},
    {"label": "Every 6 hours",                "expr": "0 */6 * * *",   "hint": "Quarter-day intervals"},
    {"label": "Quarterly (Jan/Apr/Jul/Oct)",  "expr": "0 0 1 */3 *",   "hint": "Quarterly tasks"},
]

# Field metadata: drives the breakdown table and the quick-reference card.
FIELD_META = [
    {"name": "Minute",       "range": "0–59",        "examples": "0, */5, 15,45"},
    {"name": "Hour",         "range": "0–23",        "examples": "0, 12, 8-17"},
    {"name": "Day of Month", "range": "1–31",        "examples": "1, 15, L (last)"},
    {"name": "Month",        "range": "1–12",        "examples": "1, */3, JAN-MAR"},
    {"name": "Day of Week",  "range": "0–6 (Sun=0)", "examples": "1-5, MON, 0,6"},
]

MAX_RUNS     = 50   # hard ceiling to prevent runaway iteration
MIN_RUNS     = 1
DEFAULT_RUNS = 10


# ── Helpers ───────────────────────────────────────────────────────────────────

def get_cron_description(expression: str) -> str:
    """
    Return a plain-English description of a cron expression.

    Uses cron-descriptor when available; falls back to a minimal
    field-by-field summary so the tool stays functional without it.
    """
    if CRON_DESCRIPTOR_AVAILABLE:
        try:
            opts = CronDescOptions()
            opts.throw_exception_on_parse_error = True
            opts.use_24hour_time_format = True
            return get_description(expression, opts)
        except Exception:
            pass  # fall through to manual fallback

    # Manual fallback — no library dependency.
    fields = expression.split()
    if len(fields) == 5:
        names = ["minute", "hour", "day-of-month", "month", "day-of-week"]
        parts = [f"{n}={v}" for n, v in zip(names, fields) if v != "*"]
        return "Runs: " + (", ".join(parts) if parts else "every minute")

    return expression


def generate_next_runs(expression: str, tz: ZoneInfo, count: int) -> list:
    """
    Return a list of dicts describing the next `count` scheduled datetimes.

    croniter works with naive datetimes, so we feed it a naive "now" in the
    target timezone, iterate, then re-attach the tz before returning.
    Returns an empty list if croniter is unavailable.
    """
    if not CRONITER_AVAILABLE:
        return []

    now_local_naive = datetime.datetime.now(tz=tz).replace(tzinfo=None)
    cron = croniter(expression, now_local_naive)

    runs = []
    for i in range(count):
        try:
            next_dt_naive = cron.get_next(datetime.datetime)
            next_dt_aware = next_dt_naive.replace(tzinfo=tz)
            runs.append({
                "index":        i + 1,
                "datetime_str": next_dt_aware.strftime("%Y-%m-%d %H:%M:%S"),
                "day_of_week":  next_dt_aware.strftime("%A"),
                "abbr":         next_dt_aware.strftime("%Z"),
                "epoch":        int(next_dt_aware.timestamp()),
            })
        except (StopIteration, Exception):
            # StopIteration: expression has no future occurrences.
            # Any other exception: malformed step value, etc. — stop gracefully.
            break

    return runs


def build_field_breakdown(expression: str) -> list:
    """
    Pair each field value from the expression with its metadata dict.
    Returns an empty list if the expression doesn't have exactly 5 fields.
    """
    fields = expression.split()
    if len(fields) != 5:
        return []

    breakdown = []
    for meta, value in zip(FIELD_META, fields):
        breakdown.append({
            "name":       meta["name"],
            "value":      value,
            "range":      meta["range"],
            "examples":   meta["examples"],
            "is_wildcard": value == "*",
        })
    return breakdown


def validate_cron_expression(expression: str) -> tuple[bool, str]:
    """
    Validate expression field count and syntax via croniter.

    Returns (is_valid: bool, error_message: str).
    error_message is empty string when valid.
    """
    if not CRONITER_AVAILABLE:
        # Can't validate without croniter — let the view show the library error.
        return True, ""

    fields = expression.split()
    if len(fields) != 5:
        return False, (
            f"A standard cron expression needs exactly 5 fields "
            f"(minute hour dom month weekday). You provided {len(fields)}."
        )

    if not croniter.is_valid(expression):
        return False, (
            "Invalid cron expression — croniter could not parse it. "
            "Check for out-of-range values or malformed step/range syntax."
        )

    return True, ""
