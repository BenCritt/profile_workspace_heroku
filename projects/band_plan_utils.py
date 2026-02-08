"""
Band Plan lookup logic.

Usage:
    from .band_plan_utils import lookup_frequency

    result = lookup_frequency(14.225)
    result = lookup_frequency(14.225, license_class="G")
"""

from .band_plan_data import BAND_PLAN, TECH_CW_HF_PRIVILEGES, LICENSE_CLASSES


def _freq_in_segment(freq, segment):
    """Return True if *freq* falls within *segment* boundaries (inclusive)."""
    return segment["freq_start"] <= freq <= segment["freq_end"]


def _format_freq(freq):
    """Return a human-friendly frequency string (strip trailing zeros)."""
    if freq >= 1000:
        return f"{freq:,.3f} MHz"
    return f"{freq:.3f} MHz"


def lookup_frequency(freq_mhz, license_class=None):
    """
    Look up a frequency against the US amateur band plan.

    Parameters
    ----------
    freq_mhz : float
        Frequency in MHz.
    license_class : str or None
        One of 'E', 'A', 'G', 'T' (case-insensitive), or None to show
        privileges for all classes.

    Returns
    -------
    dict with keys:
        "freq_mhz"       : float — the queried frequency.
        "freq_display"    : str  — formatted frequency string.
        "in_amateur_band" : bool — True if the frequency is within any
                            amateur allocation.
        "segments"        : list of matching segment dicts (may be >1 if
                            the frequency is on a boundary or in the
                            60m channelized list).
        "license_class"   : str or None — the queried class.
        "class_info"      : dict or None — name/description for the class.
        "can_transmit"    : bool or None — whether the queried class can
                            transmit at this frequency (None if no class
                            was specified).
        "tech_cw_note"    : dict or None — populated if the user selected
                            Technician and the frequency falls in one of
                            the special Technician HF CW sub-bands.
        "error"           : str or None — validation error message.
    """
    result = {
        "freq_mhz": freq_mhz,
        "freq_display": _format_freq(freq_mhz),
        "in_amateur_band": False,
        "segments": [],
        "license_class": None,
        "class_info": None,
        "can_transmit": None,
        "tech_cw_note": None,
        "error": None,
    }

    # ----- Validate frequency -----
    if freq_mhz <= 0:
        result["error"] = "Frequency must be a positive number."
        return result

    if freq_mhz > 300000:
        result["error"] = "Frequency exceeds 300 GHz — outside amateur allocations."
        return result

    # ----- Normalize license class -----
    if license_class:
        lc = license_class.strip().upper()
        # Accept full names as well as abbreviations.
        name_map = {
            "EXTRA": "E",
            "AMATEUR EXTRA": "E",
            "ADVANCED": "A",
            "GENERAL": "G",
            "TECHNICIAN": "T",
            "TECH": "T",
            "NOVICE": "N",
        }
        lc = name_map.get(lc, lc)
        if lc not in LICENSE_CLASSES:
            result["error"] = f"Unknown license class '{license_class}'. Use E, A, G, or T."
            return result
        result["license_class"] = lc
        result["class_info"] = LICENSE_CLASSES[lc]

    # ----- 60-meter channel matching (special tolerance) -----
    # 60m channels are each 2.8 kHz wide centered on the listed freq.
    SIXTY_M_TOLERANCE = 0.0014  # ± 1.4 kHz
    for seg in BAND_PLAN:
        if seg["band"].startswith("60 Meters"):
            center = seg["freq_start"]
            if abs(freq_mhz - center) <= SIXTY_M_TOLERANCE:
                result["in_amateur_band"] = True
                result["segments"].append(seg)
                # Don't break — only one channel should match, but be safe.

    # ----- Standard segment matching -----
    if not result["segments"]:
        for seg in BAND_PLAN:
            if seg["band"].startswith("60 Meters"):
                continue  # Already handled above.
            if _freq_in_segment(freq_mhz, seg):
                result["in_amateur_band"] = True
                result["segments"].append(seg)

    # ----- Technician HF CW check -----
    lc = result["license_class"]
    if lc == "T" and result["in_amateur_band"]:
        for tcw in TECH_CW_HF_PRIVILEGES:
            if _freq_in_segment(freq_mhz, tcw):
                result["tech_cw_note"] = tcw
                break

    # ----- Determine transmit privilege for the selected class -----
    if lc and result["in_amateur_band"]:
        # Check primary segments first.
        can_tx = any(lc in seg["classes"] for seg in result["segments"])
        # If Technician and not found in primary segments, check CW sub-bands.
        if not can_tx and lc == "T" and result["tech_cw_note"]:
            can_tx = True
        result["can_transmit"] = can_tx
    elif lc and not result["in_amateur_band"]:
        result["can_transmit"] = False

    return result


def get_all_bands_summary():
    """
    Return a de-duplicated, ordered list of band names for display
    (e.g. in a quick-reference table).
    """
    seen = set()
    bands = []
    for seg in BAND_PLAN:
        if seg["band"] not in seen:
            seen.add(seg["band"])
            bands.append({
                "name": seg["band"],
                "freq_start": seg["freq_start"],
                "freq_end": max(
                    s["freq_end"]
                    for s in BAND_PLAN
                    if s["band"] == seg["band"]
                ),
            })
    return bands
