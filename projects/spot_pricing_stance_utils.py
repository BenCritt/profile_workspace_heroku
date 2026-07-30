"""
Market-Signal to Pricing Stance Calculator -- scoring engine.

Pure functions, no Django imports, no persistence, no network I/O. Every
number in this module comes from a value the broker typed in; nothing here
calls out to a rate index, a load board API, or any external data source.
All tuning knobs (anchors, weights, band thresholds, matrix cells, cushion
rules, interpretation copy) live in STANCE_CONFIG so the template's
"How this is computed" panel can render the live model instead of a
hand-copied description of it.
"""

from decimal import Decimal, ROUND_HALF_UP, getcontext

# 50 digits of precision is overkill for this domain but costs nothing and
# removes any chance of the renormalization ratio losing precision on an
# unlucky combination of provided signals.
getcontext().prec = 50

FIFTY = Decimal("50")
HUNDRED = Decimal("100")
ONE_TENTH = Decimal("0.1")
ONE_HUNDREDTH = Decimal("0.01")


def D(value):
    """Coerce ints/floats/strings to Decimal via str() so binary-float
    noise (e.g. 0.1 -> 0.1000000000000000055511151231257827021181583404541015625)
    never enters the model. Decimals passed in are returned unchanged."""
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


STANCE_CONFIG = {
    # Each numeric signal maps its raw input through a three-anchor
    # piecewise-linear scale to a 0-100 sub-score. `weight` is this
    # signal's share of Market Heat when every signal is provided; when a
    # signal is missing, its weight drops out and the rest renormalize
    # (see compute_heat). Weights must sum to exactly 1.00 -- enforced at
    # import time below so a bad tune fails at deploy, not mid-request.
    "signals": {
        "ltr": {
            "label": "Load-to-truck ratio",
            "anchors": (D(1), D(3), D(8)),      # ascending: more loads per truck = tighter
            "weight": D("0.34"),
        },
        "call_rate": {
            "label": "Calls per hour posted",
            # Descending anchors: MORE calls means carriers want the load,
            # which means capacity is NOT scarce -- this is the one
            # inverse signal. Wiring it as ascending inverts the verdict.
            "anchors": (D("2.0"), D("0.5"), D(0)),
            "weight": D("0.26"),
        },
        "days_posted": {
            "label": "Days comparable postings have sat",
            "anchors": (D(0), D("1.5"), D(4)),  # ascending: longer uncovered = tighter
            "weight": D("0.16"),
        },
        "dh_depth": {
            "label": "Nearest trucks' deadhead (mi)",
            "anchors": (D(25), D(75), D(200)),  # ascending: farther trucks = tighter
            "weight": D("0.16"),
        },
        "diesel": {
            "label": "Diesel trend",
            # Categorical, not anchor-scaled -- a direct lookup table.
            # Deliberately the lowest weight: directionally relevant to
            # carrier cost, but a weak and lagging signal for spot heat.
            "categorical": {
                "rising_fast": D(100),
                "rising": D(70),
                "flat": D(50),
                "falling": D(20),
            },
            "weight": D("0.08"),
        },
    },

    # Human-readable labels for the diesel categorical raw value, used in
    # the breakdown table's "raw input" column and in interpretation text.
    "diesel_labels": {
        "rising_fast": "rising fast",
        "rising": "rising",
        "flat": "flat",
        "falling": "falling",
    },

    # One-line interpretation strings, three per signal, keyed on the
    # signal's OWN sub-score band (< 35 softens / 35-65 neutral / > 65
    # tightens) -- not the overall heat band. Every string cites the raw
    # value/label the broker entered so the breakdown table reads as an
    # explanation, not a canned label.
    "interpretations": {
        "ltr": {
            "tightens": "Load-to-truck ratio {value} at origin — capacity is scarce; strong upward pressure on the buy rate.",
            "neutral": "Load-to-truck ratio {value} at origin — capacity is roughly balanced; a moderate, non-decisive read.",
            "softens": "Load-to-truck ratio {value} at origin — trucks are plentiful; downward pressure on the buy rate.",
        },
        "call_rate": {
            "tightens": "Call rate {value} calls/hr on your own posting — it's going quiet; low carrier interest signals scarce capacity.",
            "neutral": "Call rate {value} calls/hr on your own posting — a typical response level, not a strong signal either way.",
            "softens": "Call rate {value} calls/hr on your own posting — carriers are calling frequently; capacity is not scarce here.",
        },
        "days_posted": {
            "tightens": "Comparable postings have sat {value} days uncovered — the market isn't clearing at posted rates; upward pressure.",
            "neutral": "Comparable postings have sat {value} days — a middling clearing time, not a strong signal.",
            "softens": "Comparable postings have sat {value} days — the market is clearing quickly; downward pressure on the buy rate.",
        },
        "dh_depth": {
            "tightens": "Nearest trucks are {value} mi deadhead away — capacity is thin near this lane; upward pressure.",
            "neutral": "Nearest trucks are {value} mi deadhead away — a middling truck-search depth.",
            "softens": "Nearest trucks are {value} mi deadhead away — trucks are close by; downward pressure on the buy rate.",
        },
        "diesel": {
            "tightens": "Diesel trend is {value} — carrier cost pressure is rising, adding weak upward pressure to asks.",
            "neutral": "Diesel trend is {value} — a neutral input; carrier costs aren't moving meaningfully.",
            "softens": "Diesel trend is {value} — carrier costs are easing, a weak downward influence.",
        },
    },

    "urgency": {
        # Descending: more hours to pickup = LESS urgent.
        "anchors": (D(48), D(12), D(3)),
        "commitment_bonus": {"quoted_only": D(0), "booked": D(15)},
    },

    # Half-open band boundaries, compared against UNROUNDED scores.
    "heat_bands": {"soft_max": D(40), "tight_min": D(65)},
    "urgency_bands": {"low_max": D(35), "high_min": D(70)},

    "stance_labels": {
        "hold_firm": "Hold Firm",
        "price_to_cover": "Price to Cover",
        "cover_now": "Cover Now / Build Cushion",
    },
    "stance_descriptions": {
        "hold_firm": "You have leverage, time, or both. Post at or below your target buy and let the market come to you. Do not widen your cushion; protect the margin.",
        "price_to_cover": "Post at market expectations and work it normally. Standard cushion, standard effort — neither squeeze nor panic.",
        "cover_now": "Coverage risk is the enemy on this one. Secure a truck early even at a modest premium, and carry the wider cushion into your customer number.",
    },

    "cushion": {
        # Each tuple is (heat_upper_bound_exclusive, base_pct). The first
        # bound the heat value is strictly less than wins. heat >= 80 (no
        # bound matches) falls through to base_ceiling.
        "base_bands": [
            (D(40), D(0)),
            (D(55), D(1)),
            (D(65), D(2)),
            (D(80), D(3)),
        ],
        "base_ceiling": D(5),          # heat >= 80
        "bonus_high_urgency": D(1),    # +1 when urgency_band == "high"
        "cap": D(6),
    },
}


def _validate_config():
    """Import-time guards so a bad config tune fails loudly at deploy
    rather than silently at request time (per BUILD PROMPT §5.1/§13)."""
    total = sum(v["weight"] for v in STANCE_CONFIG["signals"].values())
    if total != D("1.00"):
        raise AssertionError(f"STANCE_CONFIG signal weights must sum to 1.00, got {total}")

    for key, cfg in STANCE_CONFIG["signals"].items():
        if "anchors" not in cfg:
            continue
        a0, a50, a100 = cfg["anchors"]
        ascending = a0 < a50 < a100
        descending = a0 > a50 > a100
        if not (ascending or descending):
            raise ValueError(
                f"STANCE_CONFIG anchors for signal '{key}' are not strictly "
                f"monotonic: {cfg['anchors']}"
            )

    a0, a50, a100 = STANCE_CONFIG["urgency"]["anchors"]
    if not (a0 < a50 < a100 or a0 > a50 > a100):
        raise ValueError(f"STANCE_CONFIG urgency anchors not strictly monotonic: {(a0, a50, a100)}")


_validate_config()


def scale_signal(value, anchors):
    """Piecewise-linear map through (a0->0), (a50->50), (a100->100).

    Anchors may ascend (a0 < a50 < a100) or descend (a0 > a50 > a100) --
    the same two segment formulas handle both directions; only the clamp
    direction differs. Values beyond the a0 end clamp to 0, beyond the
    a100 end clamp to 100, "beyond" meaning whichever side of the anchor
    triple is farther from 50 in that direction.
    """
    value = D(value)
    a0, a50, a100 = anchors
    ascending = a0 < a100

    if ascending:
        if value <= a0:
            return Decimal(0)
        if value >= a100:
            return HUNDRED
        on_first_leg = value <= a50
    else:
        if value >= a0:
            return Decimal(0)
        if value <= a100:
            return HUNDRED
        on_first_leg = value >= a50

    if on_first_leg:
        return FIFTY * (value - a0) / (a50 - a0)
    return FIFTY + FIFTY * (value - a50) / (a100 - a50)


def display_score(value):
    """Round a score for display at an output boundary. Never call
    mid-calculation -- internal sums always use unrounded Decimals."""
    return value.quantize(ONE_TENTH, rounding=ROUND_HALF_UP)


def display_weight(value):
    """Round a renormalized weight fraction (0-1 scale) for display at an
    output boundary. Never call mid-calculation -- same rule as
    display_score, just a finer 0.01 step since weights are fractions."""
    return value.quantize(ONE_HUNDREDTH, rounding=ROUND_HALF_UP)


def _interpretation_band(subscore):
    if subscore > D(65):
        return "tightens"
    if subscore < D(35):
        return "softens"
    return "neutral"


def interpretation_for(signal_key, subscore, display_value):
    """One-line interpretation string for a signal's OWN sub-score band,
    citing the raw value/label the broker entered."""
    band = _interpretation_band(subscore)
    template = STANCE_CONFIG["interpretations"][signal_key][band]
    return template.format(value=display_value)


def compute_subscores(cleaned):
    """Map every provided raw input to its 0-100 sub-score.

    A signal is "provided" per BUILD PROMPT §4 clean() rules: the
    calls/hours pair counts as ONE signal (call_rate) and only exists
    when BOTH are present (the form guarantees this pairing before this
    function ever runs). Returns a dict keyed by signal name with raw
    value, provided flag, sub-score, and a ready-to-render interpretation
    string (None for excluded signals -- the template renders the greyed
    "not provided" row itself).
    """
    sig_cfg = STANCE_CONFIG["signals"]
    out = {}

    ltr = cleaned.get("load_to_truck_ratio")
    if ltr is not None:
        sub = scale_signal(ltr, sig_cfg["ltr"]["anchors"])
        out["ltr"] = {
            "raw": ltr, "provided": True, "subscore": sub,
            "display_raw": str(ltr),
            "interpretation": interpretation_for("ltr", sub, str(ltr)),
        }
    else:
        out["ltr"] = {"raw": None, "provided": False, "subscore": None,
                       "display_raw": None, "interpretation": None}

    calls = cleaned.get("calls_received")
    hours = cleaned.get("hours_posted")
    if calls is not None and hours is not None:
        rate = D(calls) / hours
        sub = scale_signal(rate, sig_cfg["call_rate"]["anchors"])
        rate_display = str(display_score(rate))
        out["call_rate"] = {
            "raw": rate, "provided": True, "subscore": sub,
            "display_raw": rate_display,
            "interpretation": interpretation_for("call_rate", sub, rate_display),
        }
    else:
        out["call_rate"] = {"raw": None, "provided": False, "subscore": None,
                             "display_raw": None, "interpretation": None}

    days = cleaned.get("days_posted_comparable")
    if days is not None:
        sub = scale_signal(days, sig_cfg["days_posted"]["anchors"])
        out["days_posted"] = {
            "raw": days, "provided": True, "subscore": sub,
            "display_raw": str(days),
            "interpretation": interpretation_for("days_posted", sub, str(days)),
        }
    else:
        out["days_posted"] = {"raw": None, "provided": False, "subscore": None,
                               "display_raw": None, "interpretation": None}

    dh = cleaned.get("nearest_trucks_dh")
    if dh is not None:
        sub = scale_signal(dh, sig_cfg["dh_depth"]["anchors"])
        out["dh_depth"] = {
            "raw": dh, "provided": True, "subscore": sub,
            "display_raw": str(dh),
            "interpretation": interpretation_for("dh_depth", sub, str(dh)),
        }
    else:
        out["dh_depth"] = {"raw": None, "provided": False, "subscore": None,
                            "display_raw": None, "interpretation": None}

    diesel = cleaned.get("diesel_trend")
    if diesel:
        sub = sig_cfg["diesel"]["categorical"][diesel]
        label = STANCE_CONFIG["diesel_labels"][diesel]
        out["diesel"] = {
            "raw": diesel, "provided": True, "subscore": sub,
            "display_raw": label,
            "interpretation": interpretation_for("diesel", sub, label),
        }
    else:
        # Blank means "not provided", never treated as "flat" -- per
        # BUILD PROMPT §11 edge case table.
        out["diesel"] = {"raw": None, "provided": False, "subscore": None,
                          "display_raw": None, "interpretation": None}

    return out


def compute_heat(subscores):
    """Market Heat = renormalized weighted average of provided sub-scores.

    Single Decimal ratio over the whole sum -- never round per-signal
    weights or contributions before summing (§5.3/§13). A signal not
    provided drops its weight from BOTH the numerator and denominator, so
    the remaining weights implicitly renormalize to fill the gap.
    """
    sig_cfg = STANCE_CONFIG["signals"]
    numerator = Decimal(0)
    denominator = Decimal(0)

    for key, data in subscores.items():
        if data["provided"]:
            weight = sig_cfg[key]["weight"]
            numerator += weight * data["subscore"]
            denominator += weight

    heat = numerator / denominator if denominator > 0 else Decimal(0)

    weights_used = {}
    contributions = {}
    for key, data in subscores.items():
        weight = sig_cfg[key]["weight"]
        if data["provided"] and denominator > 0:
            weights_used[key] = weight / denominator
            contributions[key] = data["subscore"] * weight / denominator
        else:
            weights_used[key] = None
            contributions[key] = None

    return {
        "heat": heat,
        "denominator": denominator,
        "weights_used": weights_used,
        "contributions": contributions,
    }


def compute_urgency(hours_to_pickup, commitment_level):
    """Urgency = time-to-pickup base score + a flat commitment bonus,
    clamped to 100. hours_to_pickup = 0 is valid (the window is now) and
    yields base = 100 with no special-case branch needed."""
    base = scale_signal(hours_to_pickup, STANCE_CONFIG["urgency"]["anchors"])
    bonus = STANCE_CONFIG["urgency"]["commitment_bonus"][commitment_level]
    urgency = min(HUNDRED, base + bonus)
    return {"base": base, "bonus": bonus, "urgency": urgency}


def _heat_band(heat):
    bands = STANCE_CONFIG["heat_bands"]
    if heat < bands["soft_max"]:
        return "soft"
    if heat < bands["tight_min"]:
        return "balanced"
    return "tight"


def _urgency_band(urgency):
    bands = STANCE_CONFIG["urgency_bands"]
    if urgency < bands["low_max"]:
        return "low"
    if urgency < bands["high_min"]:
        return "med"
    return "high"


# Rows = heat band, columns = urgency band. Stance comes ONLY from this
# lookup -- heat and urgency are never blended into a single "pressure"
# number before this point (§3/§13).
STANCE_MATRIX = {
    ("soft", "low"): "hold_firm",     ("soft", "med"): "hold_firm",     ("soft", "high"): "price_to_cover",
    ("balanced", "low"): "hold_firm", ("balanced", "med"): "price_to_cover", ("balanced", "high"): "cover_now",
    ("tight", "low"): "price_to_cover", ("tight", "med"): "cover_now",  ("tight", "high"): "cover_now",
}


def resolve_stance(heat, urgency):
    """Band both axes on their UNROUNDED values, then look up the matrix
    cell. Returns the bands, the stance key, its display label, and its
    description so the template needs no further branching."""
    heat_band = _heat_band(heat)
    urgency_band = _urgency_band(urgency)
    stance_key = STANCE_MATRIX[(heat_band, urgency_band)]
    return {
        "heat_band": heat_band,
        "urgency_band": urgency_band,
        "stance": stance_key,
        "stance_label": STANCE_CONFIG["stance_labels"][stance_key],
        "stance_description": STANCE_CONFIG["stance_descriptions"][stance_key],
    }


def recommend_cushion(heat, urgency_band):
    """Suggested contingency % to carry into the customer quote.

    Base steps on heat (0/1/2/3/5), +1 bonus if urgency is high, capped
    at 6 total. This is the number designed to hand off directly to the
    Quote Builder's contingency_pct field once that tool is merged.
    """
    cushion_cfg = STANCE_CONFIG["cushion"]
    base = cushion_cfg["base_ceiling"]  # heat >= 80 falls through to this
    for upper_bound, band_value in cushion_cfg["base_bands"]:
        if heat < upper_bound:
            base = band_value
            break

    bonus = cushion_cfg["bonus_high_urgency"] if urgency_band == "high" else Decimal(0)
    cushion_pct = min(base + bonus, cushion_cfg["cap"])

    return {"base": base, "bonus": bonus, "cushion_pct": cushion_pct}


def build_result(cleaned_data):
    """Orchestrator the view calls: runs the full pipeline over a form's
    cleaned_data and returns everything the template needs in one dict."""
    subscores = compute_subscores(cleaned_data)
    heat_data = compute_heat(subscores)
    urgency_data = compute_urgency(
        cleaned_data["hours_to_pickup"], cleaned_data["commitment_level"]
    )
    stance_data = resolve_stance(heat_data["heat"], urgency_data["urgency"])
    cushion_data = recommend_cushion(heat_data["heat"], stance_data["urgency_band"])

    excluded_count = sum(1 for data in subscores.values() if not data["provided"])

    return {
        "subscores": subscores,
        "heat": heat_data,
        "urgency": urgency_data,
        "stance": stance_data,
        "cushion": cushion_data,
        "excluded_count": excluded_count,
        "heat_display": display_score(heat_data["heat"]),
        "urgency_display": display_score(urgency_data["urgency"]),
    }


if __name__ == "__main__":
    # ---- §14.1 primary scenario: all five signals provided ----
    c1 = {
        "load_to_truck_ratio": D("6.2"),
        "days_posted_comparable": D("2.0"),
        "calls_received": 1,
        "hours_posted": D("4.0"),
        "diesel_trend": "rising",
        "nearest_trucks_dh": D("120"),
        "hours_to_pickup": D("7.5"),
        "commitment_level": "booked",
    }
    r1 = build_result(c1)
    ss1 = r1["subscores"]
    assert ss1["ltr"]["subscore"] == D("82.0")
    assert ss1["days_posted"]["subscore"] == D("60.0")
    assert ss1["call_rate"]["subscore"] == D("75.0")
    assert ss1["diesel"]["subscore"] == D("70.0")
    assert ss1["dh_depth"]["subscore"] == D("68.0")
    assert r1["heat"]["denominator"] == D("1.00")

    contrib1 = r1["heat"]["contributions"]
    assert display_score(contrib1["ltr"]) == D("27.9")
    assert display_score(contrib1["call_rate"]) == D("19.5")
    assert display_score(contrib1["days_posted"]) == D("9.6")
    assert display_score(contrib1["dh_depth"]) == D("10.9")
    assert display_score(contrib1["diesel"]) == D("5.6")

    assert r1["heat"]["heat"] == D("73.46")
    assert display_score(r1["heat"]["heat"]) == D("73.5")
    assert r1["stance"]["heat_band"] == "tight"
    assert r1["urgency"]["base"] == D("75.0")
    assert r1["urgency"]["urgency"] == D("90.0")
    assert r1["stance"]["urgency_band"] == "high"
    assert r1["stance"]["stance"] == "cover_now"
    assert r1["cushion"]["cushion_pct"] == D("4")

    # ---- §14.2 variant: renormalization + verdict flip ----
    c2 = {
        "load_to_truck_ratio": D("2.2"),
        "days_posted_comparable": D("0.75"),
        "calls_received": None,
        "hours_posted": None,
        "diesel_trend": "",
        "nearest_trucks_dh": D("40"),
        "hours_to_pickup": D("30"),
        "commitment_level": "quoted_only",
    }
    r2 = build_result(c2)
    ss2 = r2["subscores"]
    assert ss2["ltr"]["subscore"] == D("30.0")
    assert ss2["days_posted"]["subscore"] == D("25.0")
    assert ss2["dh_depth"]["subscore"] == D("15.0")
    assert r2["heat"]["denominator"] == D("0.66")
    numerator2 = sum(
        STANCE_CONFIG["signals"][k]["weight"] * ss2[k]["subscore"]
        for k in ("ltr", "days_posted", "dh_depth")
    )
    assert numerator2 == D("16.6")
    assert display_score(r2["heat"]["heat"]) == D("25.2")
    assert r2["stance"]["heat_band"] == "soft"
    assert r2["urgency"]["urgency"] == D("25.0")
    assert r2["stance"]["urgency_band"] == "low"
    assert r2["stance"]["stance"] == "hold_firm"
    assert r2["cushion"]["cushion_pct"] == D("0")

    # ---- §14.3 mandatory extras ----
    assert scale_signal(D("0.5"), (D(1), D(3), D(8))) == D(0)
    assert scale_signal(D(9), (D(1), D(3), D(8))) == D(100)
    assert scale_signal(D("3.0"), (D("2.0"), D("0.5"), D(0))) == D(0)
    assert scale_signal(D(0), (D("2.0"), D("0.5"), D(0))) == D(100)

    assert _heat_band(D(40)) == "balanced"
    assert _heat_band(D(65)) == "tight"
    assert _heat_band(D("39.9")) == "soft"
    assert _urgency_band(D(35)) == "med"
    assert _urgency_band(D(70)) == "high"
    assert _urgency_band(D("34.9")) == "low"

    assert STANCE_MATRIX[("soft", "high")] == "price_to_cover"
    assert STANCE_MATRIX[("tight", "low")] == "price_to_cover"

    total_w = sum(v["weight"] for v in STANCE_CONFIG["signals"].values())
    assert total_w == D("1.00")
    for key, cfg in STANCE_CONFIG["signals"].items():
        if "anchors" in cfg:
            a0, a50, a100 = cfg["anchors"]
            assert (a0 < a50 < a100) or (a0 > a50 > a100)

    print("ALL SELF-TESTS PASSED")