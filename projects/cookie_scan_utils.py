from __future__ import annotations

import gc
import hashlib
import os
from collections import deque
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple
from urllib.parse import urlparse, urljoin

import tldextract
from playwright.sync_api import sync_playwright

# Optional memory trimming helper (Linux); safe no-op elsewhere
try:
    from . import mem_utils  # type: ignore
except Exception:
    mem_utils = None  # type: ignore


# --- Tuning knobs (safe defaults for 512MB dynos) ---------------------------

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# Cap “Observed Set-Cookie headers” so we don't hold huge lists in RAM.
MAX_SET_COOKIE_OBSERVATIONS = 200

# Block heavy resources but keep scripts/XHR so JS-set cookies still happen.
BLOCKED_RESOURCE_TYPES = {"image", "media", "font"}


# --- Small helpers ---------------------------------------------------------

def normalize_url(url: str) -> str:
    url = (url or "").strip()
    if not url:
        return url
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url


def is_http_url(url: str) -> bool:
    try:
        return urlparse(url).scheme in ("http", "https")
    except Exception:
        return False


def get_registrable_domain(url: str) -> str:
    u = urlparse(url)
    ext = tldextract.extract(u.netloc)
    if ext.suffix:
        return f"{ext.domain}.{ext.suffix}".lower()
    return u.netloc.lower()


def is_internal(candidate_url: str, base_registrable_domain: str) -> bool:
    try:
        host = urlparse(candidate_url).netloc.lower()
        # Allow subdomains of the same registrable domain
        return host.endswith(base_registrable_domain)
    except Exception:
        return False


def format_expires(expires: Any) -> str:
    if not expires:
        return "Session"
    try:
        # Playwright cookies uses Unix timestamp seconds in many cases
        if isinstance(expires, (int, float)):
            dt = datetime.fromtimestamp(expires, tz=timezone.utc)
            return dt.strftime("%Y-%m-%d %H:%M:%S UTC")
    except Exception:
        pass
    return str(expires)


def classify_party(cookie_domain: str, base_reg_domain: str) -> str:
    d = (cookie_domain or "").lstrip(".").lower()
    if not d:
        return "Unknown"
    return "First-party" if d.endswith(base_reg_domain) else "Third-party"


def redact_value(value: str) -> str:
    if not value:
        return ""
    # Store only a short hash so we never keep long cookie values in memory
    h = hashlib.sha256(value.encode("utf-8", errors="ignore")).hexdigest()
    return f"sha256:{h[:16]}..."


def extract_links(page, base_url: str, base_reg_domain: str, limit: int = 200) -> List[str]:
    """
    Extract up to `limit` absolute links from <a href>.
    Limiting protects memory on link-heavy pages.
    """
    try:
        hrefs = page.eval_on_selector_all(
            "a[href]",
            f"els => els.slice(0, {int(limit)}).map(a => a.href)"
        )
    except Exception:
        hrefs = []

    out: List[str] = []
    for href in hrefs or []:
        if not href:
            continue
        try:
            abs_url = urljoin(base_url, href)
        except Exception:
            continue
        if not is_http_url(abs_url):
            continue
        if not is_internal(abs_url, base_reg_domain):
            continue
        out.append(abs_url)
    return out


def infer_cookie_type_and_purpose(name: str) -> Tuple[str, str]:
    """
    Very lightweight heuristic so we don't need big lookup tables in RAM.
    You can expand this later.
    """
    n = (name or "").lower()

    # Common analytics patterns
    if n.startswith("_ga") or "google" in n or "gtm" in n:
        return "Analytics", "Used to distinguish users and track site usage/analytics."

    if "session" in n or n in {"csrftoken", "sessionid"}:
        return "Necessary", "Used to maintain session state and security."

    if "cf_" in n or n.startswith("__cf"):
        return "Necessary", "Cloudflare cookie used for security/performance."

    return "Unknown", "Purpose not identified."


def _launch_chromium(p, *, headless: bool) -> Any:
    """
    Heroku-friendly + lower-memory launch:
    - If CHROMIUM_EXECUTABLE_PATH exists (buildpack), use it.
    - Otherwise, local dev: use Playwright-managed Chromium.
    """
    exe = (os.getenv("CHROMIUM_EXECUTABLE_PATH") or "").strip()

    args = [
        "--no-sandbox",
        "--disable-setuid-sandbox",
        "--disable-dev-shm-usage",  # use /tmp instead of /dev/shm
        "--disable-gpu",
        "--no-zygote",
        "--disable-extensions",
        "--disable-background-networking",
        "--disable-default-apps",
        "--disable-sync",
        "--disable-translate",
        "--metrics-recording-only",
        "--mute-audio",
        "--no-first-run",
        "--disable-features=site-per-process,TranslateUI",
    ]

    launch_kwargs: Dict[str, Any] = {
        "headless": bool(headless),
        "args": args,
        "chromium_sandbox": False,
    }
    if exe:
        launch_kwargs["executable_path"] = exe

    return p.chromium.launch(**launch_kwargs)


# --- Main scanner ----------------------------------------------------------

def scan_site_for_cookies(
    start_url: str,
    max_pages: int = 10,
    max_depth: int = 1,
    wait_ms: int = 1500,
    timeout_ms: int = 30000,
    wait_until: str = "domcontentloaded",
    headless: bool = True,
    ignore_https_errors: bool = False,
) -> Dict[str, Any]:
    """
    Crawl inside the start registrable domain and collect:
      - Cookies currently in the browser context cookie jar
      - Observed Set-Cookie headers (capped to MAX_SET_COOKIE_OBSERVATIONS)

    Memory reductions vs typical Playwright crawlers:
      - Block images/fonts/media
      - Cap set-cookie observations
      - Cap link extraction
      - Close each Page promptly
      - Trim memory after run
    """
    start_url = normalize_url(start_url)
    if not is_http_url(start_url):
        raise ValueError("Start URL must be http(s).")

    base_reg_domain = get_registrable_domain(start_url)

    visited: set[str] = set()
    q: deque[Tuple[str, int]] = deque()
    q.append((start_url, 0))

    # Store unique cookies by (name, domain, path) to avoid duplicates
    cookie_map: Dict[Tuple[str, str, str], Dict[str, Any]] = {}

    set_cookie_observations: List[Dict[str, Any]] = []

    with sync_playwright() as p:
        browser = _launch_chromium(p, headless=headless)

        context = browser.new_context(
            ignore_https_errors=ignore_https_errors,
            user_agent=DEFAULT_USER_AGENT,
            accept_downloads=False,
            service_workers="block",
        )
        context.set_default_timeout(timeout_ms)

        # Block heavy resource types to reduce memory + bandwidth
        def _route_handler(route, request):
            try:
                if request.resource_type in BLOCKED_RESOURCE_TYPES:
                    return route.abort()
            except Exception:
                pass
            return route.continue_()

        try:
            context.route("**/*", _route_handler)
        except Exception:
            pass

        # Capture Set-Cookie headers (best effort) but CAP list size
        def on_response(response):
            if len(set_cookie_observations) >= MAX_SET_COOKIE_OBSERVATIONS:
                return
            try:
                sc = response.header_value("set-cookie")
                if not sc:
                    return
                # Some servers return multiple cookies separated by newlines
                for line in sc.split("\n"):
                    line = (line or "").strip()
                    if not line:
                        continue
                    if len(set_cookie_observations) >= MAX_SET_COOKIE_OBSERVATIONS:
                        break
                    set_cookie_observations.append(
                        {
                            "url": response.url,
                            "set_cookie": line[:5000],  # avoid storing huge header strings
                        }
                    )
            except Exception:
                return

        context.on("response", on_response)

        try:
            while q and len(visited) < max_pages:
                url, depth = q.popleft()
                if url in visited:
                    continue
                if depth > max_depth:
                    continue

                visited.add(url)

                page = context.new_page()
                try:
                    page.goto(url, wait_until=wait_until, timeout=timeout_ms)
                    if wait_ms:
                        page.wait_for_timeout(wait_ms)

                    # Collect cookies currently in the jar
                    for c in context.cookies() or []:
                        key = (c.get("name", ""), c.get("domain", ""), c.get("path", ""))
                        cookie_map[key] = c

                    # Expand crawl frontier (bounded)
                    if depth < max_depth and len(visited) < max_pages:
                        for nxt in extract_links(page, url, base_reg_domain, limit=200):
                            if nxt not in visited:
                                q.append((nxt, depth + 1))

                finally:
                    try:
                        page.close()
                    except Exception:
                        pass

                # Helps keep peak RSS down on small dynos
                gc.collect()

        finally:
            try:
                context.close()
            except Exception:
                pass
            try:
                browser.close()
            except Exception:
                pass

            gc.collect()
            try:
                if mem_utils:
                    mem_utils.trim_now()
            except Exception:
                pass

    # Enrich cookie data for display
    enriched: List[Dict[str, Any]] = []
    for c in cookie_map.values():
        name = c.get("name", "")
        cookie_type, purpose = infer_cookie_type_and_purpose(name)
        domain = c.get("domain", "")
        enriched.append(
            {
                "name": name,
                "value_redacted": redact_value(c.get("value", "")),
                "domain": domain,
                "path": c.get("path", ""),
                "expires_human": format_expires(c.get("expires")),
                "httpOnly": bool(c.get("httpOnly")),
                "secure": bool(c.get("secure")),
                "sameSite": c.get("sameSite") or "",
                "party": classify_party(domain, base_reg_domain),
                "cookie_type": cookie_type,
                "purpose": purpose,
            }
        )

    summary = {
        "start_url": start_url,
        "base_registrable_domain": base_reg_domain,
        "visited_urls": len(visited),
        "cookies_in_jar": len(enriched),
        "set_cookie_headers_observed": len(set_cookie_observations),
    }

    return {
        "summary": summary,
        "visited_urls": list(visited),
        "cookies": enriched,
        "set_cookie_headers": set_cookie_observations,
    }
