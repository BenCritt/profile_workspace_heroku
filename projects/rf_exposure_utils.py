"""
RF Exposure / MPE Calculator — FCC OET Bulletin 65 utilities.

Calculates Maximum Permissible Exposure (MPE) compliance for amateur
radio stations per FCC Part 97.13(c)(1) and OET Bulletin 65.

Key formulas:
    Power density  S = (PEP × G × duty) / (4 × π × R²)
        S in mW/cm²,  PEP in mW,  G as numeric ratio,  R in cm.

    Minimum safe distance  R = √( (PEP × G × duty) / (4 × π × S_limit) )

FCC MPE limits are frequency-dependent and differ for:
    - Controlled (occupational) environments.
    - Uncontrolled (general public / residential) environments.

Reference:
    FCC OET Bulletin 65, Edition 97-01 (August 1997)
    https://www.fcc.gov/bureaus/oet/info/documents/bulletins/oet65/oet65.pdf

No external dependencies — pure Python math.
"""

import math

# ---------------------------------------------------------------------------
#  Constants
# ---------------------------------------------------------------------------

# Conversion factors.
WATTS_TO_MW = 1000.0         # 1 W = 1000 mW
FEET_TO_CM = 30.48           # 1 ft = 30.48 cm
METERS_TO_CM = 100.0         # 1 m = 100 cm
CM_TO_FEET = 1.0 / 30.48
CM_TO_METERS = 0.01

# Typical antenna duty cycles by mode (fraction of key-down time).
MODE_DUTY_CYCLES = {
    "ssb":         {"label": "SSB (Voice)",            "duty": 0.20},
    "cw":          {"label": "CW (Morse Code)",        "duty": 0.40},
    "fm":          {"label": "FM (Voice)",             "duty": 1.00},
    "digital_ft8": {"label": "FT8 / Digital",          "duty": 1.00},
    "rtty":        {"label": "RTTY",                   "duty": 1.00},
    "am":          {"label": "AM (Voice)",             "duty": 1.00},
    "custom":      {"label": "Custom Duty Cycle",      "duty": None},
}

# Ordered choices for form dropdown.
MODE_CHOICES = [
    ("ssb", "SSB (Voice) — 20% duty"),
    ("cw", "CW (Morse Code) — 40% duty"),
    ("fm", "FM (Voice) — 100% duty"),
    ("digital_ft8", "FT8 / Digital — 100% duty"),
    ("rtty", "RTTY — 100% duty"),
    ("am", "AM (Voice) — 100% duty"),
    ("custom", "Custom Duty Cycle"),
]

# Environment type choices.
ENVIRONMENT_CHOICES = [
    ("uncontrolled", "Uncontrolled (General Public / Residential)"),
    ("controlled", "Controlled (Occupational / RF-Aware)"),
]

# Gain reference choices.
GAIN_REF_CHOICES = [
    ("dBi", "dBi (relative to isotropic)"),
    ("dBd", "dBd (relative to dipole)"),
]


# ---------------------------------------------------------------------------
#  FCC MPE Limits — OET Bulletin 65, Table 1
# ---------------------------------------------------------------------------

def get_mpe_limit(frequency_mhz, environment):
    """
    Return the FCC Maximum Permissible Exposure limit in mW/cm²
    for the given frequency and environment type.

    Args:
        frequency_mhz: float — operating frequency in MHz.
        environment: str — "controlled" or "uncontrolled".

    Returns:
        float — MPE limit in mW/cm².

    Raises:
        ValueError: If frequency is out of the 0.3–100,000 MHz range.
    """
    f = frequency_mhz

    if f < 0.3 or f > 100000:
        raise ValueError(
            f"Frequency {f} MHz is outside the FCC MPE table range "
            f"(0.3–100,000 MHz)."
        )

    if environment == "controlled":
        # Controlled / Occupational limits (Table 1, Column A).
        if 0.3 <= f < 3.0:
            return 100.0
        elif 3.0 <= f < 30.0:
            return 900.0 / (f * f)
        elif 30.0 <= f < 300.0:
            return 1.0
        elif 300.0 <= f < 1500.0:
            return f / 300.0
        else:  # 1500–100000
            return 5.0

    else:  # uncontrolled
        # Uncontrolled / General Public limits (Table 1, Column B).
        if 0.3 <= f < 1.34:
            return 100.0
        elif 1.34 <= f < 30.0:
            return 180.0 / (f * f)
        elif 30.0 <= f < 300.0:
            return 0.2
        elif 300.0 <= f < 1500.0:
            return f / 1500.0
        else:  # 1500–100000
            return 1.0


# ---------------------------------------------------------------------------
#  Power density calculation
# ---------------------------------------------------------------------------

def _dbi_to_numeric(gain_dbi):
    """Convert antenna gain from dBi to a numeric (linear) ratio."""
    return 10.0 ** (gain_dbi / 10.0)


def _dbd_to_dbi(gain_dbd):
    """Convert dBd to dBi.  A dipole has 2.15 dBi gain."""
    return gain_dbd + 2.15


def calculate_power_density(power_watts, gain_dbi, distance_cm, duty_cycle=1.0,
                            feed_line_loss_db=0.0):
    """
    Calculate the far-field power density at a given distance.

    S = (P_mw × G_numeric × duty) / (4 × π × R_cm²)

    Args:
        power_watts: float — transmitter PEP output in watts.
        gain_dbi: float — antenna gain in dBi.
        distance_cm: float — distance from antenna in centimeters.
        duty_cycle: float — fraction (0.0–1.0).
        feed_line_loss_db: float — feed line loss in dB (reduces power).

    Returns:
        float — power density in mW/cm².
    """
    if distance_cm <= 0:
        return float("inf")

    # Effective power after feed line loss.
    effective_power_mw = power_watts * WATTS_TO_MW
    if feed_line_loss_db > 0:
        effective_power_mw *= 10.0 ** (-feed_line_loss_db / 10.0)

    gain_numeric = _dbi_to_numeric(gain_dbi)

    numerator = effective_power_mw * gain_numeric * duty_cycle
    denominator = 4.0 * math.pi * (distance_cm ** 2)

    return numerator / denominator


def calculate_min_safe_distance_cm(power_watts, gain_dbi, mpe_limit,
                                    duty_cycle=1.0, feed_line_loss_db=0.0):
    """
    Calculate the minimum safe distance in cm where power density
    equals the MPE limit.

    R = √( (P_mw × G × duty) / (4 × π × S_limit) )

    Returns:
        float — minimum safe distance in centimeters.
    """
    effective_power_mw = power_watts * WATTS_TO_MW
    if feed_line_loss_db > 0:
        effective_power_mw *= 10.0 ** (-feed_line_loss_db / 10.0)

    gain_numeric = _dbi_to_numeric(gain_dbi)

    numerator = effective_power_mw * gain_numeric * duty_cycle
    denominator = 4.0 * math.pi * mpe_limit

    if denominator <= 0:
        return float("inf")

    return math.sqrt(numerator / denominator)


# ---------------------------------------------------------------------------
#  Formatting helpers
# ---------------------------------------------------------------------------

def _cm_to_display(cm):
    """Return distance as a dict with feet/inches and meters/cm."""
    feet = cm * CM_TO_FEET
    meters = cm * CM_TO_METERS

    whole_feet = int(feet)
    remaining_inches = (feet - whole_feet) * 12.0

    if feet >= 1.0:
        imperial = f"{whole_feet} ft {remaining_inches:.1f} in"
    else:
        imperial = f"{remaining_inches:.1f} in"

    if meters >= 1.0:
        metric = f"{meters:.2f} m"
    else:
        metric = f"{meters * 100:.1f} cm"

    return {
        "feet": round(feet, 2),
        "meters": round(meters, 2),
        "imperial": imperial,
        "metric": metric,
    }


def _format_power_density(mw_cm2):
    """Format a power density value for display."""
    if mw_cm2 >= 1.0:
        return f"{mw_cm2:.3f} mW/cm²"
    elif mw_cm2 >= 0.001:
        return f"{mw_cm2:.4f} mW/cm²"
    else:
        return f"{mw_cm2:.2e} mW/cm²"


# ---------------------------------------------------------------------------
#  Main calculation engine
# ---------------------------------------------------------------------------

def calculate_rf_exposure(
    power_watts,
    gain_value,
    gain_reference,
    frequency_mhz,
    distance_value,
    distance_unit,
    mode,
    custom_duty_cycle=None,
    feed_line_loss_db=0.0,
):
    """
    Perform a complete RF exposure evaluation per FCC OET Bulletin 65.

    Args:
        power_watts: float — transmitter PEP output (watts).
        gain_value: float — antenna gain (in dBi or dBd per gain_reference).
        gain_reference: str — "dBi" or "dBd".
        frequency_mhz: float — operating frequency (MHz).
        distance_value: float — distance to nearest person.
        distance_unit: str — "feet" or "meters".
        mode: str — key from MODE_DUTY_CYCLES.
        custom_duty_cycle: float or None — 0–100 (percent), used when mode="custom".
        feed_line_loss_db: float — feed line loss in dB (default 0).

    Returns:
        dict with keys:
            "compliant_controlled"    : bool
            "compliant_uncontrolled"  : bool
            "power_density"           : float (mW/cm²)
            "power_density_display"   : str
            "mpe_controlled"          : float (mW/cm²)
            "mpe_uncontrolled"        : float (mW/cm²)
            "mpe_controlled_display"  : str
            "mpe_uncontrolled_display": str
            "margin_controlled_pct"   : float (percentage below limit)
            "margin_uncontrolled_pct" : float
            "min_distance_controlled" : dict (feet, meters, imperial, metric)
            "min_distance_uncontrolled": dict
            "effective_power_watts"   : float (after feed line loss)
            "gain_dbi"                : float
            "gain_display"            : str
            "duty_cycle"              : float (fraction)
            "duty_cycle_pct"          : float (percentage)
            "mode_label"              : str
            "frequency_mhz"           : float
            "distance"                : dict (feet, meters, imperial, metric)
            "error"                   : str or None
    """
    result = {"error": None}

    # --- Input validation ---
    if power_watts is None or power_watts <= 0:
        return {"error": "Transmitter power must be greater than zero."}

    if power_watts > 2000:
        return {"error": "Power exceeds 2,000 W. FCC amateur limit is 1,500 W PEP."}

    if frequency_mhz is None or frequency_mhz <= 0:
        return {"error": "Frequency must be greater than zero."}

    if frequency_mhz < 0.3 or frequency_mhz > 100000:
        return {"error": "Frequency must be between 0.3 and 100,000 MHz."}

    if gain_value is None:
        return {"error": "Please enter an antenna gain value."}

    if distance_value is None or distance_value <= 0:
        return {"error": "Distance must be greater than zero."}

    if feed_line_loss_db is None:
        feed_line_loss_db = 0.0

    if feed_line_loss_db < 0:
        return {"error": "Feed line loss cannot be negative."}

    # --- Convert gain to dBi ---
    if gain_reference == "dBd":
        gain_dbi = _dbd_to_dbi(gain_value)
        gain_display = f"{gain_value:.1f} dBd ({gain_dbi:.1f} dBi)"
    else:
        gain_dbi = gain_value
        gain_display = f"{gain_dbi:.1f} dBi"

    # --- Determine duty cycle ---
    if mode == "custom":
        if custom_duty_cycle is None or not (0 < custom_duty_cycle <= 100):
            return {"error": "Custom duty cycle must be between 1% and 100%."}
        duty_cycle = custom_duty_cycle / 100.0
    else:
        mode_info = MODE_DUTY_CYCLES.get(mode)
        if not mode_info:
            return {"error": f"Unknown mode: {mode}."}
        duty_cycle = mode_info["duty"]

    mode_label = MODE_DUTY_CYCLES.get(mode, {}).get("label", mode)

    # --- Convert distance to cm ---
    if distance_unit == "feet":
        distance_cm = distance_value * FEET_TO_CM
    else:
        distance_cm = distance_value * METERS_TO_CM

    # --- MPE limits ---
    try:
        mpe_controlled = get_mpe_limit(frequency_mhz, "controlled")
        mpe_uncontrolled = get_mpe_limit(frequency_mhz, "uncontrolled")
    except ValueError as exc:
        return {"error": str(exc)}

    # --- Power density at given distance ---
    power_density = calculate_power_density(
        power_watts, gain_dbi, distance_cm, duty_cycle, feed_line_loss_db
    )

    # --- Compliance check ---
    compliant_controlled = power_density <= mpe_controlled
    compliant_uncontrolled = power_density <= mpe_uncontrolled

    # --- Safety margins ---
    if mpe_controlled > 0:
        margin_controlled = ((mpe_controlled - power_density) / mpe_controlled) * 100
    else:
        margin_controlled = 0.0

    if mpe_uncontrolled > 0:
        margin_uncontrolled = ((mpe_uncontrolled - power_density) / mpe_uncontrolled) * 100
    else:
        margin_uncontrolled = 0.0

    # --- Minimum safe distances ---
    min_dist_controlled_cm = calculate_min_safe_distance_cm(
        power_watts, gain_dbi, mpe_controlled, duty_cycle, feed_line_loss_db
    )
    min_dist_uncontrolled_cm = calculate_min_safe_distance_cm(
        power_watts, gain_dbi, mpe_uncontrolled, duty_cycle, feed_line_loss_db
    )

    # --- Effective power after feed line loss ---
    effective_power = power_watts
    if feed_line_loss_db > 0:
        effective_power = power_watts * 10.0 ** (-feed_line_loss_db / 10.0)

    # --- Build result ---
    result.update({
        "compliant_controlled": compliant_controlled,
        "compliant_uncontrolled": compliant_uncontrolled,
        "power_density": round(power_density, 6),
        "power_density_display": _format_power_density(power_density),
        "mpe_controlled": round(mpe_controlled, 4),
        "mpe_uncontrolled": round(mpe_uncontrolled, 4),
        "mpe_controlled_display": _format_power_density(mpe_controlled),
        "mpe_uncontrolled_display": _format_power_density(mpe_uncontrolled),
        "margin_controlled_pct": round(margin_controlled, 1),
        "margin_uncontrolled_pct": round(margin_uncontrolled, 1),
        "min_distance_controlled": _cm_to_display(min_dist_controlled_cm),
        "min_distance_uncontrolled": _cm_to_display(min_dist_uncontrolled_cm),
        "effective_power_watts": round(effective_power, 2),
        "gain_dbi": round(gain_dbi, 2),
        "gain_display": gain_display,
        "duty_cycle": round(duty_cycle, 4),
        "duty_cycle_pct": round(duty_cycle * 100, 1),
        "mode_label": mode_label,
        "frequency_mhz": frequency_mhz,
        "distance": _cm_to_display(distance_cm),
        "feed_line_loss_db": round(feed_line_loss_db, 1),
    })

    return result


# ---------------------------------------------------------------------------
#  Quick-reference: common amateur station scenarios
# ---------------------------------------------------------------------------

EXAMPLE_SCENARIOS = [
    {
        "label": "100 W HF Dipole (SSB)",
        "power": 100, "gain": 2.15, "ref": "dBi", "freq": 14.2,
        "mode": "ssb", "note": "Typical 20m station",
    },
    {
        "label": "50 W VHF FM Mobile",
        "power": 50, "gain": 3.0, "ref": "dBi", "freq": 146.0,
        "mode": "fm", "note": "Typical 2m mobile whip",
    },
    {
        "label": "1500 W HF Yagi (SSB)",
        "power": 1500, "gain": 12.0, "ref": "dBi", "freq": 14.2,
        "mode": "ssb", "note": "High-power contest station",
    },
    {
        "label": "5 W HT (Handheld FM)",
        "power": 5, "gain": 0.0, "ref": "dBi", "freq": 146.0,
        "mode": "fm", "note": "Rubber duck, very close to body",
    },
]
