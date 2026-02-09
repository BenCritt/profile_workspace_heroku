"""
Antenna Length Calculator — standalone test suite.

Run:
    python test_antenna_calculator.py

All tests use the module directly — no Django ORM or HTTP needed.
"""

import sys
import unittest

# ---------------------------------------------------------------------------
#  Path shimming — allow running from the same directory as the module.
# ---------------------------------------------------------------------------
sys.path.insert(0, ".")
from antenna_calculator_utils import (
    calculate_antenna,
    ANTENNA_TYPES,
    ANTENNA_TYPE_CHOICES,
    QUICK_PICK_FREQUENCIES,
    _ft_to_m,
    _ft_to_inches,
    _format_imperial,
    _format_metric,
    LOOP_CONSTANT,
)


class TestConversionHelpers(unittest.TestCase):
    """Verify unit-conversion helper functions."""

    def test_ft_to_m(self):
        self.assertAlmostEqual(_ft_to_m(1.0), 0.3048, places=4)
        self.assertAlmostEqual(_ft_to_m(100.0), 30.48, places=2)
        self.assertAlmostEqual(_ft_to_m(0.0), 0.0, places=4)

    def test_ft_to_inches(self):
        ft, inches = _ft_to_inches(10.5)
        self.assertEqual(ft, 10)
        self.assertAlmostEqual(inches, 6.0, places=1)

    def test_ft_to_inches_sub_one(self):
        ft, inches = _ft_to_inches(0.75)
        self.assertEqual(ft, 0)
        self.assertAlmostEqual(inches, 9.0, places=1)

    def test_format_imperial(self):
        result = _format_imperial(33.0)
        self.assertIn("33 ft", result)
        self.assertIn("0.0 in", result)

    def test_format_imperial_fractional(self):
        result = _format_imperial(33.5)
        self.assertIn("33 ft", result)
        self.assertIn("6.0 in", result)

    def test_format_imperial_inches_only(self):
        result = _format_imperial(0.5)
        self.assertIn("6.0 in", result)
        self.assertNotIn("ft", result)

    def test_format_metric_meters(self):
        result = _format_metric(100.0)
        self.assertIn("m", result)
        self.assertIn("30.48", result)

    def test_format_metric_centimeters(self):
        result = _format_metric(0.1)
        self.assertIn("cm", result)


class TestDipoleCalculation(unittest.TestCase):
    """Verify the classic half-wave dipole: 468 / f."""

    def test_standard_20m_dipole(self):
        """20m dipole at 14.175 MHz with default VF."""
        result = calculate_antenna(14.175, "dipole")
        self.assertIsNone(result["error"])
        total_ft = result["elements"][0]["length_ft"]
        # 468 / 14.175 = 33.02... ft
        self.assertAlmostEqual(total_ft, 468.0 / 14.175, delta=0.1)
        # Each leg is half the total.
        leg_ft = result["elements"][1]["length_ft"]
        self.assertAlmostEqual(leg_ft, total_ft / 2.0, delta=0.05)

    def test_2m_dipole(self):
        """2m dipole at 146 MHz."""
        result = calculate_antenna(146.0, "dipole")
        self.assertIsNone(result["error"])
        total_ft = result["elements"][0]["length_ft"]
        expected = 468.0 / 146.0  # ~3.205 ft
        self.assertAlmostEqual(total_ft, expected, delta=0.05)

    def test_dipole_two_elements(self):
        """A dipole result should have exactly 2 elements."""
        result = calculate_antenna(7.15, "dipole")
        self.assertEqual(len(result["elements"]), 2)

    def test_dipole_has_notes(self):
        result = calculate_antenna(7.15, "dipole")
        self.assertTrue(len(result["notes"]) >= 1)


class TestVerticalCalculation(unittest.TestCase):
    """Quarter-wave vertical: 234 / f."""

    def test_standard_2m_vertical(self):
        result = calculate_antenna(146.0, "vertical")
        self.assertIsNone(result["error"])
        radiator_ft = result["elements"][0]["length_ft"]
        expected = 234.0 / 146.0  # ~1.603 ft
        self.assertAlmostEqual(radiator_ft, expected, delta=0.05)

    def test_vertical_two_elements(self):
        result = calculate_antenna(28.4, "vertical")
        self.assertEqual(len(result["elements"]), 2)
        # Radiator and radial should be approximately equal.
        radiator = result["elements"][0]["length_ft"]
        radial = result["elements"][1]["length_ft"]
        self.assertAlmostEqual(radiator, radial, delta=0.01)


class TestEFHWCalculation(unittest.TestCase):
    """End-Fed Half-Wave: 468 / f (same length as a dipole)."""

    def test_efhw_40m(self):
        """Classic 40m EFHW at 7.15 MHz."""
        result = calculate_antenna(7.15, "efhw")
        self.assertIsNone(result["error"])
        wire_ft = result["elements"][0]["length_ft"]
        expected = 468.0 / 7.15  # ~65.45 ft
        self.assertAlmostEqual(wire_ft, expected, delta=0.1)

    def test_efhw_one_element(self):
        result = calculate_antenna(7.15, "efhw")
        self.assertEqual(len(result["elements"]), 1)

    def test_efhw_mentions_transformer(self):
        result = calculate_antenna(7.15, "efhw")
        notes_text = " ".join(result["notes"])
        self.assertIn("49:1", notes_text)


class TestJPoleCalculation(unittest.TestCase):
    """J-Pole: half-wave radiator + quarter-wave matching stub."""

    def test_jpole_2m(self):
        result = calculate_antenna(146.0, "jpole")
        self.assertIsNone(result["error"])
        radiator_ft = result["elements"][0]["length_ft"]
        stub_ft = result["elements"][1]["length_ft"]
        # Radiator ≈ 468/146 = 3.205, stub ≈ 234/146 = 1.603.
        self.assertAlmostEqual(radiator_ft, 468.0 / 146.0, delta=0.05)
        self.assertAlmostEqual(stub_ft, 234.0 / 146.0, delta=0.05)

    def test_jpole_two_elements(self):
        result = calculate_antenna(146.0, "jpole")
        self.assertEqual(len(result["elements"]), 2)


class TestGroundPlaneCalculation(unittest.TestCase):
    """Ground plane: same as quarter-wave vertical."""

    def test_ground_plane_70cm(self):
        result = calculate_antenna(440.0, "ground_plane")
        self.assertIsNone(result["error"])
        radiator_ft = result["elements"][0]["length_ft"]
        expected = 234.0 / 440.0  # ~0.532 ft
        self.assertAlmostEqual(radiator_ft, expected, delta=0.02)

    def test_ground_plane_two_elements(self):
        result = calculate_antenna(440.0, "ground_plane")
        self.assertEqual(len(result["elements"]), 2)


class TestLoopCalculation(unittest.TestCase):
    """Full-wave loop: 1005 / f for total wire circumference."""

    def test_loop_40m(self):
        result = calculate_antenna(7.15, "loop")
        self.assertIsNone(result["error"])
        total_wire = result["elements"][0]["length_ft"]
        expected = LOOP_CONSTANT / 7.15  # ~140.56 ft
        self.assertAlmostEqual(total_wire, expected, delta=0.2)

    def test_loop_three_elements(self):
        """Loop should show: total wire, square side, delta side."""
        result = calculate_antenna(7.15, "loop")
        self.assertEqual(len(result["elements"]), 3)

    def test_loop_side_lengths(self):
        result = calculate_antenna(7.15, "loop")
        total = result["elements"][0]["length_ft"]
        square_side = result["elements"][1]["length_ft"]
        delta_side = result["elements"][2]["length_ft"]
        self.assertAlmostEqual(square_side, total / 4.0, delta=0.1)
        self.assertAlmostEqual(delta_side, total / 3.0, delta=0.1)


class TestFiveEighthsCalculation(unittest.TestCase):
    """Five-eighths-wave vertical: 585 / f."""

    def test_five_eighths_2m(self):
        result = calculate_antenna(146.0, "five_eighths")
        self.assertIsNone(result["error"])
        radiator_ft = result["elements"][0]["length_ft"]
        expected = 585.0 / 146.0  # ~4.007 ft
        self.assertAlmostEqual(radiator_ft, expected, delta=0.05)

    def test_five_eighths_two_elements(self):
        result = calculate_antenna(146.0, "five_eighths")
        self.assertEqual(len(result["elements"]), 2)


class TestVelocityFactor(unittest.TestCase):
    """VF adjustment should scale all lengths proportionally."""

    def test_lower_vf_shorter_antenna(self):
        """Insulated wire (VF=0.90) should be shorter than default (0.95)."""
        default_result = calculate_antenna(14.175, "dipole", velocity_factor=0.95)
        insulated_result = calculate_antenna(14.175, "dipole", velocity_factor=0.90)
        default_len = default_result["elements"][0]["length_ft"]
        insulated_len = insulated_result["elements"][0]["length_ft"]
        self.assertLess(insulated_len, default_len)

    def test_vf_1_longer_than_default(self):
        """VF=1.00 should give a longer antenna than the default 0.95."""
        default_result = calculate_antenna(14.175, "dipole", velocity_factor=0.95)
        full_vf_result = calculate_antenna(14.175, "dipole", velocity_factor=1.00)
        default_len = default_result["elements"][0]["length_ft"]
        full_len = full_vf_result["elements"][0]["length_ft"]
        self.assertGreater(full_len, default_len)

    def test_vf_ratio_math(self):
        """With VF=0.90 vs default 0.95, lengths should scale by 0.90/0.95."""
        result_90 = calculate_antenna(14.175, "dipole", velocity_factor=0.90)
        result_95 = calculate_antenna(14.175, "dipole", velocity_factor=0.95)
        ratio = result_90["elements"][0]["length_ft"] / result_95["elements"][0]["length_ft"]
        expected_ratio = 0.90 / 0.95
        self.assertAlmostEqual(ratio, expected_ratio, places=3)


class TestInputValidation(unittest.TestCase):
    """Edge cases and bad inputs."""

    def test_zero_frequency(self):
        result = calculate_antenna(0, "dipole")
        self.assertIsNotNone(result["error"])

    def test_negative_frequency(self):
        result = calculate_antenna(-14.0, "dipole")
        self.assertIsNotNone(result["error"])

    def test_unknown_antenna_type(self):
        result = calculate_antenna(14.175, "yagi")
        self.assertIsNotNone(result["error"])

    def test_vf_too_low(self):
        result = calculate_antenna(14.175, "dipole", velocity_factor=0.10)
        self.assertIsNotNone(result["error"])

    def test_vf_too_high(self):
        result = calculate_antenna(14.175, "dipole", velocity_factor=1.50)
        self.assertIsNotNone(result["error"])

    def test_none_frequency(self):
        result = calculate_antenna(None, "dipole")
        self.assertIsNotNone(result["error"])


class TestMetricOutput(unittest.TestCase):
    """Ensure metric values are present and consistent."""

    def test_metric_present(self):
        result = calculate_antenna(14.175, "dipole")
        for elem in result["elements"]:
            self.assertIn("length_m", elem)
            self.assertIn("metric", elem)
            self.assertGreater(elem["length_m"], 0)

    def test_metric_feet_consistency(self):
        """Metric should equal feet × 0.3048."""
        result = calculate_antenna(14.175, "dipole")
        for elem in result["elements"]:
            expected_m = round(elem["length_ft"] * 0.3048, 3)
            self.assertAlmostEqual(elem["length_m"], expected_m, places=2)


class TestResultStructure(unittest.TestCase):
    """Verify all expected keys exist in results."""

    def test_all_keys_present(self):
        result = calculate_antenna(14.175, "dipole")
        expected_keys = [
            "antenna_type", "antenna_type_key", "frequency_mhz",
            "frequency_display", "velocity_factor", "wavelength_ft",
            "wavelength_m", "wavelength_imperial", "wavelength_metric",
            "elements", "notes", "error",
        ]
        for key in expected_keys:
            self.assertIn(key, result, f"Missing key: {key}")

    def test_element_keys(self):
        result = calculate_antenna(14.175, "dipole")
        for elem in result["elements"]:
            for key in ["label", "length_ft", "length_m", "imperial", "metric"]:
                self.assertIn(key, elem, f"Missing element key: {key}")


class TestDataIntegrity(unittest.TestCase):
    """Verify static data structures are consistent."""

    def test_all_choices_in_types(self):
        """Every choice key should map to ANTENNA_TYPES."""
        for key, label in ANTENNA_TYPE_CHOICES:
            self.assertIn(key, ANTENNA_TYPES, f"Choice '{key}' not in ANTENNA_TYPES")

    def test_all_types_in_choices(self):
        """Every ANTENNA_TYPES key should appear in ANTENNA_TYPE_CHOICES."""
        choice_keys = {k for k, _ in ANTENNA_TYPE_CHOICES}
        for key in ANTENNA_TYPES:
            self.assertIn(key, choice_keys, f"Type '{key}' not in ANTENNA_TYPE_CHOICES")

    def test_quick_picks_valid(self):
        """Every quick-pick frequency should be > 0."""
        for qp in QUICK_PICK_FREQUENCIES:
            self.assertGreater(qp["freq"], 0)
            self.assertTrue(len(qp["band"]) > 0)
            self.assertTrue(len(qp["label"]) > 0)

    def test_default_vf_in_valid_range(self):
        for key, info in ANTENNA_TYPES.items():
            vf = info["default_vf"]
            self.assertGreaterEqual(vf, 0.50, f"{key}: default VF too low")
            self.assertLessEqual(vf, 1.00, f"{key}: default VF too high")


class TestAllAntennaTypes(unittest.TestCase):
    """Run every antenna type through the calculator to ensure no crashes."""

    def test_all_types_at_146mhz(self):
        for key, _ in ANTENNA_TYPE_CHOICES:
            result = calculate_antenna(146.0, key)
            self.assertIsNone(
                result["error"],
                f"Antenna type '{key}' returned error: {result.get('error')}",
            )
            self.assertGreater(
                len(result["elements"]), 0,
                f"Antenna type '{key}' returned no elements.",
            )

    def test_all_types_at_7mhz(self):
        for key, _ in ANTENNA_TYPE_CHOICES:
            result = calculate_antenna(7.15, key)
            self.assertIsNone(result["error"])
            self.assertGreater(len(result["elements"]), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
