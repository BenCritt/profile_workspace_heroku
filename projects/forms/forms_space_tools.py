# forms/forms_space_tools.py
#
# Space & Astronomy Toolkit form classes.
#
# Forms and their consuming views:
#   SatellitePassForm      → views_space_tools.satellite_pass_predictor
#   LunarPhaseCalendarForm → views_space_tools.lunar_phase_calendar
#   NightSkyPlannerForm    → views_space_tools.night_sky_planner
#
# NOTE: SatellitePassForm and LunarPhaseCalendarForm both validate ZIP codes against
# the same us_zip_data.json dataset as WeatherForm, loading zdb at module level
# to avoid redundant disk reads on every request.

from django import forms
import re
from django.core.validators import (
    MinValueValidator,
    MaxValueValidator,
    MinLengthValidator,
    MaxLengthValidator,
    URLValidator
)
from django.core.exceptions import ValidationError
from ..zip_data import _load_dataset
zdb = _load_dataset()

# --- Satellite Pass Predictor ---
class SatellitePassForm(forms.Form):
    """
    Accepts a satellite selection and a US ZIP code.
    Reuses the same us_zip_data.json validation pattern as WeatherForm.
    """
    satellite = forms.ChoiceField(
        label="Select Satellite",
        choices=[],  # Populated in __init__ to avoid top-level import.
        widget=forms.Select(attrs={
            "class": "form-select",
        }),
    )
    zip_code = forms.CharField(
        label="ZIP Code",
        max_length=5,
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "53190",
        }),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Deferred import keeps the catalog out of module-load time.
        from ..satellite_pass_predictor_utils import SATELLITE_CHOICES
        self.fields["satellite"].choices = SATELLITE_CHOICES

    def clean_zip_code(self):
        zip_code = self.cleaned_data["zip_code"]
        try:
            zdb[zip_code]
        except (KeyError, IndexError):
            raise ValidationError(
                "You've made an invalid submission. Please enter a valid US ZIP code."
            )
        return zip_code

# --- Lunar Phase Calendar ---
from datetime import date
class LunarPhaseCalendarForm(forms.Form):
    """
    Form for the Lunar Phase Calendar tool.

    month + year   — select which calendar month to display
    zip_code       — optional US ZIP; when provided, adds moon rise/set times
    """

    MONTH_CHOICES = [
        (1,  "January"),  (2,  "February"), (3,  "March"),
        (4,  "April"),    (5,  "May"),       (6,  "June"),
        (7,  "July"),     (8,  "August"),    (9,  "September"),
        (10, "October"),  (11, "November"),  (12, "December"),
    ]

    @staticmethod
    def _year_choices() -> list[tuple[int, str]]:
        """Allow 2 years in the past through 3 years ahead."""
        current = date.today().year
        return [(y, str(y)) for y in range(current - 2, current + 4)]

    month = forms.ChoiceField(
        choices=MONTH_CHOICES,
        widget=forms.Select(attrs={"class": "form-select"}),
        label="Month",
    )

    year = forms.ChoiceField(
        choices=[],          # populated in __init__ so it reflects runtime year
        widget=forms.Select(attrs={"class": "form-select"}),
        label="Year",
    )

    zip_code = forms.CharField(
        max_length=10,
        required=False,
        widget=forms.TextInput(attrs={
            "class":       "form-control",
            "placeholder": "53546",
            "pattern":     r"\d{5}(-\d{4})?",
            "inputmode":   "numeric",
            "autocomplete": "postal-code",
        }),
        label="ZIP Code",
        help_text="Optional: Enter your 5-digit US ZIP code to add moon rise and set times.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["year"].choices = self._year_choices()

    def clean_zip_code(self) -> str:
        """Strip whitespace; allow empty (field is optional)."""
        return self.cleaned_data.get("zip_code", "").strip()

    def clean_month(self) -> int:
        return int(self.cleaned_data["month"])

    def clean_year(self) -> int:
        return int(self.cleaned_data["year"])

# --- Night Sky Planner ---
class NightSkyPlannerForm(forms.Form):
    """
    Form for collecting the user's ZIP code to generate a night sky report.

    Validates that the input is a 5-digit US ZIP code. The form uses
    Bootstrap-compatible widget attributes for consistent styling with
    the site's dark theme.
    """

    zip_code = forms.CharField(
        max_length=5,
        min_length=5,
        label="ZIP Code",
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "53546",
                "pattern": "[0-9]{5}",
                "inputmode": "numeric",
                "maxlength": "5",
                "title": "Please enter a valid 5-digit US ZIP code.",
                "autocomplete": "postal-code",
                "aria-label": "US ZIP code for night sky report",
                "id": "zip-code-input",
            }
        ),
        help_text="Enter a 5-digit US ZIP code to see tonight's sky conditions.",
        error_messages={
            "required": "Please enter a ZIP code.",
            "min_length": "ZIP code must be exactly 5 digits.",
            "max_length": "ZIP code must be exactly 5 digits.",
        },
    )

    def clean_zip_code(self):
        """Validate that the ZIP code contains only digits."""
        zip_code = self.cleaned_data.get("zip_code", "").strip()

        if not zip_code.isdigit():
            raise forms.ValidationError("ZIP code must contain only numbers.")

        return zip_code