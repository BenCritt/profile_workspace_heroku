# projects/freight_bid_sheet_builder_utils.py
#
# ============================================================================
# Lane RFP / Bid Sheet Pricing Builder — pure calculation layer
# ============================================================================
# Everything the view needs to turn a pasted lane CSV into priced lanes,
# portfolio roll-ups, a headhaul/backhaul state balance, and a CSV export.
# The view stays a thin HTTP adapter; every function here is individually
# testable and Decimal-only in its money/mile math.
#
# Public functions (called from views_freight_tools.freight_bid_sheet_builder):
#   parse_lanes(raw_text, mode)              — Section 3
#   resolve_distances(lanes, daily_budget)   — Section 4 (Google mode only)
#   price_lane(lane, **globals)              — Section 5 + 6
#   build_rollups(priced_lanes)              — Section 8
#   build_state_balance(priced_lanes)        — Section 9
#   build_csv_rows(priced_lanes)             — Section 10 (download file)
#   build_export_lanes_csv_text(priced_lanes)— Section 10 (hidden re-post field)
#
# Section numbers above refer to the July 2026 build spec this module
# implements verbatim; see that document for the full rationale behind
# each design choice noted in the comments below.
# ============================================================================

import csv
import io
import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


# ============================================================================
# Constants
# ============================================================================

MAX_LANES = 25

# Round-trip sentinel used ONLY by the CSV-export re-post mechanism
# (Section 10) to carry a DISTANCE_UNAVAILABLE lane through the export's
# forced-manual-mode re-price without either (a) tripping the "miles
# required in manual mode" row error or (b) attempting a fresh Google
# lookup (export always runs with use_google forced off — there is no
# other channel to signal "this lane has no resolvable distance" through
# a stateless re-post). A human typing "NA" by hand hits the identical,
# harmless code path: the lane simply prices as unavailable.
NO_DISTANCE_SENTINEL = "NA"

_ZIP5_OR_ZIP9_RE = re.compile(r"^\d{5}(-\d{4})?$")

# Section 3.3.5 — equipment normalization (case-insensitive, trimmed).
EQUIPMENT_ALIASES = {
    "v": "V", "van": "V", "dry": "V", "dry van": "V", "dv": "V", "53v": "V",
    "r": "R", "reefer": "R", "refrigerated": "R", "rf": "R",
    "f": "F", "fb": "F", "flat": "F", "flatbed": "F",
}

# Section 9.1 — ZIP3 -> state range table, embedded verbatim as a code
# constant. Tuples of (lo, hi, state) on zero-padded 3-char strings;
# first match wins (string comparison is safe here because every bound
# is exactly 3 zero-padded digits). This trades a handful of edge-case
# prefixes for zero external dependencies -- plenty accurate for a
# directional deadhead/balance report.
ZIP3_STATE_RANGES = (
    ("005", "005", "NY"), ("006", "007", "PR"), ("008", "008", "VI"), ("009", "009", "PR"),
    ("010", "027", "MA"), ("028", "029", "RI"), ("030", "038", "NH"), ("039", "049", "ME"),
    ("050", "059", "VT"), ("060", "069", "CT"), ("070", "089", "NJ"), ("090", "098", "AE"),
    ("100", "149", "NY"), ("150", "196", "PA"), ("197", "199", "DE"),
    ("200", "200", "DC"), ("201", "201", "VA"), ("202", "205", "DC"), ("206", "219", "MD"),
    ("220", "246", "VA"), ("247", "268", "WV"), ("270", "289", "NC"), ("290", "299", "SC"),
    ("300", "319", "GA"), ("320", "339", "FL"), ("340", "340", "AA"), ("341", "349", "FL"),
    ("350", "369", "AL"), ("370", "385", "TN"), ("386", "397", "MS"), ("398", "399", "GA"),
    ("400", "427", "KY"), ("430", "459", "OH"), ("460", "479", "IN"), ("480", "499", "MI"),
    ("500", "528", "IA"), ("530", "549", "WI"), ("550", "567", "MN"), ("570", "577", "SD"),
    ("580", "588", "ND"), ("590", "599", "MT"), ("600", "629", "IL"), ("630", "658", "MO"),
    ("660", "679", "KS"), ("680", "693", "NE"), ("700", "714", "LA"), ("716", "729", "AR"),
    ("730", "732", "OK"), ("733", "733", "TX"), ("734", "749", "OK"),
    ("750", "799", "TX"), ("800", "816", "CO"), ("820", "831", "WY"), ("832", "838", "ID"),
    ("840", "847", "UT"), ("850", "865", "AZ"), ("870", "884", "NM"), ("885", "885", "TX"),
    ("889", "898", "NV"), ("900", "961", "CA"), ("962", "966", "AP"), ("967", "968", "HI"),
    ("969", "969", "GU"), ("970", "979", "OR"), ("980", "994", "WA"), ("995", "999", "AK"),
)

# Military/territorial "states" the range table resolves to that aren't
# freight-relevant for the balance table — bucketed as "??" (Unrecognized)
# per Section 9.1. Applied uniformly (per-lane display columns too, not
# just the balance table) since no real freight lane realistically uses
# these ZIP3s and treating them consistently avoids a second code path.
_NON_FREIGHT_CODES = {"AE", "AA", "AP", "GU"}

QUANTIZE_CENTS = Decimal("0.01")


# ============================================================================
# Section 3 — Parsing
# ============================================================================

def _normalize_zip(raw):
    """
    Section 3.3.4. Returns (zip5, error) — error is None on success.
    Accepts a plain 5-digit ZIP or ZIP+4 (truncates to 5). Repairs
    Excel's leading-zero stripping: a purely-numeric 3-4 digit token is
    left-padded to 5 (e.g. "6010" -> "06010").
    """
    s = (raw or "").strip()
    if not s:
        return None, "blank"
    if _ZIP5_OR_ZIP9_RE.match(s):
        return s[:5], None
    if s.isdigit() and 3 <= len(s) <= 4:
        return s.zfill(5), None
    return None, f"invalid ZIP {raw!r}"


def _normalize_equipment(raw):
    """Section 3.3.5. Returns (code, error) where code is 'V'/'R'/'F'."""
    key = (raw or "").strip().lower()
    code = EQUIPMENT_ALIASES.get(key)
    if code is None:
        return None, f"unknown equipment {raw!r}"
    return code, None


def _parse_annual_loads(raw):
    """Section 3.3.6. Integer >= 1. Tolerates thousands separators."""
    s = (raw or "").strip().replace(",", "")
    if not s:
        return None, "annual loads is required"
    try:
        # int(Decimal(...)) rather than int(s) so "100" and "100.0"
        # (a stray Excel decimal format) both work; truncates any
        # fractional part rather than erroring on it.
        val = int(Decimal(s))
    except (InvalidOperation, ValueError):
        return None, f"{raw!r} is not a valid whole number"
    if val < 1:
        return None, "must be at least 1"
    return val, None


def _parse_decimal_cell(raw):
    """
    Section 3.3.6. Strips $ and , then parses to Decimal. A blank cell
    returns (None, None) — the caller decides whether blank is allowed
    for that particular column.
    """
    s = (raw or "").strip()
    if not s:
        return None, None
    cleaned = s.replace("$", "").replace(",", "")
    try:
        val = Decimal(cleaned)
    except InvalidOperation:
        return None, f"{raw!r} is not a valid number"
    return val, None


def _parse_incumbent_cell(raw):
    """Section 3.2 — optional; when present must be > 0."""
    val, err = _parse_decimal_cell(raw)
    if err:
        return None, err
    if val is not None and val <= 0:
        return None, "incumbent rate must be greater than 0"
    return val, None


def _parse_miles_cell(raw, mode):
    """
    Section 3.2 / 4 / 10. Returns (miles, error).
    - The literal sentinel "NA" (case-insensitive) always means "no
      distance available" and is never an error in any mode — see
      NO_DISTANCE_SENTINEL docstring above.
    - Manual mode: blank is a row error. Google mode: blank is allowed
      (resolved later by resolve_distances()).
    - Must be > 0 when present.
    """
    s = (raw or "").strip()
    if s.upper() == NO_DISTANCE_SENTINEL:
        return None, None
    val, err = _parse_decimal_cell(raw)
    if err:
        return None, err
    if val is not None and val <= 0:
        return None, "miles must be greater than 0"
    if val is None and mode == "manual":
        return None, "miles is required in manual mode"
    return val, None


def parse_lanes(raw_text, mode):
    """
    Section 3.3. Parses a pasted lane CSV (or tab-separated Excel paste)
    into a list of lane dicts.

    mode: "manual" or "google" — controls whether a blank miles cell is
    a row error (manual) or left as None for resolve_distances() to
    fill in later (google).

    Returns (lanes, errors, warnings):
      lanes    — list of dicts with keys: row_num, origin_zip, dest_zip,
                 equipment, annual_loads, incumbent_rate (Decimal|None),
                 miles (Decimal|None).
      errors   — list of "Row N: ..." strings (or a single cap-limit
                 string). Non-empty means the view must reject the
                 submission and price nothing.
      warnings — non-blocking informational strings (long-miles sanity
                 check, exact-duplicate rows).
    """
    errors = []
    warnings = []

    # --- Normalize BOM / line endings, apply Excel tab->comma tolerance.
    # No legal field in this 6-column schema contains a tab, so a blanket
    # replace is safe (Section 3.3.2).
    text = raw_text.lstrip("\ufeff")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\t", ",")

    reader = csv.reader(io.StringIO(text))
    raw_rows = [row for row in reader if any(cell.strip() for cell in row)]

    # --- Header-row auto-detect (Section 3.3.3): only the FIRST row is
    # eligible, and only a silent skip — a genuine data row with a bad
    # ZIP still gets a normal, visible row error.
    if raw_rows:
        first_origin = raw_rows[0][0] if raw_rows[0] else ""
        _, zerr = _normalize_zip(first_origin)
        if zerr is not None:
            raw_rows = raw_rows[1:]
            header_skipped = True
        else:
            header_skipped = False
    else:
        header_skipped = False

    # --- 25-lane cap (Section 3.3.8 / 2.3): enforced on the raw data-row
    # count, BEFORE any per-row parsing or API work, so a >25-lane paste
    # never gets partial validation. "single clear error, no partial
    # processing."
    if len(raw_rows) > MAX_LANES:
        return [], [
            f"This submission has {len(raw_rows)} lanes, which is over the "
            f"{MAX_LANES}-lane limit per submission. Please split it into "
            "multiple submissions."
        ], []

    lanes = []
    seen_signatures = {}  # exact-duplicate soft-warning tracking (3.3.9)

    for idx, row in enumerate(raw_rows):
        # 1-based row number as the user sees it in their paste. If a
        # header row was skipped, row 1 was the header, so the first
        # data row is row 2 — this keeps "Row N" pointing at the exact
        # line the user pasted, header included.
        row_num = idx + (2 if header_skipped else 1)

        cells = [c.strip() for c in row[:6]] + [""] * max(0, 6 - len(row))
        origin_raw, dest_raw, equip_raw, loads_raw, incumbent_raw, miles_raw = cells[:6]

        row_errors = []

        origin_zip, oerr = _normalize_zip(origin_raw)
        if oerr:
            row_errors.append(f"Row {row_num}: invalid origin ZIP {origin_raw!r}")

        dest_zip, derr = _normalize_zip(dest_raw)
        if derr:
            row_errors.append(f"Row {row_num}: invalid destination ZIP {dest_raw!r}")

        equipment, eerr = _normalize_equipment(equip_raw)
        if eerr:
            row_errors.append(f"Row {row_num}: unknown equipment {equip_raw!r}")

        annual_loads, lerr = _parse_annual_loads(loads_raw)
        if lerr:
            row_errors.append(f"Row {row_num}: invalid annual loads {loads_raw!r} ({lerr})")

        incumbent_rate, ierr = _parse_incumbent_cell(incumbent_raw)
        if ierr:
            row_errors.append(f"Row {row_num}: invalid incumbent rate {incumbent_raw!r} ({ierr})")

        miles, merr = _parse_miles_cell(miles_raw, mode)
        if merr:
            row_errors.append(f"Row {row_num}: invalid miles {miles_raw!r} ({merr})")
        elif miles is not None and miles > 3200:
            # Section 3.3.10 — non-blocking sanity warning.
            warnings.append(
                f"Row {row_num}: {miles} miles is longer than any road pairing "
                "in the lower 48 — double-check this isn't a typo."
            )

        if row_errors:
            errors.extend(row_errors)
            continue  # don't add a partially-invalid lane to the price-able set

        lanes.append({
            "row_num": row_num,
            "origin_zip": origin_zip,
            "dest_zip": dest_zip,
            "equipment": equipment,
            "annual_loads": annual_loads,
            "incumbent_rate": incumbent_rate,
            "miles": miles,
        })

        # Soft duplicate-row warning — nice-to-have, never blocks pricing.
        sig = (origin_zip, dest_zip, equipment, annual_loads, incumbent_rate, miles)
        if sig in seen_signatures:
            warnings.append(
                f"Rows {seen_signatures[sig]} and {row_num} are identical — "
                "both kept as separate lanes in case both are legitimate award lines."
            )
        else:
            seen_signatures[sig] = row_num

    return lanes, errors, warnings


# ============================================================================
# Section 4 — Distance resolution (Google mode only)
# ============================================================================

def resolve_distances(lanes, daily_budget):
    """
    Section 4.2. Fills in miles for lanes with a blank miles cell via the
    site-wide shared helper utils.get_road_distance(), guarded by pair
    dedupe + the freightbid daily element sub-budget.

    IMPORTANT — call-site contract: the outer view is responsible for
    the outer 30/h/IP wall AND the Google-mode 6/h/IP check (Section 7.3)
    BEFORE calling this function; those are rate limits, not a budget,
    and the spec's ordering note requires the rate-limit check to run
    before any budget/API work. This function only handles the DAILY
    ELEMENT BUDGET check plus the actual resolution pipeline.

    Returns (lanes, warnings, rejected_reason):
      lanes           — new list with miles filled in where resolvable
                         (unresolved pairs get miles=None, matching the
                         DISTANCE_UNAVAILABLE contract price_lane()
                         already knows how to handle).
      warnings        — per-pair failure notices for the results banner.
      rejected_reason — None on success, or a user-facing string when
                        the daily budget is spent (view should treat
                        this as a form error and price NOTHING for this
                        submission — Section 4.2.3, "do not partially
                        resolve").
    """
    from datetime import date
    from django.core.cache import caches
    from .utils import get_road_distance  # site-wide shared helper — DO NOT fork

    warnings = []

    # Step 1 — dedupe unique (origin, dest) pairs among lanes missing
    # miles. Directional: (A, B) and (B, A) are two distinct pairs.
    missing_pairs = []
    seen_pairs = set()
    for lane in lanes:
        if lane["miles"] is None:
            pair = (lane["origin_zip"], lane["dest_zip"])
            if pair not in seen_pairs:
                seen_pairs.add(pair)
                missing_pairs.append(pair)

    if not missing_pairs:
        return lanes, warnings, None  # every lane already has miles

    # Step 2 — cache probe using the EXACT key get_road_distance() builds
    # (mirrored verbatim from projects/utils.py: f"road_dist_{o}_{d}" on
    # the DEFAULT cache) so this tool shares the 30-day cache with every
    # other freight tool. DO NOT change this format independently of
    # utils.get_road_distance() — read that function's source before
    # touching this block.
    default_cache = caches["default"]
    _UNROUTABLE_SENTINEL = "__unroutable__"  # matches utils.py's negative-cache value
    cache_misses = []
    resolved_pair_miles = {}
    for pair in missing_pairs:
        cache_key = f"road_dist_{pair[0]}_{pair[1]}"
        cached = default_cache.get(cache_key)
        if cached is None:
            cache_misses.append(pair)
        elif cached == _UNROUTABLE_SENTINEL:
            resolved_pair_miles[pair] = None  # recently proven unroutable
        else:
            resolved_pair_miles[pair] = Decimal(str(cached))

    # Step 3 — budget check. needed = count of cache-miss pairs only;
    # cache hits (positive or negative) cost zero elements.
    needed = len(cache_misses)
    if needed > 0:
        budget_cache = caches["freightbid"]
        budget_key = f"dm_budget:{date.today():%Y%m%d}"
        budget_cache.add(budget_key, 0, 60 * 60 * 26)  # 26h TTL; no-op if present
        used = budget_cache.get(budget_key, 0)
        if used + needed > daily_budget:
            return lanes, warnings, (
                f"The daily Google mileage budget for this tool is spent "
                f"(needs {needed} more lookups). Add a miles column and use "
                "manual mode — it has no limit."
            )

        # Step 5 — resolve each cache-miss pair, sequentially. Worst case
        # is MAX_LANES calls in a few seconds, well under 333/minute.
        actual_calls = 0
        for pair in cache_misses:
            actual_calls += 1  # count every ATTEMPT, even failures (Step 6)
            miles_val = get_road_distance(pair[0], pair[1])
            if miles_val is None:
                resolved_pair_miles[pair] = None
                warnings.append(
                    f"Could not resolve a driving route for {pair[0]} \u2192 {pair[1]}. "
                    "That lane is priced as unavailable — enter miles manually to include it."
                )
            else:
                resolved_pair_miles[pair] = Decimal(str(miles_val))

        # Step 6 — increment budget by ACTUAL API calls made, not pairs
        # probed, and even for failures (a failed call may still bill an
        # element — counting conservatively is the safe direction).
        budget_cache.incr(budget_key, actual_calls)

    # Step 7 — fan-out: apply each resolved pair's miles to every lane
    # sharing that pair.
    new_lanes = []
    for lane in lanes:
        if lane["miles"] is not None:
            new_lanes.append(lane)
            continue
        pair = (lane["origin_zip"], lane["dest_zip"])
        new_lanes.append({**lane, "miles": resolved_pair_miles.get(pair)})

    return new_lanes, warnings, None


# ============================================================================
# Section 9.1 — ZIP3 -> state
# ============================================================================

def zip3_to_state(zip5):
    """
    Derives a US state/territory from a ZIP's first 3 digits via the
    static range table above. Returns "??" for prefixes outside every
    range, or for military/territorial codes that aren't freight-relevant
    (Section 9.1) — those still price normally; they just bucket as
    "Unrecognized" wherever a state is displayed.
    """
    prefix = (zip5 or "")[:3]
    for lo, hi, state in ZIP3_STATE_RANGES:
        if lo <= prefix <= hi:
            return "??" if state in _NON_FREIGHT_CODES else state
    return "??"


# ============================================================================
# Section 5 + 6 — Pricing and flags
# ============================================================================

def price_lane(lane, target_margin_pct, fsc_per_mile, contingency_pct,
               min_linehaul_charge, rpm_by_equipment):
    """
    Prices a single lane per Section 5, then flags it per Section 6.
    All arithmetic in Decimal, full unrounded precision — quantization
    to cents happens ONLY at display/export time (build_csv_rows / the
    template's floatformat-equivalent). This matters: summing UNROUNDED
    per-lane annual figures and quantizing once at the portfolio total
    reproduces the spec's worked roll-up numbers to the penny; rounding
    each lane first and then summing does not.

    percentages arrive as whole numbers (15 means 15%); the two percent
    globals are converted to fractions once, here, at the top.

    `lane["miles"]` may be None (an unresolved Google-mode pair) — that
    lane is priced as DISTANCE_UNAVAILABLE with every rate column blank,
    per Section 4.2 step 7 / Section 6.
    """
    origin_state = zip3_to_state(lane["origin_zip"])
    dest_state = zip3_to_state(lane["dest_zip"])

    if lane["miles"] is None:
        return {
            **lane,
            "origin_state": origin_state,
            "dest_state": dest_state,
            "carrier_linehaul": None, "fsc_per_load": None, "cost_floor": None,
            "sell_linehaul": None, "all_in_rate": None, "rpm_all_in": None,
            "gp_per_load": None, "annual_gp": None, "annual_rev": None,
            "vs_incumbent": None,
            "flags": ["DISTANCE_UNAVAILABLE"],
            "floor_applied": False, "do_not_bid": False, "margin_squeeze": False,
            "max_margin_pct": None,
        }

    miles = lane["miles"]
    equipment = lane["equipment"]
    annual_loads = lane["annual_loads"]
    incumbent_rate = lane["incumbent_rate"]

    rpm_basis = rpm_by_equipment[equipment]
    margin = target_margin_pct / Decimal(100)
    contingency = contingency_pct / Decimal(100)

    carrier_linehaul = miles * rpm_basis * (1 + contingency)
    fsc_per_load = miles * fsc_per_mile
    cost_floor = carrier_linehaul + fsc_per_load

    sell_linehaul_raw = carrier_linehaul / (1 - margin)
    floor_applied = sell_linehaul_raw < min_linehaul_charge
    sell_linehaul = max(sell_linehaul_raw, min_linehaul_charge)

    all_in_rate = sell_linehaul + fsc_per_load
    rpm_all_in = all_in_rate / miles
    gp_per_load = sell_linehaul - carrier_linehaul
    annual_gp = gp_per_load * annual_loads
    annual_rev = all_in_rate * annual_loads

    vs_incumbent = (incumbent_rate - all_in_rate) if incumbent_rate is not None else None

    # --- Flags, evaluated in spec order; a lane can carry more than one.
    flags = []
    if miles < 250:
        flags.append("SHORT_HAUL")
    if floor_applied:
        flags.append("FLOOR_APPLIED")

    # Boundary (Section 6): incumbent_rate == cost_floor is MARGIN_SQUEEZE
    # at max 0.00%, NOT DO_NOT_BID. Using strict "<" for do_not_bid routes
    # the equality case to the margin-squeeze branch below automatically.
    do_not_bid = incumbent_rate is not None and incumbent_rate < cost_floor

    margin_squeeze = False
    max_margin_pct = None
    if incumbent_rate is not None and not do_not_bid:
        margin_squeeze = cost_floor <= incumbent_rate < all_in_rate
        if margin_squeeze:
            denom = incumbent_rate - fsc_per_load
            if denom <= 0:
                max_margin_pct = None  # displays as "n/a"
            else:
                max_margin_pct = (incumbent_rate - fsc_per_load - carrier_linehaul) / denom * 100

    if do_not_bid:
        flags.append("DO_NOT_BID")
    if margin_squeeze:
        flags.append("MARGIN_SQUEEZE")

    return {
        **lane,
        "origin_state": origin_state,
        "dest_state": dest_state,
        "carrier_linehaul": carrier_linehaul,
        "fsc_per_load": fsc_per_load,
        "cost_floor": cost_floor,
        "sell_linehaul": sell_linehaul,
        "all_in_rate": all_in_rate,
        "rpm_all_in": rpm_all_in,
        "gp_per_load": gp_per_load,
        "annual_gp": annual_gp,
        "annual_rev": annual_rev,
        "vs_incumbent": vs_incumbent,
        "flags": flags,
        "floor_applied": floor_applied,
        "do_not_bid": do_not_bid,
        "margin_squeeze": margin_squeeze,
        "max_margin_pct": max_margin_pct,
    }


# ============================================================================
# Section 8 — Portfolio roll-up
# ============================================================================

def build_rollups(priced_lanes):
    """
    Two roll-ups, both summed from UNROUNDED Decimal per-lane figures and
    quantized only at the final total (see price_lane docstring for why
    this order matters):

      all_lanes           — every priced lane except DISTANCE_UNAVAILABLE
      excluding_do_not_bid — same, minus DO_NOT_BID lanes too — "the
                             number a broker actually submits on."
    """
    priceable = [l for l in priced_lanes if "DISTANCE_UNAVAILABLE" not in l["flags"]]

    def _rollup(subset):
        total_rev = sum((l["annual_rev"] for l in subset), Decimal(0))
        total_gp = sum((l["annual_gp"] for l in subset), Decimal(0))
        total_miles = sum((l["miles"] * l["annual_loads"] for l in subset), Decimal(0))
        total_loads = sum((l["annual_loads"] for l in subset), 0)
        blended_margin_pct = (total_gp / total_rev * 100) if total_rev else Decimal(0)
        return {
            "lane_count": len(subset),
            "total_annual_loads": total_loads,
            "total_annual_revenue": total_rev,
            "total_annual_gp": total_gp,
            "blended_margin_pct": blended_margin_pct,
            "total_annual_miles": total_miles,
        }

    return {
        "all_lanes": _rollup(priceable),
        "excluding_do_not_bid": _rollup([l for l in priceable if not l["do_not_bid"]]),
    }


# ============================================================================
# Section 9.2 — Headhaul / backhaul balance by state
# ============================================================================

def build_state_balance(priced_lanes):
    """
    One row per state appearing as an origin or destination across ALL
    priced lanes (including DISTANCE_UNAVAILABLE ones — the balance table
    only needs ZIPs, not miles, so there's no reason to drop them here
    even though the dollar roll-up does). Sorted by |net_loads| descending.
    """
    stats = {}

    def _bucket(state):
        return stats.setdefault(
            state, {"out_lanes": 0, "in_lanes": 0, "out_loads": 0, "in_loads": 0}
        )

    for lane in priced_lanes:
        o = _bucket(lane["origin_state"])
        o["out_lanes"] += 1
        o["out_loads"] += lane["annual_loads"]

        d = _bucket(lane["dest_state"])
        d["in_lanes"] += 1
        d["in_loads"] += lane["annual_loads"]

    rows = []
    for state, s in stats.items():
        net = s["out_loads"] - s["in_loads"]
        rows.append({
            "state": state,
            "out_lanes": s["out_lanes"],
            "in_lanes": s["in_lanes"],
            "out_loads": s["out_loads"],
            "in_loads": s["in_loads"],
            "net_loads": net,
        })
    rows.sort(key=lambda r: abs(r["net_loads"]), reverse=True)
    return rows


# ============================================================================
# Section 10 — CSV export
# ============================================================================

CSV_HEADER = [
    "origin_zip", "dest_zip", "origin_state", "dest_state", "equipment",
    "miles", "annual_loads", "carrier_linehaul", "fsc_per_load", "cost_floor",
    "sell_linehaul", "all_in_rate", "rpm", "gp_per_load", "annual_gp",
    "annual_revenue", "incumbent_rate", "vs_incumbent", "flags",
]


def _q(value):
    """Quantize a Decimal to cents (ROUND_HALF_UP) for export only."""
    if value is None:
        return ""
    return str(value.quantize(QUANTIZE_CENTS, rounding=ROUND_HALF_UP))


def build_csv_rows(priced_lanes):
    """
    Section 10 — one row per lane, header exactly as specified. Money as
    plain numbers (no $ or thousands separators — the shipper template
    does its own arithmetic on these cells). Blank incumbents export as
    empty cells. Flags joined with ';'. DISTANCE_UNAVAILABLE lanes export
    with blank pricing columns and the flag set. No summary rows.

    Returns a list of lists suitable for csv.writer.writerows() — the
    caller (the view) is responsible for the HttpResponse plumbing.
    """
    rows = [CSV_HEADER]
    for lane in priced_lanes:
        rows.append([
            lane["origin_zip"], lane["dest_zip"],
            lane["origin_state"], lane["dest_state"],
            lane["equipment"],
            str(lane["miles"]) if lane["miles"] is not None else "",
            lane["annual_loads"],
            _q(lane["carrier_linehaul"]), _q(lane["fsc_per_load"]), _q(lane["cost_floor"]),
            _q(lane["sell_linehaul"]), _q(lane["all_in_rate"]),
            _q(lane["rpm_all_in"]), _q(lane["gp_per_load"]), _q(lane["annual_gp"]),
            _q(lane["annual_rev"]),
            _q(lane["incumbent_rate"]) if lane["incumbent_rate"] is not None else "",
            _q(lane["vs_incumbent"]) if lane["vs_incumbent"] is not None else "",
            ";".join(lane["flags"]),
        ])
    return rows


def build_export_lanes_csv_text(priced_lanes):
    """
    Rebuilds the original 6-column lane CSV, with resolved miles written
    into column 6, for embedding as the hidden re-post textarea value
    described in Section 10. DISTANCE_UNAVAILABLE lanes are written with
    the NO_DISTANCE_SENTINEL ("NA") in the miles column rather than being
    dropped, so the downloaded CSV can still include them (blank pricing
    + flag, per Section 10) instead of silently disappearing on export.
    """
    lines = ["origin_zip,dest_zip,equipment,annual_loads,incumbent_rate,miles"]
    for lane in priced_lanes:
        incumbent = str(lane["incumbent_rate"]) if lane["incumbent_rate"] is not None else ""
        miles_cell = NO_DISTANCE_SENTINEL if lane["miles"] is None else str(lane["miles"])
        lines.append(
            f'{lane["origin_zip"]},{lane["dest_zip"]},{lane["equipment"]},'
            f'{lane["annual_loads"]},{incumbent},{miles_cell}'
        )
    return "\n".join(lines)
