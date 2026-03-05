# forms/forms_glass_tools.py
#
# Glass Artist Toolkit form classes.
#
# Forms and their consuming views:
#   GlassVolumeForm         → views_glass_tools.glass_volume_calculator
#   KilnScheduleForm        → views_glass_tools.kiln_schedule_generator
#   StainedGlassCostForm    → views_glass_tools.stained_glass_cost_estimator
#   TempConverterForm       → views_glass_tools.kiln_controller_utils  (temp conversion tab)
#   RampCalculatorForm      → views_glass_tools.kiln_controller_utils  (ramp calculation tab)
#   StainedGlassMaterialsForm → views_glass_tools.stained_glass_materials
#   LampworkMaterialForm    → views_glass_tools.lampwork_materials
#   GlassReactionForm       → views_glass_tools.glass_reaction_checker
#   FritMixingForm          → views_glass_tools.frit_mixing_calculator
#   CircleCutterForm        → views_glass_tools.circle_cutter_calculator

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

# --- Kiln Controller Utilities ---
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