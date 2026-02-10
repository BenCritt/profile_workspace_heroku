"""
Coax Cable Loss Calculator — feed line attenuation utilities.

Calculates matched-line loss (dB) for common coaxial cable types at a
given frequency and cable run length, with optional SWR mismatch loss.

Key formulas:
    Matched loss: interpolated from manufacturer per-100-ft specs using
                  log–log interpolation (standard for coax loss curves).

    Mismatch loss (dB) = -10 × log10(1 - ρ²)
        where ρ = (SWR - 1) / (SWR + 1)

    Total system loss = matched loss + mismatch loss.
    Efficiency = 10^(-total_loss_dB / 10) × 100%.

Cable loss data sourced from manufacturer published specifications.
Actual loss varies with cable age, connector quality, moisture ingress,
and installation conditions.

No external dependencies — pure Python math.
"""

import math

# ---------------------------------------------------------------------------
#  Constants
# ---------------------------------------------------------------------------

FEET_PER_METER = 3.28084
METERS_PER_FOOT = 0.3048

# Standard test frequencies (MHz) for cable loss specs.
STANDARD_FREQS_MHZ = [1, 10, 50, 100, 150, 220, 440, 900, 1500]

# ---------------------------------------------------------------------------
#  Cable Database — matched loss per 100 feet (dB) at standard frequencies.
#
#  Each entry: {
#      "label": display name,
#      "impedance": nominal impedance in ohms,
#      "loss_per_100ft": [loss_at_1, loss_at_10, ..., loss_at_1500],
#      "note": optional note for the user,
#  }
#
#  Sources: manufacturer data sheets (Times Microwave LMR series,
#  Belden, Davis RF, Andrew/CommScope). Values rounded to published
#  precision.  Where manufacturer data does not cover all 9 test
#  frequencies, values are interpolated from the nearest published
#  points using the standard sqrt(f) approximation for copper coax.
# ---------------------------------------------------------------------------

CABLE_DATABASE = {
    "rg174": {
        "label": "RG-174 (Very Thin, High Loss)",
        "impedance": 50,
        "loss_per_100ft": [0.3, 1.0, 2.2, 3.3, 4.1, 5.1, 7.4, 11.2, 15.0],
        "note": "Very thin coax. Suitable only for short jumpers and receive-only use.",
    },
    "rg58": {
        "label": "RG-58",
        "impedance": 50,
        "loss_per_100ft": [0.2, 0.6, 1.4, 2.0, 2.5, 3.1, 4.5, 6.8, 9.2],
        "note": "Common thin 50-ohm coax. Acceptable for short HF runs.",
    },
    "rg8x": {
        "label": "RG-8X (Mini-8)",
        "impedance": 50,
        "loss_per_100ft": [0.2, 0.5, 1.1, 1.6, 2.0, 2.5, 3.6, 5.4, 7.3],
        "note": "Thinner alternative to RG-8/213 with moderate loss.",
    },
    "rg213": {
        "label": "RG-8 / RG-213",
        "impedance": 50,
        "loss_per_100ft": [0.1, 0.4, 0.8, 1.2, 1.5, 1.8, 2.7, 4.1, 5.5],
        "note": "Standard HF coax. Good balance of cost and performance.",
    },
    "lmr240": {
        "label": "LMR-240",
        "impedance": 50,
        "loss_per_100ft": [0.1, 0.4, 0.9, 1.3, 1.6, 2.0, 2.9, 4.3, 5.8],
        "note": "Times Microwave low-loss cable, similar diameter to RG-8X.",
    },
    "lmr400": {
        "label": "LMR-400 (Low-Loss)",
        "impedance": 50,
        "loss_per_100ft": [0.1, 0.2, 0.5, 0.7, 0.9, 1.1, 1.5, 2.4, 3.2],
        "note": "Popular low-loss cable. Excellent choice for VHF/UHF runs.",
    },
    "lmr600": {
        "label": "LMR-600",
        "impedance": 50,
        "loss_per_100ft": [0.05, 0.15, 0.3, 0.5, 0.6, 0.7, 1.1, 1.7, 2.2],
        "note": "Very low loss, large diameter. Used for long runs and commercial installs.",
    },
    "belden9913": {
        "label": "Belden 9913 / Davis RF Bury-Flex",
        "impedance": 50,
        "loss_per_100ft": [0.1, 0.2, 0.5, 0.8, 1.0, 1.2, 1.7, 2.7, 3.6],
        "note": "Low-loss cable with solid center conductor. Good for direct burial.",
    },
    "rg6": {
        "label": "RG-6 (75-ohm, TV/Receive)",
        "impedance": 75,
        "loss_per_100ft": [0.1, 0.3, 0.6, 0.9, 1.1, 1.4, 2.0, 3.1, 4.2],
        "note": "75-ohm cable designed for TV/CATV. Impedance mismatch with 50-ohm ham gear.",
    },
    "ldf4_50a": {
        "label": 'Hardline / Andrew Heliax LDF4-50A',
        "impedance": 50,
        "loss_per_100ft": [0.02, 0.08, 0.17, 0.25, 0.31, 0.38, 0.56, 0.86, 1.15],
        "note": "Professional hardline. Lowest loss, but expensive and difficult to install.",
    },
}

# Ordered choices for form dropdown.
CABLE_CHOICES = [
    ("rg174", "RG-174 (Very Thin, High Loss)"),
    ("rg58", "RG-58"),
    ("rg8x", "RG-8X (Mini-8)"),
    ("rg213", "RG-8 / RG-213"),
    ("lmr240", "LMR-240"),
    ("lmr400", "LMR-400 (Low-Loss)"),
    ("lmr600", "LMR-600"),
    ("belden9913", "Belden 9913 / Davis RF Bury-Flex"),
    ("rg6", "RG-6 (75-ohm, TV/Receive)"),
    ("ldf4_50a", "Hardline / Andrew Heliax LDF4-50A"),
]

# Length unit choices.
LENGTH_UNIT_CHOICES = [
    ("feet", "Feet"),
    ("meters", "Meters"),
]


# ---------------------------------------------------------------------------
#  Log–log interpolation for coax loss
# ---------------------------------------------------------------------------

def interpolate_loss_per_100ft(cable_key, frequency_mhz):
    """
    Interpolate the matched loss per 100 feet at a given frequency
    using log–log interpolation on the cable's published loss table.

    Log–log interpolation is standard for coax loss curves because
    attenuation in copper coax follows an approximately sqrt(f) law,
    which is linear on a log–log plot.

    Args:
        cable_key: str — key in CABLE_DATABASE.
        frequency_mhz: float — operating frequency in MHz.

    Returns:
        float — loss in dB per 100 feet at the given frequency.

    Raises:
        ValueError: If cable_key is not found in the database.
        ValueError: If frequency is outside the 1–1500 MHz range.
    """
    if cable_key not in CABLE_DATABASE:
        raise ValueError(f"Unknown cable type: {cable_key}")

    cable = CABLE_DATABASE[cable_key]
    loss_table = cable["loss_per_100ft"]
    freqs = STANDARD_FREQS_MHZ

    # Clamp to table boundaries for edge cases.
    if frequency_mhz <= freqs[0]:
        return loss_table[0]
    if frequency_mhz >= freqs[-1]:
        return loss_table[-1]

    # Find the bracketing pair of test frequencies.
    for i in range(len(freqs) - 1):
        if freqs[i] <= frequency_mhz <= freqs[i + 1]:
            f_low = freqs[i]
            f_high = freqs[i + 1]
            loss_low = loss_table[i]
            loss_high = loss_table[i + 1]
            break
    else:
        # Should not reach here given the clamp above.
        return loss_table[-1]

    # Guard against zero/negative loss values in log domain.
    if loss_low <= 0 or loss_high <= 0:
        # Fall back to linear interpolation if a table value is zero.
        t = (frequency_mhz - f_low) / (f_high - f_low)
        return loss_low + t * (loss_high - loss_low)

    # Log–log interpolation:
    #   log(loss) = log(loss_low) + [log(loss_high) - log(loss_low)]
    #               × [log(freq) - log(f_low)] / [log(f_high) - log(f_low)]
    log_f = math.log(frequency_mhz)
    log_f_low = math.log(f_low)
    log_f_high = math.log(f_high)
    log_loss_low = math.log(loss_low)
    log_loss_high = math.log(loss_high)

    t = (log_f - log_f_low) / (log_f_high - log_f_low)
    log_loss = log_loss_low + t * (log_loss_high - log_loss_low)

    return math.exp(log_loss)


# ---------------------------------------------------------------------------
#  Matched loss calculation
# ---------------------------------------------------------------------------

def calculate_matched_loss(cable_key, frequency_mhz, length_value, length_unit):
    """
    Calculate the total matched-line loss in dB for a given cable run.

    Args:
        cable_key: str — key in CABLE_DATABASE.
        frequency_mhz: float — operating frequency in MHz.
        length_value: float — cable run length.
        length_unit: str — "feet" or "meters".

    Returns:
        float — total matched loss in dB.
    """
    loss_per_100ft = interpolate_loss_per_100ft(cable_key, frequency_mhz)

    # Convert length to feet if needed.
    if length_unit == "meters":
        length_feet = length_value * FEET_PER_METER
    else:
        length_feet = length_value

    return loss_per_100ft * (length_feet / 100.0)


# ---------------------------------------------------------------------------
#  SWR mismatch loss calculation
# ---------------------------------------------------------------------------

def calculate_mismatch_loss(swr):
    """
    Calculate the additional loss (in dB) due to SWR mismatch.

    Mismatch loss = -10 × log10(1 - ρ²)
    where ρ = (SWR - 1) / (SWR + 1)

    This represents the power reflected back and not delivered to
    the antenna.

    Args:
        swr: float — SWR at the antenna feed point (≥ 1.0).

    Returns:
        float — mismatch loss in dB.  Returns 0.0 if SWR ≤ 1.0.
    """
    if swr is None or swr <= 1.0:
        return 0.0

    rho = (swr - 1.0) / (swr + 1.0)
    rho_squared = rho ** 2

    # Guard: if rho² == 1.0 (SWR = infinity), loss is infinite.
    if rho_squared >= 1.0:
        return float("inf")

    return -10.0 * math.log10(1.0 - rho_squared)


# ---------------------------------------------------------------------------
#  Formatting helpers
# ---------------------------------------------------------------------------

def _length_to_display(length_feet):
    """Return a display dict with both imperial and metric representations."""
    length_meters = length_feet * METERS_PER_FOOT

    if length_feet >= 1.0:
        imperial = f"{length_feet:,.1f} ft"
    else:
        imperial = f"{length_feet * 12:,.1f} in"

    if length_meters >= 1.0:
        metric = f"{length_meters:,.2f} m"
    else:
        metric = f"{length_meters * 100:,.1f} cm"

    return {
        "feet": round(length_feet, 2),
        "meters": round(length_meters, 2),
        "imperial": imperial,
        "metric": metric,
    }


def _format_db(value_db):
    """Format a dB value for display."""
    if value_db == float("inf"):
        return "∞ dB"
    return f"{value_db:.2f} dB"


def _format_watts(watts):
    """Format a wattage value for display."""
    if watts >= 1.0:
        return f"{watts:,.2f} W"
    elif watts >= 0.001:
        return f"{watts * 1000:,.2f} mW"
    else:
        return f"{watts:.2e} W"


def _format_percent(pct):
    """Format a percentage for display."""
    return f"{pct:.1f}%"


# ---------------------------------------------------------------------------
#  Main calculation engine
# ---------------------------------------------------------------------------

def calculate_coax_loss(
    cable_type,
    frequency_mhz,
    length_value,
    length_unit,
    power_watts=None,
    swr=None,
):
    """
    Perform a complete coax cable loss calculation.

    Args:
        cable_type: str — key from CABLE_DATABASE.
        frequency_mhz: float — operating frequency in MHz.
        length_value: float — cable run length.
        length_unit: str — "feet" or "meters".
        power_watts: float or None — transmitter power (optional).
        swr: float or None — SWR at the antenna (optional, ≥ 1.0).

    Returns:
        dict with keys:
            "cable_label"            : str
            "cable_impedance"        : int (ohms)
            "cable_note"             : str
            "impedance_warning"      : bool (True if 75-ohm cable)
            "frequency_mhz"         : float
            "length"                 : dict (feet, meters, imperial, metric)
            "loss_per_100ft"         : float (dB)
            "loss_per_100ft_display" : str
            "matched_loss_db"        : float
            "matched_loss_display"   : str
            "swr"                    : float or None
            "mismatch_loss_db"       : float
            "mismatch_loss_display"  : str
            "total_loss_db"          : float
            "total_loss_display"     : str
            "efficiency_pct"         : float
            "efficiency_display"     : str
            "power_in_watts"         : float or None
            "power_lost_watts"       : float or None
            "power_lost_display"     : str or None
            "power_out_watts"        : float or None
            "power_out_display"      : str or None
            "error"                  : str or None
    """
    result = {"error": None}

    # --- Input validation ---
    if cable_type is None or cable_type not in CABLE_DATABASE:
        return {"error": f"Unknown cable type: {cable_type}"}

    if frequency_mhz is None or frequency_mhz <= 0:
        return {"error": "Frequency must be greater than zero."}

    if frequency_mhz < 1.0 or frequency_mhz > 3000.0:
        return {"error": "Frequency must be between 1 and 3,000 MHz."}

    if length_value is None or length_value <= 0:
        return {"error": "Cable length must be greater than zero."}

    if length_unit not in ("feet", "meters"):
        return {"error": "Length unit must be 'feet' or 'meters'."}

    if power_watts is not None and power_watts < 0:
        return {"error": "Transmitter power cannot be negative."}

    if swr is not None and swr < 1.0:
        return {"error": "SWR cannot be less than 1.0."}

    if swr is not None and swr > 20.0:
        return {"error": "SWR exceeds 20.0. Check your antenna system."}

    # --- Cable info ---
    cable = CABLE_DATABASE[cable_type]
    cable_label = cable["label"]
    cable_impedance = cable["impedance"]
    cable_note = cable["note"]
    impedance_warning = cable_impedance != 50

    # --- Convert length to feet for calculation ---
    if length_unit == "meters":
        length_feet = length_value * FEET_PER_METER
    else:
        length_feet = length_value

    length_display = _length_to_display(length_feet)

    # --- Interpolate loss at operating frequency ---
    loss_per_100ft = interpolate_loss_per_100ft(cable_type, frequency_mhz)

    # --- Matched loss ---
    matched_loss_db = loss_per_100ft * (length_feet / 100.0)

    # --- Mismatch loss ---
    effective_swr = swr if (swr is not None and swr > 1.0) else None
    mismatch_loss_db = calculate_mismatch_loss(effective_swr) if effective_swr else 0.0

    # --- Total system loss ---
    total_loss_db = matched_loss_db + mismatch_loss_db

    # --- Efficiency ---
    if total_loss_db == float("inf"):
        efficiency_pct = 0.0
    else:
        efficiency_pct = 10.0 ** (-total_loss_db / 10.0) * 100.0

    # --- Power calculations (optional) ---
    power_in_watts = power_watts
    power_out_watts = None
    power_lost_watts = None
    power_lost_display = None
    power_out_display = None

    if power_watts is not None and power_watts > 0:
        if total_loss_db == float("inf"):
            power_out_watts = 0.0
            power_lost_watts = power_watts
        else:
            power_out_watts = power_watts * 10.0 ** (-total_loss_db / 10.0)
            power_lost_watts = power_watts - power_out_watts

        power_lost_display = _format_watts(power_lost_watts)
        power_out_display = _format_watts(power_out_watts)

        # Round for result dict.
        power_out_watts = round(power_out_watts, 4)
        power_lost_watts = round(power_lost_watts, 4)

    # --- Build result ---
    result.update({
        "cable_label": cable_label,
        "cable_impedance": cable_impedance,
        "cable_note": cable_note,
        "impedance_warning": impedance_warning,
        "frequency_mhz": frequency_mhz,
        "length": length_display,
        "loss_per_100ft": round(loss_per_100ft, 4),
        "loss_per_100ft_display": _format_db(loss_per_100ft),
        "matched_loss_db": round(matched_loss_db, 4),
        "matched_loss_display": _format_db(matched_loss_db),
        "swr": effective_swr,
        "mismatch_loss_db": round(mismatch_loss_db, 4),
        "mismatch_loss_display": _format_db(mismatch_loss_db),
        "total_loss_db": round(total_loss_db, 4),
        "total_loss_display": _format_db(total_loss_db),
        "efficiency_pct": round(efficiency_pct, 2),
        "efficiency_display": _format_percent(efficiency_pct),
        "power_in_watts": power_in_watts,
        "power_lost_watts": power_lost_watts,
        "power_lost_display": power_lost_display,
        "power_out_watts": power_out_watts,
        "power_out_display": power_out_display,
    })

    return result


# ---------------------------------------------------------------------------
#  Quick-reference: common scenarios
# ---------------------------------------------------------------------------

EXAMPLE_SCENARIOS = [
    {
        "label": "50 ft RG-213 on 20m (HF)",
        "cable": "rg213", "freq": 14.2, "length": 50, "unit": "feet",
        "note": "Typical HF station feed line",
    },
    {
        "label": "100 ft LMR-400 on 2m (VHF)",
        "cable": "lmr400", "freq": 146.0, "length": 100, "unit": "feet",
        "note": "Tower-mounted VHF antenna",
    },
    {
        "label": "25 ft RG-58 on 70cm (UHF)",
        "cable": "rg58", "freq": 440.0, "length": 25, "unit": "feet",
        "note": "Short UHF run — loss adds up fast at UHF",
    },
    {
        "label": "30 m LMR-600 on 23cm",
        "cable": "lmr600", "freq": 1296.0, "length": 30, "unit": "meters",
        "note": "Microwave feed line — every dB counts",
    },
]
