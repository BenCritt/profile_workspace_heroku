# Provides the base Form class and form field classes for building and validating form data across all apps.
from django import forms

# Used to raise custom validation errors for invalid user inputs, such as in the WeatherForm and IPForm.
from django.core.exceptions import ValidationError

# Provides access to ZIP code data for validation in the WeatherForm, ensuring users input valid ZIP codes.
from pyzipcode import ZipCodeDatabase

# Provides built-in validation for form fields:
# - MinValueValidator and MaxValueValidator: Used in MonteCarloForm to ensure numerical fields stay within specified ranges.
# - MinLengthValidator and MaxLengthValidator: Used in TextForm to ensure text fields meet character length requirements.
from django.core.validators import (
    MinValueValidator,
    MaxValueValidator,
    MinLengthValidator,
    MaxLengthValidator,
)

# Used in IPForm to validate whether the input is a valid IPv4 or IPv6 address.
import ipaddress

# Used in various form cleaning methods, such as SitemapForm and SSLCheckForm, to parse and validate URLs.
from urllib.parse import urlparse

# Imports a custom utility function to normalize URLs, adding schemes like "https://" if missing.
# Utilized in the clean methods of forms like SitemapForm and SSLCheckForm.
from .utils import normalize_url


# SEO Head Checker
class SitemapForm(forms.Form):
    """
    A Django form for collecting sitemap URLs and file type preferences for the SEO Head Checker tool.

    Fields:
        sitemap_url (str): The URL of the sitemap to process. Must be a valid URL.
        file_type (str): The preferred output file format, either Excel or CSV.
    """

    sitemap_url = forms.CharField(
        # Label displayed on the form with SEO-friendly lanaguage.
        label="Enter Sitemap URL",
        # Make this field mandatory.
        required=True,
        # Provide a placeholder so the expected input is made clear to the user.
        widget=forms.TextInput(
            attrs={
                "name": "sitemap_url",
                "id": "sitemap_url",
                "placeholder": "bencritt.net/sitemap.xml",
            }
        ),
    )

    def clean_sitemap_url(self):
        """
        Cleans and validates the 'sitemap_url' field submitted in the form.

        - Strips leading and trailing whitespace from the input URL.
        - Normalizes the URL (e.g., ensures it starts with 'http://' or 'https://').
        - Raises a validation error if the URL is invalid or cannot be normalized.

        Returns:
            str: The normalized URL if valid.

        Raises:
            forms.ValidationError: If the URL is invalid.
        """
        # Get the user-submitted URL and strip any whitespace
        url = self.cleaned_data["sitemap_url"].strip()
        try:
            # Normalize the URL (ensures it starts with http:// or https://)
            return normalize_url(url)
        except Exception:
            # Raise a validation error if the URL is invalid
            raise forms.ValidationError("Please enter a valid sitemap URL.")


# Freight Carrier Safety Reporter
class CarrierSearchForm(forms.Form):
    search_value = forms.CharField(label="Enter USDOT Number", max_length=50)

    # Handle an invalid submission.
    def clean_search_value(self):
        data = self.cleaned_data["search_value"]

        # Ensure the USDOT number is numeric
        if not data.isdigit():
            raise forms.ValidationError("Please enter a valid USDOT number.")

        return data


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
        label="",
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


# This is the form for the DNS Tool app.
class DomainForm(forms.Form):
    # Define a form field for the domain input
    domain = forms.CharField(
        # Label that will be displayed with the input field
        label="Enter Domain Name",
        # Maximum length of the input string
        max_length=253,
        widget=forms.TextInput(
            # Placeholder text to provide an example of the expected input
            attrs={"placeholder": "bencritt.net"}
        ),
    )


# This is the form for the IP Tool app.
class IPForm(forms.Form):
    # Define a form field for the IP address input
    ip_address = forms.CharField(
        # Label that will be displayed with the input field
        label="Enter IP Address",
        # Maximum length of the input string, suitable for IPv6 addresses
        max_length=45,
        # help_text="Enter a valid IPv4 or IPv6 address.",
    )

    # Method to clean and validate the IP address input
    def clean_ip_address(self):
        # Retrieve the cleaned data for the IP address field
        ip = self.cleaned_data["ip_address"]
        try:
            # Validate the IP address using the ipaddress module
            ipaddress.ip_address(ip)
        except ValueError:
            # If validation fails, raise a ValidationError
            raise forms.ValidationError("Enter a valid IP address.")
        # Return the validated IP address
        return ip


# This is the form for the SSL Certificate Checker app.
class SSLCheckForm(forms.Form):
    url = forms.CharField(
        label="Enter Website URL",
        max_length=200,
        widget=forms.TextInput(attrs={"placeholder": "bencritt.net"}),
        error_messages={
            "required": "Please enter a URL.",
            "invalid": "Please enter a valid URL.",
        },
    )

    def clean_url(self):
        url = self.cleaned_data.get("url")

        # Check if URL has a scheme (http or https)
        parsed_url = urlparse(url)
        if not parsed_url.scheme:
            # If no scheme is provided, prepend 'https://'
            url = "https://" + url

        return url
