"""
Utilities for the IP Address Lookup Tool.
All functions are safe to call from a Django view and will not raise on normal lookup errors.
They return user-displayable data structures (lists/dicts of strings) matching your current template.
"""

from __future__ import annotations

import ipaddress
from typing import Dict, List, Optional, Sequence, Union

import requests
import dns.resolver
import dns.reversename

# --- Tunables ---------------------------------------------------------------

# Keep your current two by default (others may require registration).
DEFAULT_BLACKLIST_SERVERS: Sequence[str] = (
    "zen.spamhaus.org",
    "bl.spamcop.net",
)

DNS_TIMEOUT_SECONDS = 3.0  # keep lookups snappy
HTTP_TIMEOUT_SECONDS = 4.0  # ip-api call timeout

# Optional: set custom DNS resolvers (comment out to use system defaults)
# CUSTOM_NAMESERVERS = ["1.1.1.1", "8.8.8.8"]


# --- Internal helpers -------------------------------------------------------

def _get_resolver() -> dns.resolver.Resolver:
    r = dns.resolver.Resolver(configure=True)
    # If you want to bypass system resolv.conf, uncomment:
    # r.nameservers = list(CUSTOM_NAMESERVERS)
    # Overall timeout for a single query (includes retries)
    r.lifetime = DNS_TIMEOUT_SECONDS
    r.timeout = DNS_TIMEOUT_SECONDS
    return r


def _is_ipv4(ip: str) -> bool:
    try:
        return isinstance(ipaddress.ip_address(ip), ipaddress.IPv4Address)
    except ValueError:
        return False


def _is_ipv6(ip: str) -> bool:
    try:
        return isinstance(ipaddress.ip_address(ip), ipaddress.IPv6Address)
    except ValueError:
        return False


def _ipv6_to_nibble_arpa(ipv6: str) -> Optional[str]:
    """
    Convert an IPv6 address to the nibble format used by some RBLs:
    reverse each hex nibble and join with dots, then append the zone.
    Example: 2001:db8::1 -> 1.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.8.b.d.0.1.0.0.2
    """
    try:
        addr = ipaddress.IPv6Address(ipv6)
    except ValueError:
        return None
    # 32 hex nibbles
    nibbles = "".join(f"{addr.exploded}".replace(":", ""))
    # Reverse and dot-separate
    return ".".join(reversed(list(nibbles)))


# --- Public API -------------------------------------------------------------

def lookup_ptr(ip: str) -> List[str]:
    """
    Return a list of PTR target strings, or a single-element list with an error message.
    """
    try:
        rev_name = dns.reversename.from_address(ip)
        resolver = _get_resolver()
        answers = resolver.resolve(rev_name, "PTR")
        return [r.to_text() for r in answers]
    except Exception as e:
        return [f"Error retrieving PTR records: {str(e)}"]


def geolocate_ip(ip: str) -> Union[Dict[str, Union[str, float, int]], List[str]]:
    """
    Fetch geolocation/ISP info from ip-api.com.
    On success, returns a dict matching your existing keys.
    On failure, returns a single-element list with a message.
    """
    try:
        # ip-api returns 200 even on failures; inspect JSON "status".
        resp = requests.get(
            f"http://ip-api.com/json/{ip}",
            timeout=HTTP_TIMEOUT_SECONDS,
            headers={"User-Agent": "bencritt-ip-tool/1.0"},
        )
        data = resp.json()
        if data.get("status") == "success":
            return {
                "Country": data.get("country"),
                "Region": data.get("regionName"),
                "City": data.get("city"),
                "Latitude": data.get("lat"),
                "Longitude": data.get("lon"),
                "ISP": data.get("isp"),
                "Organization": data.get("org"),
                "AS": data.get("as"),
            }
        else:
            # Keep your current behavior/shape
            message = data.get("message") or "Failed to retrieve geolocation data."
            return [message]
    except Exception as e:
        return [f"Error retrieving geolocation data: {str(e)}"]


def check_blacklists(
    ip: str,
    servers: Sequence[str] = DEFAULT_BLACKLIST_SERVERS,
) -> List[str]:
    """
    Check a small set of DNSBLs. Returns a list of 'Listed/Not listed/Error' strings,
    one per server, preserving your current output style.

    IPv4 is supported broadly. For IPv6, build the nibble format when possible, but
    note many DNSBLs either don't support IPv6 or require specific zones.
    """
    results: List[str] = []
    resolver = _get_resolver()

    is_v4 = _is_ipv4(ip)
    is_v6 = _is_ipv6(ip)

    # Pre-compute reversed tokens
    reversed_v4 = ".".join(reversed(ip.split("."))) if is_v4 else None
    nibble_v6 = _ipv6_to_nibble_arpa(ip) if is_v6 else None

    for server in servers:
        try:
            if is_v4 and reversed_v4:
                query = f"{reversed_v4}.{server}"
            elif is_v6 and nibble_v6:
                # Some zones (e.g., zen.spamhaus.org) support IPv6 via nibble.
                query = f"{nibble_v6}.{server}"
            else:
                results.append(f"Error checking {server}: Unsupported IP format")
                continue

            try:
                resolver.resolve(query, "A")
                results.append(f"Listed on {server}")
            except dns.resolver.NXDOMAIN:
                results.append(f"Not listed on {server}")
            except Exception as e:
                results.append(f"Error checking {server}: {str(e)}")

        except Exception as e:
            results.append(f"Error checking {server}: {str(e)}")

    return results
