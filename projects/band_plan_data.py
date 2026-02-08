"""
US Amateur Radio Band Plan — FCC Part 97 Sub-Band Segments

Each entry represents a contiguous frequency segment with uniform
mode permissions and license-class transmit privileges.

Frequencies are in MHz.  Privilege boundaries follow the ARRL band
chart derived from 47 CFR § 97.301 – 97.305.

NOTE:  The FCC band plan is the authoritative source.  Verify
against the current ARRL band chart at
https://www.arrl.org/band-plan before relying on this data for
on-air operation.

Maintained license classes:
  E  = Amateur Extra
  A  = Advanced  (grandfathered — no new licenses issued)
  G  = General
  T  = Technician
  N  = Novice    (grandfathered — no new licenses issued)
"""

# --------------------------------------------------------------------------- #
#  Data format for each segment:
#
#  {
#      "band":        Human-readable band name,
#      "freq_start":  Lower edge in MHz (inclusive),
#      "freq_end":    Upper edge in MHz (inclusive),
#      "modes":       List of permitted emission types,
#      "classes":     List of license-class abbreviations with
#                     transmit privileges in this segment,
#      "max_power_w": Maximum transmit power in watts PEP
#                     (default 1500 unless restricted),
#      "notes":       Optional remarks (e.g. channelized, USB-only),
#  }
# --------------------------------------------------------------------------- #

BAND_PLAN = [
    # ------------------------------------------------------------------- #
    #  160 Meters  (1.800 – 2.000 MHz)  —  MF
    # ------------------------------------------------------------------- #
    {
        "band": "160 Meters (1.8 MHz)",
        "freq_start": 1.800,
        "freq_end": 2.000,
        "modes": ["CW", "Phone", "Image", "RTTY", "Data"],
        "classes": ["E", "A", "G"],
        "max_power_w": 1500,
        "notes": "Night-time propagation band. Power may be restricted near Canadian border (see FCC § 97.303).",
    },

    # ------------------------------------------------------------------- #
    #  80 Meters  (3.500 – 4.000 MHz)  —  HF
    # ------------------------------------------------------------------- #
    {
        "band": "80 Meters (3.5 MHz)",
        "freq_start": 3.500,
        "freq_end": 3.525,
        "modes": ["CW", "RTTY", "Data"],
        "classes": ["E"],
        "max_power_w": 1500,
        "notes": "Extra-class-only CW/Data sub-band.",
    },
    {
        "band": "80 Meters (3.5 MHz)",
        "freq_start": 3.525,
        "freq_end": 3.600,
        "modes": ["CW", "RTTY", "Data"],
        "classes": ["E", "A", "G"],
        "max_power_w": 1500,
        "notes": "",
    },
    {
        "band": "80 Meters (3.5 MHz)",
        "freq_start": 3.600,
        "freq_end": 3.700,
        "modes": ["CW", "Phone", "Image", "RTTY", "Data"],
        "classes": ["E"],
        "max_power_w": 1500,
        "notes": "Extra-class Phone/CW sub-band.",
    },
    {
        "band": "80 Meters (3.5 MHz)",
        "freq_start": 3.700,
        "freq_end": 3.800,
        "modes": ["CW", "Phone", "Image", "RTTY", "Data"],
        "classes": ["E", "A"],
        "max_power_w": 1500,
        "notes": "Advanced sub-band begins at 3.700 MHz.",
    },
    {
        "band": "80 Meters (3.5 MHz)",
        "freq_start": 3.800,
        "freq_end": 4.000,
        "modes": ["CW", "Phone", "Image", "RTTY", "Data"],
        "classes": ["E", "A", "G"],
        "max_power_w": 1500,
        "notes": "General-class Phone sub-band begins at 3.800 MHz.",
    },

    # ------------------------------------------------------------------- #
    #  60 Meters  (channelized)  —  HF
    # ------------------------------------------------------------------- #
    {
        "band": "60 Meters (5 MHz)",
        "freq_start": 5.332,
        "freq_end": 5.332,
        "modes": ["CW", "Phone (USB)", "RTTY", "Data"],
        "classes": ["E", "A", "G"],
        "max_power_w": 100,
        "notes": "Channel 1 — center frequency 5.3320 MHz. USB only for phone. 100 W ERP max. Secondary allocation shared with government.",
    },
    {
        "band": "60 Meters (5 MHz)",
        "freq_start": 5.348,
        "freq_end": 5.348,
        "modes": ["CW", "Phone (USB)", "RTTY", "Data"],
        "classes": ["E", "A", "G"],
        "max_power_w": 100,
        "notes": "Channel 2 — center frequency 5.3480 MHz. USB only for phone. 100 W ERP max.",
    },
    {
        "band": "60 Meters (5 MHz)",
        "freq_start": 5.358,
        "freq_end": 5.358,
        "modes": ["CW", "Phone (USB)", "RTTY", "Data"],
        "classes": ["E", "A", "G"],
        "max_power_w": 100,
        "notes": "Channel 3 — center frequency 5.3585 MHz. USB only for phone. 100 W ERP max.",
    },
    {
        "band": "60 Meters (5 MHz)",
        "freq_start": 5.373,
        "freq_end": 5.373,
        "modes": ["CW", "Phone (USB)", "RTTY", "Data"],
        "classes": ["E", "A", "G"],
        "max_power_w": 100,
        "notes": "Channel 4 — center frequency 5.3730 MHz. USB only for phone. 100 W ERP max.",
    },
    {
        "band": "60 Meters (5 MHz)",
        "freq_start": 5.405,
        "freq_end": 5.405,
        "modes": ["CW", "Phone (USB)", "RTTY", "Data"],
        "classes": ["E", "A", "G"],
        "max_power_w": 100,
        "notes": "Channel 5 — center frequency 5.4050 MHz. USB only for phone. 100 W ERP max.",
    },

    # ------------------------------------------------------------------- #
    #  40 Meters  (7.000 – 7.300 MHz)  —  HF
    # ------------------------------------------------------------------- #
    {
        "band": "40 Meters (7 MHz)",
        "freq_start": 7.000,
        "freq_end": 7.025,
        "modes": ["CW", "RTTY", "Data"],
        "classes": ["E"],
        "max_power_w": 1500,
        "notes": "Extra-class-only CW/Data sub-band.",
    },
    {
        "band": "40 Meters (7 MHz)",
        "freq_start": 7.025,
        "freq_end": 7.125,
        "modes": ["CW", "RTTY", "Data"],
        "classes": ["E", "A", "G"],
        "max_power_w": 1500,
        "notes": "",
    },
    {
        "band": "40 Meters (7 MHz)",
        "freq_start": 7.125,
        "freq_end": 7.175,
        "modes": ["CW", "Phone", "Image", "RTTY", "Data"],
        "classes": ["E"],
        "max_power_w": 1500,
        "notes": "Extra-class Phone sub-band.",
    },
    {
        "band": "40 Meters (7 MHz)",
        "freq_start": 7.175,
        "freq_end": 7.300,
        "modes": ["CW", "Phone", "Image", "RTTY", "Data"],
        "classes": ["E", "A", "G"],
        "max_power_w": 1500,
        "notes": "General-class Phone sub-band begins at 7.175 MHz.",
    },

    # ------------------------------------------------------------------- #
    #  30 Meters  (10.100 – 10.150 MHz)  —  HF  (WARC band)
    # ------------------------------------------------------------------- #
    {
        "band": "30 Meters (10 MHz)",
        "freq_start": 10.100,
        "freq_end": 10.150,
        "modes": ["CW", "RTTY", "Data"],
        "classes": ["E", "A", "G"],
        "max_power_w": 200,
        "notes": "200 W PEP max. No phone permitted. Shared with fixed service (secondary allocation). No contests.",
    },

    # ------------------------------------------------------------------- #
    #  20 Meters  (14.000 – 14.350 MHz)  —  HF
    # ------------------------------------------------------------------- #
    {
        "band": "20 Meters (14 MHz)",
        "freq_start": 14.000,
        "freq_end": 14.025,
        "modes": ["CW", "RTTY", "Data"],
        "classes": ["E"],
        "max_power_w": 1500,
        "notes": "Extra-class-only CW/Data sub-band.",
    },
    {
        "band": "20 Meters (14 MHz)",
        "freq_start": 14.025,
        "freq_end": 14.150,
        "modes": ["CW", "RTTY", "Data"],
        "classes": ["E", "A", "G"],
        "max_power_w": 1500,
        "notes": "",
    },
    {
        "band": "20 Meters (14 MHz)",
        "freq_start": 14.150,
        "freq_end": 14.175,
        "modes": ["CW", "Phone", "Image"],
        "classes": ["E"],
        "max_power_w": 1500,
        "notes": "Extra-class Phone sub-band.",
    },
    {
        "band": "20 Meters (14 MHz)",
        "freq_start": 14.175,
        "freq_end": 14.225,
        "modes": ["CW", "Phone", "Image"],
        "classes": ["E", "A"],
        "max_power_w": 1500,
        "notes": "Advanced sub-band begins at 14.175 MHz.",
    },
    {
        "band": "20 Meters (14 MHz)",
        "freq_start": 14.225,
        "freq_end": 14.350,
        "modes": ["CW", "Phone", "Image"],
        "classes": ["E", "A", "G"],
        "max_power_w": 1500,
        "notes": "General-class Phone sub-band begins at 14.225 MHz.",
    },

    # ------------------------------------------------------------------- #
    #  17 Meters  (18.068 – 18.168 MHz)  —  HF  (WARC band)
    # ------------------------------------------------------------------- #
    {
        "band": "17 Meters (18 MHz)",
        "freq_start": 18.068,
        "freq_end": 18.110,
        "modes": ["CW", "RTTY", "Data"],
        "classes": ["E", "A", "G"],
        "max_power_w": 1500,
        "notes": "WARC band — no contests.",
    },
    {
        "band": "17 Meters (18 MHz)",
        "freq_start": 18.110,
        "freq_end": 18.168,
        "modes": ["CW", "Phone", "Image"],
        "classes": ["E", "A", "G"],
        "max_power_w": 1500,
        "notes": "WARC band — no contests.",
    },

    # ------------------------------------------------------------------- #
    #  15 Meters  (21.000 – 21.450 MHz)  —  HF
    # ------------------------------------------------------------------- #
    {
        "band": "15 Meters (21 MHz)",
        "freq_start": 21.000,
        "freq_end": 21.025,
        "modes": ["CW", "RTTY", "Data"],
        "classes": ["E"],
        "max_power_w": 1500,
        "notes": "Extra-class-only CW/Data sub-band.",
    },
    {
        "band": "15 Meters (21 MHz)",
        "freq_start": 21.025,
        "freq_end": 21.200,
        "modes": ["CW", "RTTY", "Data"],
        "classes": ["E", "A", "G"],
        "max_power_w": 1500,
        "notes": "",
    },
    {
        "band": "15 Meters (21 MHz)",
        "freq_start": 21.200,
        "freq_end": 21.225,
        "modes": ["CW", "Phone", "Image"],
        "classes": ["E"],
        "max_power_w": 1500,
        "notes": "Extra-class Phone sub-band.",
    },
    {
        "band": "15 Meters (21 MHz)",
        "freq_start": 21.225,
        "freq_end": 21.275,
        "modes": ["CW", "Phone", "Image"],
        "classes": ["E", "A"],
        "max_power_w": 1500,
        "notes": "Advanced sub-band begins at 21.225 MHz.",
    },
    {
        "band": "15 Meters (21 MHz)",
        "freq_start": 21.275,
        "freq_end": 21.450,
        "modes": ["CW", "Phone", "Image"],
        "classes": ["E", "A", "G"],
        "max_power_w": 1500,
        "notes": "General-class Phone sub-band begins at 21.275 MHz.",
    },

    # ------------------------------------------------------------------- #
    #  12 Meters  (24.890 – 24.990 MHz)  —  HF  (WARC band)
    # ------------------------------------------------------------------- #
    {
        "band": "12 Meters (24 MHz)",
        "freq_start": 24.890,
        "freq_end": 24.930,
        "modes": ["CW", "RTTY", "Data"],
        "classes": ["E", "A", "G"],
        "max_power_w": 1500,
        "notes": "WARC band — no contests.",
    },
    {
        "band": "12 Meters (24 MHz)",
        "freq_start": 24.930,
        "freq_end": 24.990,
        "modes": ["CW", "Phone", "Image"],
        "classes": ["E", "A", "G"],
        "max_power_w": 1500,
        "notes": "WARC band — no contests.",
    },

    # ------------------------------------------------------------------- #
    #  10 Meters  (28.000 – 29.700 MHz)  —  HF
    # ------------------------------------------------------------------- #
    {
        "band": "10 Meters (28 MHz)",
        "freq_start": 28.000,
        "freq_end": 28.300,
        "modes": ["CW", "RTTY", "Data"],
        "classes": ["E", "A", "G", "T"],
        "max_power_w": 1500,
        "notes": "Technician class has CW privileges 28.000–28.300 MHz (200 W PEP max for Technician).",
    },
    {
        "band": "10 Meters (28 MHz)",
        "freq_start": 28.300,
        "freq_end": 29.700,
        "modes": ["CW", "Phone", "Image", "RTTY", "Data"],
        "classes": ["E", "A", "G", "T"],
        "max_power_w": 1500,
        "notes": "Technician class has full privileges 28.300–29.700 MHz (200 W PEP max for Technician). FM simplex/repeater activity near 29.600 MHz.",
    },

    # ------------------------------------------------------------------- #
    #  6 Meters  (50.0 – 54.0 MHz)  —  VHF
    # ------------------------------------------------------------------- #
    {
        "band": "6 Meters (50 MHz)",
        "freq_start": 50.000,
        "freq_end": 50.100,
        "modes": ["CW", "Beacons"],
        "classes": ["E", "A", "G", "T"],
        "max_power_w": 1500,
        "notes": "CW/Beacon sub-band. 50.000–50.100 primarily CW and beacons by convention.",
    },
    {
        "band": "6 Meters (50 MHz)",
        "freq_start": 50.100,
        "freq_end": 54.000,
        "modes": ["CW", "Phone", "Image", "RTTY", "Data", "FM", "SSB"],
        "classes": ["E", "A", "G", "T"],
        "max_power_w": 1500,
        "notes": "All license classes. SSB calling frequency 50.125 MHz. FM simplex/repeater activity 51.0–54.0 by convention.",
    },

    # ------------------------------------------------------------------- #
    #  2 Meters  (144.0 – 148.0 MHz)  —  VHF
    # ------------------------------------------------------------------- #
    {
        "band": "2 Meters (144 MHz)",
        "freq_start": 144.000,
        "freq_end": 144.100,
        "modes": ["CW", "Beacons"],
        "classes": ["E", "A", "G", "T"],
        "max_power_w": 1500,
        "notes": "CW/Beacon sub-band.",
    },
    {
        "band": "2 Meters (144 MHz)",
        "freq_start": 144.100,
        "freq_end": 148.000,
        "modes": ["CW", "Phone", "Image", "RTTY", "Data", "FM", "SSB"],
        "classes": ["E", "A", "G", "T"],
        "max_power_w": 1500,
        "notes": "All license classes. SSB calling 144.200. FM simplex 146.520. Repeater inputs 146.0–146.4, outputs 146.6–147.0 by convention.",
    },

    # ------------------------------------------------------------------- #
    #  1.25 Meters  (222.0 – 225.0 MHz)  —  VHF
    # ------------------------------------------------------------------- #
    {
        "band": "1.25 Meters (222 MHz)",
        "freq_start": 222.000,
        "freq_end": 225.000,
        "modes": ["CW", "Phone", "Image", "RTTY", "Data", "FM"],
        "classes": ["E", "A", "G", "T"],
        "max_power_w": 1500,
        "notes": "All license classes. FM calling frequency 223.500 MHz by convention.",
    },

    # ------------------------------------------------------------------- #
    #  70 Centimeters  (420.0 – 450.0 MHz)  —  UHF
    # ------------------------------------------------------------------- #
    {
        "band": "70 Centimeters (420 MHz)",
        "freq_start": 420.000,
        "freq_end": 450.000,
        "modes": ["CW", "Phone", "Image", "RTTY", "Data", "FM", "ATV", "SSB"],
        "classes": ["E", "A", "G", "T"],
        "max_power_w": 1500,
        "notes": "All license classes. FM simplex 446.000 MHz. Secondary allocation — shared with government radiolocation. ATV (Amateur Television) activity above 440 MHz.",
    },

    # ------------------------------------------------------------------- #
    #  33 Centimeters  (902.0 – 928.0 MHz)  —  UHF
    # ------------------------------------------------------------------- #
    {
        "band": "33 Centimeters (902 MHz)",
        "freq_start": 902.000,
        "freq_end": 928.000,
        "modes": ["CW", "Phone", "Image", "RTTY", "Data", "FM"],
        "classes": ["E", "A", "G", "T"],
        "max_power_w": 1500,
        "notes": "Secondary allocation — shared with ISM and Part 15 devices. Not available in all areas. Limited amateur activity.",
    },

    # ------------------------------------------------------------------- #
    #  23 Centimeters  (1240.0 – 1300.0 MHz)  —  UHF
    # ------------------------------------------------------------------- #
    {
        "band": "23 Centimeters (1240 MHz)",
        "freq_start": 1240.000,
        "freq_end": 1300.000,
        "modes": ["CW", "Phone", "Image", "RTTY", "Data", "FM", "ATV"],
        "classes": ["E", "A", "G", "T"],
        "max_power_w": 1500,
        "notes": "Secondary allocation. ATV and digital links common. Shared with radiolocation and satellite services.",
    },
]

# --------------------------------------------------------------------------- #
#  Quick-reference: license class full names and descriptions
# --------------------------------------------------------------------------- #
LICENSE_CLASSES = {
    "E": {"name": "Amateur Extra", "description": "Full privileges on all amateur bands."},
    "A": {"name": "Advanced", "description": "Grandfathered class (no new licenses). Privileges between General and Extra."},
    "G": {"name": "General", "description": "HF privileges with some sub-band restrictions."},
    "T": {"name": "Technician", "description": "Full VHF/UHF privileges. Limited HF privileges (10m, 6m, plus CW on select HF bands)."},
    "N": {"name": "Novice", "description": "Grandfathered class (no new licenses). Limited CW on HF, plus 222 and 1240 MHz segments."},
}

# --------------------------------------------------------------------------- #
#  Technician HF CW privileges (beyond 10m/6m) — for reference/notes
#  Technicians also have CW privileges on portions of 80m, 40m, and 15m
#  at 200 W PEP max (same segments as Novice):
#    80m: 3.525–3.600 MHz  (CW only, 200 W)
#    40m: 7.025–7.125 MHz  (CW only, 200 W)
#    15m: 21.025–21.200 MHz (CW only, 200 W)
#  These overlap with General segments above but at reduced power.
# --------------------------------------------------------------------------- #
TECH_CW_HF_PRIVILEGES = [
    {
        "band": "80 Meters (3.5 MHz)",
        "freq_start": 3.525,
        "freq_end": 3.600,
        "modes": ["CW"],
        "max_power_w": 200,
        "notes": "Technician CW sub-band on 80m (200 W PEP max).",
    },
    {
        "band": "40 Meters (7 MHz)",
        "freq_start": 7.025,
        "freq_end": 7.125,
        "modes": ["CW"],
        "max_power_w": 200,
        "notes": "Technician CW sub-band on 40m (200 W PEP max).",
    },
    {
        "band": "15 Meters (21 MHz)",
        "freq_start": 21.025,
        "freq_end": 21.200,
        "modes": ["CW"],
        "max_power_w": 200,
        "notes": "Technician CW sub-band on 15m (200 W PEP max).",
    },
]
