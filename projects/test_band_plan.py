"""
Tests for band plan lookup logic.

Run standalone:  python test_band_plan.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from band_plan_data import BAND_PLAN, TECH_CW_HF_PRIVILEGES, LICENSE_CLASSES


def _freq_in_segment(freq, segment):
    return segment["freq_start"] <= freq <= segment["freq_end"]


def lookup_frequency(freq_mhz, license_class=None):
    result = {
        "freq_mhz": freq_mhz,
        "in_amateur_band": False,
        "segments": [],
        "license_class": None,
        "class_info": None,
        "can_transmit": None,
        "tech_cw_note": None,
        "error": None,
    }

    if freq_mhz <= 0:
        result["error"] = "Frequency must be a positive number."
        return result

    lc = None
    if license_class:
        lc = license_class.strip().upper()
        name_map = {
            "EXTRA": "E", "AMATEUR EXTRA": "E", "ADVANCED": "A",
            "GENERAL": "G", "TECHNICIAN": "T", "TECH": "T", "NOVICE": "N",
        }
        lc = name_map.get(lc, lc)
        if lc not in LICENSE_CLASSES:
            result["error"] = f"Unknown license class '{license_class}'."
            return result
        result["license_class"] = lc
        result["class_info"] = LICENSE_CLASSES[lc]

    SIXTY_M_TOLERANCE = 0.0014
    for seg in BAND_PLAN:
        if seg["band"].startswith("60 Meters"):
            center = seg["freq_start"]
            if abs(freq_mhz - center) <= SIXTY_M_TOLERANCE:
                result["in_amateur_band"] = True
                result["segments"].append(seg)

    if not result["segments"]:
        for seg in BAND_PLAN:
            if seg["band"].startswith("60 Meters"):
                continue
            if _freq_in_segment(freq_mhz, seg):
                result["in_amateur_band"] = True
                result["segments"].append(seg)

    if lc == "T" and result["in_amateur_band"]:
        for tcw in TECH_CW_HF_PRIVILEGES:
            if _freq_in_segment(freq_mhz, tcw):
                result["tech_cw_note"] = tcw
                break

    if lc and result["in_amateur_band"]:
        can_tx = any(lc in seg["classes"] for seg in result["segments"])
        if not can_tx and lc == "T" and result["tech_cw_note"]:
            can_tx = True
        result["can_transmit"] = can_tx
    elif lc and not result["in_amateur_band"]:
        result["can_transmit"] = False

    return result


def get_all_bands_summary():
    seen = set()
    bands = []
    for seg in BAND_PLAN:
        if seg["band"] not in seen:
            seen.add(seg["band"])
            bands.append({
                "name": seg["band"],
                "freq_start": seg["freq_start"],
                "freq_end": max(
                    s["freq_end"] for s in BAND_PLAN if s["band"] == seg["band"]
                ),
            })
    return bands


# === Tests ===

passed = 0
failed = 0


def assert_true(condition, label):
    global passed, failed
    if condition:
        passed += 1
        print(f"  \u2713 {label}")
    else:
        failed += 1
        print(f"  \u2717 FAIL: {label}")


print("=== Band Plan Checker \u2014 Unit Tests ===\n")

print("Test 1: 14.225 MHz (20m General Phone edge)")
r = lookup_frequency(14.225, "G")
assert_true(r["in_amateur_band"], "In amateur band")
assert_true(r["can_transmit"] is True, "General can transmit")
assert_true(any("Phone" in seg["modes"] for seg in r["segments"]), "Phone permitted")

print("\nTest 2: 14.010 MHz (20m Extra-only CW)")
r = lookup_frequency(14.010, "G")
assert_true(r["in_amateur_band"], "In amateur band")
assert_true(r["can_transmit"] is False, "General CANNOT transmit here")
r2 = lookup_frequency(14.010, "E")
assert_true(r2["can_transmit"] is True, "Extra CAN transmit here")

print("\nTest 3: 146.520 MHz (2m FM simplex)")
r = lookup_frequency(146.520, "T")
assert_true(r["in_amateur_band"], "In amateur band")
assert_true(r["can_transmit"] is True, "Technician can transmit on 2m")

print("\nTest 4: 100.1 MHz (FM broadcast \u2014 not amateur)")
r = lookup_frequency(100.1)
assert_true(not r["in_amateur_band"], "Not in amateur band")
assert_true(len(r["segments"]) == 0, "No segments returned")

print("\nTest 5: 5.3320 MHz (60m Channel 1)")
r = lookup_frequency(5.332, "G")
assert_true(r["in_amateur_band"], "In amateur band")
assert_true(r["can_transmit"] is True, "General can transmit on 60m")
assert_true(r["segments"][0]["max_power_w"] == 100, "Power limit 100 W")

print("\nTest 6: 7.050 MHz (40m \u2014 Technician CW sub-band)")
r = lookup_frequency(7.050, "T")
assert_true(r["in_amateur_band"], "In amateur band")
assert_true(r["can_transmit"] is True, "Technician can transmit (CW)")
assert_true(r["tech_cw_note"] is not None, "Tech CW note populated")
assert_true(r["tech_cw_note"]["max_power_w"] == 200, "200 W limit noted")

print("\nTest 7: 28.400 MHz (10m Technician Phone)")
r = lookup_frequency(28.400, "T")
assert_true(r["in_amateur_band"], "In amateur band")
assert_true(r["can_transmit"] is True, "Technician can transmit on 10m")

print("\nTest 8: 10.120 MHz (30m \u2014 200 W limit)")
r = lookup_frequency(10.120, "G")
assert_true(r["in_amateur_band"], "In amateur band")
assert_true(r["segments"][0]["max_power_w"] == 200, "200 W power limit")

print("\nTest 9: Negative frequency")
r = lookup_frequency(-5)
assert_true(r["error"] is not None, "Error returned for negative freq")

print("\nTest 10: 14.300 MHz, no class selected")
r = lookup_frequency(14.300)
assert_true(r["in_amateur_band"], "In amateur band")
assert_true(r["can_transmit"] is None, "can_transmit is None (no class)")
assert_true(len(r["segments"]) > 0, "Segments returned")

print("\nTest 11: get_all_bands_summary()")
bands = get_all_bands_summary()
assert_true(len(bands) >= 12, f"At least 12 bands returned (got {len(bands)})")
assert_true(bands[0]["name"].startswith("160"), "First band is 160m")

print("\nTest 12: 3.550 MHz \u2014 Tech CW on 80m")
r = lookup_frequency(3.550, "T")
assert_true(r["in_amateur_band"], "In amateur band")
assert_true(r["can_transmit"] is True, "Technician can transmit (CW on 80m)")
assert_true(r["tech_cw_note"] is not None, "Tech CW note for 80m")

print("\nTest 13: 21.100 MHz \u2014 Tech CW on 15m")
r = lookup_frequency(21.100, "T")
assert_true(r["in_amateur_band"], "In amateur band")
assert_true(r["can_transmit"] is True, "Technician can transmit (CW on 15m)")

print("\nTest 14: 3.750 MHz \u2014 Technician NO privileges (80m phone, outside CW sub-band)")
r = lookup_frequency(3.750, "T")
assert_true(r["in_amateur_band"], "In amateur band")
assert_true(r["can_transmit"] is False, "Technician CANNOT transmit (80m phone)")

print(f"\n{'='*40}")
print(f"Passed: {passed}   Failed: {failed}")
if failed == 0:
    print("All tests passed.")
else:
    print("SOME TESTS FAILED.")
    sys.exit(1)
