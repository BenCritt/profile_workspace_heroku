# Provides the base Form class and form field classes for building and validating form data across all apps.
from django import forms

# Used to raise custom validation errors for invalid user inputs, such as in the WeatherForm and IPForm.
from django.core.exceptions import ValidationError

# Provides access to ZIP code data for validation in the WeatherForm, ensuring users input valid ZIP codes.
from pyzipcode import ZipCodeDatabase

# Provides built-in validation for form fields:
from django.core.validators import (
    MinValueValidator,
    MaxValueValidator,
    MinLengthValidator,
    MaxLengthValidator,
    URLValidator
)

# Used in IPForm to validate whether the input is a valid IPv4 or IPv6 address.
import ipaddress

# Used in various form cleaning methods to parse and validate URLs.
from urllib.parse import urlparse

# Imports a custom utility function to normalize URLs.
from .utils import normalize_url

# Used by the Ham Radio Call Sign Lookup app.
import re

# --- Cookie Audit ---
class CookieAuditForm(forms.Form):
    url = forms.CharField(
        label="Enter Website URL",
        required=True,
        widget=forms.TextInput(
            attrs={
                "placeholder": "bencritt.net",
                "class": "form-control",
                "autofocus": "autofocus",
            }
        ),
    )

    def clean_url(self):
        raw = (self.cleaned_data.get("url") or "").strip()
        if raw and not urlparse(raw).scheme:
            raw = f"https://{raw}"
        validator = URLValidator(schemes=["http", "https"])
        try:
            validator(raw)
        except ValidationError:
            raise forms.ValidationError("Please enter a valid website URL (http/https).")
        return raw


# --- Font Inspector ---
class FontInspectorForm(forms.Form):
    url = forms.CharField(
        label="Page URL",
        widget=forms.TextInput(
            attrs={
                "placeholder": "bencritt.net",
                "class": "form-control",
            }
        ),
    )

    def clean_url(self):
        raw = self.cleaned_data["url"].strip()
        if not urlparse(raw).scheme:
            raw = f"https://{raw}"
        validator = URLValidator(schemes=["http", "https"])
        try:
            validator(raw)
        except ValidationError as e:
            raise forms.ValidationError(e.message)
        return raw


# --- Ham Radio Call Sign Lookup ---
CALLSIGN_RE = re.compile(r"^[A-Za-z0-9]{3,8}$")

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


# --- XML Splitter ---
class XMLUploadForm(forms.Form):
    file = forms.FileField(
        label="Upload your XML file here (25 MB limit)",
        widget=forms.ClearableFileInput(attrs={
            "class": "form-control",
            "accept": ".xml",
            "onchange": (
                "if(this.files.length && this.files[0].size > 26214400){"
                "alert('File is too large (limit: 25 MB).');"
                "this.value='';}"
            ),
        }),
    )

    def clean_file(self):
        f = self.cleaned_data["file"]
        if not f.name.lower().endswith(".xml"):
            raise forms.ValidationError(
                "This tool only accepts XML files. Please upload a file with the .xml extension."
            )
        allowed_types = {"text/xml", "application/xml", "application/octet-stream"}
        if getattr(f, "content_type", None) not in allowed_types:
            raise forms.ValidationError("That file doesn’t look like XML.")
        MAX_XML_SIZE = 25 * 1024 * 1024   # 25 MB
        if f.size > MAX_XML_SIZE:
            raise forms.ValidationError(
                f"File is {f.size/1_048_576:.1f} MB; the limit is {MAX_XML_SIZE/1_048_576:.0f} MB."
            )
        return f


# --- SEO Head Checker ---
class SitemapForm(forms.Form):
    sitemap_url = forms.CharField(
        label="Enter Sitemap URL",
        required=True,
        widget=forms.TextInput(
            attrs={
                "name": "sitemap_url",
                "id": "sitemap_url",
                "class": "form-control",
                "placeholder": "bencritt.net/sitemap.xml",
            }
        ),
    )

    def clean_sitemap_url(self):
        url = self.cleaned_data["sitemap_url"].strip()
        try:
            return normalize_url(url)
        except Exception:
            raise forms.ValidationError("Please enter a valid sitemap URL.")


# --- Freight Carrier Safety Reporter ---
class CarrierSearchForm(forms.Form):
    search_value = forms.CharField(
        label="Enter USDOT Number", 
        max_length=50,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "e.g. 1234567"
            }
        )
    )

    def clean_search_value(self):
        data = self.cleaned_data["search_value"]
        if not data.isdigit():
            raise forms.ValidationError("Please enter a valid USDOT number.")
        return data


# --- Grade Level Text Analyzer ---
class TextForm(forms.Form):
    text = forms.CharField(
        label="Enter text to analyze",
        widget=forms.Textarea(
            attrs={
                "class": "form-control", 
                "rows": 10,  # Updated to 10 as requested
                "style": "max-width: 800px;" # Matches the container width in your template
            }
        ),
        validators=[
            MinLengthValidator(1200, message="The sample you've provided is too short."),
            MaxLengthValidator(10000, message="The sample you've provided is too long."),
        ],
    )


# --- QR Code Generator ---
class QRForm(forms.Form):
    qr_text = forms.CharField(
        label="Enter Text or URL",
        max_length=8000,
        widget=forms.TextInput(attrs={
            "class": "form-control", 
            "placeholder": "https://www.example.com",
            "aria-label": "Text content for QR code generation"
        }),
        help_text="Enter the URL or text you want the QR code to point to."
    )


# --- Monte Carlo Simulator ---
class MonteCarloForm(forms.Form):
    sim_quantity = forms.IntegerField(
        label="Number of Simulations",
        widget=forms.NumberInput(attrs={"class": "form-control"}),
        validators=[
            MinValueValidator(1, message="The number of simulations must be at least 1."),
            MaxValueValidator(1000000, message="The number of simulations cannot exceed 1,000,000."),
        ],
    )
    min_val = forms.FloatField(
        label="Minimum Value",
        widget=forms.NumberInput(attrs={"class": "form-control"})
    )
    max_val = forms.FloatField(
        label="Maximum Value",
        widget=forms.NumberInput(attrs={"class": "form-control"})
    )
    target_val = forms.FloatField(
        label="Target Value",
        widget=forms.NumberInput(attrs={"class": "form-control"})
    )
    
    # Second Range (Optional)
    second_sim_quantity = forms.IntegerField(
        required=False,
        label="Second Number of Simulations",
        widget=forms.NumberInput(attrs={"class": "form-control"}),
        validators=[
            MinValueValidator(1, message="Must be at least 1 if used."),
            MaxValueValidator(1000000, message="Cannot exceed 1,000,000."),
        ],
    )
    second_min_val = forms.FloatField(
        label="Second Minimum Value", 
        required=False,
        widget=forms.NumberInput(attrs={"class": "form-control"})
    )
    second_max_val = forms.FloatField(
        label="Second Maximum Value", 
        required=False,
        widget=forms.NumberInput(attrs={"class": "form-control"})
    )
    second_target_val = forms.FloatField(
        label="Second Target Value", 
        required=False,
        widget=forms.NumberInput(attrs={"class": "form-control"})
    )


# --- Weather Forecast ---
zdb = ZipCodeDatabase()

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


# --- DNS Tool ---
class DomainForm(forms.Form):
    domain = forms.CharField(
        label="Enter Domain Name",
        max_length=253,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "bencritt.net"
            }
        ),
    )


# --- IP Tool ---
class IPForm(forms.Form):
    ip_address = forms.CharField(
        label="Enter IP Address",
        max_length=45,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "8.8.8.8"
            }
        )
    )

    def clean_ip_address(self):
        ip = self.cleaned_data["ip_address"]
        try:
            ipaddress.ip_address(ip)
        except ValueError:
            raise forms.ValidationError("Enter a valid IP address.")
        return ip


# --- SSL Certificate Checker ---
class SSLCheckForm(forms.Form):
    url = forms.CharField(
        label="Enter Website URL",
        max_length=200,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "bencritt.net"
            }
        ),
        error_messages={
            "required": "Please enter a URL.",
            "invalid": "Please enter a valid URL.",
        },
    )

    def clean_url(self):
        url = self.cleaned_data.get("url")
        parsed_url = urlparse(url)
        if not parsed_url.scheme:
            url = "https://" + url
        return url