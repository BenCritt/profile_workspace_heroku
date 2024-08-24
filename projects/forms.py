from django import forms
from django.core.exceptions import ValidationError
from pyzipcode import ZipCodeDatabase
from django.core.validators import (
    MinValueValidator,
    MaxValueValidator,
    MinLengthValidator,
    MaxLengthValidator,
)


# This is the form for the Grade Level Text Analyzer.
class TextForm(forms.Form):
    # Create a CharField to hold the text input, using a textarea widget for multiline input.
    text = forms.CharField(
        # Configure the textarea widget with Bootstrap class for styling and set its size.
        widget=forms.Textarea(
            attrs={"class": "form-control", "rows": 5, "style": "max-width: 500px;"}
        ),
        label="Enter text to analyze",  # Set the label for the text input field.
        # Add validators to ensure the text length is within the specified range.
        validators=[
            # Minimum length validator: Text must be at least 1200 characters.
            MinLengthValidator(
                1200, message="The sample you've provided is too short."
            ),
            # Maximum length validator: Text must not exceed 10000 characters.
            MaxLengthValidator(
                10000, message="The sample you've provided is too long."
            ),
        ],
    )


# This is the form for the QR Code Generator.
class QRForm(forms.Form):
    # Create a CharField to hold the text input for the QR code.
    qr_text = forms.CharField(
        label="",  # The label is set to an empty string for a cleaner UI without a field label.
        max_length=8000,  # Set the maximum length of the text input to 8000 characters.
        # Configure the TextInput widget with a custom class for styling and set the size attribute.
        widget=forms.TextInput(attrs={"class": "myform", "size": 30}),
    )


# This is the form for the Monte Carlo Simulator.
class MonteCarloForm(forms.Form):
    # Integer field for the number of simulations to run.
    sim_quantity = forms.IntegerField(
        label="Number of Simulations ",
        # Validators to ensure the number of simulations is within an acceptable range.
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
    # Floating point fields for the minimum and maximum values for the simulation.
    min_val = forms.FloatField(label="Minimum Value")
    max_val = forms.FloatField(label="Maximum Value")
    # Floating point field for the target value in the simulation.
    target_val = forms.FloatField(label="Target Value")
    # Optional integer field for the number of simulations for a second data range.
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
    # Optional floating point fields for the minimum and maximum values for the second data range.
    second_min_val = forms.FloatField(label="Second Minimum Value", required=False)
    second_max_val = forms.FloatField(label="Second Maximum Value", required=False)
    # Optional floating point field for the target value for the second data range.
    second_target_val = forms.FloatField(label="Second Target Value", required=False)


# This is used to make sure the user enters a valid ZIP code.
zdb = ZipCodeDatabase()


# This is the form for the Weather Forecast app.
class WeatherForm(forms.Form):
    # Define a CharField for the ZIP code with a maximum length of 5 characters.
    zip_code = forms.CharField(label="ZIP Code:", max_length=5)

    # Define a custom clean method for the zip_code field.
    def clean_zip_code(self):
        # Retrieve the zip_code from the cleaned_data dictionary.
        zip_code = self.cleaned_data["zip_code"]
        try:
            # Attempt to access the zip_code in a ZIP code database (zdb).
            # This line will raise an exception if the zip code is not found in the database.
            zdb[zip_code]
        except (KeyError, IndexError):
            raise ValidationError(
                "You've made an invalid submission. Please enter a valid ZIP code."
            )
        # If no exception is raised, return the validated zip_code.
        return zip_code


# NEW
# This is the form for the DNS Tool app.

from django import forms


class DomainForm(forms.Form):
    domain = forms.CharField(
        label="Enter Domain Name:",
        max_length=253,
        help_text="Enter a fully qualified domain name (e.g., example.com).",
    )


# Thi sis the form for the IP Tool app.
from django import forms
import ipaddress


class IPForm(forms.Form):
    ip_address = forms.CharField(
        label="Enter IP Address:",
        max_length=45,
        help_text="Enter a valid IPv4 or IPv6 address (e.g., 192.168.1.1 or 2001:0db8:85a3:0000:0000:8a2e:0370:7334).",
    )

    def clean_ip_address(self):
        ip = self.cleaned_data["ip_address"]
        try:
            ipaddress.ip_address(ip)
        except ValueError:
            raise forms.ValidationError("Enter a valid IP address.")
        return ip
