# projects/water_bodies.py
#
# Bounding-box definitions for water bodies used as a fallback by
# detect_region() when Nominatim reverse geocoding returns no land result.
#
# The list is sorted smallest-area-first at module load so the most
# specific water body matches before a generic ocean.
#
# IMPORTANT: The lookup in iss_utils.py uses a simple
#   min_lat <= lat <= max_lat AND min_lon <= lon <= max_lon
# check.  Water bodies that cross the antimeridian (±180°) CANNOT be
# represented as a single entry because min_lon > max_lon would make
# the condition always False.  Those are split into "(East)" and
# "(West)" halves that share the same display name.
#
# Changelog (relative to previous version):
#   - FIX:  Ross Sea and Bering Sea split for antimeridian crossing
#           (previously never matched any coordinate).
#   - FIX:  Scotia Sea latitude clamped to actual bounds (~-62 to -54)
#           instead of extending to the equator.
#   - FIX:  Removed duplicate "Okhotsk Sea" / "Sea of Okhotsk" entries;
#           kept one with merged best-fit bounds.
#   - FIX:  Removed duplicate "Sulawesi Sea" / "Celebes Sea"; kept
#           "Celebes Sea" (IHO standard name).
#   - FIX:  Lake Michigan east boundary extended from -86.0 to -84.8.
#   - FIX:  Adriatic Sea south boundary from 40.0 to 39.5.
#   - FIX:  Bismarck Sea north boundary from 3.0 to 0.0 (entirely
#           south of the equator).
#   - FIX:  Gulf of Carpentaria south boundary from -17.0 to -17.8.
#   - FIX:  Gulf of Maine west boundary from -71.0 to -70.5.
#   - FIX:  Drake Passage widened to -68.0 to -56.0 longitude.
#   - FIX:  Bohai Sea tightened to avoid overlapping Beijing/Tianjin land.
#   - FIX:  Bass Strait tightened to -40.5 to -38.5 latitude.

from math import cos, radians

water_bodies = [
    # ------------------------------------------------------------------ #
    #  Straits, passages, and small named features (smallest first)       #
    # ------------------------------------------------------------------ #
    {
        "name": "Jervis Bay",
        "latitude_range": (-35.2, -34.8),
        "longitude_range": (150.65, 150.85),
    },
    {
        "name": "Scotland's Moray Firth",
        "latitude_range": (57.5, 58.0),
        "longitude_range": (-4.0, -2.5),
    },
    {
        "name": "Dover Strait",
        "latitude_range": (50.8, 51.2),
        "longitude_range": (1.0, 2.0),
    },
    {
        "name": "Shetland Isles Waters",
        "latitude_range": (60.0, 61.0),
        "longitude_range": (-1.5, 0.5),
    },
    {
        "name": "Bohuslän Archipelago",
        "latitude_range": (58.0, 59.0),
        "longitude_range": (11.0, 12.0),
    },
    {
        "name": "Tinian Passage",
        "latitude_range": (15.0, 15.5),
        "longitude_range": (145.5, 146.0),
    },
    {
        "name": "Lombok Strait",
        "latitude_range": (-9.0, -8.2),
        "longitude_range": (115.4, 115.9),
    },
    {
        "name": "Kerch Strait",
        "latitude_range": (45.0, 45.5),
        "longitude_range": (36.0, 36.7),
    },
    {
        "name": "Saint George Basin",
        "latitude_range": (57.0, 58.5),
        "longitude_range": (-6.0, -4.5),
    },
    {
        "name": "Seto Inland Sea",
        "latitude_range": (34.0, 34.8),
        "longitude_range": (132.0, 134.5),
    },
    {
        "name": "Tokara Strait",
        "latitude_range": (29.0, 30.0),
        "longitude_range": (129.0, 131.0),
    },
    {
        "name": "Beagle Channel",
        "latitude_range": (-55.0, -54.5),
        "longitude_range": (-70.0, -66.5),
    },
    {
        "name": "Mackenzie Bay",
        "latitude_range": (69.0, 70.0),
        "longitude_range": (-137.0, -133.0),
    },
    {
        "name": "Peel Sound",
        "latitude_range": (72.0, 74.0),
        "longitude_range": (-97.0, -95.0),
    },
    {
        "name": "Salish Sea",
        "latitude_range": (48.0, 49.5),
        "longitude_range": (-123.5, -122.0),
    },
    {
        "name": "Timor Trough",
        "latitude_range": (-10.5, -9.5),
        "longitude_range": (124.5, 127.0),
    },
    {
        "name": "Skagerrak",
        "latitude_range": (57.5, 59.0),
        "longitude_range": (7.0, 11.0),
    },
    {
        "name": "Kattegat",
        "latitude_range": (56.0, 57.8),
        "longitude_range": (10.5, 12.5),
    },
    {
        "name": "Golfo San Matías",
        "latitude_range": (-42.0, -40.5),
        "longitude_range": (-65.5, -63.0),
    },
    {
        "name": "Amundsen Gulf",
        "latitude_range": (69.5, 71.0),
        "longitude_range": (-125.0, -118.0),
    },
    {
        "name": "Carnarvon Basin",
        "latitude_range": (-24.0, -22.0),
        "longitude_range": (112.0, 114.0),
    },
    {
        "name": "Palawan Passage",
        "latitude_range": (10.0, 12.0),
        "longitude_range": (117.5, 119.5),
    },
    {
        "name": "Porcupine Abyssal Plain",
        "latitude_range": (48.0, 50.0),
        "longitude_range": (-16.0, -13.0),
    },
    {
        "name": "Hebrides Basin",
        "latitude_range": (56.0, 59.0),
        "longitude_range": (-9.0, -6.0),
    },
    {
        "name": "Denmark Strait",
        "latitude_range": (65.0, 67.5),
        "longitude_range": (-30.0, -24.0),
    },
    {
        "name": "Luzon Strait",
        "latitude_range": (19.5, 22.0),
        "longitude_range": (120.0, 122.0),
    },
    {
        "name": "Alboran Sea",
        "latitude_range": (35.0, 36.5),
        "longitude_range": (-5.5, -1.0),
    },

    # ------------------------------------------------------------------ #
    #  Great Lakes (individual)                                           #
    # ------------------------------------------------------------------ #
    {
        "name": "Lake Ontario",
        "latitude_range": (43.2, 44.3),
        "longitude_range": (-79.8, -75.7),
    },
    {
        # East boundary extended from -86.0 to -84.8 to include full lake.
        "name": "Lake Michigan",
        "latitude_range": (41.6, 46.1),
        "longitude_range": (-87.8, -84.8),
    },
    {
        "name": "Lake Erie",
        "latitude_range": (41.4, 42.9),
        "longitude_range": (-83.5, -78.8),
    },
    {
        "name": "Lake Huron",
        "latitude_range": (43.0, 46.3),
        "longitude_range": (-84.5, -79.7),
    },
    {
        "name": "Lake Superior",
        "latitude_range": (46.4, 49.0),
        "longitude_range": (-92.2, -84.3),
    },

    # ------------------------------------------------------------------ #
    #  Regional seas, gulfs, and bays                                     #
    # ------------------------------------------------------------------ #
    {
        "name": "D'Urville Sea",
        "latitude_range": (-67.0, -64.0),
        "longitude_range": (135.0, 141.0),
    },
    {
        "name": "Bellona Trough",
        "latitude_range": (-23.0, -20.0),
        "longitude_range": (155.0, 158.0),
    },
    {
        "name": "Liguro-Provençal Basin",
        "latitude_range": (41.5, 44.0),
        "longitude_range": (5.0, 10.0),
    },
    {
        "name": "Bellingshausen Sea",
        "latitude_range": (-73.0, -68.0),
        "longitude_range": (-100.0, -72.0),
    },
    {
        "name": "Laptev Abyssal Plain",
        "latitude_range": (76.0, 79.0),
        "longitude_range": (125.0, 140.0),
    },
    {
        # West boundary from -71.0 to -70.5 to avoid clipping into MA coast.
        "name": "Gulf of Maine",
        "latitude_range": (42.0, 45.0),
        "longitude_range": (-70.5, -65.5),
    },
    {
        "name": "Sunda Trench",
        "latitude_range": (-8.0, -5.0),
        "longitude_range": (106.0, 110.0),
    },
    {
        # Tightened to avoid Beijing/Tianjin/Shandong land overlap.
        "name": "Bohai Sea",
        "latitude_range": (37.5, 41.0),
        "longitude_range": (117.5, 122.0),
    },
    {
        "name": "Hudson Strait",
        "latitude_range": (60.0, 63.5),
        "longitude_range": (-78.0, -65.0),
    },
    {
        "name": "Barents Abyssal Plain",
        "latitude_range": (73.0, 75.0),
        "longitude_range": (20.0, 45.0),
    },
    {
        "name": "Gulf of Bothnia",
        "latitude_range": (60.0, 65.8),
        "longitude_range": (17.0, 25.5),
    },
    {
        "name": "Baffin Bay Abyssal Plain",
        "latitude_range": (71.0, 75.0),
        "longitude_range": (-72.0, -60.0),
    },
    {
        "name": "Timor Sea",
        "latitude_range": (-13.0, -9.0),
        "longitude_range": (120.0, 130.0),
    },
    {
        "name": "Chukchi Abyssal Plain",
        "latitude_range": (70.0, 75.0),
        "longitude_range": (-165.0, -155.0),
    },
    {
        "name": "Tyrrhenian Sea",
        "latitude_range": (38.0, 42.0),
        "longitude_range": (9.5, 16.0),
    },
    {
        "name": "Ionian Sea",
        "latitude_range": (35.0, 40.0),
        "longitude_range": (15.0, 22.0),
    },
    {
        "name": "Celebes Sea",
        "latitude_range": (0.0, 7.0),
        "longitude_range": (118.0, 126.0),
    },
    {
        "name": "Beaufort Sea",
        "latitude_range": (69.0, 76.0),
        "longitude_range": (-150.0, -122.0),
    },
    {
        "name": "Aegean Sea",
        "latitude_range": (35.0, 41.0),
        "longitude_range": (23.0, 28.0),
    },
    {
        "name": "Newfoundland Basin",
        "latitude_range": (43.0, 50.0),
        "longitude_range": (-52.0, -44.0),
    },
    {
        # South boundary extended from -17.0 to -17.8.
        "name": "Gulf of Carpentaria",
        "latitude_range": (-17.8, -12.0),
        "longitude_range": (135.0, 142.0),
    },
    {
        "name": "Greenland-Iceland Rise",
        "latitude_range": (63.0, 67.0),
        "longitude_range": (-30.0, -15.0),
    },
    {
        # South boundary from 40.0 to 39.5 to include Strait of Otranto.
        "name": "Adriatic Sea",
        "latitude_range": (39.5, 45.8),
        "longitude_range": (12.0, 20.0),
    },
    {
        "name": "Sulu Sea",
        "latitude_range": (5.0, 12.0),
        "longitude_range": (118.0, 122.0),
    },
    {
        "name": "Banda Sea",
        "latitude_range": (-8.0, -4.0),
        "longitude_range": (123.0, 132.0),
    },
    {
        "name": "Yellow Sea",
        "latitude_range": (33.0, 39.0),
        "longitude_range": (120.0, 126.0),
    },
    {
        # Widened from -65 to -68 W to cover full passage width.
        "name": "Drake Passage",
        "latitude_range": (-62.0, -55.0),
        "longitude_range": (-68.0, -56.0),
    },
    {
        "name": "Scotia Arc",
        "latitude_range": (-61.0, -55.0),
        "longitude_range": (-46.0, -35.0),
    },
    {
        # Fixed: was (-60.0, 0.0) which extended to the equator.
        "name": "Scotia Sea",
        "latitude_range": (-62.0, -54.0),
        "longitude_range": (-50.0, -28.0),
    },
    {
        "name": "Mozambique Basin",
        "latitude_range": (-24.0, -15.0),
        "longitude_range": (35.0, 44.0),
    },
    {
        "name": "Levantine Sea",
        "latitude_range": (30.0, 36.0),
        "longitude_range": (26.0, 36.0),
    },
    {
        # Tightened from -42.5/-38.0 to -40.5/-38.5.
        "name": "Bass Strait",
        "latitude_range": (-40.5, -38.5),
        "longitude_range": (143.0, 150.0),
    },
    {
        "name": "Gulf of Aden",
        "latitude_range": (10.5, 15.5),
        "longitude_range": (43.0, 51.0),
    },
    {
        "name": "Laptev Sea",
        "latitude_range": (70.0, 78.0),
        "longitude_range": (100.0, 140.0),
    },
    {
        "name": "Northwest Passage",
        "latitude_range": (68.0, 75.0),
        "longitude_range": (-110.0, -90.0),
    },
    {
        "name": "Gulf of Thailand",
        "latitude_range": (6.0, 14.0),
        "longitude_range": (99.0, 105.0),
    },
    {
        "name": "Persian Gulf",
        "latitude_range": (24.0, 30.5),
        "longitude_range": (47.5, 56.5),
    },
    {
        "name": "Solomon Sea",
        "latitude_range": (-12.0, -5.0),
        "longitude_range": (149.0, 161.0),
    },
    {
        "name": "Gulf of California",
        "latitude_range": (23.0, 31.5),
        "longitude_range": (-114.5, -107.0),
    },
    {
        "name": "Caspian Sea",
        "latitude_range": (36.5, 47.0),
        "longitude_range": (46.8, 54.5),
    },
    {
        "name": "Gulf of Alaska",
        "latitude_range": (54.0, 61.0),
        "longitude_range": (-155.0, -135.0),
    },
    {
        # North boundary fixed from 3.0°N to 0.0° (sea is south of equator).
        "name": "Bismarck Sea",
        "latitude_range": (-6.0, 0.0),
        "longitude_range": (142.0, 152.0),
    },

    # Ross Sea: crosses antimeridian — split into east and west halves.
    # The simple min <= lon <= max check cannot handle min_lon > max_lon.
    {
        "name": "Ross Sea",
        "latitude_range": (-78.0, -70.0),
        "longitude_range": (160.0, 180.0),
    },
    {
        "name": "Ross Sea",
        "latitude_range": (-78.0, -70.0),
        "longitude_range": (-180.0, -150.0),
    },

    {
        "name": "East China Sea",
        "latitude_range": (24.0, 33.0),
        "longitude_range": (121.0, 131.0),
    },
    {
        "name": "Chukchi Sea",
        "latitude_range": (66.0, 72.0),
        "longitude_range": (-180.0, -155.0),
    },
    {
        "name": "Black Sea",
        "latitude_range": (40.5, 47.0),
        "longitude_range": (27.5, 42.0),
    },
    {
        "name": "Greenland Sea",
        "latitude_range": (70.0, 80.0),
        "longitude_range": (-20.0, 10.0),
    },
    {
        "name": "North Sea",
        "latitude_range": (51.0, 61.0),
        "longitude_range": (-4.0, 9.0),
    },
    {
        # Catch-all Great Lakes box — only matches if the five individual
        # lake entries above didn't match (e.g., inter-lake channels).
        "name": "Great Lakes",
        "latitude_range": (41.0, 49.0),
        "longitude_range": (-92.5, -75.5),
    },
    {
        "name": "Arafura Sea",
        "latitude_range": (-12.0, -5.0),
        "longitude_range": (131.0, 141.0),
    },
    {
        "name": "Java Sea",
        "latitude_range": (-8.0, -3.0),
        "longitude_range": (105.0, 118.0),
    },
    {
        "name": "Strait of Malacca",
        "latitude_range": (-1.0, 7.0),
        "longitude_range": (96.0, 104.0),
    },
    {
        "name": "Andaman Sea",
        "latitude_range": (5.0, 18.0),
        "longitude_range": (92.0, 99.0),
    },
    {
        "name": "Barents Sea",
        "latitude_range": (70.0, 82.0),
        "longitude_range": (15.0, 60.0),
    },
    {
        "name": "Baltic Sea",
        "latitude_range": (54.0, 66.0),
        "longitude_range": (10.0, 30.0),
    },
    {
        "name": "Hudson Bay",
        "latitude_range": (51.0, 63.5),
        "longitude_range": (-95.0, -77.0),
    },
    {
        "name": "Coral Sea",
        "latitude_range": (-26.0, -10.0),
        "longitude_range": (146.0, 165.0),
    },
    {
        "name": "Sea of Japan",
        "latitude_range": (33.0, 52.0),
        "longitude_range": (127.0, 142.0),
    },
    {
        "name": "Gulf of Mexico",
        "latitude_range": (18.0, 30.5),
        "longitude_range": (-98.0, -80.0),
    },
    {
        "name": "Red Sea",
        "latitude_range": (12.5, 30.0),
        "longitude_range": (32.0, 44.0),
    },
    {
        "name": "Great Australian Bight",
        "latitude_range": (-39.0, -31.0),
        "longitude_range": (115.0, 138.0),
    },
    {
        # Merged "Okhotsk Sea" and "Sea of Okhotsk" into one entry.
        "name": "Sea of Okhotsk",
        "latitude_range": (44.0, 62.0),
        "longitude_range": (135.0, 160.0),
    },
    {
        "name": "Mozambique Channel",
        "latitude_range": (-26.0, -11.0),
        "longitude_range": (33.0, 48.0),
    },
    {
        "name": "Gulf of Guinea",
        "latitude_range": (-5.0, 6.0),
        "longitude_range": (-10.0, 13.0),
    },

    # Bering Sea: crosses antimeridian — split into east and west halves.
    {
        "name": "Bering Sea",
        "latitude_range": (52.0, 66.0),
        "longitude_range": (162.0, 180.0),
    },
    {
        "name": "Bering Sea",
        "latitude_range": (52.0, 66.0),
        "longitude_range": (-180.0, -157.0),
    },

    {
        "name": "Bay of Bengal",
        "latitude_range": (5.0, 22.0),
        "longitude_range": (80.0, 100.0),
    },
    {
        "name": "Caribbean Sea",
        "latitude_range": (9.0, 22.0),
        "longitude_range": (-88.0, -60.0),
    },
    {
        "name": "Arabian Sea",
        "latitude_range": (5.0, 25.0),
        "longitude_range": (50.0, 78.0),
    },
    {
        "name": "Tasman Sea",
        "latitude_range": (-47.0, -28.0),
        "longitude_range": (150.0, 175.0),
    },
    {
        "name": "Philippine Sea",
        "latitude_range": (3.0, 26.0),
        "longitude_range": (122.0, 145.0),
    },
    {
        "name": "Mediterranean Sea",
        "latitude_range": (30.0, 46.0),
        "longitude_range": (-6.0, 36.5),
    },

    # ------------------------------------------------------------------ #
    #  Catch-all ocean basins (largest, matched last)                     #
    # ------------------------------------------------------------------ #
    {
        "name": "Arctic Ocean",
        "latitude_range": (66.5, 90.0),
        "longitude_range": (-180.0, 180.0),
    },
    {
        "name": "Southern Ocean",
        "latitude_range": (-90.0, -60.0),
        "longitude_range": (-180.0, 180.0),
    },
    {
        "name": "Central North Pacific Ocean",
        "latitude_range": (0.0, 60.0),
        "longitude_range": (100.0, 180.0),
    },
    {
        "name": "Central South Pacific Ocean",
        "latitude_range": (-60.0, 0.0),
        "longitude_range": (100.0, 180.0),
    },
    {
        "name": "North Pacific Ocean",
        "latitude_range": (0.0, 66.5),
        "longitude_range": (-180.0, -100.0),
    },
    {
        "name": "South Pacific Ocean",
        "latitude_range": (-66.5, 0.0),
        "longitude_range": (-180.0, -100.0),
    },
    {
        "name": "North Atlantic Ocean",
        "latitude_range": (0.0, 66.5),
        "longitude_range": (-100.0, 20.0),
    },
    {
        "name": "South Atlantic Ocean",
        "latitude_range": (-66.5, 0.0),
        "longitude_range": (-100.0, 20.0),
    },
    {
        "name": "Indian Ocean",
        "latitude_range": (-60.0, 30.0),
        "longitude_range": (20.0, 120.0),
    },
    {
        "name": "Atlantic Ocean",
        "latitude_range": (-60.0, 60.0),
        "longitude_range": (-80.0, 20.0),
    },
    {
        "name": "Pacific Ocean",
        "latitude_range": (-60.0, 60.0),
        "longitude_range": (-180.0, -70.0),
    },
]


def _area(body):
    """Return rough rectangular area in km² for sorting (smallest first)."""
    lat_min, lat_max = body["latitude_range"]
    lon_min, lon_max = body["longitude_range"]
    width_deg = lon_max - lon_min
    if width_deg < 0:
        width_deg += 360  # crosses antimeridian
    height_deg = lat_max - lat_min
    mid_lat = (lat_min + lat_max) / 2
    width_km = width_deg * 111.32 * cos(radians(mid_lat))
    height_km = height_deg * 111.32
    return abs(width_km * height_km)


water_bodies.sort(key=_area)
