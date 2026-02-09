"""
Antenna Length Calculator — calculation utilities.

All formulas use the standard amateur radio shortening constants that
account for typical wire end-effects:

    Half-wavelength (feet)  = 468 / f_MHz
    Quarter-wavelength (feet) = 234 / f_MHz
    Full wavelength (feet)  = 983.571 / f_MHz  (speed of light)

An optional Velocity Factor (VF) scales all lengths to account for
wire insulation, enclosed elements, or other dielectric effects.

No external dependencies — pure Python math.
"""

import math

# ---------------------------------------------------------------------------
#  Constants
# ---------------------------------------------------------------------------

# Speed of light in feet per MHz-cycle (299,792,458 m/s → ft/μs).
SPEED_OF_LIGHT_FT = 983.571

# Meters-per-foot conversion.
METERS_PER_FOOT = 0.3048

# Standard shortening factor for real-world wire antennas.
# 468 / f_MHz = 0.5 * SPEED_OF_LIGHT_FT * K, where K ≈ 0.952.
WIRE_K_FACTOR = 468.0 / (0.5 * SPEED_OF_LIGHT_FT)  # ≈ 0.9519

# Full-wave loop constant (slightly less shortening than a dipole).
LOOP_CONSTANT = 1005.0  # empirical: 1005 / f_MHz for total loop wire


# ---------------------------------------------------------------------------
#  Antenna type registry
# ---------------------------------------------------------------------------

ANTENNA_TYPES = {
    "dipole": {
        "name": "Half-Wave Dipole",
        "short_name": "Dipole",
        "description": (
            "A center-fed, half-wavelength antenna — the most fundamental "
            "and widely built HF antenna. Consists of two equal-length legs "
            "fed at the center with coaxial cable or ladder line."
        ),
        "default_vf": 0.95,
        "typical_bands": "HF (160m–6m)",
    },
    "vertical": {
        "name": "Quarter-Wave Vertical",
        "short_name": "¼λ Vertical",
        "description": (
            "A single vertical radiator approximately one quarter-wavelength "
            "tall, fed against a ground plane of radial wires. Common for "
            "both HF and VHF/UHF installations."
        ),
        "default_vf": 0.95,
        "typical_bands": "HF, VHF, UHF",
    },
    "efhw": {
        "name": "End-Fed Half-Wave (EFHW)",
        "short_name": "EFHW",
        "description": (
            "A half-wavelength wire antenna fed at one end through a matching "
            "transformer (typically 49:1 or 64:1 impedance ratio). Extremely "
            "popular for portable operations like POTA and SOTA because only "
            "one support point is needed."
        ),
        "default_vf": 0.95,
        "typical_bands": "HF (80m–10m, multi-band with harmonics)",
    },
    "jpole": {
        "name": "J-Pole",
        "short_name": "J-Pole",
        "description": (
            "An end-fed half-wave antenna with an integrated quarter-wave "
            "matching stub forming a 'J' shape. Typically built from copper "
            "pipe or twin-lead. Offers good gain with no ground radials."
        ),
        "default_vf": 0.95,
        "typical_bands": "VHF/UHF (2m, 70cm)",
    },
    "ground_plane": {
        "name": "Ground Plane",
        "short_name": "Ground Plane",
        "description": (
            "A quarter-wave vertical radiator with three or four radials "
            "angled downward at approximately 45°. The angled radials raise "
            "the feed-point impedance closer to 50 Ω for a direct coax "
            "connection. Common for VHF/UHF base stations."
        ),
        "default_vf": 0.95,
        "typical_bands": "VHF/UHF",
    },
    "loop": {
        "name": "Full-Wave Loop",
        "short_name": "Loop",
        "description": (
            "A continuous loop of wire one full electrical wavelength in "
            "circumference. Can be hung as a square, triangle (delta), or "
            "circle. Quieter on receive than a dipole and works well at "
            "modest heights."
        ),
        "default_vf": 0.95,
        "typical_bands": "HF (80m–10m)",
    },
    "five_eighths": {
        "name": "⅝-Wave Vertical",
        "short_name": "⅝λ Vertical",
        "description": (
            "A vertical antenna five-eighths of a wavelength tall. Provides "
            "approximately 3 dB gain over a quarter-wave vertical by "
            "concentrating radiation at low angles. Requires a matching "
            "network at the base. Very popular for VHF/UHF mobile and base."
        ),
        "default_vf": 0.95,
        "typical_bands": "VHF/UHF",
    },
}

# Ordered list for form dropdown rendering.
ANTENNA_TYPE_CHOICES = [
    ("dipole", "Half-Wave Dipole"),
    ("vertical", "Quarter-Wave Vertical"),
    ("efhw", "End-Fed Half-Wave (EFHW)"),
    ("jpole", "J-Pole"),
    ("ground_plane", "Ground Plane"),
    ("loop", "Full-Wave Loop"),
    ("five_eighths", "⅝-Wave Vertical"),
]


# ---------------------------------------------------------------------------
#  Common band quick-pick frequencies (center of the most-used segments)
# ---------------------------------------------------------------------------

QUICK_PICK_FREQUENCIES = [
    {"band": "160m", "freq": 1.900, "label": "160m — 1.900 MHz"},
    {"band": "80m",  "freq": 3.750, "label": "80m — 3.750 MHz"},
    {"band": "60m",  "freq": 5.357, "label": "60m — 5.357 MHz"},
    {"band": "40m",  "freq": 7.150, "label": "40m — 7.150 MHz"},
    {"band": "30m",  "freq": 10.125, "label": "30m — 10.125 MHz"},
    {"band": "20m",  "freq": 14.175, "label": "20m — 14.175 MHz"},
    {"band": "17m",  "freq": 18.118, "label": "17m — 18.118 MHz"},
    {"band": "15m",  "freq": 21.225, "label": "15m — 21.225 MHz"},
    {"band": "12m",  "freq": 24.940, "label": "12m — 24.940 MHz"},
    {"band": "10m",  "freq": 28.400, "label": "10m — 28.400 MHz"},
    {"band": "6m",   "freq": 52.000, "label": "6m — 52.000 MHz"},
    {"band": "2m",   "freq": 146.000, "label": "2m — 146.000 MHz"},
    {"band": "1.25m", "freq": 223.500, "label": "1.25m — 223.500 MHz"},
    {"band": "70cm", "freq": 440.000, "label": "70cm — 440.000 MHz"},
]


# ---------------------------------------------------------------------------
#  Conversion helpers
# ---------------------------------------------------------------------------

def _ft_to_m(feet):
    """Convert feet to meters."""
    return feet * METERS_PER_FOOT


def _ft_to_inches(feet):
    """Convert decimal feet to (whole_feet, remaining_inches) tuple."""
    whole_feet = int(feet)
    remaining_inches = (feet - whole_feet) * 12
    return whole_feet, round(remaining_inches, 1)


def _format_imperial(total_feet):
    """Return a human-friendly imperial string like '33 ft 2.4 in'."""
    ft, inches = _ft_to_inches(total_feet)
    if ft > 0:
        return f"{ft} ft {inches} in"
    return f"{inches} in"


def _format_metric(total_feet):
    """Return a human-friendly metric string like '10.12 m' or '45.3 cm'."""
    meters = _ft_to_m(total_feet)
    if meters >= 1.0:
        return f"{meters:.2f} m"
    return f"{meters * 100:.1f} cm"


# ---------------------------------------------------------------------------
#  Core calculation engine
# ---------------------------------------------------------------------------

def calculate_antenna(frequency_mhz, antenna_type, velocity_factor=None):
    """
    Calculate antenna element lengths for the given frequency and type.

    Args:
        frequency_mhz: float — design frequency in MHz (must be > 0).
        antenna_type: str — key from ANTENNA_TYPES dict.
        velocity_factor: float or None — dielectric velocity factor
                         (0.50–1.00). If None, the default VF for
                         the antenna type is used.

    Returns:
        dict with keys:
            "antenna_type"      : dict — metadata from ANTENNA_TYPES.
            "frequency_mhz"     : float — the input frequency.
            "velocity_factor"   : float — the VF that was applied.
            "wavelength_ft"     : float — full wavelength in feet.
            "wavelength_m"      : float — full wavelength in meters.
            "elements"          : list of dicts, each with:
                "label"         : str   — e.g. "Each Leg", "Radiator".
                "length_ft"     : float — length in decimal feet.
                "length_m"      : float — length in meters.
                "imperial"      : str   — formatted imperial string.
                "metric"        : str   — formatted metric string.
            "notes"             : list of str — build tips and caveats.
            "error"             : str or None.

    Raises:
        ValueError: If inputs are invalid.
    """
    # --- Input validation ---
    if antenna_type not in ANTENNA_TYPES:
        return {"error": f"Unknown antenna type: '{antenna_type}'."}

    if frequency_mhz is None or frequency_mhz <= 0:
        return {"error": "Frequency must be a positive number."}

    type_info = ANTENNA_TYPES[antenna_type]

    if velocity_factor is None:
        velocity_factor = type_info["default_vf"]

    if not (0.50 <= velocity_factor <= 1.00):
        return {"error": "Velocity factor must be between 0.50 and 1.00."}

    # --- Wavelength ---
    wavelength_ft = SPEED_OF_LIGHT_FT / frequency_mhz
    wavelength_m = _ft_to_m(wavelength_ft)

    # The standard shortening factor K ≈ 0.952 is already baked into the
    # classic constants (468, 234, etc.).  The user-supplied VF is applied
    # *on top* of those constants to handle insulation or enclosure effects.
    #
    # Effective VF ratio = user_VF / default_VF.
    # When user_VF equals the default, the classic formula is used as-is.
    vf_ratio = velocity_factor / type_info["default_vf"]

    # --- Compute elements by antenna type ---
    elements = []
    notes = []

    if antenna_type == "dipole":
        total_ft = (468.0 / frequency_mhz) * vf_ratio
        leg_ft = total_ft / 2.0
        elements.append({
            "label": "Total Length (tip to tip)",
            "length_ft": round(total_ft, 2),
            "length_m": round(_ft_to_m(total_ft), 3),
            "imperial": _format_imperial(total_ft),
            "metric": _format_metric(total_ft),
        })
        elements.append({
            "label": "Each Leg (center to tip)",
            "length_ft": round(leg_ft, 2),
            "length_m": round(_ft_to_m(leg_ft), 3),
            "imperial": _format_imperial(leg_ft),
            "metric": _format_metric(leg_ft),
        })
        notes.append(
            "Cut each leg 2–3% long and trim to resonance with an antenna "
            "analyzer or SWR meter."
        )
        notes.append(
            "Height above ground affects resonant frequency — raise the "
            "antenna to at least ¼ wavelength if possible."
        )

    elif antenna_type == "vertical":
        radiator_ft = (234.0 / frequency_mhz) * vf_ratio
        radial_ft = radiator_ft  # Radials are approximately the same length.
        elements.append({
            "label": "Radiator (vertical element)",
            "length_ft": round(radiator_ft, 2),
            "length_m": round(_ft_to_m(radiator_ft), 3),
            "imperial": _format_imperial(radiator_ft),
            "metric": _format_metric(radiator_ft),
        })
        elements.append({
            "label": "Each Ground Radial",
            "length_ft": round(radial_ft, 2),
            "length_m": round(_ft_to_m(radial_ft), 3),
            "imperial": _format_imperial(radial_ft),
            "metric": _format_metric(radial_ft),
        })
        notes.append(
            "More radials improve efficiency. Four radials is the minimum; "
            "16–32 radials laid on the ground is ideal for HF."
        )
        notes.append(
            "If radials are buried or laid on the ground, cut them ~5% "
            "longer than the calculated length."
        )

    elif antenna_type == "efhw":
        wire_ft = (468.0 / frequency_mhz) * vf_ratio
        elements.append({
            "label": "Total Wire Length",
            "length_ft": round(wire_ft, 2),
            "length_m": round(_ft_to_m(wire_ft), 3),
            "imperial": _format_imperial(wire_ft),
            "metric": _format_metric(wire_ft),
        })
        notes.append(
            "Requires a matching transformer (typically 49:1 unun) at the "
            "feed point."
        )
        notes.append(
            "An EFHW cut for 40 meters (~66 ft) will also resonate on "
            "20m, 15m, and 10m as harmonics — making it a popular "
            "multi-band portable antenna."
        )
        notes.append(
            "Add a short counterpoise wire (6–12 ft) at the transformer "
            "for improved performance."
        )

    elif antenna_type == "jpole":
        radiator_ft = (468.0 / frequency_mhz) * vf_ratio
        stub_ft = (234.0 / frequency_mhz) * vf_ratio
        elements.append({
            "label": "Radiating Element (longer side)",
            "length_ft": round(radiator_ft, 2),
            "length_m": round(_ft_to_m(radiator_ft), 3),
            "imperial": _format_imperial(radiator_ft),
            "metric": _format_metric(radiator_ft),
        })
        elements.append({
            "label": "Matching Stub (shorter side)",
            "length_ft": round(stub_ft, 2),
            "length_m": round(_ft_to_m(stub_ft), 3),
            "imperial": _format_imperial(stub_ft),
            "metric": _format_metric(stub_ft),
        })
        notes.append(
            "The two parallel elements are shorted together at the bottom "
            "and open at the top. Feed point is approximately 2–4% up "
            "from the shorted end on the longer element."
        )
        notes.append(
            "For copper-pipe construction, use ¾\" pipe for 2m or ½\" "
            "for 70cm. Space the elements ~1 inch apart."
        )

    elif antenna_type == "ground_plane":
        radiator_ft = (234.0 / frequency_mhz) * vf_ratio
        radial_ft = radiator_ft
        elements.append({
            "label": "Vertical Radiator",
            "length_ft": round(radiator_ft, 2),
            "length_m": round(_ft_to_m(radiator_ft), 3),
            "imperial": _format_imperial(radiator_ft),
            "metric": _format_metric(radiator_ft),
        })
        elements.append({
            "label": "Each Radial (×4)",
            "length_ft": round(radial_ft, 2),
            "length_m": round(_ft_to_m(radial_ft), 3),
            "imperial": _format_imperial(radial_ft),
            "metric": _format_metric(radial_ft),
        })
        notes.append(
            "Angle the four radials downward at ~45° from horizontal "
            "to bring the feed impedance close to 50 Ω."
        )
        notes.append(
            "Use an SO-239 chassis connector at the junction — center "
            "pin to the radiator, ground tabs to the radials."
        )

    elif antenna_type == "loop":
        total_wire_ft = (LOOP_CONSTANT / frequency_mhz) * vf_ratio
        # A square loop has sides of total / 4.
        square_side_ft = total_wire_ft / 4.0
        # A delta (triangle) loop has sides of total / 3.
        delta_side_ft = total_wire_ft / 3.0
        elements.append({
            "label": "Total Wire Length (circumference)",
            "length_ft": round(total_wire_ft, 2),
            "length_m": round(_ft_to_m(total_wire_ft), 3),
            "imperial": _format_imperial(total_wire_ft),
            "metric": _format_metric(total_wire_ft),
        })
        elements.append({
            "label": "Each Side (square loop, ×4)",
            "length_ft": round(square_side_ft, 2),
            "length_m": round(_ft_to_m(square_side_ft), 3),
            "imperial": _format_imperial(square_side_ft),
            "metric": _format_metric(square_side_ft),
        })
        elements.append({
            "label": "Each Side (delta / triangle loop, ×3)",
            "length_ft": round(delta_side_ft, 2),
            "length_m": round(_ft_to_m(delta_side_ft), 3),
            "imperial": _format_imperial(delta_side_ft),
            "metric": _format_metric(delta_side_ft),
        })
        notes.append(
            "Feed at the bottom for horizontal polarization (best for "
            "DX) or at a corner/side for vertical polarization (better "
            "for local/NVIS)."
        )
        notes.append(
            "The loop constant 1005/f is an empirical value. Actual "
            "resonance varies with shape and height — trim with an "
            "antenna analyzer."
        )

    elif antenna_type == "five_eighths":
        radiator_ft = (585.0 / frequency_mhz) * vf_ratio
        radial_ft = (234.0 / frequency_mhz) * vf_ratio
        elements.append({
            "label": "Radiator (⅝λ element)",
            "length_ft": round(radiator_ft, 2),
            "length_m": round(_ft_to_m(radiator_ft), 3),
            "imperial": _format_imperial(radiator_ft),
            "metric": _format_metric(radiator_ft),
        })
        elements.append({
            "label": "Each Ground Radial (¼λ)",
            "length_ft": round(radial_ft, 2),
            "length_m": round(_ft_to_m(radial_ft), 3),
            "imperial": _format_imperial(radial_ft),
            "metric": _format_metric(radial_ft),
        })
        notes.append(
            "A ⅝λ vertical is NOT resonant at 50 Ω and requires a "
            "matching network (typically a series coil or gamma match) "
            "at the base."
        )
        notes.append(
            "Provides approximately 3 dB gain over a ¼λ vertical by "
            "pushing more radiation toward the horizon."
        )

    # --- Assemble result ---
    return {
        "antenna_type": type_info,
        "antenna_type_key": antenna_type,
        "frequency_mhz": frequency_mhz,
        "frequency_display": f"{frequency_mhz:.3f} MHz" if frequency_mhz < 100 else f"{frequency_mhz:.2f} MHz",
        "velocity_factor": velocity_factor,
        "wavelength_ft": round(wavelength_ft, 2),
        "wavelength_m": round(wavelength_m, 3),
        "wavelength_imperial": _format_imperial(wavelength_ft),
        "wavelength_metric": _format_metric(wavelength_ft),
        "elements": elements,
        "notes": notes,
        "error": None,
    }
