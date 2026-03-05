# forms/forms_seo_tools.py
#
# SEO Professional Toolkit form classes.
#
# Forms and their consuming views:
#   SitemapForm     → views_seo_tools.seo_head_checker
#                     (submitted URL is passed to start_sitemap_processing task endpoint)
#   OGPreviewerForm → views_seo_tools.og_previewer

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

# SitemapForm.clean_sitemap_url() calls normalize_url().
from ..utils import normalize_url

# OGPreviewerForm uses urlparse for URL validation.
from urllib.parse import urlparse

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

# --- Open Graph Previewer ---
class OGPreviewerForm(forms.Form):
    url_input = forms.URLField(
        label="Page URL",
        max_length=2048,
        widget=forms.TextInput(attrs={
            "class":        "form-control",
            "id":           "url_input",
            "placeholder":  "nintendo.com",
            "autocomplete": "off",
            "spellcheck":   "false",
        }),
        # Allow bare domains; normalise_url() prepends https:// in the view.
        # We override the default URLField validator to accept non-schemed input
        # gracefully — the view will normalise and re-validate.
        error_messages={
            "required": "Please enter a URL.",
            "invalid":  "That doesn't look like a valid URL. Please include a domain name.",
        },
    )

    def clean_url_input(self):
        """Strip whitespace; let the view handle scheme injection."""
        return self.cleaned_data.get("url_input", "").strip()