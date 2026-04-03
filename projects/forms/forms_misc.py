# forms/forms_misc.py
#
# Miscellaneous standalone form classes. Each form here has exactly one
# consuming view and does not fit neatly into any other category module.
#
# Forms and their consuming views:
#   QRForm          → views_misc.qr_code_generator
#   MonteCarloForm  → views_misc.monte_carlo_simulator
#   AITokenCostForm → views_misc.ai_api_cost_estimator

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

# --- AI Token & API Cost Estimator ---
class AITokenCostForm(forms.Form):
    input_text = forms.CharField(
        label="Enter or paste text to tokenize",
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 6,
                "placeholder": "Paste your text snippet, prompt, or data here to estimate its token count and API cost...",
                "autofocus": True,
            }
        ),
        validators=[
            MinLengthValidator(1, message="Please provide some text to evaluate."),
            # 5,000,000 characters ≈ 1.25M tokens — accommodates massive context 
            # windows used by modern frontier models.
            MaxLengthValidator(5000000, message="Text exceeds the 5,000,000-character limit for this tool (~1.25M tokens)."),
        ],
    )

    TASK_CHOICES = [
        ("summarize", "Summarization (≈15% of input, min. 150 tokens)"),
        ("translate", "Translation / Proofreading (≈100% of input)"),
        ("code",      "Code Refactoring (≈120% of input)"),
        ("classify",  "Classification / Extraction (≈150 tokens fixed)"),
        ("generate",  "Content Generation (≈50% of input, 500–4,000 token range)"),
    ]

    task_type = forms.ChoiceField(
        label="What type of AI task is this?",
        choices=TASK_CHOICES,
        widget=forms.Select(attrs={"class": "form-select"}),
    )

# --- Job Fit Analyzer ---
class JobFitForm(forms.Form):
    # --- The Honeypot Field ---
    company_website = forms.CharField(
        required=False,
        label="Company Website",
        widget=forms.TextInput(attrs={
            "tabindex": "-1",       # Prevents keyboard navigation focus
            "autocomplete": "off",  # Prevents browser autofill from breaking it
        })
    )
    job_description = forms.CharField(
        label="Job Description",
        widget=forms.Textarea(attrs={
            "class": "form-control",
            "placeholder": "Paste the full job description here...",
            "rows": 12,
            "autofocus": True,
            "aria-label": "Job description text for AI fit analysis",
        }),
        validators=[
            MinLengthValidator(50,  message="Please paste the full job description (at least 50 characters)."),
            MaxLengthValidator(20000, message="Job description exceeds the 20,000-character limit. Please trim and try again."),
        ],
        help_text="Paste the complete job posting for the most accurate analysis. There is a rate limit of 5 requests per hour per IP address to limit my API costs.",
        required=True,
    )