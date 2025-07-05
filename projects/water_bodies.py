from math import cos, radians

water_bodies = [
    {
        "name": "Jervis Bay",
        "latitude_range": (-35.0, -34.5),
        "longitude_range": (150.7, 151.0),
    },
    {
        "name": "Scotland's Moray Firth",
        "latitude_range": (57.5, 58.5),
        "longitude_range": (-3.5, -2.5),
    },
    {
        "name": "Dover Strait",
        "latitude_range": (50.5, 51.5),
        "longitude_range": (1.0, 2.0),
    },
    {
        "name": "Shetland Isles Waters",
        "latitude_range": (60.0, 61.0),
        "longitude_range": (-1.0, 0.5),
    },
    {
        "name": "Bohuslän Archipelago",
        "latitude_range": (58.0, 59.0),
        "longitude_range": (11.0, 12.5),
    },
    {
        "name": "Tinian Passage",
        "latitude_range": (15.0, 16.0),
        "longitude_range": (145.5, 146.5),
    },
    {
        "name": "Lombok Strait",
        "latitude_range": (-9.0, -8.0),
        "longitude_range": (115.0, 116.0),
    },
    {
        "name": "Kerch Strait",
        "latitude_range": (45.0, 46.0),
        "longitude_range": (35.0, 36.5),
    },
    {
        "name": "Saint George Basin",
        "latitude_range": (57.0, 58.5),
        "longitude_range": (-6.0, -4.5),
    },
    {
        "name": "Seto Inland Sea",
        "latitude_range": (34.0, 35.0),
        "longitude_range": (132.0, 134.0),
    },
    {
        "name": "Tokara Strait",
        "latitude_range": (29.0, 30.0),
        "longitude_range": (129.0, 131.0),
    },
    {
        "name": "Beagle Channel",
        "latitude_range": (-55.0, -54.0),
        "longitude_range": (-69.0, -66.0),
    },
    {
        "name": "Mackenzie Bay",
        "latitude_range": (69.0, 70.0),
        "longitude_range": (-135.0, -130.0),
    },
    {
        "name": "Peel Sound",
        "latitude_range": (72.0, 74.0),
        "longitude_range": (-96.0, -93.0),
    },
    {
        "name": "Salish Sea",
        "latitude_range": (48.0, 50.0),
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
        "latitude_range": (56.0, 58.0),
        "longitude_range": (10.0, 13.0),
    },
    {
        "name": "Golfo San Matías",
        "latitude_range": (-41.5, -40.0),
        "longitude_range": (-65.0, -62.0),
    },
    {
        "name": "Amundsen Gulf",
        "latitude_range": (69.0, 71.0),
        "longitude_range": (-125.0, -120.0),
    },
    {
        "name": "Carnarvon Basin",
        "latitude_range": (-24.0, -22.0),
        "longitude_range": (112.0, 114.0),
    },
    {
        "name": "Palawan Passage",
        "latitude_range": (10.0, 12.0),
        "longitude_range": (118.0, 120.0),
    },
    {
        "name": "Porcupine Abyssal Plain",
        "latitude_range": (48.0, 50.0),
        "longitude_range": (-16.0, -13.0),
    },
    {
        "name": "Hebrides Basin",
        "latitude_range": (56.0, 59.0),
        "longitude_range": (-8.0, -5.0),
    },
    {
        "name": "Denmark Strait",
        "latitude_range": (65.5, 68.0),
        "longitude_range": (-33.0, -28.0),
    },
    {
        "name": "Luzon Strait",
        "latitude_range": (20.0, 22.5),
        "longitude_range": (119.5, 122.0),
    },
    {
        "name": "Alboran Sea",
        "latitude_range": (35.0, 37.0),
        "longitude_range": (-5.0, -1.0),
    },
    {
        "name": "Lake Ontario",
        "latitude_range": (43.0, 45.0),
        "longitude_range": (-79.5, -75.0),
    },
    {
        "name": "Lake Michigan",
        "latitude_range": (41.0, 46.0),
        "longitude_range": (-88.0, -86.0),
    },
    {
        "name": "Lake Erie",
        "latitude_range": (41.0, 43.0),
        "longitude_range": (-84.0, -79.0),
    },
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
        "name": "Lake Huron",
        "latitude_range": (43.0, 46.0),
        "longitude_range": (-84.0, -80.0),
    },
    {
        "name": "Liguro-Provençal Basin",
        "latitude_range": (41.0, 44.0),
        "longitude_range": (6.0, 10.0),
    },
    {
        "name": "Bellingshausen Sea",
        "latitude_range": (-73.0, -70.0),
        "longitude_range": (-90.0, -80.0),
    },
    {
        "name": "Laptev Abyssal Plain",
        "latitude_range": (76.0, 79.0),
        "longitude_range": (125.0, 140.0),
    },
    {
        "name": "Gulf of Maine",
        "latitude_range": (42.0, 45.0),
        "longitude_range": (-71.0, -66.0),
    },
    {
        "name": "Sunda Trench",
        "latitude_range": (-8.0, -5.0),
        "longitude_range": (106.0, 110.0),
    },
    {
        "name": "Bohai Sea",
        "latitude_range": (37.0, 41.0),
        "longitude_range": (117.0, 121.0),
    },
    {
        "name": "Hudson Strait",
        "latitude_range": (60.0, 63.0),
        "longitude_range": (-79.0, -70.0),
    },
    {
        "name": "Barents Abyssal Plain",
        "latitude_range": (73.0, 75.0),
        "longitude_range": (20.0, 45.0),
    },
    {
        "name": "Gulf of Bothnia",
        "latitude_range": (60.0, 65.0),
        "longitude_range": (17.0, 23.0),
    },
    {
        "name": "Baffin Bay Abyssal Plain",
        "latitude_range": (71.0, 75.0),
        "longitude_range": (-72.0, -60.0),
    },
    {
        "name": "Timor Sea",
        "latitude_range": (-12.0, -9.0),
        "longitude_range": (125.0, 130.0),
    },
    {
        "name": "Chukchi Abyssal Plain",
        "latitude_range": (70.0, 75.0),
        "longitude_range": (-165.0, -155.0),
    },
    {
        "name": "Tyrrhenian Sea",
        "latitude_range": (38.0, 42.0),
        "longitude_range": (10.0, 15.0),
    },
    {
        "name": "Lake Superior",
        "latitude_range": (46.0, 49.0),
        "longitude_range": (-92.0, -84.0),
    },
    {
        "name": "Ionian Sea",
        "latitude_range": (34.0, 41.0),
        "longitude_range": (19.0, 22.0),
    },
    {
        "name": "Sulawesi Sea",
        "latitude_range": (3.0, 7.0),
        "longitude_range": (120.0, 125.0),
    },
    {
        "name": "Beaufort Sea",
        "latitude_range": (70.0, 75.0),
        "longitude_range": (-135.0, -120.0),
    },
    {
        "name": "Aegean Sea",
        "latitude_range": (35.0, 41.0),
        "longitude_range": (23.0, 28.0),
    },
    {
        "name": "Newfoundland Basin",
        "latitude_range": (45.0, 50.0),
        "longitude_range": (-55.0, -48.0),
    },
    {
        "name": "Carpentaria Gulf",
        "latitude_range": (-17.0, -12.0),
        "longitude_range": (135.0, 140.0),
    },
    {
        "name": "Timor Sea (West)",
        "latitude_range": (-13.0, -8.0),
        "longitude_range": (120.0, 125.0),
    },
    {
        "name": "Greenland-Iceland Rise",
        "latitude_range": (63.0, 67.0),
        "longitude_range": (-30.0, -15.0),
    },
    {
        "name": "Adriatic Sea",
        "latitude_range": (40.0, 45.0),
        "longitude_range": (12.0, 19.0),
    },
    {
        "name": "Sulu Sea",
        "latitude_range": (5.0, 12.0),
        "longitude_range": (118.0, 122.0),
    },
    {
        "name": "Banda Sea",
        "latitude_range": (-8.0, -4.0),
        "longitude_range": (123.0, 130.0),
    },
    {
        "name": "Yellow Sea",
        "latitude_range": (33.0, 39.0),
        "longitude_range": (120.0, 126.0),
    },
    {
        "name": "Drake Passage",
        "latitude_range": (-60.0, -56.0),
        "longitude_range": (-65.0, -50.0),
    },
    {
        "name": "Scotia Arc",
        "latitude_range": (-61.0, -55.0),
        "longitude_range": (-46.0, -35.0),
    },
    {
        "name": "Mozambique Basin",
        "latitude_range": (-22.0, -15.0),
        "longitude_range": (38.0, 44.0),
    },
    {
        "name": "Levantine Sea",
        "latitude_range": (30.0, 36.0),
        "longitude_range": (26.0, 34.0),
    },
    {
        "name": "Bass Strait",
        "latitude_range": (-42.5, -38.0),
        "longitude_range": (138.0, 150.0),
    },
    {
        "name": "Gulf of Aden",
        "latitude_range": (10.0, 15.0),
        "longitude_range": (43.0, 52.0),
    },
    {
        "name": "Laptev Sea",
        "latitude_range": (70.0, 78.0),
        "longitude_range": (120.0, 140.0),
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
        "latitude_range": (24.0, 30.0),
        "longitude_range": (48.0, 57.0),
    },
    {
        "name": "Solomon Sea",
        "latitude_range": (-10.0, -5.0),
        "longitude_range": (150.0, 160.0),
    },
    {
        "name": "Celebes Sea",
        "latitude_range": (0.0, 8.0),
        "longitude_range": (120.0, 127.0),
    },
    {
        "name": "Gulf of California",
        "latitude_range": (23.0, 31.0),
        "longitude_range": (-115.0, -107.0),
    },
    {
        "name": "Caspian Sea",
        "latitude_range": (36.0, 47.0),
        "longitude_range": (47.0, 54.0),
    },
    {
        "name": "Gulf of Alaska",
        "latitude_range": (54.0, 60.0),
        "longitude_range": (-160.0, -140.0),
    },
    {
        "name": "Bismarck Sea",
        "latitude_range": (-3.0, 3.0),
        "longitude_range": (142.0, 153.0),
    },
    {
        "name": "Ross Sea",
        "latitude_range": (-78.0, -70.0),
        "longitude_range": (160.0, -170.0),
    },
    {
        "name": "East China Sea",
        "latitude_range": (24.0, 32.0),
        "longitude_range": (121.0, 131.0),
    },
    {
        "name": "Chukchi Sea",
        "latitude_range": (66.0, 75.0),
        "longitude_range": (-180.0, -155.0),
    },
    {
        "name": "Black Sea",
        "latitude_range": (40.0, 47.0),
        "longitude_range": (27.0, 42.0),
    },
    {
        "name": "Greenland Sea",
        "latitude_range": (70.0, 80.0),
        "longitude_range": (-20.0, 10.0),
    },
    {
        "name": "North Sea",
        "latitude_range": (51.0, 61.0),
        "longitude_range": (-5.0, 10.0),
    },
    {
        "name": "Great Lakes",
        "latitude_range": (41.0, 49.0),
        "longitude_range": (-92.0, -76.0),
    },
    {
        "name": "Arafura Sea",
        "latitude_range": (-11.0, -2.0),
        "longitude_range": (130.0, 141.0),
    },
    {
        "name": "Java Sea",
        "latitude_range": (-10.0, 0.0),
        "longitude_range": (105.0, 115.0),
    },
    {
        "name": "Strait of Malacca",
        "latitude_range": (-6.0, 6.0),
        "longitude_range": (96.0, 105.0),
    },
    {
        "name": "Andaman Sea",
        "latitude_range": (6.0, 20.0),
        "longitude_range": (92.0, 100.0),
    },
    {
        "name": "Barents Sea",
        "latitude_range": (70.0, 82.0),
        "longitude_range": (20.0, 60.0),
    },
    {
        "name": "Baltic Sea",
        "latitude_range": (54.0, 66.0),
        "longitude_range": (10.0, 30.0),
    },
    {
        "name": "Hudson Bay",
        "latitude_range": (52.0, 63.0),
        "longitude_range": (-96.0, -75.0),
    },
    {
        "name": "Coral Sea",
        "latitude_range": (-25.0, -13.0),
        "longitude_range": (146.0, 160.0),
    },
    {
        "name": "Sea of Japan",
        "latitude_range": (33.0, 46.0),
        "longitude_range": (127.0, 144.0),
    },
    {
        "name": "Gulf of Mexico",
        "latitude_range": (18.0, 31.0),
        "longitude_range": (-97.0, -81.0),
    },
    {
        "name": "Red Sea",
        "latitude_range": (12.0, 30.0),
        "longitude_range": (32.0, 44.0),
    },
    {
        "name": "Great Australian Bight",
        "latitude_range": (-40.0, -30.0),
        "longitude_range": (110.0, 135.0),
    },
    {
        "name": "Okhotsk Sea",
        "latitude_range": (43.0, 60.0),
        "longitude_range": (135.0, 155.0),
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
    {
        "name": "Sea of Okhotsk",
        "latitude_range": (44.0, 60.0),
        "longitude_range": (135.0, 162.0),
    },
    {
        "name": "Bering Sea",
        "latitude_range": (52.0, 66.0),
        "longitude_range": (160.0, -157.0),
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
        "longitude_range": (50.0, 72.0),
    },
    {
        "name": "Tasman Sea",
        "latitude_range": (-47.0, -28.0),
        "longitude_range": (140.0, 170.0),
    },
    {
        "name": "Philippine Sea",
        "latitude_range": (5.0, 25.0),
        "longitude_range": (120.0, 155.0),
    },
    {
        "name": "Arctic Ocean",
        "latitude_range": (66.5, 90.0),
        "longitude_range": (-180.0, 180.0),
    },
    {
        "name": "Scotia Sea",
        "latitude_range": (-60.0, 0.0),
        "longitude_range": (-60.0, -25.0),
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
    """Return rough rectangular area in km² (redundancy for sorting)."""
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
