# projects/dns_tool_utils.py
from __future__ import annotations
from typing import Dict, Iterable, List, Optional, Tuple
import dns.resolver
from dns.resolver import NoAnswer, NXDOMAIN, Timeout, NoNameservers
from urllib.parse import urlparse

# Central place to manage which records you support
DEFAULT_RECORD_TYPES: List[str] = [
    "A", "AAAA", "MX", "NS", "CNAME", "TXT", "SOA", "SRV", "CAA",
]

def normalize_domain(raw: str) -> str:
    """
    Normalize a user-entered domain:
    - strip spaces
    - lower-case
    - strip scheme if a URL was pasted
    - remove trailing dot if present
    """
    s = (raw or "").strip().lower()
    if s.startswith("http://") or s.startswith("https://"):
        host = urlparse(s).hostname
        if host:
            s = host
    if s.endswith("."):
        s = s[:-1]
    return s

def fetch_dns_records(
    domain: str,
    record_types: Optional[Iterable[str]] = None,
    *,
    timeout: Optional[float] = None,
    nameservers: Optional[Iterable[str]] = None,
) -> Tuple[Dict[str, List[str]], Optional[str]]:
    """
    Resolve a set of DNS record types for a domain.
    Returns (results_dict, error_message).
    - results_dict maps record type -> list of strings (either answers or a single explanatory message)
    - error_message is a general message if any unexpected error occurred
    """
    resolver = dns.resolver.Resolver()
    if timeout is not None:
        resolver.timeout = timeout
        resolver.lifetime = max(timeout, resolver.lifetime)
    if nameservers:
        resolver.nameservers = list(nameservers)

    rtypes = list(record_types) if record_types else DEFAULT_RECORD_TYPES
    results: Dict[str, List[str]] = {}
    error_message: Optional[str] = None

    for rtype in rtypes:
        try:
            answers = resolver.resolve(domain, rtype)
            results[rtype] = [r.to_text() for r in answers]
        except NoAnswer:
            results[rtype] = ["No records found"]
        except NXDOMAIN:
            results[rtype] = ["Domain does not exist"]
        except Timeout:
            results[rtype] = ["DNS query timed out"]
        except NoNameservers:
            results[rtype] = ["No nameservers could be reached"]
        except Exception as e:
            results[rtype] = [f"Error retrieving {rtype} records: {e}"]
            error_message = "An unexpected error occurred while retrieving DNS records."

    return results, error_message

def add_no_cache_headers(response):
    """Optional: only use if you still want manual headers in addition to @cache_control."""
    response["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response["Pragma"] = "no-cache"
    response["Expires"] = "0"
    return response
