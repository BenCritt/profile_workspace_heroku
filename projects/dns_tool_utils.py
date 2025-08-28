from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Tuple
from urllib.parse import urlparse
import ipaddress

import dns.resolver
import dns.reversename
import dns.rdatatype as rdatatype
from dns.resolver import NoAnswer, NXDOMAIN, Timeout, NoNameservers


# Central place to manage which records you support
DEFAULT_RECORD_TYPES: List[str] = [
    "A", "AAAA", "MX", "NS", "CNAME", "TXT", "SOA", "SRV", "CAA",
    # High-value modern records
    "HTTPS", "SVCB", "SSHFP", "DNSKEY", "DS", "RRSIG", "TLSA", "NAPTR",
    # Nice-to-have
    "PTR", "LOC", "URI", "SPF",
]


def normalize_domain(raw: str) -> str:
    """
    Normalize a user-entered domain:
    - strip spaces
    - lower-case
    - strip scheme if a URL was pasted
    - remove trailing dot if present
    Note: we DO NOT convert IPs to reverse names here; fetch_dns_records handles that.
    """
    s = (raw or "").strip()
    # If it looks like a URL, extract hostname
    if s.lower().startswith(("http://", "https://")):
        host = urlparse(s).hostname
        if host:
            s = host
    s = s.strip().rstrip(".").lower()
    return s


def _idna_ascii(name: str) -> str:
    """Return ASCII/IDNA form for a Unicode domain label safely."""
    try:
        return name.encode("idna").decode("ascii")
    except Exception:
        return name  # fall back; resolver may still handle/raise appropriately


def _extract_cnames_from_response(answers) -> List[str]:
    """Extract any CNAMEs encountered while resolving (e.g., during A/AAAA)."""
    cnames: List[str] = []
    try:
        resp = getattr(answers, "response", None)
        if resp and getattr(resp, "answer", None):
            for rrset in resp.answer:
                if rrset.rdtype == rdatatype.CNAME:
                    for r in rrset:
                        # r.target is a dns.name.Name; normalize to no trailing dot
                        cnames.append(r.target.to_text().rstrip("."))
    except Exception:
        pass
    return cnames


def _format_txt_rdata(r) -> str:
    # dnspython may expose .strings (bytes) or .to_text() with quotes
    if hasattr(r, "strings") and r.strings:
        parts = []
        for s in r.strings:
            try:
                parts.append(s.decode("utf-8", "ignore") if isinstance(s, (bytes, bytearray)) else str(s))
            except Exception:
                parts.append(str(s))
        return " ".join(parts)
    # Fallback: strip surrounding quotes if present
    t = r.to_text()
    if len(t) >= 2 and t[0] == '"' and t[-1] == '"':
        return t[1:-1]
    return t


def _format_rdata(r) -> str:
    t = r.rdtype
    if t == rdatatype.TXT:
        return _format_txt_rdata(r)
    if t == rdatatype.MX:
        return f"{getattr(r, 'preference', '?')} {str(getattr(r, 'exchange', '')).rstrip('.')}"
    if t == rdatatype.SSHFP:
        return f"alg={getattr(r, 'algorithm', '?')} fp_type={getattr(r, 'fp_type', '?')} {getattr(r, 'fingerprint', '')}"
    if t == rdatatype.DNSKEY:
        # key tag requires computing from rdata; fall back to to_text() if dnspython API differs
        try:
            from dns.dnssec import key_id
            key_tag = key_id(r)
            return f"flags={r.flags} proto={r.protocol} alg={r.algorithm} key_tag={key_tag}"
        except Exception:
            return r.to_text()
    if t == rdatatype.DS:
        # digest may be bytes in newer dnspython
        digest = getattr(r, "digest", "")
        if isinstance(digest, (bytes, bytearray)):
            digest = digest.hex()
        return f"key_tag={r.key_tag} alg={r.algorithm} digest_type={r.digest_type} digest={digest}"
    if t == rdatatype.TLSA:
        cert = getattr(r, "cert", b"")
        if isinstance(cert, (bytes, bytearray)):
            cert = cert.hex()
        return f"usage={r.usage} selector={r.selector} mtype={r.mtype} cert={cert}"
    if t == rdatatype.SRV:
        return f"priority={r.priority} weight={r.weight} port={r.port} target={str(r.target).rstrip('.')}"
    if t == rdatatype.CAA:
        return f"{r.flags} {r.tag} {getattr(r, 'value', '')}"
    # For HTTPS/SVCB/URI/LOC/etc., .to_text() is typically readable
    return r.to_text()


def _answers_to_list(answers) -> List[str]:
    items: List[str] = []
    for r in answers:
        try:
            items.append(_format_rdata(r))
        except Exception:
            try:
                items.append(r.to_text())
            except Exception as e:
                items.append(f"<unprintable rdata: {e}>")
    return items


def fetch_dns_records(
    domain: str,
    record_types: Optional[Iterable[str]] = None,
    *,
    timeout: Optional[float] = 3.0,
    nameservers: Optional[Iterable[str]] = None,
) -> Tuple[Dict[str, List[str]], Optional[str]]:
    """
    Resolve a set of DNS record types for a domain.
    Returns (results_dict, error_message).
    - results_dict maps record type -> list of strings (either answers or a single explanatory message)
    - error_message is a general message if any unexpected error occurred
    Behavior tweaks:
    - If input is an IP, we automatically perform PTR lookup only.
    - We surface CNAMEs encountered during A/AAAA resolution.
    - For direct CNAME queries, we use raise_on_no_answer=False to avoid exceptions.
    """
    resolver = dns.resolver.Resolver()
    if timeout is not None:
        try:
            resolver.timeout = float(timeout)
            # dnspython uses both timeout (per try) and lifetime (overall)
            resolver.lifetime = max(float(timeout), getattr(resolver, "lifetime", float(timeout)))
        except Exception:
            pass
    if nameservers:
        resolver.nameservers = list(nameservers)

    # Decide on qname and record set based on whether input is an IP
    qname = domain
    rtypes = list(record_types) if record_types else list(DEFAULT_RECORD_TYPES)

    is_ip = False
    try:
        ipaddress.ip_address(domain)
        is_ip = True
    except ValueError:
        is_ip = False

    if is_ip:
        # For IPs, query the reverse name and limit to PTR for a clean UX
        qname = dns.reversename.from_address(domain).to_text().rstrip(".")
        rtypes = ["PTR"]
    else:
        # Convert Unicode IDN to ASCII for wire format
        qname = _idna_ascii(domain)

    results: Dict[str, List[str]] = {}
    error_message: Optional[str] = None
    saw_nxdomain = False

    for rtype in rtypes:
        try:
            # Special handling for direct CNAME queries
            if rtype.upper() == "CNAME":
                ans = resolver.resolve(qname, "CNAME", raise_on_no_answer=False)
                if getattr(ans, "rrset", None):
                    results["CNAME"] = _answers_to_list(ans)
                else:
                    results["CNAME"] = ["No records found"]
                continue

            answers = resolver.resolve(qname, rtype)
            items = _answers_to_list(answers)

            # If A/AAAA, surface any followed CNAMEs first (when present)
            if rtype in ("A", "AAAA"):
                cnames = _extract_cnames_from_response(answers)
                if cnames:
                    items = cnames + items

            results[rtype] = items

        except NoAnswer:
            results[rtype] = ["No records found"]
        except NXDOMAIN:
            results[rtype] = ["Domain does not exist"]
            saw_nxdomain = True
        except Timeout:
            results[rtype] = ["DNS query timed out"]
        except NoNameservers:
            results[rtype] = ["No nameservers could be reached"]
        except Exception as e:
            results[rtype] = [f"Error retrieving {rtype} records: {e}"]
            error_message = "An unexpected error occurred while retrieving DNS records."

        # Optional micro-optimization: stop if NXDOMAIN
        if saw_nxdomain:
            # Fill remaining types with the same message for consistency
            for rt in rtypes:
                if rt not in results:
                    results[rt] = ["Domain does not exist"]
            break

    return results, error_message


def add_no_cache_headers(response):
    """Optional: only use if you still want manual headers in addition to @cache_control."""
    response["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response["Pragma"] = "no-cache"
    response["Expires"] = "0"
    return response
