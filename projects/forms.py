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

# --- Freight Partial / Volume LTL Estimator ---
class PartialRateForm(forms.Form):
    TRAILER_CHOICES = [
        ("dry_van", "53' Dry Van (26 Pallets / 40,000 lbs)"),
        ("reefer", "53' Reefer (26 Pallets / 38,000 lbs)"),
        ("flatbed", "48' Flatbed (24 Pallets / 45,000 lbs)"),
    ]

    # --- Location Data ---
    origin_zip = forms.CharField(
        label="Origin ZIP Code",
        max_length=5,
        widget=forms.TextInput(attrs={
            "class": "form-control", 
            "placeholder": "90210",
            "inputmode": "numeric"
            })
    )
    dest_zip = forms.CharField(
        label="Destination ZIP Code",
        max_length=5,
        widget=forms.TextInput(attrs={
            "class": "form-control", 
            "placeholder": "10001",
            "inputmode": "numeric"
            })
    )

    # --- Freight Data ---
    trailer_type = forms.ChoiceField(
        label="Trailer Type",
        choices=TRAILER_CHOICES,
        initial="dry_van",
        widget=forms.Select(attrs={"class": "form-select"})
    )
    pallets = forms.IntegerField(
        label="Pallet Count",
        help_text="Volume LTL is typically 5 to 14 pallets.",
        widget=forms.NumberInput(attrs={
            "class": "form-control",
            "inputmode": "numeric",
            "step": "1",
            "min": "1",
            "max": "20",
            "placeholder": "8"
            }),
        validators=[MinValueValidator(1), MaxValueValidator(20)],
    )
    weight = forms.FloatField(
        label="Total Weight (lbs)",
        widget=forms.NumberInput(attrs={
            "class": "form-control", 
            "placeholder": "12000",
            "inputmode": "decimal",
            "min": "0.00001"
            }),
        validators=[MinValueValidator(0.00001)],
    )

    # --- Financial Data ---
    base_ftl_cpm = forms.FloatField(
        label="Current FTL Rate Per Mile ($)",
        help_text="The going rate for a Full Truckload today.",
        widget=forms.NumberInput(attrs={
            "class": "form-control", 
            "placeholder": "2.50", 
            "step": "0.01",
            "inputmode": "decimal",
            "min": "0.01"
            }),
        validators=[MinValueValidator(0.01)],
    )
    markup = forms.FloatField(
        label="Broker Markup Multiplier",
        help_text="Standard is 1.25 (25% markup).",
        widget=forms.NumberInput(attrs={
            "class": "form-control", 
            "placeholder": "1.25", 
            "step": "0.01",
            "inputmode": "decimal",
            "min": "1.0"
            }),
        validators=[MinValueValidator(1.0)],
    )
    min_charge = forms.FloatField(
        label="Minimum Charge ($)",
        help_text="Your absolute minimum to move any freight.",
        widget=forms.NumberInput(attrs={
            "class": "form-control", 
            "placeholder": "500", 
            "step": "1",
            "inputmode": "numeric",
            "min": "0"
            }),
        validators=[MinValueValidator(0)],
    )

    def clean_origin_zip(self):
        zip_code = self.cleaned_data["origin_zip"]
        try:
            zdb[zip_code]
        except (KeyError, IndexError):
            raise forms.ValidationError("Invalid Origin ZIP code.")
        return zip_code

    def clean_dest_zip(self):
        zip_code = self.cleaned_data["dest_zip"]
        try:
            zdb[zip_code]
        except (KeyError, IndexError):
            raise forms.ValidationError("Invalid Destination ZIP code.")
        return zip_code

# --- Deadhead Calculator ---
class DeadheadCalculatorForm(forms.Form):
    # --- Location Data ---
    current_zip = forms.CharField(
        label="Current Truck Location (ZIP Code)",
        max_length=5,
        help_text="Where the truck is now (or last drop location).",
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "60601",
            "inputmode": "numeric"
        })
    )
    pickup_zip = forms.CharField(
        label="Next Pickup Location (ZIP Code)",
        max_length=5,
        help_text="The shipper's pickup ZIP for the load being evaluated.",
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "46201",
            "inputmode": "numeric"
        })
    )

    # --- Operating Cost ---
    operating_cpm = forms.FloatField(
        label="Operating Cost Per Mile ($)",
        help_text="Your all-in CPM (use the CPM Calculator if unsure).",
        widget=forms.NumberInput(attrs={
            "class": "form-control",
            "placeholder": "1.75",
            "inputmode": "decimal",
            "step": "0.01",
            "min": "0.01"
        }),
        validators=[MinValueValidator(0.01, message="Operating CPM must be at least $0.01.")],
    )

    # --- Optional: Load Evaluation Fields ---
    load_rate = forms.FloatField(
        label="Offered Load Rate ($)",
        required=False,
        help_text="(Optional) The flat dollar rate offered for the next load.",
        widget=forms.NumberInput(attrs={
            "class": "form-control",
            "placeholder": "2800",
            "inputmode": "decimal",
            "step": "0.01",
            "min": "0"
        }),
        validators=[MinValueValidator(0)],
    )
    delivery_zip = forms.CharField(
        label="Delivery Destination (ZIP Code)",
        max_length=5,
        required=False,
        help_text="(Optional) The consignee's delivery ZIP. Required if evaluating a load.",
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "37201",
            "inputmode": "numeric"
        })
    )

    # --- ZIP Code Validation ---
    def clean_current_zip(self):
        zip_code = self.cleaned_data["current_zip"]
        try:
            zdb[zip_code]
        except (KeyError, IndexError):
            raise forms.ValidationError("Invalid Current Location ZIP code.")
        return zip_code

    def clean_pickup_zip(self):
        zip_code = self.cleaned_data["pickup_zip"]
        try:
            zdb[zip_code]
        except (KeyError, IndexError):
            raise forms.ValidationError("Invalid Pickup Location ZIP code.")
        return zip_code

    def clean_delivery_zip(self):
        zip_code = self.cleaned_data.get("delivery_zip", "").strip()
        if not zip_code:
            return ""  # Optional field; empty is fine.
        try:
            zdb[zip_code]
        except (KeyError, IndexError):
            raise forms.ValidationError("Invalid Delivery Destination ZIP code.")
        return zip_code

    def clean(self):
        cleaned_data = super().clean()
        load_rate = cleaned_data.get("load_rate")
        delivery_zip = cleaned_data.get("delivery_zip", "").strip()

        # If one optional field is filled, the other must also be filled.
        if load_rate and not delivery_zip:
            self.add_error(
                "delivery_zip",
                "A Delivery ZIP is required when evaluating a load rate."
            )
        if delivery_zip and not load_rate:
            self.add_error(
                "load_rate",
                "An Offered Load Rate is required when a Delivery ZIP is provided."
            )

        return cleaned_data

# --- Multi Stop Route Splitter ---
class MultiStopSplitterForm(forms.Form):
    """
    Accepts an origin, a destination, up to 5 intermediate stops (ZIPs),
    and an optional per-stop fee for invoicing.

    Fieldset 1 — Route Endpoints (required):  origin_zip, destination_zip
    Fieldset 2 — Intermediate Stops (optional): stop_1 through stop_5
    Fieldset 3 — Stop-Off Billing  (optional): stop_off_charge
    """

    # --- Route Endpoints ---
    origin_zip = forms.CharField(
        label="Origin ZIP Code",
        max_length=5,
        help_text="First pickup or starting location.",
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "60601",
            "inputmode": "numeric",
        }),
    )
    destination_zip = forms.CharField(
        label="Final Destination ZIP Code",
        max_length=5,
        help_text="Last delivery or ending location.",
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "90210",
            "inputmode": "numeric",
        }),
    )

    # --- Intermediate Stops (all optional) ---
    stop_1 = forms.CharField(
        label="Stop 1 ZIP",
        max_length=5,
        required=False,
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "46201",
            "inputmode": "numeric",
        }),
    )
    stop_2 = forms.CharField(
        label="Stop 2 ZIP",
        max_length=5,
        required=False,
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "37201",
            "inputmode": "numeric",
        }),
    )
    stop_3 = forms.CharField(
        label="Stop 3 ZIP",
        max_length=5,
        required=False,
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "",
            "inputmode": "numeric",
        }),
    )
    stop_4 = forms.CharField(
        label="Stop 4 ZIP",
        max_length=5,
        required=False,
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "",
            "inputmode": "numeric",
        }),
    )
    stop_5 = forms.CharField(
        label="Stop 5 ZIP",
        max_length=5,
        required=False,
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "",
            "inputmode": "numeric",
        }),
    )

    # --- Stop-Off Billing (optional) ---
    stop_off_charge = forms.FloatField(
        label="Stop-Off Charge Per Stop ($)",
        required=False,
        help_text="(Optional) Flat fee billed per intermediate stop. Common: $50–$150.",
        widget=forms.NumberInput(attrs={
            "class": "form-control",
            "placeholder": "75",
            "inputmode": "decimal",
            "step": "0.01",
            "min": "0",
        }),
        validators=[MinValueValidator(0)],
    )

    # --- ZIP Validation Helpers ---
    def _validate_zip(self, field_name, label):
        """Shared ZIP validation for optional stop fields."""
        zip_code = self.cleaned_data.get(field_name, "").strip()
        if not zip_code:
            return ""  # Empty optional fields are fine.
        try:
            zdb[zip_code]
        except (KeyError, IndexError):
            raise forms.ValidationError(f"Invalid {label} ZIP code.")
        return zip_code

    def clean_origin_zip(self):
        zip_code = self.cleaned_data["origin_zip"].strip()
        try:
            zdb[zip_code]
        except (KeyError, IndexError):
            raise forms.ValidationError("Invalid Origin ZIP code.")
        return zip_code

    def clean_destination_zip(self):
        zip_code = self.cleaned_data["destination_zip"].strip()
        try:
            zdb[zip_code]
        except (KeyError, IndexError):
            raise forms.ValidationError("Invalid Destination ZIP code.")
        return zip_code

    def clean_stop_1(self):
        return self._validate_zip("stop_1", "Stop 1")

    def clean_stop_2(self):
        return self._validate_zip("stop_2", "Stop 2")

    def clean_stop_3(self):
        return self._validate_zip("stop_3", "Stop 3")

    def clean_stop_4(self):
        return self._validate_zip("stop_4", "Stop 4")

    def clean_stop_5(self):
        return self._validate_zip("stop_5", "Stop 5")

    def clean(self):
        cleaned_data = super().clean()

        origin = cleaned_data.get("origin_zip", "")
        destination = cleaned_data.get("destination_zip", "")
        stops = [
            cleaned_data.get(f"stop_{i}", "").strip()
            for i in range(1, 6)
        ]
        # Filter out empty stops, preserving user-specified order.
        intermediate = [z for z in stops if z]

        # Assemble full ordered route for the view.
        route_zips = []
        if origin:
            route_zips.append(origin)
        route_zips.extend(intermediate)
        if destination:
            route_zips.append(destination)

        cleaned_data["route_zips"] = route_zips

        # Validate: origin and destination must differ when no stops are given.
        if origin and destination and origin == destination and not intermediate:
            self.add_error(
                "destination_zip",
                "Origin and Destination are the same ZIP with no intermediate stops."
            )

        return cleaned_data

# --- Lane Rate Analyzer ---
class LaneRateAnalyzerForm(forms.Form):
    """
    Accepts origin/destination ZIPs, a quoted line-haul rate, and optional
    FSC and operating CPM for deeper analysis.

    Fieldset 1 — Lane (required):  origin_zip, dest_zip
    Fieldset 2 — Rate (required):  line_haul_rate
    Fieldset 3 — Optional Analysis: fuel_surcharge, operating_cpm
    """

    # --- Lane Endpoints ---
    origin_zip = forms.CharField(
        label="Origin ZIP Code",
        max_length=5,
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "60601",
            "inputmode": "numeric",
        }),
    )
    dest_zip = forms.CharField(
        label="Destination ZIP Code",
        max_length=5,
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "30301",
            "inputmode": "numeric",
        }),
    )

    # --- Rate ---
    line_haul_rate = forms.FloatField(
        label="Line-Haul Rate ($)",
        help_text="The flat dollar rate quoted for this load (before FSC).",
        widget=forms.NumberInput(attrs={
            "class": "form-control",
            "placeholder": "2800",
            "inputmode": "decimal",
            "step": "0.01",
            "min": "0.01",
        }),
        validators=[MinValueValidator(0.01, message="Rate must be at least $0.01.")],
    )

    # --- Optional: Fuel Surcharge ---
    fuel_surcharge = forms.FloatField(
        label="Fuel Surcharge — Total ($)",
        required=False,
        help_text="(Optional) Total FSC for the trip. Shows all-in RPM.",
        widget=forms.NumberInput(attrs={
            "class": "form-control",
            "placeholder": "225",
            "inputmode": "decimal",
            "step": "0.01",
            "min": "0",
        }),
        validators=[MinValueValidator(0)],
    )

    # --- Optional: Operating CPM ---
    operating_cpm = forms.FloatField(
        label="Operating Cost Per Mile ($)",
        required=False,
        help_text="(Optional) Your all-in CPM. Shows margin analysis.",
        widget=forms.NumberInput(attrs={
            "class": "form-control",
            "placeholder": "1.75",
            "inputmode": "decimal",
            "step": "0.01",
            "min": "0.01",
        }),
        validators=[MinValueValidator(0.01)],
    )

    # --- ZIP Validation ---
    def clean_origin_zip(self):
        zip_code = self.cleaned_data["origin_zip"].strip()
        try:
            zdb[zip_code]
        except (KeyError, IndexError):
            raise forms.ValidationError("Invalid Origin ZIP code.")
        return zip_code

    def clean_dest_zip(self):
        zip_code = self.cleaned_data["dest_zip"].strip()
        try:
            zdb[zip_code]
        except (KeyError, IndexError):
            raise forms.ValidationError("Invalid Destination ZIP code.")
        return zip_code

# --- Freight Margin Calculator ---
class FreightMarginForm(forms.Form):
    """
    Calculates brokerage gross profit and margin on a freight load.

    Fieldset 1 — Rates (required):   customer_rate, carrier_rate
    Fieldset 2 — FSC (optional):     customer_fsc, carrier_fsc
    Fieldset 3 — Accessorials (opt):  customer_accessorials, carrier_accessorials
    Fieldset 4 — Lane (optional):     origin_zip, dest_zip (for per-mile metrics)
    """

    # --- Required: Customer (Shipper) Rate ---
    customer_rate = forms.FloatField(
        label="Customer Rate ($)",
        help_text="The total line-haul rate billed to the shipper.",
        widget=forms.NumberInput(attrs={
            "class": "form-control",
            "placeholder": "3200",
            "inputmode": "decimal",
            "step": "0.01",
            "min": "0.01",
        }),
        validators=[MinValueValidator(0.01, message="Customer rate must be at least $0.01.")],
    )

    # --- Required: Carrier Rate ---
    carrier_rate = forms.FloatField(
        label="Carrier Rate ($)",
        help_text="The line-haul rate paid to the carrier.",
        widget=forms.NumberInput(attrs={
            "class": "form-control",
            "placeholder": "2600",
            "inputmode": "decimal",
            "step": "0.01",
            "min": "0.01",
        }),
        validators=[MinValueValidator(0.01, message="Carrier rate must be at least $0.01.")],
    )

    # --- Optional: Fuel Surcharges ---
    customer_fsc = forms.FloatField(
        label="Customer FSC ($)",
        required=False,
        help_text="(Optional) Fuel surcharge billed to customer.",
        widget=forms.NumberInput(attrs={
            "class": "form-control",
            "placeholder": "275",
            "inputmode": "decimal",
            "step": "0.01",
            "min": "0",
        }),
        validators=[MinValueValidator(0)],
    )
    carrier_fsc = forms.FloatField(
        label="Carrier FSC ($)",
        required=False,
        help_text="(Optional) Fuel surcharge paid to carrier.",
        widget=forms.NumberInput(attrs={
            "class": "form-control",
            "placeholder": "225",
            "inputmode": "decimal",
            "step": "0.01",
            "min": "0",
        }),
        validators=[MinValueValidator(0)],
    )

    # --- Optional: Accessorials ---
    customer_accessorials = forms.FloatField(
        label="Customer Accessorials ($)",
        required=False,
        help_text="(Optional) Total accessorial charges billed to customer (lumper, liftgate, etc.).",
        widget=forms.NumberInput(attrs={
            "class": "form-control",
            "placeholder": "150",
            "inputmode": "decimal",
            "step": "0.01",
            "min": "0",
        }),
        validators=[MinValueValidator(0)],
    )
    carrier_accessorials = forms.FloatField(
        label="Carrier Accessorials ($)",
        required=False,
        help_text="(Optional) Total accessorial costs paid to carrier.",
        widget=forms.NumberInput(attrs={
            "class": "form-control",
            "placeholder": "100",
            "inputmode": "decimal",
            "step": "0.01",
            "min": "0",
        }),
        validators=[MinValueValidator(0)],
    )

    # --- Optional: Lane (for per-mile metrics) ---
    origin_zip = forms.CharField(
        label="Origin ZIP Code",
        max_length=5,
        required=False,
        help_text="(Optional) Shows margin per mile using exact Google Maps road miles.",
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "60601",
            "inputmode": "numeric",
        }),
    )
    dest_zip = forms.CharField(
        label="Destination ZIP Code",
        max_length=5,
        required=False,
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "30301",
            "inputmode": "numeric",
        }),
    )

    # --- ZIP Validation ---
    def clean_origin_zip(self):
        zip_code = self.cleaned_data.get("origin_zip", "").strip()
        if not zip_code:
            return ""  # Optional field; empty is fine.
        try:
            zdb[zip_code]
        except (KeyError, IndexError):
            raise forms.ValidationError("Invalid Origin ZIP code.")
        return zip_code

    def clean_dest_zip(self):
        zip_code = self.cleaned_data.get("dest_zip", "").strip()
        if not zip_code:
            return ""  # Optional field; empty is fine.
        try:
            zdb[zip_code]
        except (KeyError, IndexError):
            raise forms.ValidationError("Invalid Destination ZIP code.")
        return zip_code

    def clean(self):
        cleaned_data = super().clean()
        origin_zip = cleaned_data.get("origin_zip", "").strip()
        dest_zip = cleaned_data.get("dest_zip", "").strip()

        # If one ZIP is filled, the other must also be filled.
        if origin_zip and not dest_zip:
            self.add_error(
                "dest_zip",
                "A Destination ZIP is required when an Origin ZIP is provided."
            )
        if dest_zip and not origin_zip:
            self.add_error(
                "origin_zip",
                "An Origin ZIP is required when a Destination ZIP is provided."
            )

        return cleaned_data

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