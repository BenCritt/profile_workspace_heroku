"""
Coax Cable Loss Calculator — standalone test suite.

Run:
    python test_coax_calculator.py

All tests use the module directly — no Django ORM or HTTP needed.
"""

import sys
import math
import unittest

sys.path.insert(0, ".")
from coax_calculator_utils import (
    interpolate_loss_per_100ft,
    calculate_matched_loss,
    calculate_mismatch_loss,
    calculate_coax_loss,
    _length_to_display,
    _format_db,
    _format_watts,
    _format_percent,
    CABLE_DATABASE,
    CABLE_CHOICES,
    LENGTH_UNIT_CHOICES,
    STANDARD_FREQS_MHZ,
    EXAMPLE_SCENARIOS,
    FEET_PER_METER,
    METERS_PER_FOOT,
)


# ===================================================================
#  Cable Database Integrity Tests
# ===================================================================

class TestCableDatabaseIntegrity(unittest.TestCase):
    """Verify the cable database is complete and well-formed."""

    def test_all_cable_choices_in_database(self):
        """Every cable choice key should exist in CABLE_DATABASE."""
        for key, _ in CABLE_CHOICES:
            self.assertIn(key, CABLE_DATABASE, f"Cable '{key}' missing from database")

    def test_all_database_entries_in_choices(self):
        """Every database key should appear in CABLE_CHOICES."""
        choice_keys = {k for k, _ in CABLE_CHOICES}
        for key in CABLE_DATABASE:
            self.assertIn(key, choice_keys, f"Database key '{key}' missing from CABLE_CHOICES")

    def test_all_cables_have_required_fields(self):
        """Each cable must have label, impedance, loss_per_100ft, and note."""
        for key, cable in CABLE_DATABASE.items():
            self.assertIn("label", cable, f"{key} missing 'label'")
            self.assertIn("impedance", cable, f"{key} missing 'impedance'")
            self.assertIn("loss_per_100ft", cable, f"{key} missing 'loss_per_100ft'")
            self.assertIn("note", cable, f"{key} missing 'note'")

    def test_loss_table_length_matches_freqs(self):
        """Each cable's loss table must have one entry per standard frequency."""
        expected_len = len(STANDARD_FREQS_MHZ)
        for key, cable in CABLE_DATABASE.items():
            self.assertEqual(
                len(cable["loss_per_100ft"]), expected_len,
                f"{key} has {len(cable['loss_per_100ft'])} entries, expected {expected_len}"
            )

    def test_loss_values_positive(self):
        """All loss-per-100ft values should be positive."""
        for key, cable in CABLE_DATABASE.items():
            for i, loss in enumerate(cable["loss_per_100ft"]):
                self.assertGreater(
                    loss, 0.0,
                    f"{key} has non-positive loss {loss} at freq index {i}"
                )

    def test_loss_values_monotonically_increasing(self):
        """Loss should generally increase with frequency for each cable."""
        for key, cable in CABLE_DATABASE.items():
            losses = cable["loss_per_100ft"]
            for i in range(1, len(losses)):
                self.assertGreaterEqual(
                    losses[i], losses[i - 1],
                    f"{key}: loss at {STANDARD_FREQS_MHZ[i]} MHz ({losses[i]}) "
                    f"< loss at {STANDARD_FREQS_MHZ[i-1]} MHz ({losses[i-1]})"
                )

    def test_impedance_values(self):
        """Impedance should be 50 or 75 ohms."""
        for key, cable in CABLE_DATABASE.items():
            self.assertIn(cable["impedance"], (50, 75),
                f"{key} has unexpected impedance: {cable['impedance']}")

    def test_rg6_is_75_ohm(self):
        """RG-6 should be flagged as 75-ohm."""
        self.assertEqual(CABLE_DATABASE["rg6"]["impedance"], 75)

    def test_cable_count(self):
        """Should have at least 10 cable types."""
        self.assertGreaterEqual(len(CABLE_DATABASE), 10)


# ===================================================================
#  Interpolation Tests
# ===================================================================

class TestInterpolation(unittest.TestCase):
    """Verify log-log interpolation of cable loss."""

    def test_exact_frequency_match(self):
        """At a standard test frequency, should return the exact table value."""
        for key in CABLE_DATABASE:
            for i, freq in enumerate(STANDARD_FREQS_MHZ):
                expected = CABLE_DATABASE[key]["loss_per_100ft"][i]
                actual = interpolate_loss_per_100ft(key, freq)
                self.assertAlmostEqual(
                    actual, expected, places=4,
                    msg=f"{key} at {freq} MHz: got {actual}, expected {expected}"
                )

    def test_interpolation_between_points(self):
        """Interpolated value should fall between the two bracketing values."""
        for key in CABLE_DATABASE:
            losses = CABLE_DATABASE[key]["loss_per_100ft"]
            # Test at 25 MHz (between 10 and 50).
            result = interpolate_loss_per_100ft(key, 25.0)
            idx_10 = STANDARD_FREQS_MHZ.index(10)
            idx_50 = STANDARD_FREQS_MHZ.index(50)
            self.assertGreaterEqual(result, losses[idx_10],
                f"{key} at 25 MHz: {result} < loss at 10 MHz ({losses[idx_10]})")
            self.assertLessEqual(result, losses[idx_50],
                f"{key} at 25 MHz: {result} > loss at 50 MHz ({losses[idx_50]})")

    def test_interpolation_at_14_2_mhz(self):
        """14.2 MHz (20m band center) should interpolate between 10 and 50 MHz."""
        result = interpolate_loss_per_100ft("rg213", 14.2)
        loss_10 = CABLE_DATABASE["rg213"]["loss_per_100ft"][1]  # 0.4
        loss_50 = CABLE_DATABASE["rg213"]["loss_per_100ft"][2]  # 0.8
        self.assertGreater(result, loss_10)
        self.assertLess(result, loss_50)

    def test_interpolation_at_146_mhz(self):
        """146 MHz (2m band) should interpolate between 100 and 150 MHz."""
        result = interpolate_loss_per_100ft("lmr400", 146.0)
        loss_100 = CABLE_DATABASE["lmr400"]["loss_per_100ft"][3]  # 0.7
        loss_150 = CABLE_DATABASE["lmr400"]["loss_per_100ft"][4]  # 0.9
        self.assertGreaterEqual(result, loss_100)
        self.assertLessEqual(result, loss_150)

    def test_below_minimum_frequency(self):
        """Frequency ≤ 1 MHz should return the 1 MHz table value."""
        for key in CABLE_DATABASE:
            expected = CABLE_DATABASE[key]["loss_per_100ft"][0]
            self.assertAlmostEqual(
                interpolate_loss_per_100ft(key, 0.5), expected, places=4
            )
            self.assertAlmostEqual(
                interpolate_loss_per_100ft(key, 1.0), expected, places=4
            )

    def test_above_maximum_frequency(self):
        """Frequency ≥ 1500 MHz should return the 1500 MHz table value."""
        for key in CABLE_DATABASE:
            expected = CABLE_DATABASE[key]["loss_per_100ft"][-1]
            self.assertAlmostEqual(
                interpolate_loss_per_100ft(key, 2000.0), expected, places=4
            )
            self.assertAlmostEqual(
                interpolate_loss_per_100ft(key, 1500.0), expected, places=4
            )

    def test_unknown_cable_raises(self):
        """Unknown cable key should raise ValueError."""
        with self.assertRaises(ValueError):
            interpolate_loss_per_100ft("nonexistent_cable", 100.0)

    def test_log_log_accuracy_rg58_at_300mhz(self):
        """Verify log-log interpolation math for a known midpoint."""
        # Between 220 MHz (3.1 dB) and 440 MHz (4.5 dB) for RG-58.
        freq = 300.0
        f_low, f_high = 220.0, 440.0
        loss_low, loss_high = 3.1, 4.5

        log_f = math.log(freq)
        t = (log_f - math.log(f_low)) / (math.log(f_high) - math.log(f_low))
        expected = math.exp(math.log(loss_low) + t * (math.log(loss_high) - math.log(loss_low)))

        actual = interpolate_loss_per_100ft("rg58", 300.0)
        self.assertAlmostEqual(actual, expected, places=4)


# ===================================================================
#  Matched Loss Calculation Tests
# ===================================================================

class TestMatchedLoss(unittest.TestCase):
    """Verify matched-line loss calculations."""

    def test_100ft_at_table_frequency(self):
        """100 ft at a table frequency should equal the table value."""
        expected = CABLE_DATABASE["rg213"]["loss_per_100ft"][3]  # 100 MHz: 1.2 dB
        actual = calculate_matched_loss("rg213", 100.0, 100.0, "feet")
        self.assertAlmostEqual(actual, expected, places=4)

    def test_50ft_is_half_of_100ft(self):
        """50 ft should produce half the loss of 100 ft."""
        loss_100 = calculate_matched_loss("rg213", 100.0, 100.0, "feet")
        loss_50 = calculate_matched_loss("rg213", 100.0, 50.0, "feet")
        self.assertAlmostEqual(loss_50, loss_100 / 2.0, places=4)

    def test_200ft_is_double_100ft(self):
        """200 ft should produce double the loss of 100 ft."""
        loss_100 = calculate_matched_loss("lmr400", 440.0, 100.0, "feet")
        loss_200 = calculate_matched_loss("lmr400", 440.0, 200.0, "feet")
        self.assertAlmostEqual(loss_200, loss_100 * 2.0, places=4)

    def test_meters_conversion(self):
        """30.48 meters should equal 100 feet of loss."""
        loss_ft = calculate_matched_loss("rg58", 146.0, 100.0, "feet")
        loss_m = calculate_matched_loss("rg58", 146.0, 30.48, "meters")
        self.assertAlmostEqual(loss_ft, loss_m, places=2)

    def test_very_short_run(self):
        """1 ft run should produce very small loss."""
        loss = calculate_matched_loss("rg213", 14.2, 1.0, "feet")
        self.assertLess(loss, 0.1)
        self.assertGreater(loss, 0.0)

    def test_very_long_run(self):
        """1000 ft of RG-174 at 440 MHz should produce substantial loss."""
        loss = calculate_matched_loss("rg174", 440.0, 1000.0, "feet")
        self.assertGreater(loss, 50.0)  # 7.4 dB/100ft × 10 = 74 dB

    def test_higher_frequency_more_loss(self):
        """Same cable and length at higher frequency should have more loss."""
        loss_hf = calculate_matched_loss("lmr400", 14.2, 100.0, "feet")
        loss_uhf = calculate_matched_loss("lmr400", 440.0, 100.0, "feet")
        self.assertGreater(loss_uhf, loss_hf)

    def test_better_cable_less_loss(self):
        """LMR-400 should have less loss than RG-58 at same freq/length."""
        loss_rg58 = calculate_matched_loss("rg58", 146.0, 100.0, "feet")
        loss_lmr400 = calculate_matched_loss("lmr400", 146.0, 100.0, "feet")
        self.assertLess(loss_lmr400, loss_rg58)


# ===================================================================
#  SWR Mismatch Loss Tests
# ===================================================================

class TestMismatchLoss(unittest.TestCase):
    """Verify SWR mismatch loss formula."""

    def test_swr_1_0_no_loss(self):
        """SWR 1.0 (perfect match) should produce zero mismatch loss."""
        self.assertAlmostEqual(calculate_mismatch_loss(1.0), 0.0, places=6)

    def test_swr_none_no_loss(self):
        """SWR None should produce zero mismatch loss."""
        self.assertAlmostEqual(calculate_mismatch_loss(None), 0.0, places=6)

    def test_swr_below_1_no_loss(self):
        """SWR below 1.0 should produce zero mismatch loss."""
        self.assertAlmostEqual(calculate_mismatch_loss(0.5), 0.0, places=6)

    def test_swr_2_0_known_value(self):
        """SWR 2.0:1 should produce ~0.512 dB mismatch loss."""
        # ρ = (2-1)/(2+1) = 1/3, ρ² = 1/9
        # loss = -10 * log10(1 - 1/9) = -10 * log10(8/9) ≈ 0.512 dB
        expected = -10.0 * math.log10(1.0 - (1.0 / 9.0))
        actual = calculate_mismatch_loss(2.0)
        self.assertAlmostEqual(actual, expected, places=3)
        self.assertAlmostEqual(actual, 0.512, delta=0.01)

    def test_swr_3_0_known_value(self):
        """SWR 3.0:1 should produce ~1.25 dB mismatch loss."""
        # ρ = (3-1)/(3+1) = 0.5, ρ² = 0.25
        # loss = -10 * log10(0.75) ≈ 1.249 dB
        expected = -10.0 * math.log10(1.0 - 0.25)
        actual = calculate_mismatch_loss(3.0)
        self.assertAlmostEqual(actual, expected, places=3)

    def test_swr_1_5_moderate(self):
        """SWR 1.5:1 should produce a small but nonzero mismatch loss."""
        loss = calculate_mismatch_loss(1.5)
        self.assertGreater(loss, 0.0)
        self.assertLess(loss, 0.5)  # Should be ~0.177 dB

    def test_swr_10_0_high(self):
        """SWR 10.0 should produce significant mismatch loss."""
        loss = calculate_mismatch_loss(10.0)
        self.assertGreater(loss, 2.0)

    def test_swr_increases_with_swr(self):
        """Higher SWR should always produce more mismatch loss."""
        swr_values = [1.1, 1.5, 2.0, 3.0, 5.0, 10.0]
        losses = [calculate_mismatch_loss(s) for s in swr_values]
        for i in range(1, len(losses)):
            self.assertGreater(losses[i], losses[i - 1],
                f"Loss at SWR {swr_values[i]} not > SWR {swr_values[i-1]}")

    def test_swr_infinity_returns_inf(self):
        """Extremely high SWR (infinite reflection) should return inf."""
        # SWR = infinity means ρ = 1.0, ρ² = 1.0, log10(0) = -inf
        # In practice, very high SWR approaches this.
        loss = calculate_mismatch_loss(1e10)
        # ρ approaches 1, so loss approaches infinity.
        self.assertGreater(loss, 30.0)


# ===================================================================
#  Main Calculation Engine Tests
# ===================================================================

class TestCalculateCoaxLoss(unittest.TestCase):
    """Verify the main calculate_coax_loss() function."""

    def _call(self, **overrides):
        defaults = {
            "cable_type": "rg213",
            "frequency_mhz": 146.0,
            "length_value": 100.0,
            "length_unit": "feet",
            "power_watts": None,
            "swr": None,
        }
        defaults.update(overrides)
        return calculate_coax_loss(**defaults)

    def test_basic_calculation_no_error(self):
        """Basic call should return no error."""
        result = self._call()
        self.assertIsNone(result["error"])

    def test_cable_label_populated(self):
        result = self._call()
        self.assertEqual(result["cable_label"], "RG-8 / RG-213")

    def test_impedance_warning_for_rg6(self):
        """RG-6 (75-ohm) should trigger impedance warning."""
        result = self._call(cable_type="rg6")
        self.assertTrue(result["impedance_warning"])

    def test_no_impedance_warning_for_50_ohm(self):
        """50-ohm cables should not trigger impedance warning."""
        result = self._call(cable_type="lmr400")
        self.assertFalse(result["impedance_warning"])

    def test_matched_loss_is_positive(self):
        result = self._call()
        self.assertGreater(result["matched_loss_db"], 0.0)

    def test_mismatch_loss_zero_without_swr(self):
        result = self._call(swr=None)
        self.assertAlmostEqual(result["mismatch_loss_db"], 0.0)

    def test_mismatch_loss_zero_at_swr_1(self):
        result = self._call(swr=1.0)
        self.assertAlmostEqual(result["mismatch_loss_db"], 0.0)

    def test_mismatch_loss_positive_with_swr(self):
        result = self._call(swr=2.0)
        self.assertGreater(result["mismatch_loss_db"], 0.0)

    def test_total_loss_is_sum(self):
        """Total loss should equal matched + mismatch."""
        result = self._call(swr=2.5)
        expected = result["matched_loss_db"] + result["mismatch_loss_db"]
        self.assertAlmostEqual(result["total_loss_db"], expected, places=3)

    def test_efficiency_100ft_lmr400_146mhz(self):
        """100 ft LMR-400 at 146 MHz should be quite efficient."""
        result = self._call(cable_type="lmr400", frequency_mhz=146.0)
        self.assertGreater(result["efficiency_pct"], 75.0)

    def test_efficiency_decreases_with_length(self):
        short = self._call(length_value=25.0)
        long = self._call(length_value=200.0)
        self.assertGreater(short["efficiency_pct"], long["efficiency_pct"])

    def test_meters_input(self):
        """Meters input should convert correctly."""
        result = self._call(length_value=30.0, length_unit="meters")
        self.assertIsNone(result["error"])
        self.assertAlmostEqual(result["length"]["meters"], 30.0, delta=0.1)

    def test_power_calculations_present(self):
        """When power is provided, power results should be populated."""
        result = self._call(power_watts=100.0)
        self.assertIsNotNone(result["power_in_watts"])
        self.assertIsNotNone(result["power_out_watts"])
        self.assertIsNotNone(result["power_lost_watts"])
        self.assertIsNotNone(result["power_out_display"])
        self.assertIsNotNone(result["power_lost_display"])

    def test_power_calculations_absent(self):
        """When power is not provided, power results should be None."""
        result = self._call(power_watts=None)
        self.assertIsNone(result["power_out_watts"])
        self.assertIsNone(result["power_lost_watts"])

    def test_power_out_plus_lost_equals_in(self):
        """Power out + power lost should equal power in."""
        result = self._call(power_watts=100.0, swr=2.0)
        total = result["power_out_watts"] + result["power_lost_watts"]
        self.assertAlmostEqual(total, 100.0, delta=0.01)

    def test_power_out_matches_efficiency(self):
        """Power out should match efficiency × power in."""
        result = self._call(power_watts=100.0)
        expected_out = 100.0 * (result["efficiency_pct"] / 100.0)
        self.assertAlmostEqual(result["power_out_watts"], expected_out, delta=0.1)

    def test_3db_loss_halves_power(self):
        """If total loss is close to 3 dB, power out should be close to half."""
        # Find a cable/freq/length combo that gives ~3 dB.
        # RG-58 at 440 MHz, ~67 ft → 4.5 dB/100ft × 0.67 ≈ 3.0 dB
        result = calculate_coax_loss(
            cable_type="rg58", frequency_mhz=440.0,
            length_value=67.0, length_unit="feet",
            power_watts=100.0, swr=None,
        )
        # Total loss should be ~3 dB, power out ~50 W.
        self.assertAlmostEqual(result["total_loss_db"], 3.0, delta=0.2)
        self.assertAlmostEqual(result["power_out_watts"], 50.0, delta=5.0)

    def test_all_cables_produce_valid_results(self):
        """Every cable in the database should produce a valid result."""
        for key in CABLE_DATABASE:
            result = self._call(cable_type=key)
            self.assertIsNone(
                result["error"],
                f"Cable '{key}' returned error: {result.get('error')}"
            )
            self.assertGreater(result["matched_loss_db"], 0.0)
            self.assertGreater(result["efficiency_pct"], 0.0)
            self.assertLessEqual(result["efficiency_pct"], 100.0)


# ===================================================================
#  Input Validation Tests
# ===================================================================

class TestInputValidation(unittest.TestCase):

    def _call(self, **overrides):
        defaults = {
            "cable_type": "rg213",
            "frequency_mhz": 146.0,
            "length_value": 100.0,
            "length_unit": "feet",
            "power_watts": None,
            "swr": None,
        }
        defaults.update(overrides)
        return calculate_coax_loss(**defaults)

    def test_unknown_cable_type(self):
        result = self._call(cable_type="nonexistent")
        self.assertIsNotNone(result["error"])

    def test_none_cable_type(self):
        result = self._call(cable_type=None)
        self.assertIsNotNone(result["error"])

    def test_zero_frequency(self):
        result = self._call(frequency_mhz=0)
        self.assertIsNotNone(result["error"])

    def test_negative_frequency(self):
        result = self._call(frequency_mhz=-10)
        self.assertIsNotNone(result["error"])

    def test_frequency_below_range(self):
        result = self._call(frequency_mhz=0.5)
        self.assertIsNotNone(result["error"])

    def test_frequency_above_range(self):
        result = self._call(frequency_mhz=5000)
        self.assertIsNotNone(result["error"])

    def test_zero_length(self):
        result = self._call(length_value=0)
        self.assertIsNotNone(result["error"])

    def test_negative_length(self):
        result = self._call(length_value=-50)
        self.assertIsNotNone(result["error"])

    def test_invalid_length_unit(self):
        result = self._call(length_unit="cubits")
        self.assertIsNotNone(result["error"])

    def test_negative_power(self):
        result = self._call(power_watts=-100)
        self.assertIsNotNone(result["error"])

    def test_swr_below_1(self):
        result = self._call(swr=0.5)
        self.assertIsNotNone(result["error"])

    def test_swr_above_20(self):
        result = self._call(swr=25.0)
        self.assertIsNotNone(result["error"])

    def test_frequency_at_lower_boundary(self):
        """Frequency exactly at 1.0 MHz should be accepted."""
        result = self._call(frequency_mhz=1.0)
        self.assertIsNone(result["error"])

    def test_frequency_at_upper_boundary(self):
        """Frequency exactly at 3000.0 MHz should be accepted."""
        result = self._call(frequency_mhz=3000.0)
        self.assertIsNone(result["error"])

    def test_swr_exactly_1(self):
        """SWR exactly 1.0 should be accepted with zero mismatch."""
        result = self._call(swr=1.0)
        self.assertIsNone(result["error"])
        self.assertAlmostEqual(result["mismatch_loss_db"], 0.0)

    def test_swr_exactly_20(self):
        """SWR exactly 20.0 should be accepted."""
        result = self._call(swr=20.0)
        self.assertIsNone(result["error"])

    def test_zero_power_accepted(self):
        """Power of 0 watts should be accepted (no power calcs shown)."""
        result = self._call(power_watts=0.0)
        self.assertIsNone(result["error"])
        # Power calcs should be None since power_watts is 0.
        self.assertIsNone(result["power_out_watts"])


# ===================================================================
#  Formatting Tests
# ===================================================================

class TestFormatting(unittest.TestCase):

    def test_length_to_display_100ft(self):
        d = _length_to_display(100.0)
        self.assertAlmostEqual(d["feet"], 100.0, delta=0.01)
        self.assertIn("100", d["imperial"])
        self.assertIn("ft", d["imperial"])

    def test_length_to_display_metric(self):
        d = _length_to_display(100.0)
        self.assertAlmostEqual(d["meters"], 30.48, delta=0.01)
        self.assertIn("m", d["metric"])

    def test_length_to_display_short(self):
        d = _length_to_display(0.5)
        self.assertIn("in", d["imperial"])

    def test_format_db(self):
        self.assertIn("3.50", _format_db(3.5))
        self.assertIn("dB", _format_db(3.5))

    def test_format_db_infinity(self):
        self.assertIn("∞", _format_db(float("inf")))

    def test_format_watts_large(self):
        s = _format_watts(75.5)
        self.assertIn("75.50", s)
        self.assertIn("W", s)

    def test_format_watts_small(self):
        s = _format_watts(0.05)
        self.assertIn("mW", s)

    def test_format_percent(self):
        self.assertEqual(_format_percent(85.3), "85.3%")


# ===================================================================
#  Result Structure Tests
# ===================================================================

class TestResultStructure(unittest.TestCase):

    def test_all_keys_present_without_power(self):
        result = calculate_coax_loss(
            cable_type="rg213", frequency_mhz=146.0,
            length_value=100.0, length_unit="feet",
        )
        expected_keys = [
            "cable_label", "cable_impedance", "cable_note", "impedance_warning",
            "frequency_mhz", "length",
            "loss_per_100ft", "loss_per_100ft_display",
            "matched_loss_db", "matched_loss_display",
            "swr", "mismatch_loss_db", "mismatch_loss_display",
            "total_loss_db", "total_loss_display",
            "efficiency_pct", "efficiency_display",
            "power_in_watts", "power_lost_watts", "power_lost_display",
            "power_out_watts", "power_out_display",
            "error",
        ]
        for key in expected_keys:
            self.assertIn(key, result, f"Missing key: {key}")

    def test_length_dict_keys(self):
        result = calculate_coax_loss(
            cable_type="rg213", frequency_mhz=146.0,
            length_value=100.0, length_unit="feet",
        )
        for k in ["feet", "meters", "imperial", "metric"]:
            self.assertIn(k, result["length"], f"Missing '{k}' in length dict")

    def test_error_result_is_minimal(self):
        """Error results should contain only the error key."""
        result = calculate_coax_loss(
            cable_type="bad", frequency_mhz=146.0,
            length_value=100.0, length_unit="feet",
        )
        self.assertIsNotNone(result["error"])
        self.assertEqual(len(result), 1)


# ===================================================================
#  Example Scenarios Tests
# ===================================================================

class TestExampleScenarios(unittest.TestCase):

    def test_example_scenarios_structure(self):
        for ex in EXAMPLE_SCENARIOS:
            self.assertIn("cable", ex)
            self.assertIn("freq", ex)
            self.assertIn("length", ex)
            self.assertIn("unit", ex)
            self.assertIn("label", ex)
            self.assertGreater(ex["freq"], 0)
            self.assertGreater(ex["length"], 0)

    def test_example_scenarios_produce_valid_results(self):
        for ex in EXAMPLE_SCENARIOS:
            result = calculate_coax_loss(
                cable_type=ex["cable"],
                frequency_mhz=ex["freq"],
                length_value=ex["length"],
                length_unit=ex["unit"],
            )
            self.assertIsNone(
                result["error"],
                f"Example '{ex['label']}' returned error: {result.get('error')}"
            )


# ===================================================================
#  Edge Case & Integration Tests
# ===================================================================

class TestEdgeCases(unittest.TestCase):

    def test_hardline_lowest_loss(self):
        """Hardline should have the lowest loss of any cable at any frequency."""
        for i, freq in enumerate(STANDARD_FREQS_MHZ):
            hardline_loss = CABLE_DATABASE["ldf4_50a"]["loss_per_100ft"][i]
            for key, cable in CABLE_DATABASE.items():
                if key == "ldf4_50a":
                    continue
                self.assertLessEqual(
                    hardline_loss, cable["loss_per_100ft"][i],
                    f"Hardline loss ({hardline_loss}) > {key} ({cable['loss_per_100ft'][i]}) "
                    f"at {freq} MHz"
                )

    def test_rg174_highest_loss(self):
        """RG-174 should have the highest loss of any cable."""
        for i, freq in enumerate(STANDARD_FREQS_MHZ):
            rg174_loss = CABLE_DATABASE["rg174"]["loss_per_100ft"][i]
            for key, cable in CABLE_DATABASE.items():
                if key == "rg174":
                    continue
                self.assertGreaterEqual(
                    rg174_loss, cable["loss_per_100ft"][i],
                    f"RG-174 loss ({rg174_loss}) < {key} ({cable['loss_per_100ft'][i]}) "
                    f"at {freq} MHz"
                )

    def test_frequency_above_table_uses_last_value(self):
        """Frequencies above 1500 MHz should use the 1500 MHz value."""
        result = calculate_coax_loss(
            cable_type="lmr400", frequency_mhz=2400.0,
            length_value=100.0, length_unit="feet",
        )
        expected_loss = CABLE_DATABASE["lmr400"]["loss_per_100ft"][-1]
        self.assertAlmostEqual(result["loss_per_100ft"], expected_loss, places=3)

    def test_swr_with_power(self):
        """SWR + power should reduce power delivered more than matched loss alone."""
        no_swr = calculate_coax_loss(
            cable_type="rg213", frequency_mhz=146.0,
            length_value=100.0, length_unit="feet",
            power_watts=100.0, swr=None,
        )
        with_swr = calculate_coax_loss(
            cable_type="rg213", frequency_mhz=146.0,
            length_value=100.0, length_unit="feet",
            power_watts=100.0, swr=3.0,
        )
        self.assertLess(with_swr["power_out_watts"], no_swr["power_out_watts"])
        self.assertGreater(with_swr["total_loss_db"], no_swr["total_loss_db"])

    def test_conversion_constants(self):
        """Verify feet/meter conversion constants are consistent."""
        self.assertAlmostEqual(FEET_PER_METER * METERS_PER_FOOT, 1.0, places=6)


if __name__ == "__main__":
    unittest.main(verbosity=2)
