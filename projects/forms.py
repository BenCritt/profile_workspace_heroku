from django import forms
from django.core.exceptions import ValidationError
from pyzipcode import ZipCodeDatabase
from django import forms
from django.core.validators import (
    MinValueValidator,
    MaxValueValidator,
    MinLengthValidator,
    MaxLengthValidator,
)


class TextForm(forms.Form):
    text = forms.CharField(
        widget=forms.Textarea(
            attrs={"class": "form-control", "rows": 5, "style": "max-width: 500px;"}
        ),
        label="Enter text to analyze",
        validators=[
            MinLengthValidator(
                1200, message="The sample you've provided is too short."
            ),
            MaxLengthValidator(
                10000, message="The sample you've provided is too long."
            ),
        ],
    )


class QRForm(forms.Form):
    qr_text = forms.CharField(
        label="",
        max_length=8000,
        widget=forms.TextInput(attrs={"class": "myform", "size": 30}),
    )


class MonteCarloForm(forms.Form):
    sim_quantity = forms.IntegerField(
        label="Number of Simulations ",
        validators=[
            MinValueValidator(
                1, message="The number of simulations must be at least 1."
            ),
            MaxValueValidator(
                1000000,
                message="The number of simulations cannot exceed 1,000,000.  This limit ensures server resources aren't overused.",
            ),
        ],
    )
    min_val = forms.FloatField(label="Minimum Value")
    max_val = forms.FloatField(label="Maximum Value")
    target_val = forms.FloatField(label="Target Value")

    second_sim_quantity = forms.IntegerField(
        required=False,
        label="Second Number of Simulations",
        validators=[
            MinValueValidator(
                1,
                message="The value for second number of simulations, if you wish to include a second data range, must be at least 1.  If you only want one data range in your graph, please leave the secondary fields blank.",
            ),
            MaxValueValidator(
                1000000,
                message="The number of second simulations cannot exceed 1,000,000.  This limit ensures server resources aren't overused.",
            ),
        ],
    )
    second_min_val = forms.FloatField(label="Second Minimum Value", required=False)
    second_max_val = forms.FloatField(label="Second Maximum Value", required=False)
    second_target_val = forms.FloatField(label="Second Target Value", required=False)


zdb = ZipCodeDatabase()


class WeatherForm(forms.Form):
    zip_code = forms.CharField(label="ZIP Code:", max_length=5)

    def clean_zip_code(self):
        zip_code = self.cleaned_data["zip_code"]
        try:
            zdb[zip_code]  # this will raise an exception if the zip code is invalid
        except (KeyError, IndexError):
            raise ValidationError(
                "You've made an invalid submission. Please enter a valid ZIP code."
            )
        return zip_code
