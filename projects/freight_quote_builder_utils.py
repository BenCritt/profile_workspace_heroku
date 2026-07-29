"""
freight_quote_builder_utils.py

Pure calculation engine for the Freight Quote Builder & Max Buy Rate
Calculator. No Django imports. No network calls. Every function takes
plain values (Decimal, str, bool, list[dict]) and returns plain values,
so this whole module is unit-testable without a request/response cycle.

Money rule: every currency value is a Decimal. Quantize to cents with
ROUND_HALF_UP only at output boundaries (money()), never mid-calculation,
per the site's money-handling convention.
"""

from decimal import Decimal, ROUND_HALF_UP, InvalidOperation

TWO_PLACES = Decimal("0.01")

LADDER_TIERS = [Decimal("10"), Decimal("12"), Decimal("15"), Decimal("18"), Decimal("20")]

# Fixed accessorial presets. Order here drives both form field generation
# and the table row order everywhere else, so it is the single source of
# truth (imported by forms_freight_tools.py and the template context).
ACCESSORIAL_PRESETS = [
    ("liftgate", "Liftgate"),
    ("residential_pickup", "Residential Pickup"),
    ("residential_delivery", "Residential Delivery"),
    ("inside_delivery", "Inside Delivery"),
    ("driver_assist_lumper", "Driver Assist / Lumper"),
    ("tarps", "Tarps"),
    ("extra_stop", "Extra Stop"),
    ("tonu", "TONU"),
    ("reconsignment", "Reconsignment"),
    ("layover", "Layover"),
    ("hazmat", "Hazmat"),
    ("team_service", "Team Service"),
    ("heavy_tri_axle", "Heavy / Tri-Axle"),
    ("pallet_exchange", "Pallet Exchange"),
]


def money(value: Decimal) -> Decimal:
    """Round a Decimal to cents at an output boundary. Never call mid-calculation."""
    return value.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


class QuoteBuilderError(Exception):
    """
    Raised for configurations that are mathematically unsolvable (not user
    typos - those are caught by form validation). The view catches this
    and renders it as context["error_message"], same as an API failure.
    """
    pass


# ---------------------------------------------------------------------------
# 5.1 Miles — resolution itself happens in the view (it needs get_road_distance,
# a network call, which has no place in a pure-function module). This module
# only guards that whatever miles value it is handed is usable.
# ---------------------------------------------------------------------------

def ensure_positive_miles(miles) -> Decimal:
    """
    Coerce miles to Decimal and guard > 0. Raises QuoteBuilderError on
    anything else so the view can render the no-results error state
    instead of hitting a ZeroDivisionError deeper in the pipeline.

    NOTE: get_road_distance() (and manual_miles before Django coerces it)
    can hand this a float. Decimal(str(x)) avoids binary-float noise like
    Decimal(2.1) -> Decimal('2.0999999999999996...'); never Decimal(x) directly
    on a float.
    """
    if miles is None:
        raise QuoteBuilderError("miles_unresolved")
    try:
        miles_dec = miles if isinstance(miles, Decimal) else Decimal(str(miles))
    except (InvalidOperation, ValueError):
        raise QuoteBuilderError("miles_unresolved")
    if miles_dec <= 0:
        raise QuoteBuilderError("miles_unresolved")
    return miles_dec


# ---------------------------------------------------------------------------
# 5.2 Linehaul
# ---------------------------------------------------------------------------

def calculate_linehaul(basis: str, amount: Decimal, miles: Decimal) -> Decimal:
    """
    basis="flat"      -> amount is the total linehaul dollars, independent of miles.
    basis="per_mile"  -> amount is a rate per mile; multiply by resolved miles.

    This function is direction-agnostic: callers use it for the sell-side
    rate (Mode A/C) or the buy-side rate (Mode B) - "linehaul" here just
    means "the rate the user typed in," not which side of the deal it's on.
    """
    if basis == "per_mile":
        return amount * miles
    return amount


# ---------------------------------------------------------------------------
# 5.3 Fuel surcharge
# ---------------------------------------------------------------------------

def calculate_fsc_sell(
    fsc_method: str,
    linehaul_sell: Decimal,
    miles: Decimal,
    doe_price: Decimal | None,
    peg_price: Decimal | None,
    mpg: Decimal | None,
    fsc_percent: Decimal | None,
    fsc_flat: Decimal | None,
) -> Decimal:
    """
    Sell-side FSC. Requires linehaul_sell as an input because the "percent"
    method bills FSC as a percentage of the sell-side linehaul - this makes
    fsc_sell UNDEFINED until linehaul_sell is known, which matters for Mode B
    (see solve_mode_b_reverse below, which handles that ordering problem).

    Guard: mpg must be > 0 for the peg method. Form-level validation should
    already reject mpg<=0, but this module never trusts an upstream layer
    on a division - ZeroDivisionError here would be a bug, not a user error.
    """
    if fsc_method == "peg":
        if mpg is None or mpg <= 0:
            raise QuoteBuilderError("mpg_not_positive")
        # Floor at 0: when DOE drops below the peg, surcharge is zero, never negative.
        fsc_per_mile = max(Decimal("0"), (doe_price - peg_price) / mpg)
        return fsc_per_mile * miles
    if fsc_method == "percent":
        return linehaul_sell * (fsc_percent / Decimal("100"))
    if fsc_method == "flat":
        return fsc_flat
    return Decimal("0")  # "none"


def calculate_fsc_buy(
    fsc_sell: Decimal,
    fsc_carrier_pass_through: bool,
    fsc_buy_override: Decimal | None,
) -> Decimal:
    """Buy-side FSC: pass-through mirrors the sell-side figure, else the broker's own override (blank -> 0)."""
    if fsc_carrier_pass_through:
        return fsc_sell
    return fsc_buy_override if fsc_buy_override is not None else Decimal("0")


# ---------------------------------------------------------------------------
# 5.4 Accessorials & detention
# ---------------------------------------------------------------------------

def sum_accessorials(accessorial_rows: list[dict]) -> tuple[Decimal, Decimal]:
    """
    accessorial_rows: [{"key": str, "label": str, "customer_charge": Decimal, "carrier_cost": Decimal}, ...]
    All-blank rows are valid (edge case: treat as zero, not an error) - this
    just sums whatever is there, including an empty list.
    """
    accessorial_sell = sum((r["customer_charge"] for r in accessorial_rows), Decimal("0"))
    accessorial_buy = sum((r["carrier_cost"] for r in accessorial_rows), Decimal("0"))
    return accessorial_sell, accessorial_buy


def calculate_detention(
    expected_detention_hours: Decimal,
    detention_rate_customer: Decimal | None,
    detention_rate_carrier: Decimal | None,
) -> tuple[Decimal, Decimal]:
    """Blank rate with nonzero hours still prices to 0 on that side - a broker who doesn't bill detention to one party is a valid, common scenario, not an error."""
    hours = expected_detention_hours or Decimal("0")
    rate_customer = detention_rate_customer or Decimal("0")
    rate_carrier = detention_rate_carrier or Decimal("0")
    return hours * rate_customer, hours * rate_carrier


# ---------------------------------------------------------------------------
# 5.6 Margin (the classic bug section) & ladder
# ---------------------------------------------------------------------------

def calculate_margin_pct(sell_total: Decimal, buy_total: Decimal) -> Decimal | None:
    """
    Margin is ALWAYS on revenue (sell_total), never markup on cost. Returns
    None when sell_total <= 0 so the caller can render "-" instead of
    dividing by zero (edge case table: sell_total==0 -> no margin %, never divide).
    """
    if sell_total <= 0:
        return None
    return (sell_total - buy_total) / sell_total * Decimal("100")


def build_margin_ladder(
    sell_total: Decimal,
    fsc_buy: Decimal,
    accessorial_buy: Decimal,
    detention_buy: Decimal,
    target_margin_pct: Decimal,
    miles: Decimal,
) -> list[dict]:
    """
    Standard tiers (10/12/15/18/20) plus the user's own target inserted in
    sorted position if it isn't already one of them. fsc_buy/accessorial_buy/
    detention_buy are held CONSTANT across every tier (only the linehaul
    portion flexes with margin) - those three lines are largely pass-through
    costs the broker doesn't negotiate tier-by-tier; linehaul is the lever.
    """
    tiers = list(LADDER_TIERS)
    is_custom_target = target_margin_pct not in tiers
    if is_custom_target:
        tiers.append(target_margin_pct)
    tiers = sorted(set(tiers))

    fixed_buy_costs = fsc_buy + accessorial_buy + detention_buy
    rows = []
    for tier_pct in tiers:
        max_buy_total = sell_total * (Decimal("1") - tier_pct / Decimal("100"))
        max_linehaul_buy = max_buy_total - fixed_buy_costs
        is_reachable = max_linehaul_buy > 0
        rows.append({
            "margin_pct": tier_pct,
            "max_buy_total": money(max_buy_total),
            "max_linehaul_buy": money(max_linehaul_buy) if is_reachable else None,
            "max_buy_rpm": money(max_buy_total / miles) if miles > 0 else None,
            "gross_profit_at_tier": money(sell_total - max_buy_total),
            "is_reachable": is_reachable,
            "is_user_target": tier_pct == target_margin_pct,
        })
    return rows


def calculate_walkaway(sell_total: Decimal, contingency_pct: Decimal) -> Decimal:
    """The hard floor: above this buy total, the load loses money once the risk reserve is honored."""
    contingency_reserve = sell_total * (contingency_pct / Decimal("100"))
    return sell_total - contingency_reserve


def calculate_per_mile_metrics(
    linehaul_sell: Decimal, sell_total: Decimal, buy_total: Decimal, gross_profit: Decimal, miles: Decimal
) -> dict:
    """All four guarded on miles > 0 (caller ensures this via ensure_positive_miles before reaching here)."""
    if miles <= 0:
        return {"rpm_linehaul_sell": None, "rpm_all_in_sell": None, "rpm_buy": None, "margin_per_mile": None}
    return {
        "rpm_linehaul_sell": money(linehaul_sell / miles),
        "rpm_all_in_sell": money(sell_total / miles),
        "rpm_buy": money(buy_total / miles),
        "margin_per_mile": money(gross_profit / miles),
    }


# ---------------------------------------------------------------------------
# 5.10 Mode B (buy known -> build sell)
#
# The one-line spec ("sell_total_required = buy_total/(1-M); back out
# linehaul by subtracting sell-side FSC/accessorials/detention") is correct
# UNLESS fsc_method=="percent", because percent-FSC makes fsc_sell a
# function of linehaul_sell - the very thing we're solving for. Two cases:
#
#   fsc_carrier_pass_through=False: fsc_buy is a direct user override, so
#   buy_total is fully known up front. Only fsc_sell depends on the unknown
#   linehaul_sell, giving one simple equation:
#       L + L*F = (known sell_total_required) - accessorial_sell - detention_sell
#
#   fsc_carrier_pass_through=True: fsc_buy MIRRORS fsc_sell, so buy_total
#   itself depends on the unknown linehaul_sell too (via fsc_sell -> fsc_buy).
#   Solving the resulting single linear equation in L gives the closed form
#   below. Guarded: if the denominator collapses to <= 0 (only possible at
#   extreme fsc_percent + target_margin_pct combinations), the configuration
#   has no finite solution and this raises rather than returning nonsense.
# ---------------------------------------------------------------------------

def solve_mode_b_reverse(
    linehaul_buy: Decimal,
    fsc_method: str,
    fsc_percent: Decimal | None,
    fsc_carrier_pass_through: bool,
    fsc_buy_override: Decimal | None,
    doe_price: Decimal | None,
    peg_price: Decimal | None,
    mpg: Decimal | None,
    fsc_flat: Decimal | None,
    accessorial_sell: Decimal,
    accessorial_buy: Decimal,
    detention_sell: Decimal,
    detention_buy: Decimal,
    target_margin_pct: Decimal,
    miles: Decimal,
) -> dict:
    """Returns {"linehaul_sell", "fsc_sell", "fsc_buy", "sell_total", "buy_total"} - all Decimal, unrounded (caller rounds at the end)."""
    M = target_margin_pct / Decimal("100")
    if M >= 1:
        raise QuoteBuilderError("target_margin_pct_invalid")  # form validation should already reject >=100

    if fsc_method == "percent":
        F = fsc_percent / Decimal("100")

        if not fsc_carrier_pass_through:
            # fsc_buy is a direct override -> buy_total fully known already.
            fsc_buy = fsc_buy_override if fsc_buy_override is not None else Decimal("0")
            buy_total = linehaul_buy + fsc_buy + accessorial_buy + detention_buy
            sell_total = buy_total / (Decimal("1") - M)
            # L*(1+F) = sell_total - accessorial_sell - detention_sell
            denom = Decimal("1") + F
            linehaul_sell = (sell_total - accessorial_sell - detention_sell) / denom
            fsc_sell = linehaul_sell * F

        else:
            # fsc_buy mirrors fsc_sell, which mirrors the still-unknown linehaul_sell.
            # Closed form (derived from combining all five equations above):
            #   L = [LB - K*(1-M)] / [(1-M) - F*M]
            #   where LB = linehaul_buy + accessorial_buy + detention_buy
            #         K  = accessorial_sell + detention_sell
            LB = linehaul_buy + accessorial_buy + detention_buy
            K = accessorial_sell + detention_sell
            denom = (Decimal("1") - M) - F * M
            if denom <= 0:
                # e.g. fsc_percent=100 and target_margin_pct>=50 simultaneously.
                raise QuoteBuilderError("mode_b_percent_unsolvable")
            linehaul_sell = (LB - K * (Decimal("1") - M)) / denom
            fsc_sell = linehaul_sell * F
            fsc_buy = fsc_sell
            buy_total = linehaul_buy + fsc_buy + accessorial_buy + detention_buy
            sell_total = buy_total / (Decimal("1") - M)

    else:
        # peg / flat / none: fsc_sell does not depend on linehaul_sell at all,
        # so it can be computed directly and the spec's literal instruction applies.
        fsc_sell = calculate_fsc_sell(fsc_method, Decimal("0"), miles, doe_price, peg_price, mpg, fsc_percent, fsc_flat)
        fsc_buy = calculate_fsc_buy(fsc_sell, fsc_carrier_pass_through, fsc_buy_override)
        buy_total = linehaul_buy + fsc_buy + accessorial_buy + detention_buy
        sell_total = buy_total / (Decimal("1") - M)
        linehaul_sell = sell_total - fsc_sell - accessorial_sell - detention_sell

    return {
        "linehaul_sell": linehaul_sell,
        "fsc_sell": fsc_sell,
        "fsc_buy": fsc_buy,
        "sell_total": sell_total,
        "buy_total": buy_total,
    }


# ---------------------------------------------------------------------------
# Orchestrator - the one function the view calls.
# ---------------------------------------------------------------------------

def build_quote(cleaned_data: dict, miles: Decimal) -> dict:
    """
    cleaned_data: FreightQuoteBuilderForm.cleaned_data (already validated).
    miles: resolved by the view (manual entry or get_road_distance), already
    checked positive via ensure_positive_miles.

    Returns a dict of Decimal/bool/list values ready for template display.
    All money values in the returned dict are rounded to cents (money()) -
    this is the output boundary; nothing upstream of this return should
    have rounded early.
    """
    mode = cleaned_data["pricing_mode"]
    target_margin_pct = cleaned_data["target_margin_pct"]

    accessorial_sell, accessorial_buy = sum_accessorials(cleaned_data["accessorial_rows"])
    detention_sell, detention_buy = calculate_detention(
        cleaned_data.get("expected_detention_hours") or Decimal("0"),
        cleaned_data.get("detention_rate_customer"),
        cleaned_data.get("detention_rate_carrier"),
    )

    fsc_kwargs = dict(
        fsc_method=cleaned_data["fsc_method"],
        doe_price=cleaned_data.get("doe_price"),
        peg_price=cleaned_data.get("peg_price"),
        mpg=cleaned_data.get("mpg"),
        fsc_percent=cleaned_data.get("fsc_percent"),
        fsc_flat=cleaned_data.get("fsc_flat"),
    )

    if mode == "buy_known":
        # linehaul_amount is the rate paid TO the carrier in this mode.
        linehaul_buy = calculate_linehaul(cleaned_data["linehaul_basis"], cleaned_data["linehaul_amount"], miles)
        solved = solve_mode_b_reverse(
            linehaul_buy=linehaul_buy,
            fsc_method=fsc_kwargs["fsc_method"],
            fsc_percent=fsc_kwargs["fsc_percent"],
            fsc_carrier_pass_through=cleaned_data["fsc_carrier_pass_through"],
            fsc_buy_override=cleaned_data.get("fsc_buy_override"),
            doe_price=fsc_kwargs["doe_price"],
            peg_price=fsc_kwargs["peg_price"],
            mpg=fsc_kwargs["mpg"],
            fsc_flat=fsc_kwargs["fsc_flat"],
            accessorial_sell=accessorial_sell,
            accessorial_buy=accessorial_buy,
            detention_sell=detention_sell,
            detention_buy=detention_buy,
            target_margin_pct=target_margin_pct,
            miles=miles,
        )
        linehaul_sell = solved["linehaul_sell"]
        fsc_sell = solved["fsc_sell"]
        fsc_buy = solved["fsc_buy"]
        sell_total = solved["sell_total"]
        buy_total = solved["buy_total"]
        linehaul_buy_display = linehaul_buy

    else:
        # Mode A (sell_known) and Mode C (from_scratch) share this forward path.
        # NOTE: Mode C ("RPM basis" -> "solve for both sides") has no formula of
        # its own in the build prompt's calc spec (§5.1-5.10 define Mode A and
        # Mode B only). Treated here as Mode A with the linehaul always read as
        # a per-mile RPM, since that's the only reading consistent with "starts
        # from an RPM" while reusing the fully-specified §5.1-5.9 math. Flagged
        # in BUILD NOTES - confirm this matches your intent for Mode C.
        effective_basis = "per_mile" if mode == "from_scratch" else cleaned_data["linehaul_basis"]
        linehaul_sell = calculate_linehaul(effective_basis, cleaned_data["linehaul_amount"], miles)
        fsc_sell = calculate_fsc_sell(linehaul_sell=linehaul_sell, miles=miles, **fsc_kwargs)
        fsc_buy = calculate_fsc_buy(fsc_sell, cleaned_data["fsc_carrier_pass_through"], cleaned_data.get("fsc_buy_override"))
        sell_total = linehaul_sell + fsc_sell + accessorial_sell + detention_sell

        # No buy-side rate exists yet in this mode (that's what we're solving
        # for) - the "recommended" buy total is the target-margin point on the
        # ladder itself, kept consistent with the ladder's own math below.
        buy_total = sell_total * (Decimal("1") - target_margin_pct / Decimal("100"))
        linehaul_buy_display = buy_total - fsc_buy - accessorial_buy - detention_buy

    gross_profit = sell_total - buy_total
    margin_pct = calculate_margin_pct(sell_total, buy_total)
    ladder = build_margin_ladder(sell_total, fsc_buy, accessorial_buy, detention_buy, target_margin_pct, miles)
    walkaway_buy_total = calculate_walkaway(sell_total, cleaned_data.get("contingency_pct") or Decimal("0"))
    per_mile = calculate_per_mile_metrics(linehaul_sell, sell_total, buy_total, gross_profit, miles)

    accessorial_display_rows = [
        {"label": r["label"], "customer_charge": money(r["customer_charge"]), "carrier_cost": money(r["carrier_cost"])}
        for r in cleaned_data["accessorial_rows"]
        if r["customer_charge"] or r["carrier_cost"]
    ]

    return {
        "mode": mode,
        "miles": miles,
        "linehaul_sell": money(linehaul_sell),
        "linehaul_buy": money(linehaul_buy_display) if linehaul_buy_display > 0 else None,
        "fsc_sell": money(fsc_sell),
        "fsc_buy": money(fsc_buy),
        "accessorial_sell": money(accessorial_sell),
        "accessorial_buy": money(accessorial_buy),
        "accessorial_rows": accessorial_display_rows,
        "detention_sell": money(detention_sell),
        "detention_buy": money(detention_buy),
        "sell_total": money(sell_total),
        "buy_total": money(buy_total),
        "gross_profit": money(gross_profit),
        # margin_pct is never None here (sell_total > 0 is guaranteed upstream
        # by ensure_positive_miles + validated positive linehaul), but the
        # None branch is kept so template rendering can safely use `|default:"—"`.
        "margin_pct": margin_pct.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) if margin_pct is not None else None,
        "ladder": ladder,
        "walkaway_buy_total": money(walkaway_buy_total),
        **per_mile,
    }


def format_customer_quote_text(context: dict, origin_zip: str, destination_zip: str, equipment_label: str) -> str:
    """
    Builds the monospace, copy-to-clipboard customer quote block (§6.1).
    Deliberately excludes every broker-economics figure - this text is
    what gets pasted to the customer, so margin/gross-profit/ladder data
    must never appear here even if a future edit adds more context fields.
    """
    lines = [
        "FREIGHT QUOTE",
        f"{origin_zip} -> {destination_zip}  |  {equipment_label}  |  {context['miles']} mi",
        "",
        f"{'Linehaul':<28}${context['linehaul_sell']:>10,.2f}",
        f"{'Fuel Surcharge':<28}${context['fsc_sell']:>10,.2f}",
    ]
    for row in context["accessorial_rows"]:
        lines.append(f"{row['label']:<28}${row['customer_charge']:>10,.2f}")
    lines.append("-" * 38)
    lines.append(f"{'ALL-IN TOTAL':<28}${context['sell_total']:>10,.2f}")
    lines.append(f"{'Rate per mile':<28}${context['rpm_all_in_sell']:>10,.2f}")
    lines.append("")
    lines.append("Quote valid 24 hours from issue. Subject to equipment availability.")
    lines.append("Rate assumes standard loading/unloading; detention billed per terms.")
    return "\n".join(lines)