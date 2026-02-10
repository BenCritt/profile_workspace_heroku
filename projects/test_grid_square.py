"""
Grid Square Converter — standalone test suite.

Run:
    python test_grid_square.py

All tests use the module directly — no Django ORM or HTTP needed.
"""

import sys
import unittest

sys.path.insert(0, ".")
from grid_square_utils import (
    validate_grid_square,
    validate_coordinates,
    grid_to_coordinates,
    coordinates_to_grid,
    zip_to_grid,
    PRECISION_TABLE,
    _format_coordinate,
    _format_dms,
)


# ===================================================================
#  Validation Tests
# ===================================================================

class TestValidateGridSquare(unittest.TestCase):
    """Test grid square input validation and normalization."""

    def test_valid_4_char(self):
        grid, error = validate_grid_square("EN53")
        self.assertIsNone(error)
        self.assertEqual(grid, "EN53")

    def test_valid_6_char(self):
        grid, error = validate_grid_square("EN53dj")
        self.assertIsNone(error)
        self.assertEqual(grid, "EN53dj")

    def test_valid_8_char(self):
        grid, error = validate_grid_square("EN53dj27")
        self.assertIsNone(error)
        self.assertEqual(grid, "EN53dj27")

    def test_normalizes_case(self):
        """Field should uppercase, subsquare should lowercase."""
        grid, error = validate_grid_square("en53DJ")
        self.assertIsNone(error)
        self.assertEqual(grid, "EN53dj")

    def test_normalizes_8_char_case(self):
        grid, error = validate_grid_square("en53DJ27")
        self.assertIsNone(error)
        self.assertEqual(grid, "EN53dj27")

    def test_strips_whitespace(self):
        grid, error = validate_grid_square("  EN53dj  ")
        self.assertIsNone(error)
        self.assertEqual(grid, "EN53dj")

    def test_rejects_empty(self):
        _, error = validate_grid_square("")
        self.assertIsNotNone(error)

    def test_rejects_none(self):
        _, error = validate_grid_square(None)
        self.assertIsNotNone(error)

    def test_rejects_odd_length(self):
        _, error = validate_grid_square("EN53d")
        self.assertIsNotNone(error)

    def test_rejects_3_char(self):
        _, error = validate_grid_square("EN5")
        self.assertIsNotNone(error)

    def test_rejects_field_out_of_range(self):
        """Field letters must be A–R (not S or beyond)."""
        _, error = validate_grid_square("SN53")
        self.assertIsNotNone(error)

    def test_rejects_subsquare_out_of_range(self):
        """Subsquare letters must be a–x (not y or z)."""
        _, error = validate_grid_square("EN53yz")
        self.assertIsNotNone(error)

    def test_accepts_boundary_field_AR(self):
        """AR is the maximum valid field (A=0, R=17 for both axes)."""
        grid, error = validate_grid_square("RR99")
        self.assertIsNone(error)

    def test_accepts_boundary_field_AA(self):
        grid, error = validate_grid_square("AA00")
        self.assertIsNone(error)


class TestValidateCoordinates(unittest.TestCase):
    """Test coordinate input validation."""

    def test_valid(self):
        self.assertIsNone(validate_coordinates(43.0, -89.0))

    def test_lat_too_high(self):
        self.assertIsNotNone(validate_coordinates(91.0, 0.0))

    def test_lat_too_low(self):
        self.assertIsNotNone(validate_coordinates(-91.0, 0.0))

    def test_lon_too_high(self):
        self.assertIsNotNone(validate_coordinates(0.0, 181.0))

    def test_lon_too_low(self):
        self.assertIsNotNone(validate_coordinates(0.0, -181.0))

    def test_none_lat(self):
        self.assertIsNotNone(validate_coordinates(None, 0.0))

    def test_none_lon(self):
        self.assertIsNotNone(validate_coordinates(0.0, None))

    def test_boundary_values(self):
        """Exact boundaries should be valid."""
        self.assertIsNone(validate_coordinates(90.0, 180.0))
        self.assertIsNone(validate_coordinates(-90.0, -180.0))


# ===================================================================
#  Grid → Coordinates (Decode) Tests
# ===================================================================

class TestGridToCoordinates(unittest.TestCase):
    """Test decoding grid squares to lat/lon."""

    def test_madison_wi_4char(self):
        """EN53 should decode to the center of that 2°×1° field+square."""
        result = grid_to_coordinates("EN53")
        self.assertIsNone(result["error"])
        # EN53 spans lon -90 to -88, lat 43 to 44.
        # Center: -89.0, 43.5.
        self.assertAlmostEqual(result["latitude"], 43.5, delta=0.1)
        self.assertAlmostEqual(result["longitude"], -89.0, delta=0.1)

    def test_madison_wi_6char(self):
        """EN53dj should be a more precise location near Madison."""
        result = grid_to_coordinates("EN53dj")
        self.assertIsNone(result["error"])
        # Latitude should be in the 43.x range.
        self.assertGreater(result["latitude"], 43.0)
        self.assertLess(result["latitude"], 44.0)
        # Longitude should be in the -90 to -88 range.
        self.assertGreater(result["longitude"], -90.0)
        self.assertLess(result["longitude"], -88.0)

    def test_returns_bbox(self):
        result = grid_to_coordinates("EN53")
        self.assertIn("bbox", result)
        bbox = result["bbox"]
        self.assertLess(bbox["lat_min"], bbox["lat_max"])
        self.assertLess(bbox["lon_min"], bbox["lon_max"])

    def test_precision_label_4char(self):
        result = grid_to_coordinates("EN53")
        self.assertEqual(result["precision"], "Field + Square")

    def test_precision_label_6char(self):
        result = grid_to_coordinates("EN53dj")
        self.assertEqual(result["precision"], "Subsquare")

    def test_precision_label_8char(self):
        result = grid_to_coordinates("EN53dj27")
        self.assertEqual(result["precision"], "Extended")

    def test_origin_AA00(self):
        """AA00 should decode near -180 lon, -90 lat (South Pacific)."""
        result = grid_to_coordinates("AA00")
        self.assertIsNone(result["error"])
        self.assertAlmostEqual(result["longitude"], -179.0, delta=1.5)
        self.assertAlmostEqual(result["latitude"], -89.5, delta=1.0)

    def test_antimeridian_RR99(self):
        """RR99 should decode near +180 lon, +90 lat."""
        result = grid_to_coordinates("RR99")
        self.assertIsNone(result["error"])
        self.assertAlmostEqual(result["longitude"], 179.0, delta=1.5)
        self.assertAlmostEqual(result["latitude"], 89.5, delta=1.0)

    def test_london_jj00(self):
        """JO01 is near London."""
        result = grid_to_coordinates("JO01")
        self.assertIsNone(result["error"])
        # London is roughly 51.5°N, -0.1°E.
        self.assertAlmostEqual(result["latitude"], 51.5, delta=1.0)
        self.assertAlmostEqual(result["longitude"], -1.0, delta=3.0)

    def test_error_on_invalid(self):
        result = grid_to_coordinates("ZZZZ")
        self.assertIsNotNone(result["error"])

    def test_formatted_displays(self):
        result = grid_to_coordinates("EN53dj")
        self.assertIn("°", result["lat_display"])
        self.assertIn("°", result["lon_display"])


# ===================================================================
#  Coordinates → Grid (Encode) Tests
# ===================================================================

class TestCoordinatesToGrid(unittest.TestCase):
    """Test encoding lat/lon to grid squares."""

    def test_madison_wi(self):
        """Madison, WI (43.07, -89.40) should be in EN53."""
        result = coordinates_to_grid(43.07, -89.40)
        self.assertIsNone(result["error"])
        self.assertTrue(result["grid"].startswith("EN53"))

    def test_precision_4(self):
        result = coordinates_to_grid(43.07, -89.40, precision=4)
        self.assertEqual(len(result["grid"]), 4)
        self.assertEqual(result["grid"], "EN53")

    def test_precision_6(self):
        result = coordinates_to_grid(43.07, -89.40, precision=6)
        self.assertEqual(len(result["grid"]), 6)

    def test_precision_8(self):
        result = coordinates_to_grid(43.07, -89.40, precision=8)
        self.assertEqual(len(result["grid"]), 8)

    def test_returns_all_levels(self):
        """Should return grid_4, grid_6, grid_8 when precision=8."""
        result = coordinates_to_grid(43.07, -89.40, precision=8)
        self.assertTrue(len(result["grid_4"]) == 4)
        self.assertTrue(len(result["grid_6"]) == 6)
        self.assertTrue(len(result["grid_8"]) == 8)
        # grid_6 should start with grid_4.
        self.assertTrue(result["grid_6"].startswith(result["grid_4"]))
        # grid_8 should start with grid_6.
        self.assertTrue(result["grid_8"].startswith(result["grid_6"]))

    def test_new_york(self):
        """New York City (40.71, -74.01) should be in FN20."""
        result = coordinates_to_grid(40.71, -74.01, precision=4)
        self.assertEqual(result["grid"], "FN20")

    def test_tokyo(self):
        """Tokyo (35.68, 139.77) should be in PM95."""
        result = coordinates_to_grid(35.68, 139.77, precision=4)
        self.assertEqual(result["grid"], "PM95")

    def test_sydney(self):
        """Sydney (-33.87, 151.21) should be in QF56."""
        result = coordinates_to_grid(-33.87, 151.21, precision=4)
        self.assertEqual(result["grid"], "QF56")

    def test_south_pole(self):
        """South Pole (-90, 0) should not crash."""
        result = coordinates_to_grid(-90.0, 0.0, precision=4)
        self.assertIsNone(result["error"])
        self.assertEqual(len(result["grid"]), 4)

    def test_north_pole(self):
        """North Pole (90, 0) should not crash."""
        result = coordinates_to_grid(90.0, 0.0, precision=4)
        self.assertIsNone(result["error"])

    def test_antimeridian_positive(self):
        result = coordinates_to_grid(0.0, 180.0, precision=4)
        self.assertIsNone(result["error"])

    def test_antimeridian_negative(self):
        result = coordinates_to_grid(0.0, -180.0, precision=4)
        self.assertIsNone(result["error"])

    def test_error_invalid_lat(self):
        result = coordinates_to_grid(91.0, 0.0)
        self.assertIsNotNone(result["error"])

    def test_error_invalid_lon(self):
        result = coordinates_to_grid(0.0, 181.0)
        self.assertIsNotNone(result["error"])

    def test_default_precision_is_6(self):
        result = coordinates_to_grid(43.07, -89.40)
        self.assertEqual(len(result["grid"]), 6)


# ===================================================================
#  Round-Trip Consistency Tests
# ===================================================================

class TestRoundTrip(unittest.TestCase):
    """Encode → Decode → Encode should produce the same grid square."""

    def _round_trip(self, lat, lon, precision):
        """Encode coords → grid, decode grid → coords, re-encode → grid.
        The two grid strings should be identical."""
        encode1 = coordinates_to_grid(lat, lon, precision=precision)
        grid1 = encode1["grid"]
        decode = grid_to_coordinates(grid1)
        encode2 = coordinates_to_grid(
            decode["latitude"], decode["longitude"], precision=precision
        )
        grid2 = encode2["grid"]
        return grid1, grid2

    def test_round_trip_4char_madison(self):
        g1, g2 = self._round_trip(43.07, -89.40, 4)
        self.assertEqual(g1, g2)

    def test_round_trip_6char_madison(self):
        g1, g2 = self._round_trip(43.07, -89.40, 6)
        self.assertEqual(g1, g2)

    def test_round_trip_8char_madison(self):
        g1, g2 = self._round_trip(43.07, -89.40, 8)
        self.assertEqual(g1, g2)

    def test_round_trip_6char_london(self):
        g1, g2 = self._round_trip(51.5, -0.1, 6)
        self.assertEqual(g1, g2)

    def test_round_trip_6char_tokyo(self):
        g1, g2 = self._round_trip(35.68, 139.77, 6)
        self.assertEqual(g1, g2)

    def test_round_trip_6char_buenos_aires(self):
        g1, g2 = self._round_trip(-34.6, -58.4, 6)
        self.assertEqual(g1, g2)

    def test_round_trip_8char_origin(self):
        """Near the origin of the grid system."""
        g1, g2 = self._round_trip(-89.0, -179.0, 8)
        self.assertEqual(g1, g2)


# ===================================================================
#  ZIP Code Conversion Tests
# ===================================================================

class TestZipToGrid(unittest.TestCase):
    """Test ZIP-to-grid using a mock geocoder."""

    def _mock_get_coordinates(self, zip_code):
        """Return known coordinates for test ZIP codes."""
        known = {
            "53704": (43.0731, -89.4012),   # Madison, WI
            "10001": (40.7484, -73.9967),   # New York, NY
            "90210": (34.0901, -118.4065),  # Beverly Hills, CA
        }
        return known.get(zip_code)

    def test_madison_zip(self):
        result = zip_to_grid("53704", self._mock_get_coordinates)
        self.assertIsNone(result.get("zip_error"))
        self.assertTrue(result["grid"].startswith("EN53"))
        self.assertEqual(result["zip_code"], "53704")

    def test_new_york_zip(self):
        result = zip_to_grid("10001", self._mock_get_coordinates)
        self.assertIsNone(result.get("zip_error"))
        self.assertTrue(result["grid"].startswith("FN30"))

    def test_invalid_zip_format(self):
        result = zip_to_grid("ABCDE", self._mock_get_coordinates)
        self.assertIsNotNone(result["error"])

    def test_too_short_zip(self):
        result = zip_to_grid("123", self._mock_get_coordinates)
        self.assertIsNotNone(result["error"])

    def test_empty_zip(self):
        result = zip_to_grid("", self._mock_get_coordinates)
        self.assertIsNotNone(result["error"])

    def test_unknown_zip(self):
        result = zip_to_grid("00000", self._mock_get_coordinates)
        self.assertIsNotNone(result["error"])

    def test_returns_8_char_precision(self):
        """ZIP lookup always returns 8-character precision."""
        result = zip_to_grid("53704", self._mock_get_coordinates)
        self.assertEqual(len(result["grid"]), 8)


# ===================================================================
#  Formatting Tests
# ===================================================================

class TestFormatting(unittest.TestCase):
    """Test coordinate display formatting."""

    def test_format_coordinate_north(self):
        s = _format_coordinate(43.0731, "lat")
        self.assertIn("N", s)
        self.assertIn("43.0731", s)

    def test_format_coordinate_south(self):
        s = _format_coordinate(-33.87, "lat")
        self.assertIn("S", s)

    def test_format_coordinate_east(self):
        s = _format_coordinate(139.77, "lon")
        self.assertIn("E", s)

    def test_format_coordinate_west(self):
        s = _format_coordinate(-89.40, "lon")
        self.assertIn("W", s)

    def test_format_dms_north(self):
        s = _format_dms(43.0731, "lat")
        self.assertIn("N", s)
        self.assertIn("43°", s)

    def test_format_dms_west(self):
        s = _format_dms(-89.4012, "lon")
        self.assertIn("W", s)
        self.assertIn("89°", s)


# ===================================================================
#  Data Integrity Tests
# ===================================================================

class TestDataIntegrity(unittest.TestCase):
    """Verify static data structures."""

    def test_precision_table_entries(self):
        self.assertEqual(len(PRECISION_TABLE), 3)

    def test_precision_table_keys(self):
        for row in PRECISION_TABLE:
            for key in ["characters", "example", "lon_resolution",
                        "lat_resolution", "approx_area"]:
                self.assertIn(key, row)

    def test_precision_table_examples_valid(self):
        """Each example in the precision table should validate."""
        for row in PRECISION_TABLE:
            grid, error = validate_grid_square(row["example"])
            self.assertIsNone(error, f"Example '{row['example']}' failed validation")


if __name__ == "__main__":
    unittest.main(verbosity=2)
