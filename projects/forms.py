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
                "placeholder": "nintendo.com",
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
                "rows": 10,
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
    
    # NEW BEGIN

# --- Glass Volume Calculator ---
class GlassVolumeForm(forms.Form):
    SHAPE_CHOICES = [
        ("cylinder", "Cylinder / Round Mold"),
        ("rectangle", "Rectangle / Square Dam"),
    ]
    UNIT_CHOICES = [
        ("inches", "Inches"),
        ("cm", "Centimeters"),
    ]

    shape = forms.ChoiceField(
        choices=SHAPE_CHOICES,
        label="Mold Shape",
        initial="cylinder",
        widget=forms.Select(attrs={"class": "form-select"})
    )
    units = forms.ChoiceField(
        choices=UNIT_CHOICES,
        label="Measurement Units",
        initial="inches",
        widget=forms.Select(attrs={"class": "form-select"})
    )
    # Dimensions
    diameter = forms.FloatField(
        required=False,
        label="Diameter",
        help_text="Required for Cylinder shapes.",
        widget=forms.NumberInput(attrs={"class": "form-control", "placeholder": "e.g. 6.0"})
    )
    length = forms.FloatField(
        required=False,
        label="Length",
        help_text="Required for Rectangle shapes.",
        widget=forms.NumberInput(attrs={"class": "form-control", "placeholder": "e.g. 8.0"})
    )
    width = forms.FloatField(
        required=False,
        label="Width",
        help_text="Required for Rectangle shapes.",
        widget=forms.NumberInput(attrs={"class": "form-control", "placeholder": "e.g. 4.0"})
    )
    depth = forms.FloatField(
        required=True,
        label="Target Thickness / Depth",
        help_text="Thickness of the finished piece.",
        widget=forms.NumberInput(attrs={"class": "form-control", "placeholder": "e.g. 0.375"})
    )
    
    def clean(self):
        cleaned_data = super().clean()
        shape = cleaned_data.get("shape")
        
        # Conditional validation based on shape selection
        if shape == "cylinder":
            if not cleaned_data.get("diameter"):
                self.add_error("diameter", "Diameter is required for cylinder shapes.")
        elif shape == "rectangle":
            if not cleaned_data.get("length"):
                self.add_error("length", "Length is required for rectangle shapes.")
            if not cleaned_data.get("width"):
                self.add_error("width", "Width is required for rectangle shapes.")
        
        return cleaned_data
    
# --- Kiln Schedule Generator ---
class KilnScheduleForm(forms.Form):
    BRAND_CHOICES = [
        ("bullseye", "Bullseye (COE 90)"),
        ("system96", "System 96 / Oceanside (COE 96)"),
        ("verre", "Verre (COE 90)"),
        ("soft", "Soft Glass / Effetre (COE 104)"),
        ("boro", "Borosilicate (COE 33)"),
    ]
    PROJECT_CHOICES = [
        ("full_fuse", "Full Fuse (Smooth surface)"),
        ("tack_fuse", "Tack Fuse (Textured surface)"),
        ("slump", "Slump (Shape into mold)"),
        ("fire_polish", "Fire Polish (Shine edges)"),
    ]
    THICKNESS_CHOICES = [
        ("standard", "Standard (Up to 6mm / 0.25\")"),
        ("thick", "Thick (Up to 9mm / 0.375\")"),
        ("extra_thick", "Extra Thick (Up to 12mm / 0.5\")"),
    ]

    brand = forms.ChoiceField(
        choices=BRAND_CHOICES,
        label="Glass Manufacturer",
        initial="bullseye",
        help_text="Determines the correct annealing temperature.",
        widget=forms.Select(attrs={"class": "form-select"})
    )
    project_type = forms.ChoiceField(
        choices=PROJECT_CHOICES,
        label="Firing Schedule Type",
        widget=forms.Select(attrs={"class": "form-select"})
    )
    thickness = forms.ChoiceField(
        choices=THICKNESS_CHOICES,
        label="Total Project Thickness",
        help_text="Thicker projects require slower heating to prevent thermal shock.",
        widget=forms.Select(attrs={"class": "form-select"})
    )

# --- Stained Glass Cost Estimator ---
class StainedGlassCostForm(forms.Form):
    # Dimensions
    width = forms.FloatField(
        label="Width (inches)",
        widget=forms.NumberInput(attrs={"class": "form-control", "placeholder": "e.g. 12"})
    )
    height = forms.FloatField(
        label="Height (inches)",
        widget=forms.NumberInput(attrs={"class": "form-control", "placeholder": "e.g. 24"})
    )
    
    # Project Details
    pieces = forms.IntegerField(
        label="Number of Pieces",
        help_text="Total number of glass pieces in the pattern.",
        widget=forms.NumberInput(attrs={"class": "form-control", "placeholder": "e.g. 50"})
    )
    
    # Costs
    glass_price = forms.FloatField(
        label="Avg. Glass Cost ($/sq ft)",
        initial=15.00,
        widget=forms.NumberInput(attrs={"class": "form-control"})
    )
    labor_rate = forms.FloatField(
        label="Hourly Labor Rate ($)",
        initial=25.00,
        widget=forms.NumberInput(attrs={"class": "form-control"})
    )
    estimated_hours = forms.FloatField(
        label="Estimated Labor Hours",
        required=False,
        help_text="Leave blank to auto-calculate based on piece count (avg 15 mins/piece).",
        widget=forms.NumberInput(attrs={"class": "form-control"})
    )

# --- Kiln Controller Utilities ---
class TempConverterForm(forms.Form):
    # Field to identify which form is being submitted
    action = forms.CharField(widget=forms.HiddenInput(), initial="convert")
    
    temperature = forms.FloatField(
        label="Enter Temperature",
        widget=forms.NumberInput(attrs={"class": "form-control", "placeholder": "e.g. 1490"})
    )
    from_unit = forms.ChoiceField(
        choices=[("F", "Fahrenheit (°F)"), ("C", "Celsius (°C)")],
        label="Convert From",
        widget=forms.Select(attrs={"class": "form-select"})
    )

class RampCalculatorForm(forms.Form):
    # Field to identify which form is being submitted
    action = forms.CharField(widget=forms.HiddenInput(), initial="ramp")

    start_temp = forms.FloatField(
        label="Current Temp",
        widget=forms.NumberInput(attrs={"class": "form-control", "placeholder": "e.g. 70"})
    )
    target_temp = forms.FloatField(
        label="Target Temp",
        widget=forms.NumberInput(attrs={"class": "form-control", "placeholder": "e.g. 1225"})
    )
    rate = forms.FloatField(
        label="Rate (°/hour)",
        widget=forms.NumberInput(attrs={"class": "form-control", "placeholder": "e.g. 300"})
    )

    # --- Stained Glass Materials Calculator ---
class StainedGlassMaterialsForm(forms.Form):
    METHOD_CHOICES = [
        ("foil", "Copper Foil Method"),
        ("lead", "Lead Came Method"),
    ]
    
    method = forms.ChoiceField(
        label="Construction Method",
        choices=METHOD_CHOICES,
        initial="foil",
        widget=forms.Select(attrs={"class": "form-select"})
    )
    width = forms.FloatField(
        label="Panel Width (inches)",
        widget=forms.NumberInput(attrs={"class": "form-control", "placeholder": "e.g. 16"})
    )
    height = forms.FloatField(
        label="Panel Height (inches)",
        widget=forms.NumberInput(attrs={"class": "form-control", "placeholder": "e.g. 20"})
    )
    pieces = forms.IntegerField(
        label="Number of Pieces",
        help_text="Count from your pattern.",
        widget=forms.NumberInput(attrs={"class": "form-control", "placeholder": "e.g. 45"})
    )
    waste_factor = forms.IntegerField(
        label="Waste Safety Margin (%)",
        initial=15,
        help_text="Extra material to account for trimming and mistakes.",
        widget=forms.NumberInput(attrs={"class": "form-control"})
    )

# --- Lampwork / Boro Calculator ---
class LampworkMaterialForm(forms.Form):
    GLASS_TYPES = [
        ("boro", "Borosilicate (COE 33)"),
        ("soft", "Soft Glass / Effetre (COE 104)"),
        ("satake", "Satake (COE 120)"), # Japanese Lead Glass
        ("coe90", "Bullseye (COE 90)"),
        ("coe96", "System 96 / Oceanside (COE 96)"),
        ("crystal", "Full Lead Crystal (Generic)"), # Heavy Crystal
        ("quartz", "Quartz / Fused Silica"),
    ]
    FORM_FACTORS = [
        ("rod", "Solid Rod"),
        ("tube", "Tubing"),
    ]

    glass_type = forms.ChoiceField(
        label="Glass Type",
        choices=GLASS_TYPES,
        initial="boro",
        widget=forms.Select(attrs={"class": "form-select"})
    )
    form_factor = forms.ChoiceField(
        label="Glass Shape",
        choices=FORM_FACTORS,
        initial="rod",
        widget=forms.Select(attrs={"class": "form-select", "id": "id_form_factor"})
    )
    diameter_mm = forms.FloatField(
        label="Diameter (mm)",
        widget=forms.NumberInput(attrs={"class": "form-control", "placeholder": "e.g. 12"})
    )
    wall_mm = forms.FloatField(
        label="Wall Thickness (mm)",
        required=False,
        help_text="Required for Tubing.",
        widget=forms.NumberInput(attrs={"class": "form-control", "placeholder": "e.g. 2.2"})
    )
    length_inches = forms.FloatField(
        label="Length Needed (inches)",
        widget=forms.NumberInput(attrs={"class": "form-control", "placeholder": "e.g. 20"})
    )
    quantity = forms.IntegerField(
        label="Quantity",
        initial=1,
        widget=forms.NumberInput(attrs={"class": "form-control"})
    )
    
    def clean(self):
        cleaned_data = super().clean()
        form_factor = cleaned_data.get("form_factor")
        wall = cleaned_data.get("wall_mm")
        diameter = cleaned_data.get("diameter_mm")

        if form_factor == "tube":
            if not wall:
                self.add_error("wall_mm", "Wall thickness is required for tubing.")
            elif diameter and (wall * 2 >= diameter):
                self.add_error("wall_mm", "Wall thickness cannot exceed half the diameter.")
        
        return cleaned_data

# NEW END
# NEW 2 BEGIN
# --- Freight Class Calculator ---
class FreightClassForm(forms.Form):
    length = forms.FloatField(
        label="Length (inches)",
        widget=forms.NumberInput(attrs={"class": "form-control", "placeholder": "e.g. 48"})
    )
    width = forms.FloatField(
        label="Width (inches)",
        widget=forms.NumberInput(attrs={"class": "form-control", "placeholder": "e.g. 40"})
    )
    height = forms.FloatField(
        label="Height (inches)",
        widget=forms.NumberInput(attrs={"class": "form-control", "placeholder": "e.g. 50"})
    )
    weight = forms.FloatField(
        label="Weight per Pallet (lbs)",
        widget=forms.NumberInput(attrs={"class": "form-control", "placeholder": "e.g. 1500"})
    )
    quantity = forms.IntegerField(
        label="Quantity (Pallet Count)",
        initial=1,
        widget=forms.NumberInput(attrs={"class": "form-control"})
    )

# --- Fuel Surcharge Calculator ---
class FuelSurchargeForm(forms.Form):
    trip_miles = forms.FloatField(
        label="Total Trip Miles",
        widget=forms.NumberInput(attrs={"class": "form-control", "placeholder": "e.g. 1200"})
    )
    current_price = forms.FloatField(
        label="Current Diesel Price ($/gal)",
        widget=forms.NumberInput(attrs={"class": "form-control", "placeholder": "e.g. 3.85"})
    )
    base_price = forms.FloatField(
        label="Base 'Peg' Price ($/gal)",
        initial=1.20,
        help_text="The baseline fuel cost established in your contract (often $1.20).",
        widget=forms.NumberInput(attrs={"class": "form-control"})
    )
    mpg = forms.FloatField(
        label="Truck MPG",
        initial=6.0,
        help_text="Average miles per gallon (Industry standard is usually 6.0 or 6.5).",
        widget=forms.NumberInput(attrs={"class": "form-control"})
    )

# --- HOS Trip Planner ---
class HOSTripPlannerForm(forms.Form):
    total_miles = forms.FloatField(
        label="Total Trip Miles",
        widget=forms.NumberInput(attrs={"class": "form-control", "placeholder": "e.g. 1450"})
    )
    avg_speed = forms.FloatField(
        label="Average Speed (mph)",
        initial=55.0,
        widget=forms.NumberInput(attrs={"class": "form-control", "placeholder": "e.g. 55"})
    )
    start_date = forms.DateField(
        label="Start Date",
        widget=forms.DateInput(attrs={"class": "form-control", "type": "date"})
    )
    start_time = forms.TimeField(
        label="Start Time",
        widget=forms.TimeInput(attrs={"class": "form-control", "type": "time"})
    )
# NEW 2 END