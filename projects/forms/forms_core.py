# forms/forms_core.py
#
# Shared / core form classes used by more than one view category.
#
# Forms and their consuming views:
#   WeatherForm   → views_misc.weather
#                   views_space_tools.iss_tracker  (ZIP used for observer location)
#   TextForm      → views_it_tools.grade_level_analyzer
#
# NOTE: WeatherForm is intentionally kept here (not in forms_misc or forms_space_tools)
# because it is the only form shared across two different view category modules.
# Moving it into either consumer's module would create a cross-category import.

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

# WeatherForm validates against the local ZIP dataset.
# The module-level _load_dataset() call is intentionally at import time
# (same as in the original monolithic forms.py) so the dataset is loaded
# once per worker process, not on every request.
from ..zip_data import _load_dataset

# --- Weather Forecast ---
zdb = _load_dataset()

class WeatherForm(forms.Form):
    zip_code = forms.CharField(
        label="ZIP Code:", 
        max_length=5,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "53545"
            }
        )
    )

    def clean_zip_code(self):
        zip_code = self.cleaned_data["zip_code"]
        try:
            zdb[zip_code]
        except (KeyError, IndexError):
            raise ValidationError("You've made an invalid submission. Please enter a valid ZIP code.")
        return zip_code


# --- Grade Level Text Analyzer ---
class TextForm(forms.Form):
    text = forms.CharField(
        label="Enter text to analyze",
        widget=forms.Textarea(
            attrs={
                "class": "form-control", 
                "rows": 10,
            }
        ),
        validators=[
            MinLengthValidator(1200, message="The sample you've provided is too short."),
            MaxLengthValidator(10000, message="The sample you've provided is too long."),
        ],
    )