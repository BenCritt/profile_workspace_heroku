# forms/forms_freight_tools.py
#
# Freight Professional Toolkit form classes.
#
# Forms and their consuming views:
#   CarrierSearchForm       → views_freight_tools.freight_class_calculator
#   FreightClassForm        → views_freight_tools.freight_class_calculator
#   FuelSurchargeForm       → views_freight_tools.fuel_surcharge_calculator
#   HOSTripPlannerForm      → views_freight_tools.hos_trip_planner
#   TieDownForm             → views_freight_tools.tie_down_calculator
#   CPMCalculatorForm       → views_freight_tools.cost_per_mile_calculator
#   LinearFootForm          → views_freight_tools.linear_foot_calculator
#   DetentionFeeForm        → views_freight_tools.detention_layover_fee_calculator
#   WarehouseStorageForm    → views_freight_tools.warehouse_storage_calculator
#   PartialRateForm         → views_freight_tools.partial_rate_calculator
#   DeadheadCalculatorForm  → views_freight_tools.deadhead_calculator
#   MultiStopSplitterForm   → views_freight_tools.multi_stop_splitter
#   LaneRateAnalyzerForm    → views_freight_tools.lane_rate_analyzer
#   FreightMarginForm       → views_freight_tools.freight_margin_calculator

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