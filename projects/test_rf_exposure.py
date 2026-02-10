"""
RF Exposure Calculator — standalone test suite.

Run:
    python test_rf_exposure.py

All tests use the module directly — no Django ORM or HTTP needed.
"""

import sys
import math
import unittest

sys.path.insert(0, ".")
from rf_exposure_utils import (
    get_mpe_limit,
    calculate_power_density,
    calculate_min_safe_distance_cm,
    calculate_rf_exposure,
    _dbi_to_numeric,
    _dbd_to_dbi,
    _cm_to_display,
    _format_power_density,
    MODE_DUTY_CYCLES,
    MODE_CHOICES,
    EXAMPLE_SCENARIOS,
    FEET_TO_CM,
    WATTS_TO_MW,
)


# ===================================================================
#  MPE Limit Table Tests (OET Bulletin 65, Table 1)
# ===================================================================

class TestMPELimitsControlled(unittest.TestCase):
    """Verify controlled (occupational) MPE limits."""

    def test_below_3mhz(self):
        """0.3–3 MHz controlled: 100 mW/cm²."""
        self.assertEqual(get_mpe_limit(1.0, "controlled"), 100.0)
        self.assertEqual(get_mpe_limit(0.3, "controlled"), 100.0)
        self.assertAlmostEqual(get_mpe_limit(2.99, "controlled"), 100.0)

    def test_3_to_30mhz(self):
        """3–30 MHz controlled: 900/f²."""
        # At 3 MHz: 900/9 = 100
        self.assertAlmostEqual(get_mpe_limit(3.0, "controlled"), 100.0)
        # At 10 MHz: 900/100 = 9
        self.assertAlmostEqual(get_mpe_limit(10.0, "controlled"), 9.0)
        # At 14.2 MHz: 900/201.64 ≈ 4.464
        self.assertAlmostEqual(get_mpe_limit(14.2, "controlled"), 900.0 / (14.2**2), places=3)

    def test_30_to_300mhz(self):
        """30–300 MHz controlled: 1.0 mW/cm²."""
        self.assertEqual(get_mpe_limit(30.0, "controlled"), 1.0)
        self.assertEqual(get_mpe_limit(146.0, "controlled"), 1.0)
        self.assertEqual(get_mpe_limit(299.0, "controlled"), 1.0)

    def test_300_to_1500mhz(self):
        """300–1500 MHz controlled: f/300."""
        self.assertAlmostEqual(get_mpe_limit(300.0, "controlled"), 1.0)
        self.assertAlmostEqual(get_mpe_limit(900.0, "controlled"), 3.0)
        self.assertAlmostEqual(get_mpe_limit(440.0, "controlled"), 440.0 / 300.0, places=3)

    def test_above_1500mhz(self):
        """1500–100000 MHz controlled: 5.0 mW/cm²."""
        self.assertEqual(get_mpe_limit(1500.0, "controlled"), 5.0)
        self.assertEqual(get_mpe_limit(5800.0, "controlled"), 5.0)


class TestMPELimitsUncontrolled(unittest.TestCase):
    """Verify uncontrolled (general public) MPE limits."""

    def test_below_1_34mhz(self):
        """0.3–1.34 MHz uncontrolled: 100 mW/cm²."""
        self.assertEqual(get_mpe_limit(0.5, "uncontrolled"), 100.0)
        self.assertEqual(get_mpe_limit(1.0, "uncontrolled"), 100.0)

    def test_1_34_to_30mhz(self):
        """1.34–30 MHz uncontrolled: 180/f²."""
        # At 1.34 MHz: 180/1.7956 ≈ 100.25
        limit = get_mpe_limit(1.34, "uncontrolled")
        self.assertAlmostEqual(limit, 180.0 / (1.34**2), places=2)
        # At 14.2 MHz: 180/201.64 ≈ 0.893
        self.assertAlmostEqual(
            get_mpe_limit(14.2, "uncontrolled"), 180.0 / (14.2**2), places=3
        )

    def test_30_to_300mhz(self):
        """30–300 MHz uncontrolled: 0.2 mW/cm²."""
        self.assertEqual(get_mpe_limit(146.0, "uncontrolled"), 0.2)

    def test_300_to_1500mhz(self):
        """300–1500 MHz uncontrolled: f/1500."""
        self.assertAlmostEqual(get_mpe_limit(440.0, "uncontrolled"), 440.0 / 1500.0, places=4)

    def test_above_1500mhz(self):
        """1500–100000 MHz uncontrolled: 1.0 mW/cm²."""
        self.assertEqual(get_mpe_limit(2400.0, "uncontrolled"), 1.0)

    def test_uncontrolled_stricter_than_controlled(self):
        """Uncontrolled limits should be ≤ controlled limits at all test freqs."""
        test_freqs = [1.0, 3.5, 7.15, 14.2, 28.4, 50.0, 146.0, 440.0, 1296.0, 2400.0]
        for f in test_freqs:
            ctrl = get_mpe_limit(f, "controlled")
            unctrl = get_mpe_limit(f, "uncontrolled")
            self.assertLessEqual(unctrl, ctrl,
                f"Uncontrolled limit ({unctrl}) > controlled ({ctrl}) at {f} MHz")


class TestMPELimitsEdgeCases(unittest.TestCase):
    """Edge cases for MPE limit lookup."""

    def test_below_range(self):
        with self.assertRaises(ValueError):
            get_mpe_limit(0.1, "controlled")

    def test_above_range(self):
        with self.assertRaises(ValueError):
            get_mpe_limit(200000, "controlled")

    def test_exact_boundary_0_3(self):
        """0.3 MHz should not raise."""
        get_mpe_limit(0.3, "controlled")
        get_mpe_limit(0.3, "uncontrolled")


# ===================================================================
#  Gain Conversion Tests
# ===================================================================

class TestGainConversions(unittest.TestCase):

    def test_dbi_to_numeric_zero(self):
        """0 dBi = gain of 1 (isotropic)."""
        self.assertAlmostEqual(_dbi_to_numeric(0.0), 1.0, places=4)

    def test_dbi_to_numeric_3db(self):
        """3 dBi ≈ 2× power gain."""
        self.assertAlmostEqual(_dbi_to_numeric(3.0), 2.0, delta=0.05)

    def test_dbi_to_numeric_10db(self):
        """10 dBi = 10× power gain."""
        self.assertAlmostEqual(_dbi_to_numeric(10.0), 10.0, places=2)

    def test_dbd_to_dbi(self):
        """0 dBd = 2.15 dBi (dipole reference)."""
        self.assertAlmostEqual(_dbd_to_dbi(0.0), 2.15, places=2)

    def test_dbd_to_dbi_6dbd(self):
        """6 dBd = 8.15 dBi."""
        self.assertAlmostEqual(_dbd_to_dbi(6.0), 8.15, places=2)


# ===================================================================
#  Power Density Formula Tests
# ===================================================================

class TestPowerDensity(unittest.TestCase):
    """Verify the far-field power density formula S = PG / 4πR²."""

    def test_known_calculation(self):
        """100 W, 2.15 dBi (dipole), 10 ft distance, 100% duty."""
        distance_cm = 10.0 * FEET_TO_CM  # 304.8 cm
        gain_numeric = _dbi_to_numeric(2.15)  # ≈ 1.6415
        expected = (100 * 1000 * gain_numeric) / (4 * math.pi * distance_cm**2)
        actual = calculate_power_density(100, 2.15, distance_cm, 1.0, 0.0)
        self.assertAlmostEqual(actual, expected, places=4)

    def test_duty_cycle_halves_density(self):
        """50% duty should produce half the power density."""
        distance_cm = 500.0
        full = calculate_power_density(100, 2.15, distance_cm, 1.0)
        half = calculate_power_density(100, 2.15, distance_cm, 0.5)
        self.assertAlmostEqual(half, full * 0.5, places=6)

    def test_feed_line_loss_reduces_density(self):
        """3 dB feed loss = half the power density."""
        distance_cm = 500.0
        no_loss = calculate_power_density(100, 2.15, distance_cm, 1.0, 0.0)
        with_loss = calculate_power_density(100, 2.15, distance_cm, 1.0, 3.0)
        self.assertAlmostEqual(with_loss, no_loss * 0.5, delta=0.001)

    def test_zero_distance_returns_inf(self):
        result = calculate_power_density(100, 2.15, 0.0, 1.0)
        self.assertEqual(result, float("inf"))

    def test_inverse_square_law(self):
        """Doubling distance should quarter the power density."""
        d1 = calculate_power_density(100, 2.15, 100.0, 1.0)
        d2 = calculate_power_density(100, 2.15, 200.0, 1.0)
        self.assertAlmostEqual(d1 / d2, 4.0, delta=0.01)


# ===================================================================
#  Minimum Safe Distance Tests
# ===================================================================

class TestMinSafeDistance(unittest.TestCase):

    def test_known_distance(self):
        """Verify min distance formula: R = √(PG / 4πS)."""
        power = 100
        gain_dbi = 2.15
        mpe = 0.2  # uncontrolled at 146 MHz
        gain_numeric = _dbi_to_numeric(gain_dbi)
        expected_cm = math.sqrt(
            (power * 1000 * gain_numeric * 1.0) / (4 * math.pi * mpe)
        )
        actual_cm = calculate_min_safe_distance_cm(power, gain_dbi, mpe, 1.0, 0.0)
        self.assertAlmostEqual(actual_cm, expected_cm, places=2)

    def test_higher_power_larger_distance(self):
        """More power → larger safe distance."""
        d100 = calculate_min_safe_distance_cm(100, 2.15, 1.0, 1.0)
        d1500 = calculate_min_safe_distance_cm(1500, 2.15, 1.0, 1.0)
        self.assertGreater(d1500, d100)

    def test_higher_gain_larger_distance(self):
        """More gain → larger safe distance."""
        d_low = calculate_min_safe_distance_cm(100, 0.0, 1.0, 1.0)
        d_high = calculate_min_safe_distance_cm(100, 12.0, 1.0, 1.0)
        self.assertGreater(d_high, d_low)


# ===================================================================
#  Full Calculation Integration Tests
# ===================================================================

class TestCalculateRFExposure(unittest.TestCase):
    """End-to-end tests of the main calculate_rf_exposure function."""

    def test_100w_20m_ssb_dipole(self):
        """Typical 100W 20m SSB station with a dipole — should pass easily."""
        result = calculate_rf_exposure(
            power_watts=100, gain_value=2.15, gain_reference="dBi",
            frequency_mhz=14.2, distance_value=25, distance_unit="feet",
            mode="ssb",
        )
        self.assertIsNone(result["error"])
        self.assertTrue(result["compliant_uncontrolled"])
        self.assertTrue(result["compliant_controlled"])
        self.assertAlmostEqual(result["duty_cycle"], 0.20)

    def test_1500w_hf_yagi_ssb(self):
        """1500W with a high-gain Yagi — may or may not pass depending on distance."""
        result = calculate_rf_exposure(
            power_watts=1500, gain_value=12.0, gain_reference="dBi",
            frequency_mhz=14.2, distance_value=5, distance_unit="feet",
            mode="ssb",
        )
        self.assertIsNone(result["error"])
        # At 5 feet with 1500W and 12dBi, likely exceeds at least uncontrolled.
        # Min safe distance should be substantial.
        self.assertGreater(result["min_distance_uncontrolled"]["feet"], 5)

    def test_5w_ht_fm(self):
        """5W handheld at 146 MHz — should pass even at close range."""
        result = calculate_rf_exposure(
            power_watts=5, gain_value=0.0, gain_reference="dBi",
            frequency_mhz=146.0, distance_value=1, distance_unit="feet",
            mode="fm",
        )
        self.assertIsNone(result["error"])

    def test_dbd_reference(self):
        """dBd input should be converted to dBi (+2.15)."""
        result = calculate_rf_exposure(
            power_watts=100, gain_value=0.0, gain_reference="dBd",
            frequency_mhz=14.2, distance_value=25, distance_unit="feet",
            mode="ssb",
        )
        self.assertIsNone(result["error"])
        self.assertAlmostEqual(result["gain_dbi"], 2.15, places=2)

    def test_meters_unit(self):
        """Distance in meters should work."""
        result = calculate_rf_exposure(
            power_watts=100, gain_value=2.15, gain_reference="dBi",
            frequency_mhz=14.2, distance_value=10, distance_unit="meters",
            mode="ssb",
        )
        self.assertIsNone(result["error"])
        self.assertAlmostEqual(result["distance"]["meters"], 10.0)

    def test_custom_duty_cycle(self):
        """Custom duty cycle at 50%."""
        result = calculate_rf_exposure(
            power_watts=100, gain_value=2.15, gain_reference="dBi",
            frequency_mhz=14.2, distance_value=25, distance_unit="feet",
            mode="custom", custom_duty_cycle=50,
        )
        self.assertIsNone(result["error"])
        self.assertAlmostEqual(result["duty_cycle"], 0.50)

    def test_feed_line_loss(self):
        """Feed line loss should reduce effective power."""
        no_loss = calculate_rf_exposure(
            power_watts=100, gain_value=2.15, gain_reference="dBi",
            frequency_mhz=14.2, distance_value=25, distance_unit="feet",
            mode="ssb", feed_line_loss_db=0.0,
        )
        with_loss = calculate_rf_exposure(
            power_watts=100, gain_value=2.15, gain_reference="dBi",
            frequency_mhz=14.2, distance_value=25, distance_unit="feet",
            mode="ssb", feed_line_loss_db=3.0,
        )
        self.assertLess(with_loss["power_density"], no_loss["power_density"])
        # 3 dB loss ≈ half power
        self.assertAlmostEqual(with_loss["effective_power_watts"], 50.0, delta=1.0)

    def test_all_modes_work(self):
        """Every mode key should produce a valid result."""
        for mode_key, _ in MODE_CHOICES:
            kwargs = {
                "power_watts": 100, "gain_value": 2.15, "gain_reference": "dBi",
                "frequency_mhz": 14.2, "distance_value": 25, "distance_unit": "feet",
                "mode": mode_key,
            }
            if mode_key == "custom":
                kwargs["custom_duty_cycle"] = 50
            result = calculate_rf_exposure(**kwargs)
            self.assertIsNone(
                result["error"],
                f"Mode '{mode_key}' returned error: {result.get('error')}",
            )


# ===================================================================
#  Input Validation Tests
# ===================================================================

class TestInputValidation(unittest.TestCase):

    def _call(self, **overrides):
        defaults = {
            "power_watts": 100, "gain_value": 2.15, "gain_reference": "dBi",
            "frequency_mhz": 14.2, "distance_value": 25, "distance_unit": "feet",
            "mode": "ssb",
        }
        defaults.update(overrides)
        return calculate_rf_exposure(**defaults)

    def test_zero_power(self):
        result = self._call(power_watts=0)
        self.assertIsNotNone(result["error"])

    def test_negative_power(self):
        result = self._call(power_watts=-50)
        self.assertIsNotNone(result["error"])

    def test_excessive_power(self):
        result = self._call(power_watts=3000)
        self.assertIsNotNone(result["error"])

    def test_zero_frequency(self):
        result = self._call(frequency_mhz=0)
        self.assertIsNotNone(result["error"])

    def test_frequency_below_range(self):
        result = self._call(frequency_mhz=0.1)
        self.assertIsNotNone(result["error"])

    def test_zero_distance(self):
        result = self._call(distance_value=0)
        self.assertIsNotNone(result["error"])

    def test_negative_distance(self):
        result = self._call(distance_value=-5)
        self.assertIsNotNone(result["error"])

    def test_none_gain(self):
        result = self._call(gain_value=None)
        self.assertIsNotNone(result["error"])

    def test_negative_feed_loss(self):
        result = self._call(feed_line_loss_db=-1)
        self.assertIsNotNone(result["error"])

    def test_custom_mode_without_duty(self):
        result = self._call(mode="custom", custom_duty_cycle=None)
        self.assertIsNotNone(result["error"])

    def test_custom_mode_zero_duty(self):
        result = self._call(mode="custom", custom_duty_cycle=0)
        self.assertIsNotNone(result["error"])


# ===================================================================
#  Formatting Tests
# ===================================================================

class TestFormatting(unittest.TestCase):

    def test_cm_to_display_imperial(self):
        d = _cm_to_display(304.8)  # 10 feet exactly
        self.assertAlmostEqual(d["feet"], 10.0, delta=0.01)
        self.assertIn("10 ft", d["imperial"])

    def test_cm_to_display_metric(self):
        d = _cm_to_display(100.0)  # 1 meter
        self.assertAlmostEqual(d["meters"], 1.0, places=2)

    def test_format_power_density_large(self):
        s = _format_power_density(5.0)
        self.assertIn("5.000", s)
        self.assertIn("mW/cm²", s)

    def test_format_power_density_small(self):
        s = _format_power_density(0.005)
        self.assertIn("mW/cm²", s)

    def test_format_power_density_very_small(self):
        s = _format_power_density(0.0001)
        self.assertIn("mW/cm²", s)


# ===================================================================
#  Data Integrity Tests
# ===================================================================

class TestDataIntegrity(unittest.TestCase):

    def test_all_mode_choices_have_duty(self):
        """Every mode choice key should exist in MODE_DUTY_CYCLES."""
        for key, _ in MODE_CHOICES:
            self.assertIn(key, MODE_DUTY_CYCLES)

    def test_all_duty_cycles_valid(self):
        """Duty cycles should be None (custom) or 0 < d ≤ 1."""
        for key, info in MODE_DUTY_CYCLES.items():
            if key == "custom":
                self.assertIsNone(info["duty"])
            else:
                self.assertGreater(info["duty"], 0.0)
                self.assertLessEqual(info["duty"], 1.0)

    def test_example_scenarios_structure(self):
        for ex in EXAMPLE_SCENARIOS:
            self.assertIn("power", ex)
            self.assertIn("gain", ex)
            self.assertIn("freq", ex)
            self.assertIn("mode", ex)
            self.assertGreater(ex["power"], 0)


# ===================================================================
#  Result Structure Tests
# ===================================================================

class TestResultStructure(unittest.TestCase):

    def test_all_keys_present(self):
        result = calculate_rf_exposure(
            power_watts=100, gain_value=2.15, gain_reference="dBi",
            frequency_mhz=14.2, distance_value=25, distance_unit="feet",
            mode="ssb",
        )
        expected_keys = [
            "compliant_controlled", "compliant_uncontrolled",
            "power_density", "power_density_display",
            "mpe_controlled", "mpe_uncontrolled",
            "mpe_controlled_display", "mpe_uncontrolled_display",
            "margin_controlled_pct", "margin_uncontrolled_pct",
            "min_distance_controlled", "min_distance_uncontrolled",
            "effective_power_watts", "gain_dbi", "gain_display",
            "duty_cycle", "duty_cycle_pct", "mode_label",
            "frequency_mhz", "distance", "error",
        ]
        for key in expected_keys:
            self.assertIn(key, result, f"Missing key: {key}")

    def test_distance_dict_keys(self):
        result = calculate_rf_exposure(
            power_watts=100, gain_value=2.15, gain_reference="dBi",
            frequency_mhz=14.2, distance_value=25, distance_unit="feet",
            mode="ssb",
        )
        for dist_key in ["distance", "min_distance_controlled", "min_distance_uncontrolled"]:
            d = result[dist_key]
            for k in ["feet", "meters", "imperial", "metric"]:
                self.assertIn(k, d, f"Missing '{k}' in result['{dist_key}']")


if __name__ == "__main__":
    unittest.main(verbosity=2)
