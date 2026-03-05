# forms/forms_it_tools.py
#
# IT Professional Toolkit form classes.
#
# Forms and their consuming views:
#   CookieAuditForm       → views_it_tools.cookie_audit_view
#   FontInspectorForm     → views_it_tools.font_inspector
#   XMLUploadForm         → views_it_tools.xml_splitter
#   DomainForm            → views_it_tools.dns_tool
#   IPForm                → views_it_tools.ip_tool
#   SSLCheckForm          → views_it_tools.ssl_check
#   SubnetCalculatorForm  → views_it_tools.subnet_calculator
#   EmailAuthForm         → views_it_tools.email_auth_validator
#   WhoisForm             → views_it_tools.whois_lookup
#   HttpHeaderForm        → views_it_tools.http_header_inspector
#   RedirectCheckerForm   → views_it_tools.redirect_checker_view
#   JsonLdValidatorForm   → views_it_tools.jsonld_validator_view
#   RobotsAnalyzerForm    → views_it_tools.robots_analyzer_view
#   CronBuilderForm       → views_it_tools.cron_builder
#   EpochToHumanForm      → views_it_tools.timestamp_converter  (epoch → human tab)
#   HumanToEpochForm      → views_it_tools.timestamp_converter  (human → epoch tab)

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
# Used by IPForm for IPv4/IPv6 validation.
import ipaddress

# Used by CookieAuditForm and FontInspectorForm for URL parsing/validation.
from urllib.parse import urlparse

# Used by SitemapForm and others to normalise URLs before validation.
from ..utils import normalize_url


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

# --- Subnet Calculator ---
class SubnetCalculatorForm(forms.Form):
    # Generate choices from /32 down to /0
    CIDR_CHOICES = [
        (i, f"/{i}  (Mask: {ipaddress.IPv4Network(f'0.0.0.0/{i}').netmask})") 
        for i in range(32, -1, -1)
    ]

    ip_address = forms.CharField(
        label="IP Address",
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "192.168.1.5",
            "autofocus": "autofocus"
        })
    )
    cidr = forms.ChoiceField(
        label="Subnet Mask (CIDR)",
        choices=CIDR_CHOICES,
        initial=24,
        widget=forms.Select(attrs={"class": "form-select"})
    )

    def clean_ip_address(self):
        ip = self.cleaned_data["ip_address"].strip()
        try:
            ipaddress.ip_address(ip)
        except ValueError:
            raise forms.ValidationError("Please enter a valid IP address (IPv4 or IPv6).")
        return ip

# --- SPF/DKIM/DMARC Validator ---
class EmailAuthForm(forms.Form):
    domain = forms.CharField(
        label="Domain Name",
        max_length=253,
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "bencritt.net",
            "autofocus": "autofocus"
        })
    )
    dkim_selector = forms.CharField(
        label="DKIM Selector (Optional)",
        required=False,
        max_length=63,
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "google, default, k1, etc."
        }),
        help_text="Enter a selector (e.g., 'google') to validate a specific DKIM key."
    )

    def clean_domain(self):
        # Reuse your existing normalize function if available, or basic strip
        raw = self.cleaned_data["domain"].lower().strip()
        # Strip protocols if user pasted a URL
        if "://" in raw:
            try:
                raw = urlparse(raw).hostname or raw
            except:
                pass
        return raw.strip("/")

# --- WHOIS Lookup ---
class WhoisForm(forms.Form):
    domain = forms.CharField(
        label="Domain Name",
        max_length=253,
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "bencritt.net",
            "autofocus": "autofocus"
        })
    )

    def clean_domain(self):
        raw = self.cleaned_data["domain"].lower().strip()
        # Strip protocols if user pasted a URL
        if "://" in raw:
            try:
                raw = urlparse(raw).hostname or raw
            except:
                pass
        return raw.strip("/")

# --- HTTP Header Inspector ---
class HttpHeaderForm(forms.Form):
    url = forms.CharField(
        label="Enter URL",
        max_length=500,
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "bencritt.net",
            "autofocus": "autofocus"
        })
    )

    def clean_url(self):
        url = self.cleaned_data["url"].strip()
        # Basic cleanup: if user types "google.com", we assume https://
        if not url.startswith(('http://', 'https://')):
            url = f"https://{url}"
        
        validator = URLValidator(schemes=['http', 'https'])
        try:
            validator(url)
        except ValidationError:
            raise forms.ValidationError("Please enter a valid URL (e.g. https://example.com).")
        
        return url

# --- Redirect Chain Checker ---
class RedirectCheckerForm(forms.Form):
    """
    Form for the Redirect Chain Checker tool.
    Accepts a URL and follows its full redirect chain.
    """

    url = forms.CharField(
        label="Enter URL",
        max_length=2048,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "bencrittenden.com",
                "autofocus": True,
                "id": "id_url",
            }
        ),
    )

    def clean_url(self):
        """
        Normalize the URL input:
        - Strip whitespace.
        - Prepend https:// if no scheme is provided.
        - Reject non-HTTP(S) schemes.
        - Reject URLs without a valid hostname.
        """
        url = self.cleaned_data["url"].strip()

        # If the user didn't include a scheme, default to https.
        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        parsed = urlparse(url)

        # Only allow http and https schemes.
        if parsed.scheme not in ("http", "https"):
            raise forms.ValidationError(
                "Only HTTP and HTTPS URLs are supported."
            )

        # Ensure there's actually a hostname.
        if not parsed.hostname:
            raise forms.ValidationError(
                "Please enter a valid URL with a hostname (e.g., example.com)."
            )

        return url

# --- JSON-LD Validator ---
class JsonLdValidatorForm(forms.Form):
    """
    Form for the Structured Data / JSON-LD Validator.
    Accepts a URL to fetch and extract JSON-LD blocks from.
    """
    url = forms.CharField(
        label="Page URL",
        max_length=2048,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "bencritt.net/projects/seo-tools/",
                "autofocus": True,
                "id": "id_url",
            }
        ),
    )

    def clean_url(self):
        """
        Normalize the URL input:
        - Strip whitespace.
        - Prepend https:// if no scheme is provided.
        - Reject non-HTTP(S) schemes.
        - Reject URLs without a valid hostname.
        """
        url = self.cleaned_data["url"].strip()

        # If the user didn't include a scheme, default to https.
        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        parsed = urlparse(url)

        if parsed.scheme not in ("http", "https"):
            raise forms.ValidationError(
                "Only HTTP and HTTPS URLs are supported."
            )

        if not parsed.hostname:
            raise forms.ValidationError(
                "Please enter a valid URL with a hostname (e.g., example.com)."
            )

        return url

# --- Robots Analyzer ---
class RobotsAnalyzerForm(forms.Form):
    """
    Form for the Robots.txt Analyzer.
    Accepts a domain to fetch robots.txt from, and an optional path
    to test against the parsed rules.
    """

    domain = forms.CharField(
        label="Domain",
        max_length=253,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "bencritt.net",
                "autofocus": True,
                "id": "id_domain",
            }
        ),
    )

    test_path = forms.CharField(
        label="Test Path",
        max_length=2048,
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "/private/page or /images/photo.jpg",
                "id": "id_test_path",
            }
        ),
    )

    def clean_domain(self):
        """
        Normalize domain input:
        - Strip whitespace.
        - Strip any scheme and path so we get a bare hostname.
        - Basic hostname validation.
        """
        raw = self.cleaned_data["domain"].strip()

        # If the user pasted a full URL, extract just the hostname.
        if raw.startswith(("http://", "https://")):
            parsed = urlparse(raw)
            raw = parsed.hostname or ""

        # Strip trailing slashes / paths if someone typed "example.com/page".
        raw = raw.split("/")[0].strip().lower()

        if not raw:
            raise forms.ValidationError(
                "Please enter a valid domain (e.g., example.com)."
            )

        # Very lightweight hostname check.
        hostname_re = re.compile(
            r"^(?!-)[A-Za-z0-9-]{1,63}(?<!-)(\.[A-Za-z0-9-]{1,63})*\.[A-Za-z]{2,}$"
        )
        if not hostname_re.match(raw):
            raise forms.ValidationError(
                f"\"{raw}\" does not look like a valid domain name."
            )

        return raw

    def clean_test_path(self):
        """
        Normalize the optional test path:
        - Strip whitespace.
        - Ensure it starts with /.
        """
        path = self.cleaned_data.get("test_path", "").strip()
        if path and not path.startswith("/"):
            path = "/" + path
        return path

# --- Cron Expression Builder ---
class CronBuilderForm(forms.Form):
    """
    Validates user input for the Cron Expression Builder.
    Field-level validation here keeps the view lean; business-logic
    validation (croniter syntax check, timezone lookup) stays in the view
    and utils so the view controls the error messaging UX.
    """

    cron_expression = forms.CharField(
        label="Cron Expression",
        max_length=100,
        strip=True,
        widget=forms.TextInput(attrs={
            "class": "form-control form-control-lg font-monospace",
            "id": "cron_expression",
            "placeholder": "* * * * *",
            "autocomplete": "off",
            "spellcheck": "false",
        }),
        error_messages={
            "required": "Please enter a cron expression.",
        },
    )

    tz_select = forms.ChoiceField(
        label="Timezone",
        choices=[],               # populated in __init__ from the utils constant
        widget=forms.Select(attrs={
            "class": "form-select",
            "id": "tz_select",
        }),
    )

    num_runs = forms.IntegerField(
        label="Next runs",
        min_value=1,
        max_value=50,
        initial=10,
        widget=forms.NumberInput(attrs={
            "class": "form-control",
            "id": "num_runs",
        }),
        error_messages={
            "min_value": "Must request at least 1 run.",
            "max_value": "Maximum is 50 runs.",
            "invalid": "Please enter a valid whole number.",
        },
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Deferred import — keeps utils out of module-load time.
        from ..cron_builder_utils import COMMON_TIMEZONES
        self.fields["tz_select"].choices = [(tz, tz) for tz in COMMON_TIMEZONES]

    def clean_cron_expression(self):
        """Normalise whitespace. Hard syntax validation lives in the view/utils."""
        value = self.cleaned_data.get("cron_expression", "").strip()
        value = " ".join(value.split())
        return value

    def clean_num_runs(self):
        """Clamp to [1, 50] even if browser validation was bypassed."""
        value = self.cleaned_data.get("num_runs", 10)
        if value is None:
            return 10
        return max(1, min(int(value), 50))

# --- Unix Epoch/Timestamp Converter ---
class EpochToHumanForm(forms.Form):
    """
    Tab A — accepts a raw Unix timestamp (seconds or milliseconds).
    Validation of the numeric range and ms/s auto-detection happens in
    the utils layer; this form just ensures the field isn't blank.
    """

    epoch_input = forms.CharField(
        label="Unix Timestamp",
        max_length=25,
        strip=True,
        widget=forms.TextInput(attrs={
            "class": "form-control font-monospace",
            "id": "epoch_input",
            "placeholder": "e.g. 1700000000  or  1700000000000 (ms)",
            "autocomplete": "off",
        }),
        error_messages={
            "required": "Please enter a Unix timestamp.",
        },
    )

    def clean_epoch_input(self):
        value = self.cleaned_data.get("epoch_input", "").strip()
        if not value:
            raise forms.ValidationError("Please enter a Unix timestamp.")
        try:
            float(value)
        except ValueError:
            raise forms.ValidationError(
                f"'{value}' is not a valid number. Enter a Unix timestamp in seconds or milliseconds."
            )
        return value

# --- Unix Epoch/Timestamp Converter ---
class HumanToEpochForm(forms.Form):
    """
    Tab B — accepts a human-readable date, time, and timezone,
    and converts to a Unix epoch.
    """

    date_input = forms.DateField(
        label="Date",
        input_formats=["%Y-%m-%d"],
        widget=forms.DateInput(attrs={
            "class": "form-control",
            "id": "date_input",
            "type": "date",
        }),
        error_messages={
            "required": "Please enter a date.",
            "invalid": "Date must be in YYYY-MM-DD format.",
        },
    )

    time_input = forms.CharField(
        label="Time (HH:MM or HH:MM:SS)",
        max_length=8,
        strip=True,
        widget=forms.TimeInput(attrs={
            "class": "form-control font-monospace",
            "id": "time_input",
            "type": "time",
            "step": "1",
        }),
        error_messages={
            "required": "Please enter a time.",
        },
    )

    tz_select = forms.ChoiceField(
        label="Timezone",
        choices=[],  # populated in __init__
        widget=forms.Select(attrs={
            "class": "form-select",
            "id": "tz_select_human",
        }),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Deferred import — keeps utils out of module-load time.
        from ..timestamp_converter_utils import COMMON_TIMEZONES
        self.fields["tz_select"].choices = [(tz, tz) for tz in COMMON_TIMEZONES]

    def clean_time_input(self):
        """Normalise HH:MM → HH:MM:SS so strptime always has seconds."""
        value = self.cleaned_data.get("time_input", "").strip()
        if len(value) == 5:
            value += ":00"
        if len(value) != 8:
            raise forms.ValidationError("Time must be in HH:MM or HH:MM:SS format.")
        return value