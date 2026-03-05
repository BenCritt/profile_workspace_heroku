# forms/forms_radio_tools.py
#
# Amateur Radio Toolkit form classes.
#
# Forms and their consuming views:
#   CallsignLookupForm    → views_radio_tools.ham_radio_call_sign_lookup
#   BandPlanForm          → views_radio_tools.band_plan_checker
#   RepeaterFinderForm    → views_radio_tools.repeater_finder
#   AntennaCalculatorForm → views_radio_tools.antenna_calculator
#   GridSquareForm        → views_radio_tools.grid_square_converter
#   RFExposureForm        → views_radio_tools.rf_exposure_calculator
#   CoaxCableLossForm     → views_radio_tools.coax_cable_loss_calculator
#
# NOTE: CALLSIGN_RE is a module-level compiled regex reused by CallsignLookupForm
# and any future forms that validate amateur radio callsign format.
# Requires `import re` to be present before this constant is defined.

from django import forms
import re
CALLSIGN_RE = re.compile(r"^[A-Za-z0-9]{3,8}$")
from django.core.validators import (
    MinValueValidator,
    MaxValueValidator,
    MinLengthValidator,
    MaxLengthValidator,
    URLValidator
)
from django.core.exceptions import ValidationError

# Used by CallsignLookupForm.
import re

# --- Ham Radio Call Sign Lookup --
class CallsignLookupForm(forms.Form):
    callsign = forms.CharField(
        label="Call Sign: ",
        max_length=8,
        widget=forms.TextInput(
            attrs={
                "placeholder": "W9YT",
                "class": "form-control"
            }
        ),
    )

    def clean_callsign(self):
        cs = self.cleaned_data["callsign"].strip().upper()
        if not CALLSIGN_RE.fullmatch(cs):
            raise forms.ValidationError(f"“{cs}” is not a valid call-sign.")
        return cs

# --- Band Plan Checker ---
LICENSE_CLASS_CHOICES = [
    ("", "— Show all classes —"),
    ("T", "Technician"),
    ("G", "General"),
    ("A", "Advanced (grandfathered)"),
    ("E", "Amateur Extra"),
]

class BandPlanForm(forms.Form):
    frequency = forms.FloatField(
        label="Frequency (MHz)",
        min_value=0.001,
        max_value=300000,
        widget=forms.NumberInput(
            attrs={
                "class": "form-control",
                "placeholder": "14.225",
                "step": "any",
                "id": "id_frequency",
                "autofocus": True,
            }
        ),
        help_text="Enter the frequency in megahertz (MHz).",
        error_messages={
            "required": "Please enter a frequency.",
            "invalid": "Enter a valid number (e.g. 14.225).",
            "min_value": "Frequency must be greater than 0.",
            "max_value": "Frequency must be 300,000 MHz or less.",
        },
    )

    license_class = forms.ChoiceField(
        label="Your License Class (optional)",
        choices=LICENSE_CLASS_CHOICES,
        required=False,
        widget=forms.Select(
            attrs={
                "class": "form-select",
                "id": "id_license_class",
            }
        ),
        help_text="Select your license class to check your transmit privileges at this frequency.",
    )

# --- Repeater Finder ---
BAND_CHOICES = [
    ("2m", "2 Meters (144–148 MHz)"),
    ("70cm", "70 Centimeters (420–450 MHz)"),
    ("1.25m", "1.25 Meters (222–225 MHz)"),
    ("6m", "6 Meters (50–54 MHz)"),
]

RADIUS_CHOICES = [
    (10, "10 miles"),
    (15, "15 miles"),
    (20, "20 miles"),
    (30, "30 miles (default)"),
    (40, "40 miles"),
]

class RepeaterFinderForm(forms.Form):
    origin_zip = forms.CharField(
        label="Origin ZIP Code",
        max_length=10,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "53704",
                "id": "id_origin_zip",
                "inputmode": "numeric",
                "autofocus": True,
            }
        ),
        help_text="Starting point of your route.",
        error_messages={
            "required": "Please enter an origin ZIP code.",
        },
    )

    dest_zip = forms.CharField(
        label="Destination ZIP Code",
        max_length=10,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "60601",
                "id": "id_dest_zip",
                "inputmode": "numeric",
            }
        ),
        help_text="End point of your route.",
        error_messages={
            "required": "Please enter a destination ZIP code.",
        },
    )

    search_radius = forms.TypedChoiceField(
        label="Search Radius",
        choices=RADIUS_CHOICES,
        coerce=int,
        initial=30,
        widget=forms.Select(
            attrs={
                "class": "form-select",
                "id": "id_search_radius",
            }
        ),
        help_text="How far from the route centerline to search for repeaters.",
    )

    bands = forms.MultipleChoiceField(
        label="Bands to Include",
        choices=BAND_CHOICES,
        initial=["2m", "70cm"],
        widget=forms.CheckboxSelectMultiple(
            attrs={"class": "form-check-input"},
        ),
        help_text="Select which amateur bands to include in results.",
        error_messages={
            "required": "Please select at least one band.",
        },
    )

    def clean_origin_zip(self):
        value = self.cleaned_data["origin_zip"].strip()
        if not value.isdigit() or len(value) != 5:
            raise forms.ValidationError("Enter a valid 5-digit US ZIP code.")
        return value

    def clean_dest_zip(self):
        value = self.cleaned_data["dest_zip"].strip()
        if not value.isdigit() or len(value) != 5:
            raise forms.ValidationError("Enter a valid 5-digit US ZIP code.")
        return value

    def clean(self):
        cleaned = super().clean()
        origin = cleaned.get("origin_zip")
        dest = cleaned.get("dest_zip")
        if origin and dest and origin == dest:
            raise forms.ValidationError(
                "Origin and destination cannot be the same ZIP code."
            )
        return cleaned

# --- Antenna Length Calculator ---
VELOCITY_FACTOR_HELP = (
    "Accounts for wire insulation or enclosed elements. "
    "Bare copper wire ≈ 0.95; insulated wire ≈ 0.93; "
    "copper pipe ≈ 0.95; twin-lead ≈ 0.82. "
    "Leave blank to use the standard default for the selected antenna type."
)
class AntennaCalculatorForm(forms.Form):
    from ..antenna_calculator_utils import ANTENNA_TYPE_CHOICES
    frequency = forms.FloatField(
        label="Design Frequency (MHz)",
        min_value=0.001,
        max_value=3000.0,
        widget=forms.NumberInput(
            attrs={
                "class": "form-control",
                "placeholder": "146.000",
                "id": "id_frequency",
                "step": "any",
                "inputmode": "decimal",
                "autofocus": True,
            }
        ),
        help_text="Enter the target frequency in megahertz (MHz).",
        error_messages={
            "required": "Please enter a design frequency.",
            "min_value": "Frequency must be greater than zero.",
            "max_value": "Frequency must be 3,000 MHz or less.",
        },
    )

    antenna_type = forms.ChoiceField(
        label="Antenna Type",
        choices=ANTENNA_TYPE_CHOICES,
        initial="dipole",
        widget=forms.Select(
            attrs={
                "class": "form-select",
                "id": "id_antenna_type",
            }
        ),
        help_text="Select the antenna design you want to build.",
    )

    velocity_factor = forms.FloatField(
        label="Velocity Factor (optional)",
        required=False,
        min_value=0.50,
        max_value=1.00,
        widget=forms.NumberInput(
            attrs={
                "class": "form-control",
                "placeholder": "0.95",
                "id": "id_velocity_factor",
                "step": "0.01",
                "inputmode": "decimal",
            }
        ),
        help_text=VELOCITY_FACTOR_HELP,
        error_messages={
            "min_value": "Velocity factor cannot be less than 0.50.",
            "max_value": "Velocity factor cannot exceed 1.00.",
        },
    )

# --- Grid Square Converter ---
CONVERSION_CHOICES = [
    ("grid_to_coords", "Grid Square → Coordinates"),
    ("coords_to_grid", "Coordinates → Grid Square"),
    ("zip_to_grid", "ZIP Code → Grid Square"),
]

PRECISION_CHOICES = [
    (4, "4 characters (Field + Square)"),
    (6, "6 characters (Subsquare) — default"),
    (8, "8 characters (Extended)"),
]

class GridSquareForm(forms.Form):
    conversion_mode = forms.ChoiceField(
        label="Conversion Direction",
        choices=CONVERSION_CHOICES,
        initial="grid_to_coords",
        widget=forms.RadioSelect(
            attrs={"class": "form-check-input"},
        ),
        help_text="Choose which direction to convert.",
    )

    grid_square = forms.CharField(
        label="Grid Square",
        required=False,
        max_length=8,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "EN53dj",
                "id": "id_grid_square",
            }
        ),
        help_text="Enter a 4, 6, or 8 character Maidenhead grid square.",
    )

    latitude = forms.FloatField(
        label="Latitude",
        required=False,
        min_value=-90.0,
        max_value=90.0,
        widget=forms.NumberInput(
            attrs={
                "class": "form-control",
                "placeholder": "43.0731",
                "id": "id_latitude",
                "step": "any",
                "inputmode": "decimal",
            }
        ),
        help_text="Decimal degrees (−90 to 90). Negative = South.",
    )

    longitude = forms.FloatField(
        label="Longitude",
        required=False,
        min_value=-180.0,
        max_value=180.0,
        widget=forms.NumberInput(
            attrs={
                "class": "form-control",
                "placeholder": "-89.4012",
                "id": "id_longitude",
                "step": "any",
                "inputmode": "decimal",
            }
        ),
        help_text="Decimal degrees (−180 to 180). Negative = West.",
    )

    zip_code = forms.CharField(
        label="ZIP Code",
        required=False,
        max_length=5,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "53704",
                "id": "id_zip_code",
                "inputmode": "numeric",
            }
        ),
        help_text="Enter a 5-digit US ZIP code.",
    )

    precision = forms.TypedChoiceField(
        label="Output Precision",
        choices=PRECISION_CHOICES,
        coerce=int,
        initial=6,
        widget=forms.Select(
            attrs={
                "class": "form-select",
                "id": "id_precision",
            }
        ),
        help_text="Number of grid square characters to output (for coordinate/ZIP conversion).",
    )

    def clean(self):
        cleaned = super().clean()
        mode = cleaned.get("conversion_mode")

        if mode == "grid_to_coords":
            grid = cleaned.get("grid_square", "").strip()
            if not grid:
                raise forms.ValidationError(
                    "Please enter a grid square to convert."
                )

        elif mode == "coords_to_grid":
            lat = cleaned.get("latitude")
            lon = cleaned.get("longitude")
            if lat is None or lon is None:
                raise forms.ValidationError(
                    "Please enter both latitude and longitude."
                )

        elif mode == "zip_to_grid":
            zip_code = cleaned.get("zip_code", "").strip()
            if not zip_code:
                raise forms.ValidationError(
                    "Please enter a ZIP code."
                )
            if not zip_code.isdigit() or len(zip_code) != 5:
                raise forms.ValidationError(
                    "Enter a valid 5-digit US ZIP code."
                )

        return cleaned

# -- RF Exposure Calculator --
DISTANCE_UNIT_CHOICES = [
    ("feet", "Feet"),
    ("meters", "Meters"),
]

class RFExposureForm(forms.Form):
    from ..rf_exposure_utils import MODE_CHOICES, GAIN_REF_CHOICES
    power_watts = forms.FloatField(
        label="Transmitter Power (Watts PEP)",
        min_value=0.1,
        max_value=2000,
        widget=forms.NumberInput(
            attrs={
                "class": "form-control",
                "placeholder": "100",
                "id": "id_power_watts",
                "step": "any",
                "inputmode": "decimal",
                "autofocus": True,
            }
        ),
        help_text="Peak Envelope Power at the transmitter output. FCC amateur limit is 1,500 W PEP.",
        error_messages={
            "required": "Please enter your transmitter power.",
            "min_value": "Power must be greater than zero.",
            "max_value": "Power cannot exceed 2,000 watts.",
        },
    )

    frequency_mhz = forms.FloatField(
        label="Operating Frequency (MHz)",
        min_value=0.3,
        max_value=100000,
        widget=forms.NumberInput(
            attrs={
                "class": "form-control",
                "placeholder": "14.200",
                "id": "id_frequency_mhz",
                "step": "any",
                "inputmode": "decimal",
            }
        ),
        help_text="Frequency in megahertz. MPE limits vary by frequency band.",
        error_messages={
            "required": "Please enter your operating frequency.",
            "min_value": "Frequency must be at least 0.3 MHz.",
        },
    )

    gain_value = forms.FloatField(
        label="Antenna Gain",
        min_value=-10.0,
        max_value=50.0,
        widget=forms.NumberInput(
            attrs={
                "class": "form-control",
                "placeholder": "2.15",
                "id": "id_gain_value",
                "step": "any",
                "inputmode": "decimal",
            }
        ),
        help_text=(
            "Antenna gain. Common values: 0 dBd (dipole), 2.15 dBi (dipole), "
            "6–8 dBi (3-element Yagi), 0 dBi (¼λ vertical)."
        ),
    )

    gain_reference = forms.ChoiceField(
        label="Gain Reference",
        choices=GAIN_REF_CHOICES,
        initial="dBi",
        widget=forms.Select(
            attrs={
                "class": "form-select",
                "id": "id_gain_reference",
            }
        ),
    )

    distance_value = forms.FloatField(
        label="Distance to Nearest Person",
        min_value=0.1,
        max_value=10000,
        widget=forms.NumberInput(
            attrs={
                "class": "form-control",
                "placeholder": "25",
                "id": "id_distance_value",
                "step": "any",
                "inputmode": "decimal",
            }
        ),
        help_text="Distance from the antenna to the nearest area accessible by people.",
    )

    distance_unit = forms.ChoiceField(
        label="Distance Unit",
        choices=DISTANCE_UNIT_CHOICES,
        initial="feet",
        widget=forms.Select(
            attrs={
                "class": "form-select",
                "id": "id_distance_unit",
            }
        ),
    )

    mode = forms.ChoiceField(
        label="Transmission Mode",
        choices=MODE_CHOICES,
        initial="ssb",
        widget=forms.Select(
            attrs={
                "class": "form-select",
                "id": "id_mode",
            }
        ),
        help_text="Mode determines the duty cycle, which affects average power.",
    )

    custom_duty_cycle = forms.FloatField(
        label="Custom Duty Cycle (%)",
        required=False,
        min_value=1,
        max_value=100,
        widget=forms.NumberInput(
            attrs={
                "class": "form-control",
                "placeholder": "50",
                "id": "id_custom_duty_cycle",
                "step": "1",
                "inputmode": "numeric",
            }
        ),
        help_text="Only used when Transmission Mode is set to Custom.",
    )

    feed_line_loss_db = forms.FloatField(
        label="Feed Line Loss (dB, optional)",
        required=False,
        min_value=0.0,
        max_value=30.0,
        widget=forms.NumberInput(
            attrs={
                "class": "form-control",
                "placeholder": "1.5",
                "id": "id_feed_line_loss",
                "step": "any",
                "inputmode": "decimal",
            }
        ),
        help_text=(
            "Loss in your feed line reduces the power radiated by the antenna. "
            "Leave blank or 0 for a worst-case (no loss) evaluation."
        ),
    )

    def clean(self):
        cleaned = super().clean()
        mode = cleaned.get("mode")
        custom = cleaned.get("custom_duty_cycle")

        if mode == "custom" and (custom is None or custom <= 0):
            raise forms.ValidationError(
                "Please enter a custom duty cycle percentage (1–100%)."
            )

        return cleaned

# --- Coax Cable Loss Calculator --
class CoaxCableLossForm(forms.Form):
    from ..coax_calculator_utils import CABLE_CHOICES, LENGTH_UNIT_CHOICES
    cable_type = forms.ChoiceField(
        label="Cable Type",
        choices=CABLE_CHOICES,
        initial="rg213",
        widget=forms.Select(
            attrs={
                "class": "form-select",
                "id": "id_cable_type",
                "autofocus": True,
            }
        ),
        help_text="Select the coaxial cable type used in your feed line.",
    )

    frequency_mhz = forms.FloatField(
        label="Frequency (MHz)",
        min_value=1.0,
        max_value=3000.0,
        widget=forms.NumberInput(
            attrs={
                "class": "form-control",
                "placeholder": "146.0",
                "id": "id_frequency_mhz",
                "step": "any",
                "inputmode": "decimal",
            }
        ),
        help_text="Operating frequency in megahertz (1–3,000 MHz).",
        error_messages={
            "required": "Please enter your operating frequency.",
            "min_value": "Frequency must be at least 1.0 MHz.",
            "max_value": "Frequency cannot exceed 3,000 MHz.",
        },
    )

    length_value = forms.FloatField(
        label="Cable Length",
        min_value=0.1,
        max_value=5000.0,
        widget=forms.NumberInput(
            attrs={
                "class": "form-control",
                "placeholder": "100",
                "id": "id_length_value",
                "step": "any",
                "inputmode": "decimal",
            }
        ),
        help_text="Total length of the coaxial cable run.",
        error_messages={
            "required": "Please enter the cable length.",
            "min_value": "Cable length must be greater than zero.",
            "max_value": "Cable length cannot exceed 5,000.",
        },
    )

    length_unit = forms.ChoiceField(
        label="Unit",
        choices=LENGTH_UNIT_CHOICES,
        initial="feet",
        widget=forms.Select(
            attrs={
                "class": "form-select",
                "id": "id_length_unit",
            }
        ),
    )

    power_watts = forms.FloatField(
        label="Transmitter Power (Watts, optional)",
        required=False,
        min_value=0.0,
        max_value=5000.0,
        widget=forms.NumberInput(
            attrs={
                "class": "form-control",
                "placeholder": "100",
                "id": "id_power_watts",
                "step": "any",
                "inputmode": "decimal",
            }
        ),
        help_text="If provided, calculates watts lost and watts delivered to the antenna.",
        error_messages={
            "max_value": "Power cannot exceed 5,000 watts.",
        },
    )

    swr = forms.FloatField(
        label="SWR at Antenna (optional)",
        required=False,
        min_value=1.0,
        max_value=20.0,
        widget=forms.NumberInput(
            attrs={
                "class": "form-control",
                "placeholder": "1.5",
                "id": "id_swr",
                "step": "any",
                "inputmode": "decimal",
            }
        ),
        help_text="Standing Wave Ratio at the antenna. Leave blank or 1.0 to skip mismatch loss.",
        error_messages={
            "min_value": "SWR cannot be less than 1.0.",
            "max_value": "SWR cannot exceed 20.0.",
        },
    )