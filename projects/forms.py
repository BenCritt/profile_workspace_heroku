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
                "placeholder": "1234567"
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
            "placeholder": "https://www.bencritt.net",
            "aria-label": "Text content for QR code generation"
        }),
        help_text="Enter the URL or text you want the QR code to point to."
    )


# --- Monte Carlo Simulator ---
class MonteCarloForm(forms.Form):
    sim_quantity = forms.IntegerField(
        label="Number of Simulations",
        widget=forms.NumberInput(attrs={
            "class": "form-control",
            "inputmode": "numeric", # Standard numeric keypad
            "step": "1",            # Whole numbers only
            "min": "1"              # Prevents quantity less than 1
            }),
        validators=[
            MinValueValidator(1, message="The number of simulations must be at least 1."),
            MaxValueValidator(1000000, message="The number of simulations cannot exceed 1,000,000."),
        ],
    )
    min_val = forms.FloatField(
        label="Minimum Value",
        widget=forms.NumberInput(attrs={
            "class": "form-control",
            "inputmode": "decimal",  # Triggers the correct mobile keyboard
            "step": "any"            # Allows decimals and negative numbers
            })
    )
    max_val = forms.FloatField(
        label="Maximum Value",
        widget=forms.NumberInput(attrs={
            "class": "form-control",
            "inputmode": "decimal",  # Triggers the correct mobile keyboard
            "step": "any"            # Allows decimals and negative numbers
            })
    )
    target_val = forms.FloatField(
        label="Target Value",
        widget=forms.NumberInput(attrs={
            "class": "form-control",
            "inputmode": "decimal",  # Triggers the correct mobile keyboard
            "step": "any"            # Allows decimals and negative numbers
            })
    )
    
    # Second Range (Optional)
    second_sim_quantity = forms.IntegerField(
        required=False,
        label="Second Number of Simulations",
        widget=forms.NumberInput(attrs={
            "class": "form-control",
            "inputmode": "numeric", # Standard numeric keypad
            "min": "1"              # Prevents negative numbers
            }),
        validators=[
            MinValueValidator(1, message="Must be at least 1 if used."),
            MaxValueValidator(1000000, message="Cannot exceed 1,000,000."),
        ],
    )
    second_min_val = forms.FloatField(
        label="Second Minimum Value", 
        required=False,
        widget=forms.NumberInput(attrs={
            "class": "form-control",
            "inputmode": "decimal",  # Triggers the correct mobile keyboard
            "step": "any"            # Allows decimals and negative numbers
            })
    )
    second_max_val = forms.FloatField(
        label="Second Maximum Value", 
        required=False,
        widget=forms.NumberInput(attrs={
            "class": "form-control",
            "inputmode": "decimal",  # Triggers the correct mobile keyboard
            "step": "any"            # Allows decimals and negative numbers
            })
    )
    second_target_val = forms.FloatField(
        label="Second Target Value", 
        required=False,
        widget=forms.NumberInput(attrs={
            "class": "form-control",
            "inputmode": "decimal",  # Triggers the correct mobile keyboard
            "step": "any"            # Allows decimals and negative numbers
            })
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
    # NEW: Glass choices identical to the Lampwork calculator
    GLASS_TYPES = [
        ("boro", "Borosilicate (COE 33)"),
        ("soft", "Soft Glass / Effetre (COE 104)"),
        ("coe90", "Bullseye (COE 90)"),
        ("coe96", "System 96 / Oceanside (COE 96)"),
        ("crystal", "Full Lead Crystal (Generic)"),
        ("satake", "Satake (COE 120)"),
        ("quartz", "Quartz / Fused Silica"),
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
    # NEW: Glass Type Field
    glass_type = forms.ChoiceField(
        label="Glass Manufacturer",
        choices=GLASS_TYPES,
        initial="coe90",
        help_text="Crucial for calculating exact weight.",
        widget=forms.Select(attrs={"class": "form-select"})
    )
    
    # Dimensions
    diameter = forms.FloatField(
        required=False,
        label="Diameter",
        help_text="Required for Cylinder shapes.",
        widget=forms.NumberInput(attrs={
            "class": "form-control", 
            "placeholder": "6.0",
            "inputmode": "decimal", # Standard numeric keypad
            "min": "0.00001"        # Prevents negative numbers
            }),
        validators=[MinValueValidator(0.00001, message="Diameter must be no less than 0.00001 inches.")],
    )
    length = forms.FloatField(
        required=False,
        label="Length",
        help_text="Required for Rectangle shapes.",
        widget=forms.NumberInput(attrs={
            "class": "form-control", 
            "placeholder": "8.0",
            "inputmode": "decimal", # Standard numeric keypad
            "min": "0.00001"        # Prevents negative numbers
            }),
        validators=[MinValueValidator(0.00001, message="Length must be no less than 0.00001 inches.")],
    )
    width = forms.FloatField(
        required=False,
        label="Width",
        help_text="Required for Rectangle shapes.",
        widget=forms.NumberInput(attrs={
            "class": "form-control", 
            "placeholder": "4.0",
            "inputmode": "decimal", # Standard numeric keypad
            "min": "0.00001"        # Prevents negative numbers
            }),
        validators=[MinValueValidator(0.00001, message="Width must be no less than 0.00001 inches.")],
    )
    depth = forms.FloatField(
        required=True,
        label="Target Thickness / Depth",
        help_text="Thickness of the finished piece.",
        widget=forms.NumberInput(attrs={
            "class": "form-control", 
            "placeholder": "0.375",
            "inputmode": "decimal", # Standard numeric keypad
            "min": "0.00001"        # Prevents negative numbers
            }),
        validators=[MinValueValidator(0.00001, message="Target thickness must be no less than 0.00001 inches.")],
    )
    waste_factor = forms.IntegerField(
        label="Waste / Coldworking Buffer (%)",
        help_text="Account for pot-melt loss and grinding.",
        widget=forms.NumberInput(attrs={
            "class": "form-control",
            "inputmode": "decimal", # Triggers the correct mobile keyboard
            "min": "0",             # Prevents negative numbers
            "placeholder": "15"
            }),
        validators=[MinValueValidator(0, message="Waste factor cannot be negative.")],
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
        ("contour_fuse", "Contour Fuse (Softened edges)"),
        ("tack_fuse", "Tack Fuse (Textured surface)"),
        ("slump", "Slump (Shape into mold)"),
        ("fire_polish", "Fire Polish (Shine edges)"),
    ]
    THICKNESS_CHOICES = [
        ("single", "1 Layer / Standard (3mm)"),
        ("two_layer", "2 Layers / Thick (6mm)"),
        ("multi_layer", "3+ Layers / Extra Thick (9mm+)"),
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
        label="Layers / Total Thickness",
        help_text="Multi-layer projects require a 'Bubble Squeeze' and longer annealing times.",
        widget=forms.Select(attrs={"class": "form-select"})
    )

# --- Stained Glass Cost Estimator ---
class StainedGlassCostForm(forms.Form):
    # Dimensions
    width = forms.FloatField(
        label="Width (inches)",
        widget=forms.NumberInput(attrs={
            "class": "form-control", 
            "placeholder": "12",
            "inputmode": "decimal", # Triggers the correct mobile keyboard
            "min": "0.00001"        # Prevents negative numbers
            }),
        validators=[MinValueValidator(0.00001, message="Width cannot be less than 0.00001 inches.")],
    )
    height = forms.FloatField(
        label="Height (inches)",
        widget=forms.NumberInput(attrs={
            "class": "form-control", 
            "placeholder": "24",
            "inputmode": "decimal", # Triggers the correct mobile keyboard
            "min": "0.00001"        # Prevents negative numbers
            }),
        validators=[MinValueValidator(0.00001, message="Height cannot be less than 0.00001 inches.")],
    )
    
    # Project Details
    pieces = forms.IntegerField(
        label="Number of Pieces",
        help_text="Total number of glass pieces in the pattern.",
        widget=forms.NumberInput(attrs={
            "class": "form-control", 
            "placeholder": "50",
            "inputmode": "numeric", # Standard numeric keypad
            "step": "1",            # Whole numbers only
            "min": "1"              # Prevents quanitity less than 1
        }),
        validators=[MinValueValidator(1, message="Quantity cannot be less than 1.")],
    )
    
    # Costs
    glass_price = forms.FloatField(
        label="Avg. Glass Cost ($/sq ft)",
        widget=forms.NumberInput(attrs={
            "class": "form-control",
            "inputmode": "decimal", # Triggers the correct mobile keyboard
            "min": "0.01",          # Prevents values less than a cent
            "placeholder": "15.00"
            }),
        validators=[MinValueValidator(0.01, message="Cost cannot be less than $0.01 per square foot.")],
    )
    labor_rate = forms.FloatField(
        label="Hourly Labor Rate ($)",
        widget=forms.NumberInput(attrs={
            "class": "form-control",
            "inputmode": "decimal", # Triggers the correct mobile keyboard
            "min": "0.01",          # Prevents values less than a cent
            "placeholder": "25.00"
            }),
        validators=[MinValueValidator(0.01, message="Labor rate cannot be less than $0.01 per hour.")],
    )
    estimated_hours = forms.FloatField(
        label="Estimated Labor Hours",
        required=False,
        help_text="Leave blank to auto-calculate based on piece count (avg 15 mins/piece).",
        widget=forms.NumberInput(attrs={
            "class": "form-control",
            "inputmode": "decimal", # Triggers the correct mobile keyboard
            "min": "0.0166"         # Prevents values less than one minute
            }),
        validators=[MinValueValidator(0.0166, message="Labor hours cannot be less than one minute.")],
    )
    markup = forms.FloatField(
        label="Profit Markup Multiplier",
        help_text="Standard is 2.0x for retail. Wholesale is often 1.5x.",
        widget=forms.NumberInput(attrs={
            "class": "form-control", 
            "step": "0.1",
            "inputmode": "decimal", # Triggers the correct mobile keyboard
            "min": "0",             # Prevents negative numbers
            "placeholder": "2.0"
            }),
        validators=[MinValueValidator(0, message="Profit markup cannot be negative.")],
    )

# --- Kiln Controller Utilities ---
class TempConverterForm(forms.Form):
    # Field to identify which form is being submitted
    action = forms.CharField(widget=forms.HiddenInput(), initial="convert")
    
    temperature = forms.FloatField(
        label="Enter Temperature",
        widget=forms.NumberInput(attrs={
            "class": "form-control", 
            "placeholder": "1490",
            "inputmode": "decimal",  # Triggers the correct mobile keyboard
            "step": "any"            # Allows decimals and negative numbers
            })
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
        widget=forms.NumberInput(attrs={
            "class": "form-control", 
            "placeholder": "70",
            "inputmode": "decimal",  # Triggers the correct mobile keyboard
            "step": "any"            # Allows decimals and negative numbers
            })
    )
    target_temp = forms.FloatField(
        label="Target Temp",
        widget=forms.NumberInput(attrs={
            "class": "form-control", 
            "placeholder": "1225",
            "inputmode": "decimal",  # Triggers the correct mobile keyboard
            "step": "any"            # Allows decimals and negative numbers
            })
    )
    rate = forms.FloatField(
        label="Rate (°/hour)",
        widget=forms.NumberInput(attrs={
            "class": "form-control", 
            "placeholder": "300",
            "inputmode": "decimal", # Triggers the correct mobile keyboard
            "min": "0.00001"        # Prevents negative numbers
            }),
        validators=[MinValueValidator(0.00001, message="Rate must be no less than 0.00001 °/hour.")],
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
        widget=forms.NumberInput(attrs={
            "class": "form-control", 
            "placeholder": "16",
            "inputmode": "decimal", # Triggers the correct mobile keyboard
            "min": "0.00001"        # Prevents negative numbers
            }),
        validators=[MinValueValidator(0.00001, message="Width must be no less than 0.00001 inches.")],
    )
    height = forms.FloatField(
        label="Panel Height (inches)",
        widget=forms.NumberInput(attrs={
            "class": "form-control", 
            "placeholder": "20",
            "inputmode": "decimal", # Triggers the correct mobile keyboard
            "min": "0.00001"        # Prevents negative numbers
            }),
        validators=[MinValueValidator(0.00001, message="Height must be no less than 0.00001 inches.")],
    )
    pieces = forms.IntegerField(
        label="Number of Pieces",
        help_text="Count from your pattern.",
        widget=forms.NumberInput(attrs={
            "class": "form-control", 
            "placeholder": "45",
            "inputmode": "numeric", # Standard numeric keypad
            "step": "1",            # Whole numbers only
            "min": "1"              # Prevents quanitity less than 1
            }),
        validators=[MinValueValidator(1, message="Quantity cannot be less than 1.")],
    )
    waste_factor = forms.IntegerField(
        label="Waste Safety Margin (%)",
        help_text="Extra material to account for trimming and mistakes.",
        widget=forms.NumberInput(attrs={
            "class": "form-control",
            "inputmode": "decimal", # Triggers the correct mobile keyboard
            "min": "0",       # Prevents negative numbers
            "placeholder": "15"
            }),
        validators=[MinValueValidator(0, message="Waste safety margin must be no less than 0%")],
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
        widget=forms.NumberInput(attrs={
            "class": "form-control", 
            "placeholder": "12",
            "inputmode": "decimal", # Triggers the correct mobile keyboard
            "min": "0.00001"        # Prevents negative numbers
            }),
        validators=[MinValueValidator(0.00001, message="Diameter must be no less than 0.00001 mm")],
    )
    wall_mm = forms.FloatField(
        label="Wall Thickness (mm)",
        required=False,
        help_text="Required for Tubing.",
        widget=forms.NumberInput(attrs={
            "class": "form-control", 
            "placeholder": "2.2",
            "inputmode": "decimal", # Triggers the correct mobile keyboard
            "min": "0.00001"        # Prevents negative numbers
            }),
        validators=[MinValueValidator(0.00001, message="Wall thickness must be no less than 0.00001 mm")],
    )
    length_inches = forms.FloatField(
        label="Length Needed (inches)",
        help_text="Standard Boro rods are ~20 inches. Soft glass is ~13 inches.",
        widget=forms.NumberInput(attrs={
            "class": "form-control", 
            "placeholder": "20",
            "inputmode": "decimal", # Triggers the correct mobile keyboard
            "min": "0.00001"        # Prevents negative numbers
            }),
        validators=[MinValueValidator(0.00001, message="Length must be no less than 0.00001 inches")],
    )
    quantity = forms.IntegerField(
        label="Quantity",
        widget=forms.NumberInput(attrs={
            "class": "form-control",
            "inputmode": "numeric", # Standard numeric keypad
            "step": "1",            # Whole numbers only
            "min": "1",              # Prevents quantity less than 1
            "placeholder": "1"
            }),
        validators=[MinValueValidator(1, message="Quantity cannot be less than 1.")],
    )
    
    def clean(self):
        cleaned_data = super().clean()
        form_factor = cleaned_data.get("form_factor")
        wall = cleaned_data.get("wall_mm")
        diameter = cleaned_data.get("diameter_mm")

        if form_factor == "tube":
            if not wall:
                self.add_error("wall_mm", "Wall thickness is required for tubing.")
            elif diameter and wall and (wall * 2 >= diameter):
                self.add_error("wall_mm", "Wall thickness cannot be equal to or greater than half the diameter.")
        
        return cleaned_data

# --- Freight Class Calculator ---
class FreightClassForm(forms.Form):
    length = forms.FloatField(
        label="Length (inches)",
        widget=forms.NumberInput(attrs={
            "class": "form-control", 
            "placeholder": "48",
            "inputmode": "decimal", # Triggers the correct mobile keyboard
            "min": "0.00001"        # Prevents negative numbers
            }),
        validators=[MinValueValidator(0.00001, message="Length must be no less than 0.00001 inches")],
    )
    width = forms.FloatField(
        label="Width (inches)",
        widget=forms.NumberInput(attrs={
            "class": "form-control", 
            "placeholder": "40",
            "inputmode": "decimal", # Triggers the correct mobile keyboard
            "min": "0.00001"        # Prevents negative numbers
            }),
        validators=[MinValueValidator(0.00001, message="Width must be no less than 0.00001 inches")],
    )
    height = forms.FloatField(
        label="Height (inches)",
        widget=forms.NumberInput(attrs={
            "class": "form-control", 
            "placeholder": "50",
            "inputmode": "decimal", # Triggers the correct mobile keyboard
            "min": "0.00001"        # Prevents negative numbers
            }),
        validators=[MinValueValidator(0.00001, message="Height must be no less than 0.00001 inches")],
    )
    weight = forms.FloatField(
        label="Weight per Pallet (lbs)",
        widget=forms.NumberInput(attrs={
            "class": "form-control", 
            "placeholder": "1500",
            "inputmode": "decimal", # Triggers the correct mobile keyboard
            "min": "0.00001"        # Prevents negative numbers
            }),
        validators=[MinValueValidator(0.00001, message="Weight must be no less than 0.00001 lbs.")],
    )
    quantity = forms.IntegerField(
        label="Quantity (Pallet Count)",
        widget=forms.NumberInput(attrs={
            "class": "form-control",
            "inputmode": "numeric", # Standard numeric keypad
            "step": "1",            # Whole numbers only
            "min": "1",             # Prevents quantity less than 1
            "placeholder": "1"
            }),
        validators=[MinValueValidator(1, message="Quantity cannot be less than 1.")],
    )

# --- Fuel Surcharge Calculator ---
class FuelSurchargeForm(forms.Form):
    trip_miles = forms.FloatField(
        label="Total Trip Miles",
        widget=forms.NumberInput(attrs={
            "class": "form-control", 
            "placeholder": "1200",
            "inputmode": "decimal", # Triggers the correct mobile keyboard
            "min": "0.00001"        # Prevents negative numbers
            }),
        validators=[MinValueValidator(0.00001, message="Total miles must be no less than 0.00001 miles.")],
    )
    current_price = forms.FloatField(
        label="Current Diesel Price ($/gal)",
        widget=forms.NumberInput(attrs={
            "class": "form-control", 
            "placeholder": "3.85",
            "inputmode": "decimal", # Triggers the correct mobile keyboard
            "min": "0.01"           # Prevents value less than 1 cent
            }),
        validators=[MinValueValidator(0.01, message="Price cannot be less than $0.01 per gallon.")],
    )
    base_price = forms.FloatField(
        label="Base 'Peg' Price ($/gal)",
        help_text="The baseline fuel cost established in your contract (often $1.20).",
        widget=forms.NumberInput(attrs={
            "class": "form-control",
            "inputmode": "decimal", # Triggers the correct mobile keyboard
            "placeholder": "1.20", # Suggested default
            "min": "0.01"              # Prevents value less than 1 cent
            }),
        validators=[MinValueValidator(0.01, message="Price cannot be less than $0.01 per gallon.")],
    )
    mpg = forms.FloatField(
        label="Miles Per Gallon (MPG)",
        help_text="Average miles per gallon (Industry standard is usually 6.0 or 6.5).",
        widget=forms.NumberInput(attrs={
            "class": "form-control",
            "inputmode": "decimal",  # Triggers the correct mobile keyboard
            "placeholder": "6.0", # Suggested default
            "min": "0.00001"        # Prevents negative numbers
            }),
        validators=[MinValueValidator(0.00001, message="MPG must be no less than 0.00001.")],
    )

# --- HOS Trip Planner ---
class HOSTripPlannerForm(forms.Form):
    total_miles = forms.FloatField(
        label="Total Trip Miles",
        widget=forms.NumberInput(attrs={
            "class": "form-control", 
            "placeholder": "1450",
            "inputmode": "decimal", # Triggers the correct mobile keyboard
            "min": "0.00001"        # Prevents negative numbers
            }),
        validators=[MinValueValidator(0.00001, message="Total miles must be no less than 0.00001 miles.")],
    )
    avg_speed = forms.FloatField(
        label="Average Speed (mph)",
        widget=forms.NumberInput(attrs={
            "class": "form-control", 
            "placeholder": "55",
            "inputmode": "decimal", # Triggers the correct mobile keyboard
            "min": "0.00001"        # Prevents negative numbers
            }),
        validators=[MinValueValidator(0.00001, message="Average speed must be no less than 0.00001 mph.")],
    )
    start_date = forms.DateField(
        label="Start Date",
        widget=forms.DateInput(attrs={"class": "form-control", "type": "date"})
    )
    start_time = forms.TimeField(
        label="Start Time",
        widget=forms.TimeInput(attrs={"class": "form-control", "type": "time"})
    )

# --- Glass Reaction Checker ---
class GlassReactionForm(forms.Form):
    FAMILY_CHOICES = [
        ("sulfur", "Sulfur/Selenium Bearing (Yellows, Reds, Oranges)"),
        ("copper", "Copper Bearing (Turquoise, Cyan, Some Blues)"),
        ("lead", "Lead Bearing (Select Cranberries, Special Pinks)"),
        ("reactive_clear", "Reactive Ice/Cloud (Specialty Reactives)"),
        ("silver", "Silver Foil / Silver Leaf"),
        ("none", "Non-Reactive (Standard Clears, Blacks, Neutrals)"),
    ]

    glass_a = forms.ChoiceField(
        choices=FAMILY_CHOICES,
        label="First Glass Component",
        widget=forms.Select(attrs={"class": "form-select"})
    )
    glass_b = forms.ChoiceField(
        choices=FAMILY_CHOICES,
        label="Second Glass Component",
        widget=forms.Select(attrs={"class": "form-select"})
    )

# --- Enamel/Frit Mixing Calculator ---
class FritMixingForm(forms.Form):
    STYLE_CHOICES = [
        ("painting", "Fluid Painting (Brush)"),
        ("screen_print", "Screen Printing (Squeegee)"),
        ("paste", "Stiff Paste (Palette Knife)"),
        ("airbrush", "Airbrush / Spraying"),
    ]

    powder_weight = forms.FloatField(
        label="Powder/Frit Weight (grams)",
        widget=forms.NumberInput(attrs={
            "class": "form-control", 
            "placeholder": "10.0",
            "inputmode": "decimal", # Triggers the correct mobile keyboard
            "min": "0.00001"        # Prevents negative numbers
            }),
        validators=[MinValueValidator(0.00001, message="Powder weight must be no less than 0.00001 grams.")],
        help_text="Weigh your dry powder first."
    )
    application_style = forms.ChoiceField(
        choices=STYLE_CHOICES,
        label="Desired Application Style",
        initial="painting",
        widget=forms.Select(attrs={"class": "form-select"})
    )

# --- Circle/Oval Cutter Calculator ---
class CircleCutterForm(forms.Form):
    # Add this inside your CircleCutterForm class
    cutter_offset = forms.FloatField(
            label="Cutter Head Offset",
            help_text="Distance from the center pivot to the cutting wheel. (Standard is 0.20 or 3/16\").",
            widget=forms.NumberInput(attrs={
                "class": "form-control",
                "placeholder": "0.20",
                "step": "0.01",
                "inputmode": "decimal",
                "min": "0.01" # Update frontend validation
                }),
            validators=[MinValueValidator(0.01, message="Offset must be greater than zero.")],
        )

    SHAPE_CHOICES = [
        ("circle", "Circle"),
        ("oval_width", "Oval (Width/Minor Axis)"),
        ("oval_length", "Oval (Length/Major Axis)"),
    ]

    GRIND_CHOICES = [
        (0.0, "No Grinding (Exact Cut)"),
        (0.0625, "1/16 inch (Light Grind)"),
        (0.125, "1/8 inch (Standard Grind)"),
        (0.25, "1/4 inch (Heavy Grind/Foil)"),
    ]

    target_diameter = forms.FloatField(
        label="Desired Finished Diameter (inches)",
        widget=forms.NumberInput(attrs={
            "class": "form-control", 
            "placeholder": "10.5",
            "inputmode": "decimal", # Triggers the correct mobile keyboard
            "min": "0.00001"        # Prevents negative numbers
            }),
        validators=[MinValueValidator(0.00001, message="Diameter must be no less than 0.00001 inches.")]
    )
    shape_type = forms.ChoiceField(
        choices=SHAPE_CHOICES,
        label="Shape Type",
        initial="circle",
        widget=forms.Select(attrs={"class": "form-select"})
    )
    grind_allowance = forms.ChoiceField(
        choices=GRIND_CHOICES,
        label="Edge Grinding Allowance",
        initial=0.0625,
        help_text="Adds extra glass to account for material lost on the grinder.",
        widget=forms.Select(attrs={"class": "form-select"})
    )

# --- Tie-Down / Load Securement Calculator ---
class TieDownForm(forms.Form):
    STRAP_CHOICES = [
        (3333, "Standard 2-inch Web Strap (3,333 lbs WLL)"),
        (5400, "Heavy-Duty 4-inch Web Strap (5,400 lbs WLL)"),
        (4700, "Grade 70 Chain - 5/16 inch (4,700 lbs WLL)"),
        (6600, "Grade 70 Chain - 3/8 inch (6,600 lbs WLL)"),
    ]

    cargo_weight = forms.FloatField(
        label="Cargo Weight (lbs)",
        widget=forms.NumberInput(attrs={
            "class": "form-control", 
            "placeholder": "15000",
            "inputmode": "decimal", # Triggers the correct mobile keyboard
            "min": "0.00001"        # Prevents negative numbers
            }),
        validators=[MinValueValidator(0.00001, message="Weight must be no less than 0.00001 lbs.")],
    )
    cargo_length = forms.FloatField(
        label="Cargo Length (feet)",
        widget=forms.NumberInput(attrs={
            "class": "form-control", 
            "placeholder": "12",
            "inputmode": "decimal", # Triggers the correct mobile keyboard
            "min": "0.00001"        # Prevents negative numbers
            }),
        validators=[MinValueValidator(0.00001, message="Length must be no less than 0.00001 feet.")],
    )
    strap_wll = forms.ChoiceField(
        choices=STRAP_CHOICES,
        label="Strap / Tie-Down Type",
        help_text="Select the Working Load Limit (WLL) of your securement device.",
        widget=forms.Select(attrs={"class": "form-select"})
    )

# --- Cost Per Mile (CPM) Calculator ---
class CPMCalculatorForm(forms.Form):
    # Monthly Fixed Costs
    monthly_miles = forms.FloatField(
        label="Average Monthly Miles",
        help_text="Total loaded and empty miles driven per month.",
        widget=forms.NumberInput(attrs={
            "class": "form-control", 
            "placeholder": "10000",
            "inputmode": "decimal",
            "min": "0.00001"
            }),
        validators=[MinValueValidator(0.00001, message="Miles must be greater than zero.")],
    )
    truck_payment = forms.FloatField(
        label="Truck & Trailer Payment ($)",
        widget=forms.NumberInput(attrs={
            "class": "form-control", 
            "placeholder": "2500",
            "inputmode": "decimal",
            "min": "0"
            }),
        validators=[MinValueValidator(0)],
    )
    insurance = forms.FloatField(
        label="Monthly Insurance ($)",
        widget=forms.NumberInput(attrs={
            "class": "form-control", 
            "placeholder": "1200",
            "inputmode": "decimal",
            "min": "0"
            }),
        validators=[MinValueValidator(0)],
    )
    other_fixed = forms.FloatField(
        label="Other Fixed Costs ($)",
        help_text="Permits, parking, load board subscriptions, etc.",
        widget=forms.NumberInput(attrs={
            "class": "form-control", 
            "placeholder": "300",
            "inputmode": "decimal",
            "min": "0"
            }),
        validators=[MinValueValidator(0)],
    )

    # Variable Costs (Per Mile or Monthly)
    fuel_cpm = forms.FloatField(
        label="Fuel Cost Per Mile ($)",
        help_text="Divide your average fuel price by your truck's MPG.",
        widget=forms.NumberInput(attrs={
            "class": "form-control", 
            "placeholder": "0.65",
            "inputmode": "decimal",
            "min": "0"
            }),
        validators=[MinValueValidator(0)],
    )
    maintenance_cpm = forms.FloatField(
        label="Maintenance & Tires Per Mile ($)",
        help_text="Industry standard is roughly $0.15 - $0.20 per mile.",
        widget=forms.NumberInput(attrs={
            "class": "form-control", 
            "placeholder": "0.15",
            "inputmode": "decimal",
            "min": "0"
            }),
        validators=[MinValueValidator(0)],
    )
    driver_pay = forms.FloatField(
        label="Driver Pay Per Mile ($)",
        help_text="What you pay yourself or your driver.",
        widget=forms.NumberInput(attrs={
            "class": "form-control", 
            "placeholder": "0.60",
            "inputmode": "decimal",
            "min": "0"
            }),
        validators=[MinValueValidator(0)],
    )
# --- LTL Linear Foot & Density Visualizer ---
class LinearFootForm(forms.Form):
    # Pallet Dimensions
    length = forms.FloatField(
        label="Length per Pallet (inches)",
        widget=forms.NumberInput(attrs={
            "class": "form-control", 
            "placeholder": "48",
            "inputmode": "decimal",
            "min": "0.00001"
            }),
        validators=[MinValueValidator(0.00001)],
    )
    width = forms.FloatField(
        label="Width per Pallet (inches)",
        widget=forms.NumberInput(attrs={
            "class": "form-control", 
            "placeholder": "40",
            "inputmode": "decimal",
            "min": "0.00001"
            }),
        validators=[MinValueValidator(0.00001)],
    )
    height = forms.FloatField(
        label="Height per Pallet (inches)",
        widget=forms.NumberInput(attrs={
            "class": "form-control", 
            "placeholder": "48",
            "inputmode": "decimal",
            "min": "0.00001"
            }),
        validators=[MinValueValidator(0.00001)],
    )
    weight = forms.FloatField(
        label="Weight per Pallet (lbs)",
        widget=forms.NumberInput(attrs={
            "class": "form-control", 
            "placeholder": "500",
            "inputmode": "decimal",
            "min": "0.00001"
            }),
        validators=[MinValueValidator(0.00001)],
    )
    quantity = forms.IntegerField(
        label="Total Pallet Count",
        widget=forms.NumberInput(attrs={
            "class": "form-control",
            "inputmode": "numeric",
            "step": "1",
            "min": "1"
            }),
        validators=[MinValueValidator(1)],
    )
    
    # Linear Foot Rule Triggers
    is_stackable = forms.ChoiceField(
        choices=[(True, "Yes, these pallets can be stacked."), (False, "No, do not stack (Top Freight only).")],
        label="Are these pallets stackable?",
        widget=forms.Select(attrs={"class": "form-select"})
    )
# --- Detention & Layover Fee Calculator ---
class DetentionFeeForm(forms.Form):
    # Time Inputs
    arrival_date = forms.DateField(
        label="Arrival Date",
        widget=forms.DateInput(attrs={"class": "form-control", "type": "date"})
    )
    arrival_time = forms.TimeField(
        label="Arrival Time",
        widget=forms.TimeInput(attrs={"class": "form-control", "type": "time"})
    )
    departure_date = forms.DateField(
        label="Departure Date",
        widget=forms.DateInput(attrs={"class": "form-control", "type": "date"})
    )
    departure_time = forms.TimeField(
        label="Departure Time",
        widget=forms.TimeInput(attrs={"class": "form-control", "type": "time"})
    )

    # Contract Terms
    free_time_hours = forms.FloatField(
        label="Contracted Free Time (Hours)",
        help_text="Industry standard is 2.0 hours.",
        widget=forms.NumberInput(attrs={
            "class": "form-control",
            "placeholder": "2.0",
            "inputmode": "decimal",
            "min": "0"
            }),
        validators=[MinValueValidator(0)],
    )
    hourly_rate = forms.FloatField(
        label="Detention Rate per Hour ($)",
        help_text="Often ranges from $40 to $80 per hour.",
        widget=forms.NumberInput(attrs={
            "class": "form-control", 
            "placeholder": "60",
            "inputmode": "decimal",
            "min": "0"
            }),
        validators=[MinValueValidator(0)],
    )
    
    def clean(self):
        cleaned_data = super().clean()
        a_date = cleaned_data.get("arrival_date")
        a_time = cleaned_data.get("arrival_time")
        d_date = cleaned_data.get("departure_date")
        d_time = cleaned_data.get("departure_time")

        if a_date and a_time and d_date and d_time:
            from datetime import datetime
            arrival = datetime.combine(a_date, a_time)
            departure = datetime.combine(d_date, d_time)

            if departure <= arrival:
                raise forms.ValidationError("Departure time must be after the arrival time.")
        
        return cleaned_data
    
# --- Warehouse Pallet Storage Estimator ---
class WarehouseStorageForm(forms.Form):
    # Warehouse Area Dimensions
    area_length = forms.FloatField(
        label="Storage Area Length (feet)",
        widget=forms.NumberInput(attrs={
            "class": "form-control", 
            "placeholder": "40",
            "inputmode": "decimal",
            "min": "0.00001"
            }),
        validators=[MinValueValidator(0.00001)],
    )
    area_width = forms.FloatField(
        label="Storage Area Width (feet)",
        widget=forms.NumberInput(attrs={
            "class": "form-control", 
            "placeholder": "20",
            "inputmode": "decimal",
            "min": "0.00001"
            }),
        validators=[MinValueValidator(0.00001)],
    )

    # Pallet Dimensions
    pallet_length = forms.FloatField(
        label="Pallet Length (inches)",
        help_text="Standard is 48 inches.",
        widget=forms.NumberInput(attrs={
            "class": "form-control", 
            "placeholder": "48",
            "inputmode": "decimal",
            "min": "0.00001"
            }),
        validators=[MinValueValidator(0.00001)],
    )
    pallet_width = forms.FloatField(
        label="Pallet Width (inches)",
        help_text="Standard is 40 inches.",
        widget=forms.NumberInput(attrs={
            "class": "form-control", 
            "placeholder": "40",
            "inputmode": "decimal",
            "min": "0.00001"
            }),
        validators=[MinValueValidator(0.00001)],
    )

    # Stacking
    stack_height = forms.IntegerField(
        label="Max Stacking Height (Pallets)",
        help_text="1 = Floor loaded (no stacking). 2 = Double stacked.",
        widget=forms.NumberInput(attrs={
            "class": "form-control",
            "placeholder": "1",
            "inputmode": "numeric",
            "step": "1",
            "min": "1"
            }),
        validators=[MinValueValidator(1)],
    )