"""
Redirect Chain Checke

Core logic for following a URL's redirect chain hop-by-hop.
Returns structured data about each hop including status codes,
response times, headers, and any issues detected.
"""

import time
from urllib.parse import urlparse

import requests


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Maximum number of redirects to follow before declaring a runaway chain.
MAX_REDIRECTS = 20

# Per-hop request timeout in seconds.
REQUEST_TIMEOUT = 10

# HTTP status codes that indicate a redirect.
REDIRECT_STATUS_CODES = {301, 302, 303, 307, 308}

# Human-readable labels for redirect status codes.
STATUS_LABELS = {
    301: "301 Moved Permanently",
    302: "302 Found (Temporary)",
    303: "303 See Other",
    307: "307 Temporary Redirect",
    308: "308 Permanent Redirect",
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def trace_redirects(start_url):
    """
    Follow the redirect chain starting at `start_url`.

    Returns a dict with:
        "hops"       : list of hop dicts (see below)
        "total_hops" : int, number of redirects (excludes the final response)
        "total_time" : float, cumulative wall-clock seconds
        "issues"     : list of human-readable warning/error strings
        "has_loop"   : bool, True if a redirect loop was detected
        "final_url"  : str, the URL that ultimately responded with a non-redirect
        "chain_type" : str, summary label ("clean", "warnings", "errors")

    Each hop dict contains:
        "hop_number"    : int (1-indexed; 0 = the original request)
        "url"           : str, the URL requested
        "status_code"   : int
        "status_label"  : str, e.g. "301 Moved Permanently"
        "location"      : str or None, the Location header value
        "response_time" : float, seconds for this hop
        "server"        : str or None, the Server header
        "content_type"  : str or None
        "is_redirect"   : bool
        "is_final"      : bool
        "error"         : str or None, if the request itself failed
    """
    hops = []
    issues = []
    visited_urls = []
    current_url = start_url
    total_time = 0.0
    has_loop = False

    for i in range(MAX_REDIRECTS + 1):
        # --- Loop detection (check before making the request) ---
        if current_url in visited_urls:
            has_loop = True
            issues.append(
                f"Redirect loop detected: hop {i} returns to {current_url} "
                f"(first seen at hop {visited_urls.index(current_url)})."
            )
            break

        visited_urls.append(current_url)

        # --- Make the request (do NOT follow redirects automatically) ---
        hop = _fetch_hop(current_url, hop_number=i)
        total_time += hop["response_time"]
        hops.append(hop)

        # If the request itself failed (DNS error, timeout, etc.), stop.
        if hop["error"]:
            issues.append(f"Hop {i}: {hop['error']}")
            break

        # If this is not a redirect, we've reached the final destination.
        if not hop["is_redirect"]:
            hop["is_final"] = True
            break

        # --- Collect the Location header for the next hop ---
        location = hop["location"]
        if not location:
            issues.append(
                f"Hop {i}: Server returned {hop['status_code']} but "
                f"no Location header was present."
            )
            break

        current_url = location

    else:
        # We exhausted MAX_REDIRECTS without reaching a final response.
        issues.append(
            f"Redirect chain exceeded {MAX_REDIRECTS} hops. "
            f"Possible runaway redirect."
        )

    # --- Post-processing: detect common issues ---
    issues.extend(_analyze_chain(hops))

    # Determine the final URL (last hop's URL, or the last Location).
    final_url = hops[-1]["url"] if hops else start_url

    # Classify overall chain health.
    if any("loop" in iss.lower() or "exceeded" in iss.lower() for iss in issues):
        chain_type = "errors"
    elif issues:
        chain_type = "warnings"
    else:
        chain_type = "clean"

    return {
        "hops": hops,
        "total_hops": max(len(hops) - 1, 0),  # Exclude the final landing.
        "total_time": round(total_time, 3),
        "issues": issues,
        "has_loop": has_loop,
        "final_url": final_url,
        "chain_type": chain_type,
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _fetch_hop(url, hop_number):
    """
    Perform a single HTTP request without following redirects.
    Returns a structured hop dict.
    """
    hop = {
        "hop_number": hop_number,
        "url": url,
        "status_code": None,
        "status_label": "",
        "location": None,
        "response_time": 0.0,
        "server": None,
        "content_type": None,
        "is_redirect": False,
        "is_final": False,
        "error": None,
    }

    try:
        start = time.monotonic()
        resp = requests.get(
            url,
            allow_redirects=False,
            timeout=REQUEST_TIMEOUT,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (compatible; BenCrittRedirectChecker/1.0; "
                    "+https://www.bencritt.net/projects/redirect-checker/)"
                ),
                "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
            },
            # Don't download large response bodies — we only need headers.
            stream=True,
        )
        elapsed = time.monotonic() - start

        hop["status_code"] = resp.status_code
        hop["status_label"] = STATUS_LABELS.get(
            resp.status_code, f"{resp.status_code}"
        )
        hop["response_time"] = round(elapsed, 3)
        hop["server"] = resp.headers.get("Server")
        hop["content_type"] = resp.headers.get("Content-Type")

        if resp.status_code in REDIRECT_STATUS_CODES:
            hop["is_redirect"] = True
            raw_location = resp.headers.get("Location", "")

            # Handle relative Location headers by resolving against the
            # current URL's scheme + netloc.
            if raw_location and not raw_location.startswith(("http://", "https://")):
                parsed_current = urlparse(url)
                if raw_location.startswith("/"):
                    raw_location = (
                        f"{parsed_current.scheme}://{parsed_current.netloc}"
                        f"{raw_location}"
                    )
                else:
                    # Relative path — resolve against current directory.
                    base_path = parsed_current.path.rsplit("/", 1)[0]
                    raw_location = (
                        f"{parsed_current.scheme}://{parsed_current.netloc}"
                        f"{base_path}/{raw_location}"
                    )

            hop["location"] = raw_location if raw_location else None

        # Close the connection promptly (we streamed and don't need the body).
        resp.close()

    except requests.exceptions.Timeout:
        hop["error"] = f"Request timed out after {REQUEST_TIMEOUT}s."
        hop["response_time"] = REQUEST_TIMEOUT

    except requests.exceptions.TooManyRedirects:
        hop["error"] = "Too many redirects (requests library limit)."

    except requests.exceptions.ConnectionError as exc:
        # Provide a friendlier message for DNS failures.
        err_str = str(exc)
        if "NameResolutionError" in err_str or "getaddrinfo" in err_str:
            parsed = urlparse(url)
            hop["error"] = f"DNS resolution failed for {parsed.hostname}."
        else:
            hop["error"] = f"Connection error: {_truncate(err_str, 200)}"

    except requests.exceptions.SSLError as exc:
        hop["error"] = f"SSL/TLS error: {_truncate(str(exc), 200)}"

    except requests.exceptions.RequestException as exc:
        hop["error"] = f"Request failed: {_truncate(str(exc), 200)}"

    return hop


def _analyze_chain(hops):
    """
    Examine the completed hop list for common SEO/technical issues.
    Returns a list of human-readable warning strings.
    """
    warnings = []

    redirect_hops = [h for h in hops if h["is_redirect"]]

    # Flag chains longer than 2 redirects.
    if len(redirect_hops) > 2:
        warnings.append(
            f"Long redirect chain: {len(redirect_hops)} redirects detected. "
            f"Search engines prefer chains of 2 or fewer hops."
        )

    # Flag mixed permanent + temporary redirects.
    permanent_codes = {301, 308}
    temporary_codes = {302, 303, 307}
    has_permanent = any(h["status_code"] in permanent_codes for h in redirect_hops)
    has_temporary = any(h["status_code"] in temporary_codes for h in redirect_hops)
    if has_permanent and has_temporary:
        warnings.append(
            "Mixed redirect types: chain contains both permanent (301/308) "
            "and temporary (302/303/307) redirects. This can confuse search "
            "engine crawlers about which URL to index."
        )

    # Flag HTTP → HTTPS hops that aren't 301 (common misconfiguration).
    for h in redirect_hops:
        if (
            h["url"].startswith("http://")
            and h["location"]
            and h["location"].startswith("https://")
            and h["status_code"] != 301
        ):
            warnings.append(
                f"Hop {h['hop_number']}: HTTP→HTTPS redirect uses "
                f"{h['status_code']} instead of 301. For SEO, the "
                f"HTTP→HTTPS redirect should be a 301 Moved Permanently."
            )

    # Flag any hop with a slow response time (over 2 seconds).
    for h in hops:
        if h["response_time"] > 2.0 and not h["error"]:
            warnings.append(
                f"Hop {h['hop_number']}: Slow response "
                f"({h['response_time']}s). Each redirect adds latency."
            )

    return warnings


def _truncate(text, max_length):
    """Truncate a string and append '…' if it exceeds max_length."""
    if len(text) <= max_length:
        return text
    return text[: max_length - 1] + "…"
