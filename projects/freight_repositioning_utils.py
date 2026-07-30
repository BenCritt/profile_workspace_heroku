"""
projects/utils/freight_repositioning_utils.py

Roundtrip / Repositioning Rate Calculator -- pure calculation module.

Models a spot-market broker's carrier-economics decision as a full trip:
carrier's current position -> deadhead-in -> loaded delivery -> deadhead-
to-reload -> next loaded leg (or empty repositioning). A spot load is not
origin-to-destination in isolation -- the carrier prices the whole
movement, and this module makes that whole movement visible.

Glossary (use these exact terms in templates/schema so nothing drifts):
    Loaded RPM          rate / loaded miles -- the number everyone quotes.
    Effective RPM        rate / (deadhead-in + loaded miles) -- what the
                          movement actually pays per mile driven for THIS
                          load.
    Roundtrip RPM         (this load's buy + reload revenue) / all miles in
                          the full trip.
    This-load floor       minimum buy for a carrier pricing this load alone.
    Roundtrip floor       minimum buy for a carrier pricing the full trip.
    Negotiation zone      the interval between the two floors.
    Reposition adjustment roundtrip floor - this-load floor (signed):
                          positive = dead-market premium, negative =
                          reload-market discount.

No Django imports anywhere in this module. Every public function returns a
plain dict (or None where a section doesn't apply) so the view/template can
consume results without coupling to internals here. The seven functions
below are the required orchestration surface; a handful of small private-
ish helpers (money, loaded_rpm, effective_rpm, roundtrip_revenue,
roundtrip_rpm, roundtrip_net) sit alongside them purely to keep each
formula written once (DRY) and independently testable.
"""

from decimal import Decimal, ROUND_HALF_UP

TWO_PLACES = Decimal("0.01")


def money(value: Decimal) -> Decimal:
    """
    Round a Decimal to cents at an output boundary. Never call this
    mid-calculation -- every function below keeps full, unrounded Decimal
    precision internally. Only _quantize_result() calls this, and only
    once, on the finished dict build_result() is about to return.
    """
    return value.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def resolve_loaded_miles(origin_zip, destination_zip, manual_miles):
    """
    Resolve the loaded-leg mileage for this submission.

    Manual entry always wins and skips the API entirely -- site-wide quota
    discipline is at most one Distance Matrix element per submission, and
    only for the loaded leg. Deadhead legs are never looked up (a carrier's
    current position arrives as "he's 40 out" over the phone -- approximate
    by nature, and wiring multiple legs to the API would quadruple quota
    burn for false precision).

    Returns:
        Decimal miles, or None if neither manual miles nor a resolvable
        ZIP pair was supplied. The caller (build_result) treats None as
        the "no results panel, use manual miles" error state.
    """
    if manual_miles is not None:
        return manual_miles

    if not origin_zip or not destination_zip:
        return None

    # Deferred import: keeps this module runnable standalone (see the
    # __main__ self-test at the bottom) without requiring the Django
    # package context a top-of-file relative import would need, and
    # without touching the API at all on the manual-miles path above.
    # NOTE: import path inferred per BUILD PROMPT §1 ("utils.get_road_distance")
    # -- adjust to wherever the shared helper actually lives in your
    # projects/utils/ package if it differs.
    from .utils import get_road_distance

    try:
        miles = get_road_distance(origin_zip, destination_zip)
    except Exception:
        # API failure: no retry, no exception bubbling into the view.
        # Report the miss so the caller renders the "use manual miles"
        # message instead of crashing the request.
        return None

    if miles is None:
        return None

    return Decimal(str(miles))


def loaded_rpm(buy_total: Decimal, loaded_miles: Decimal) -> Decimal:
    """Rate per loaded mile -- the number everyone quotes. Caller guards loaded_miles > 0."""
    return buy_total / loaded_miles


def effective_rpm(buy_total: Decimal, miles_worked: Decimal) -> Decimal:
    """Rate per mile actually driven (loaded + deadhead-in) for this load. Caller guards miles_worked > 0."""
    return buy_total / miles_worked


def roundtrip_revenue(buy_total: Decimal, reload_revenue: Decimal) -> Decimal:
    """This load's buy plus whatever the reload is expected to pay."""
    return buy_total + reload_revenue


def roundtrip_rpm(revenue_total: Decimal, roundtrip_miles: Decimal) -> Decimal:
    """Blended rate across every mile in the full trip. Caller guards roundtrip_miles > 0."""
    return revenue_total / roundtrip_miles


def roundtrip_net(revenue_total: Decimal, roundtrip_cost: Decimal) -> Decimal:
    return revenue_total - roundtrip_cost


def compute_this_load(loaded_miles: Decimal, dh_origin: Decimal, cost: Decimal, profit: Decimal) -> dict:
    """
    This-load economics: what a carrier pricing this single move -- with no
    knowledge of or interest in what happens after delivery -- needs to say
    yes.

    THE CLASSIC BUG FOR THIS TOOL: cost and required profit apply to every
    mile the truck drives for this move, loaded AND deadhead-in -- never
    just loaded_miles. `breakeven_this` and `floor_this` below multiply by
    `miles_worked`, not `loaded_miles`. Do not "simplify" that.
    """
    miles_worked = dh_origin + loaded_miles  # loaded_miles > 0 is guaranteed by build_result's guard, so miles_worked > 0 here too.

    carrier_cost_this = cost * miles_worked
    breakeven_this = carrier_cost_this  # same number, named separately per the glossary: breakeven IS cost; floor is cost+profit.
    floor_this = (cost + profit) * miles_worked
    deadhead_dilution_pct = (dh_origin / miles_worked) * Decimal("100")

    return {
        "loaded_miles": loaded_miles,
        "dh_origin": dh_origin,
        "miles_worked": miles_worked,
        "cost_per_mile": cost,          # raw input, carried through for the template's assumptions-recap line (§6 item 5)
        "profit_per_mile": profit,      # same
        "carrier_cost_this": carrier_cost_this,
        "breakeven_this": breakeven_this,
        "floor_this": floor_this,
        "deadhead_dilution_pct": deadhead_dilution_pct,
    }


def compute_roundtrip(loaded_miles, dh_origin, dh_reload, reload_loaded_miles, reload_rpm, cost, profit):
    """
    Roundtrip economics -- the full trip a carrier is actually deciding on:
    deadhead-in, loaded delivery, deadhead-to-reload, and the next loaded
    leg (or pure empty repositioning if there is no next load lined up yet).

    Returns None when there is nothing post-delivery to model at all, so
    the caller can suppress the entire roundtrip section rather than
    rendering it as a wall of zeros.
    """
    has_roundtrip = (dh_reload + reload_loaded_miles) > 0
    if not has_roundtrip:
        return None

    # reload_rpm can be None when only dh_reload is set (pure repositioning,
    # no next load lined up) -- that's zero revenue, not an error. Forms-level
    # cross-validation already guarantees reload_loaded_miles > 0 requires a
    # real reload_rpm, so a None here only happens when reload_loaded_miles
    # is itself 0 -- reload_revenue is correctly 0 either way.
    effective_reload_rpm = reload_rpm if reload_rpm is not None else Decimal("0")

    reload_revenue_amt = effective_reload_rpm * reload_loaded_miles
    roundtrip_miles = dh_origin + loaded_miles + dh_reload + reload_loaded_miles
    roundtrip_cost = cost * roundtrip_miles
    breakeven_roundtrip = roundtrip_cost - reload_revenue_amt
    floor_roundtrip = roundtrip_cost + (profit * roundtrip_miles) - reload_revenue_amt

    return {
        "has_roundtrip": True,
        "dh_reload": dh_reload,
        "reload_loaded_miles": reload_loaded_miles,
        "reload_rpm": effective_reload_rpm,
        "reload_revenue": reload_revenue_amt,
        "roundtrip_miles": roundtrip_miles,
        "roundtrip_cost": roundtrip_cost,
        "breakeven_roundtrip": breakeven_roundtrip,
        "floor_roundtrip": floor_roundtrip,
    }


def compute_floors_and_zone(this_load: dict, roundtrip) -> dict:
    """
    The negotiation zone: the interval between the this-load floor and the
    roundtrip floor, plus the signed reposition adjustment that says which
    direction the reload pushes the number and by how much.

    NOTE: in addition to zone_low/zone_high/reposition_adjustment (the
    fields named in BUILD PROMPT §5.8), this also carries floor_this and
    floor_roundtrip forward explicitly. Zone bounds alone can't tell a
    caller which raw floor is "this load's" vs "the roundtrip's" once
    min()/max() has been applied -- broker_overlay and the template both
    need to label GP/margin rows by floor identity, not just by zone
    position, so the unambiguous values travel together here.
    """
    floor_this = this_load["floor_this"]

    if roundtrip is None:
        # No roundtrip modeled: the zone collapses to a single floor. The
        # template keys off has_roundtrip to say "floor" instead of "zone"
        # -- this dict doesn't fake a zero-width zone, it just reports the
        # one floor twice so zone_low/zone_high stay well-defined for any
        # code that reads them unconditionally.
        return {
            "has_roundtrip": False,
            "floor_this": floor_this,
            "floor_roundtrip": None,
            "zone_low": floor_this,
            "zone_high": floor_this,
            "reposition_adjustment": None,
        }

    floor_roundtrip = roundtrip["floor_roundtrip"]
    reposition_adjustment = floor_roundtrip - floor_this

    return {
        "has_roundtrip": True,
        "floor_this": floor_this,
        "floor_roundtrip": floor_roundtrip,
        "zone_low": min(floor_this, floor_roundtrip),
        "zone_high": max(floor_this, floor_roundtrip),
        "reposition_adjustment": reposition_adjustment,
        # Stock Django templates have no `abs` filter -- precompute the
        # magnitude here so the "reload-market discount" interpretation
        # string (negative adjustment) can display "$X" without a template
        # filter hack (e.g. `|cut:"-"`) that would be fragile if the
        # formatting ever changes.
        "reposition_adjustment_abs": abs(reposition_adjustment),
    }


def evaluate_ask(ask_total, this_load: dict, roundtrip, floors: dict):
    """
    Where a carrier's actual ask sits relative to the negotiation zone, plus
    the at-ask figures (loaded/effective RPM, carrier net, and roundtrip
    figures when modeled). Returns None when no ask was submitted.
    """
    if ask_total is None:
        return None

    miles = this_load["loaded_miles"]
    miles_worked = this_load["miles_worked"]

    result = {
        "ask_total": ask_total,
        "loaded_rpm": loaded_rpm(ask_total, miles),
        "effective_rpm": effective_rpm(ask_total, miles_worked),
        "carrier_net_this": ask_total - this_load["carrier_cost_this"],
    }

    if roundtrip is not None:
        rt_revenue = roundtrip_revenue(ask_total, roundtrip["reload_revenue"])
        result["roundtrip_revenue"] = rt_revenue
        result["roundtrip_rpm"] = roundtrip_rpm(rt_revenue, roundtrip["roundtrip_miles"])
        result["roundtrip_net"] = roundtrip_net(rt_revenue, roundtrip["roundtrip_cost"])

    # Position verdict -- §5.6 state machine. Evaluated cost -> zone_low ->
    # zone_high in that exact order; the bands are adjacent, not overlapping,
    # so this ordering alone disambiguates every case.
    breakeven_this = this_load["breakeven_this"]
    zone_low = floors["zone_low"]
    zone_high = floors["zone_high"]

    if ask_total < breakeven_this:
        verdict = "below_cost"          # No rational carrier profits at this number on this move alone.
    elif ask_total < zone_low:
        verdict = "below_zone"          # Covers cost but not the profit requirement.
    elif ask_total <= zone_high:
        verdict = "in_zone"             # Falls inside the negotiation zone.
    else:
        verdict = "above_zone"          # Exceeds both floors -- squeeze room exists.

    result["verdict"] = verdict
    result["zone_low"] = zone_low
    result["zone_high"] = zone_high

    if verdict == "above_zone":
        result["zone_delta"] = ask_total - zone_high
    elif verdict == "below_zone":
        result["zone_delta"] = zone_low - ask_total
    else:
        result["zone_delta"] = Decimal("0")

    if verdict == "in_zone" and roundtrip is not None:
        # "State which floor it's nearer" (§5.6) -- only meaningful with two
        # distinct floors; with no roundtrip, zone_low == zone_high == floor_this
        # and there's nothing to disambiguate.
        dist_to_this = abs(ask_total - floors["floor_this"])
        dist_to_roundtrip = abs(ask_total - floors["floor_roundtrip"])
        result["nearer_floor"] = "this_load" if dist_to_this <= dist_to_roundtrip else "roundtrip"

    return result


def broker_overlay(sell_total, target_margin_pct, ask_total, floors: dict):
    """
    Broker margin overlay -- only computed when a sell rate is entered.
    Margin is on revenue (sell_total), never markup on cost: same rule,
    same classic bug, as the Quote Builder. Negative margins are reported
    as-is, never clamped to zero -- a broker needs to see a losing load
    clearly, not have it hidden.
    """
    if sell_total is None or sell_total <= 0:
        # Form-level validation (min_value=0.01) should make sell_total<=0
        # unreachable in practice; guarded here anyway per §11's explicit
        # "sell_total > 0" division-guard requirement, and so a malformed
        # cleaned_data dict (e.g. in a unit test) can't trigger a ZeroDivisionError.
        return None

    def margin_pct(buy_total: Decimal) -> Decimal:
        return (sell_total - buy_total) / sell_total * Decimal("100")

    def gross_profit(buy_total: Decimal) -> Decimal:
        return sell_total - buy_total

    floor_this = floors["floor_this"]
    floor_roundtrip = floors.get("floor_roundtrip")

    max_buy_at_target = sell_total * (Decimal("1") - target_margin_pct / Decimal("100"))

    result = {
        "sell_total": sell_total,
        "target_margin_pct": target_margin_pct,
        "max_buy_at_target": max_buy_at_target,
        "gp_at_floor_this": gross_profit(floor_this),
        "margin_at_floor_this": margin_pct(floor_this),
    }

    if ask_total is not None:
        result["gp_at_ask"] = gross_profit(ask_total)
        result["margin_at_ask"] = margin_pct(ask_total)

    if floor_roundtrip is not None:
        result["gp_at_floor_roundtrip"] = gross_profit(floor_roundtrip)
        result["margin_at_floor_roundtrip"] = margin_pct(floor_roundtrip)

    # Reachability: does the target-margin max buy clear the floor that
    # reflects the carrier's REAL decision? That's the roundtrip floor
    # whenever one is modeled (this is what BUILD PROMPT §5.7's own worked
    # phrasing -- "clears the roundtrip floor by $7.50" -- checks against;
    # §11's compressed edge-case table says "zone_low" instead, but zone_low
    # is only equal to the roundtrip floor in the reload-discount case, and
    # the §14 worked example is the dead-market-premium case where zone_low
    # is floor_this, not floor_roundtrip. Followed the worked example over
    # the table gloss -- see BUILD NOTES).
    reachability_floor = floor_roundtrip if floor_roundtrip is not None else floor_this
    reachability_gap = max_buy_at_target - reachability_floor  # positive = clears the floor by this much; negative = short by this much
    result["reachability_floor_used"] = "roundtrip" if floor_roundtrip is not None else "this_load"
    result["reachability_gap"] = reachability_gap
    result["reachability_gap_abs"] = abs(reachability_gap)  # for the "short by $X" template string -- see compute_floors_and_zone's note on stock Django templates having no `abs` filter.
    result["target_reachable"] = reachability_gap >= 0

    return result


def _quantize_result(obj):
    """
    Recursively quantize every Decimal leaf in a result structure to cents
    (ROUND_HALF_UP) -- the single output boundary per the money-handling
    rule: round only what the template renders, never mid-calculation.
    Runs exactly once, on the dict build_result is about to return.
    """
    if isinstance(obj, Decimal):
        return money(obj)
    if isinstance(obj, dict):
        return {k: _quantize_result(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_quantize_result(v) for v in obj]
    return obj


def build_result(cleaned_data: dict) -> dict:
    """
    Orchestrator the view calls with the form's cleaned_data. Resolves
    miles, runs every calculation section, and returns one dict ready for
    template rendering with every Decimal already quantized to the display
    boundary.
    """
    origin_zip = cleaned_data.get("origin_zip")
    destination_zip = cleaned_data.get("destination_zip")
    manual_miles = cleaned_data.get("loaded_manual_miles")

    loaded_miles = resolve_loaded_miles(origin_zip, destination_zip, manual_miles)

    if loaded_miles is None:
        # API failure, or no manual miles and no resolvable ZIP pair.
        return {"error": True, "has_results": False}

    same_zip = bool(origin_zip) and bool(destination_zip) and origin_zip == destination_zip

    if loaded_miles <= 0:
        # Same-ZIP local drayage is allowed by the form (no ValidationError
        # for matching ZIPs), but a literal zero-mile result can't safely
        # feed loaded_rpm's division regardless of why it happened -- every
        # division in this module is guarded on loaded_miles > 0 (§11), so
        # zero is always the "can't compute, use manual miles" error state,
        # same-ZIP or not.
        return {"error": True, "has_results": False}

    # Local-drayage warning: allowed, but flagged when the resolved distance
    # rounds to next to nothing. Only reachable when loaded_miles > 0 above,
    # so this never overlaps with the error state.
    same_zip_low_miles = same_zip and loaded_miles < 1

    # --- Fields with a spec'd numeric default: coalesce None -> default.
    # Deliberately `is None` checks, not `value or default` -- several of
    # these defaults are non-zero (cost, profit) and an explicit 0 is a
    # legitimate value for e.g. required_carrier_profit_per_mile that must
    # not get silently overwritten by a falsy-value shortcut.
    dh_origin = cleaned_data.get("dh_origin")
    dh_origin = dh_origin if dh_origin is not None else Decimal("0")

    cost = cleaned_data.get("carrier_cost_per_mile")
    cost = cost if cost is not None else Decimal("1.95")

    profit = cleaned_data.get("required_carrier_profit_per_mile")
    profit = profit if profit is not None else Decimal("0.30")

    this_load = compute_this_load(loaded_miles, dh_origin, cost, profit)

    dh_reload = cleaned_data.get("dh_reload")
    dh_reload = dh_reload if dh_reload is not None else Decimal("0")

    reload_loaded_miles = cleaned_data.get("reload_loaded_miles")
    reload_loaded_miles = reload_loaded_miles if reload_loaded_miles is not None else Decimal("0")

    reload_rpm_value = cleaned_data.get("reload_rpm")

    roundtrip = compute_roundtrip(
        loaded_miles, dh_origin, dh_reload, reload_loaded_miles, reload_rpm_value, cost, profit
    )

    floors = compute_floors_and_zone(this_load, roundtrip)

    # Resolve the ask total from basis + amount (flat vs. per-loaded-mile).
    ask_total = None
    carrier_ask_amount = cleaned_data.get("carrier_ask_amount")
    if carrier_ask_amount is not None:
        if cleaned_data.get("carrier_ask_basis") == "per_loaded_mile":
            ask_total = carrier_ask_amount * loaded_miles
        else:
            ask_total = carrier_ask_amount

    ask_eval = evaluate_ask(ask_total, this_load, roundtrip, floors)

    # Resolve the sell total the same way.
    sell_total = None
    sell_amount = cleaned_data.get("sell_amount")
    if sell_amount is not None:
        if cleaned_data.get("sell_basis") == "per_loaded_mile":
            sell_total = sell_amount * loaded_miles
        else:
            sell_total = sell_amount

    target_margin_pct = cleaned_data.get("target_margin_pct")
    target_margin_pct = target_margin_pct if target_margin_pct is not None else Decimal("15.0")

    overlay = broker_overlay(sell_total, target_margin_pct, ask_total, floors)

    result = {
        "has_results": True,
        "error": False,
        "used_manual_miles": manual_miles is not None,
        "same_zip_low_miles": same_zip_low_miles,
        "this_load": this_load,
        "roundtrip": roundtrip,
        "has_roundtrip": roundtrip is not None,
        "floors": floors,
        "ask": ask_eval,
        "has_ask": ask_eval is not None,
        "overlay": overlay,
        "has_overlay": overlay is not None,
        "destination_market_strength": cleaned_data.get("destination_market_strength"),
    }

    return _quantize_result(result)


if __name__ == "__main__":
    # ==========================================================================
    # MANDATORY SELF-TEST -- BUILD PROMPT §14.3
    # Imports nothing beyond this module's own dependencies (Decimal only).
    # Never executes on a normal Django import; only when this file is run
    # directly (`python freight_repositioning_utils.py`).
    # ==========================================================================

    base_case_input = {
        "origin_zip": None,
        "destination_zip": None,
        "loaded_manual_miles": Decimal("500"),
        "dh_origin": Decimal("60"),
        "dh_reload": Decimal("40"),
        "reload_loaded_miles": Decimal("300"),
        "reload_rpm": Decimal("2.10"),
        "carrier_cost_per_mile": Decimal("1.95"),
        "required_carrier_profit_per_mile": Decimal("0.30"),
        "carrier_ask_basis": "flat",
        "carrier_ask_amount": Decimal("1400.00"),
        "sell_basis": "flat",
        "sell_amount": Decimal("1650.00"),
        "target_margin_pct": Decimal("15.0"),
        "destination_market_strength": "custom",
    }

    r = build_result(base_case_input)

    assert r["this_load"]["miles_worked"] == Decimal("560"), r["this_load"]["miles_worked"]
    assert r["ask"]["loaded_rpm"] == Decimal("2.80"), r["ask"]["loaded_rpm"]
    assert r["ask"]["effective_rpm"] == Decimal("2.50"), r["ask"]["effective_rpm"]
    assert r["this_load"]["deadhead_dilution_pct"] == Decimal("10.71"), r["this_load"]["deadhead_dilution_pct"]
    assert r["this_load"]["carrier_cost_this"] == Decimal("1092.00"), r["this_load"]["carrier_cost_this"]
    assert r["ask"]["carrier_net_this"] == Decimal("308.00"), r["ask"]["carrier_net_this"]
    assert r["this_load"]["breakeven_this"] == Decimal("1092.00"), r["this_load"]["breakeven_this"]
    assert r["this_load"]["floor_this"] == Decimal("1260.00"), r["this_load"]["floor_this"]
    assert r["roundtrip"]["reload_revenue"] == Decimal("630.00"), r["roundtrip"]["reload_revenue"]
    assert r["roundtrip"]["roundtrip_miles"] == Decimal("900"), r["roundtrip"]["roundtrip_miles"]
    assert r["roundtrip"]["roundtrip_cost"] == Decimal("1755.00"), r["roundtrip"]["roundtrip_cost"]
    assert r["ask"]["roundtrip_revenue"] == Decimal("2030.00"), r["ask"]["roundtrip_revenue"]
    assert r["ask"]["roundtrip_rpm"] == Decimal("2.26"), r["ask"]["roundtrip_rpm"]
    assert r["ask"]["roundtrip_net"] == Decimal("275.00"), r["ask"]["roundtrip_net"]
    assert r["roundtrip"]["breakeven_roundtrip"] == Decimal("1125.00"), r["roundtrip"]["breakeven_roundtrip"]
    assert r["roundtrip"]["floor_roundtrip"] == Decimal("1395.00"), r["roundtrip"]["floor_roundtrip"]
    assert r["floors"]["reposition_adjustment"] == Decimal("135.00"), r["floors"]["reposition_adjustment"]
    assert r["floors"]["zone_low"] == Decimal("1260.00"), r["floors"]["zone_low"]
    assert r["floors"]["zone_high"] == Decimal("1395.00"), r["floors"]["zone_high"]
    assert r["ask"]["verdict"] == "above_zone", r["ask"]["verdict"]
    assert r["ask"]["zone_delta"] == Decimal("5.00"), r["ask"]["zone_delta"]
    assert r["overlay"]["gp_at_ask"] == Decimal("250.00"), r["overlay"]["gp_at_ask"]
    assert r["overlay"]["margin_at_ask"] == Decimal("15.15"), r["overlay"]["margin_at_ask"]
    assert r["overlay"]["margin_at_floor_this"] == Decimal("23.64"), r["overlay"]["margin_at_floor_this"]
    assert r["overlay"]["margin_at_floor_roundtrip"] == Decimal("15.45"), r["overlay"]["margin_at_floor_roundtrip"]
    assert r["overlay"]["max_buy_at_target"] == Decimal("1402.50"), r["overlay"]["max_buy_at_target"]
    assert r["overlay"]["reachability_gap"] == Decimal("7.50"), r["overlay"]["reachability_gap"]
    assert r["overlay"]["target_reachable"] is True

    # §5.5 identity check -- catches transposed formulas.
    identity_rhs = money(
        (Decimal("1.95") + Decimal("0.30")) * (Decimal("40") + Decimal("300")) - Decimal("630.00")
    )
    assert r["floors"]["reposition_adjustment"] == identity_rhs == Decimal("135.00"), (
        r["floors"]["reposition_adjustment"], identity_rhs
    )

    # --- Variant: same inputs except reload_rpm = 2.75 (verifies the sign flip) ---
    variant_input = dict(base_case_input)
    variant_input["reload_rpm"] = Decimal("2.75")
    v = build_result(variant_input)

    assert v["roundtrip"]["reload_revenue"] == Decimal("825.00"), v["roundtrip"]["reload_revenue"]
    assert v["roundtrip"]["breakeven_roundtrip"] == Decimal("930.00"), v["roundtrip"]["breakeven_roundtrip"]
    assert v["roundtrip"]["floor_roundtrip"] == Decimal("1200.00"), v["roundtrip"]["floor_roundtrip"]
    assert v["floors"]["reposition_adjustment"] == Decimal("-60.00"), v["floors"]["reposition_adjustment"]
    assert v["floors"]["zone_low"] == Decimal("1200.00"), v["floors"]["zone_low"]
    assert v["floors"]["zone_high"] == Decimal("1260.00"), v["floors"]["zone_high"]

    print("ALL SELF-TESTS PASSED")
