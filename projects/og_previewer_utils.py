"""
og_previewer_utils.py — Open Graph / Social Card Previewer
Utility layer: HTML parser, fetch helpers, URL normalisation, and card-data builder.

All heavy logic lives here so views.py stays thin.

Dependencies:
  `requests` is used if available (almost certainly in requirements.txt already).
  Falls back to urllib so the app degrades gracefully rather than hard-crashing.
  If requests isn't installed yet: requests>=2.28.0
"""

import re
import time
import urllib.request
import urllib.error
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

# Try requests first; fall back to urllib on import failure.
try:
    import requests as _requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False


# ── Constants ──────────────────────────────────────────────────────────────────

FETCH_TIMEOUT   = 10          # seconds before giving up on a slow server
MAX_BODY_BYTES  = 512_000     # 512 KB — enough to capture any <head> without streaming huge pages
USER_AGENT      = (
    "Mozilla/5.0 (compatible; OGPreviewer/1.0; +https://www.bencritt.net/projects/og-previewer/)"
)

# Truncation limits that match each platform's documented / observed rendering behaviour.
LIMITS = {
    "google": {
        "title":       60,
        "description": 160,
        "url":         75,
    },
    "twitter_summary": {
        "title":       70,
        "description": 200,
    },
    "twitter_large": {
        "title":       70,
        "description": 200,
    },
    "facebook": {
        "title":       90,
        "description": 300,
        "site_name":   30,
    },
    "linkedin": {
        "title":       120,
        "description": 300,
    },
}


# ── HTML Parser ────────────────────────────────────────────────────────────────

class HeadTagParser(HTMLParser):
    """
    Lightweight SAX-style parser that extracts only what we need from <head>.
    Stops as soon as </head> or <body> is encountered — avoids scanning the
    entire document body, which could be very large.
    """

    def __init__(self):
        super().__init__()
        self.in_head   = False
        self.in_title  = False
        self.head_done = False
        self.tags: dict[str, str] = {}   # property/name → content
        self._title_buf: list[str] = []

    # ── HTMLParser callbacks ──────────────────────────────────────────────────

    def handle_starttag(self, tag, attrs):
        if self.head_done:
            return

        attr_dict = dict(attrs)

        if tag == "head":
            self.in_head = True
            return

        # Some pages omit </head>; treat <body> as end-of-head too.
        if tag == "body":
            self.head_done = True
            return

        if not self.in_head:
            return

        if tag == "title":
            self.in_title = True
            return

        if tag == "meta":
            self._process_meta(attr_dict)
            return

        if tag == "link":
            self._process_link(attr_dict)
            return

    def handle_endtag(self, tag):
        if tag == "head":
            self.head_done = True
            self.in_head   = False
        if tag == "title":
            self.in_title = False
            self.tags["_html_title"] = "".join(self._title_buf).strip()

    def handle_data(self, data):
        if self.in_title:
            self._title_buf.append(data)

    # ── Tag processors ─────────────────────────────────────────────────────────

    def _process_meta(self, attrs: dict):
        """Store meta[property] and meta[name] tags keyed by their identifier."""
        content = attrs.get("content", "").strip()
        if not content:
            return

        # og:*, article:*, video:*, music:*, etc.
        prop = attrs.get("property", "").lower().strip()
        if prop:
            self.tags[prop] = content
            return

        # name="description" | "twitter:card" | "robots" | etc.
        name = attrs.get("name", "").lower().strip()
        if name:
            self.tags[name] = content
            return

    def _process_link(self, attrs: dict):
        """Store canonical URL and the first favicon encountered."""
        rel  = attrs.get("rel", "").lower().strip()
        href = attrs.get("href", "").strip()
        if not href:
            return

        if rel == "canonical":
            self.tags["_canonical"] = href
        elif rel in ("icon", "shortcut icon", "apple-touch-icon"):
            # Keep only the first favicon found.
            if "_favicon" not in self.tags:
                self.tags["_favicon"] = href


# ── Fetch helpers ──────────────────────────────────────────────────────────────

def fetch_head_html(url: str) -> tuple[str, str, float]:
    """
    Fetch the page at `url`, returning (html_snippet, final_url, elapsed_seconds).
    Reads at most MAX_BODY_BYTES to avoid streaming huge files into memory.
    Raises ValueError with a user-friendly message on any failure.
    """
    headers = {"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"}
    start   = time.perf_counter()

    if REQUESTS_AVAILABLE:
        try:
            resp = _requests.get(
                url,
                headers=headers,
                timeout=FETCH_TIMEOUT,
                allow_redirects=True,
                stream=True,
            )
            resp.raise_for_status()
            # Stream only what we need.
            raw_bytes = b""
            for chunk in resp.iter_content(chunk_size=8192):
                raw_bytes += chunk
                if len(raw_bytes) >= MAX_BODY_BYTES:
                    break
            elapsed   = time.perf_counter() - start
            final_url = resp.url
            encoding  = resp.encoding or "utf-8"
            html      = raw_bytes.decode(encoding, errors="replace")
        except _requests.exceptions.Timeout:
            raise ValueError(
                f"The request timed out after {FETCH_TIMEOUT}s. "
                "The server may be slow or unreachable."
            )
        except _requests.exceptions.TooManyRedirects:
            raise ValueError("Too many redirects — the URL may be caught in a redirect loop.")
        except _requests.exceptions.ConnectionError as exc:
            raise ValueError(f"Connection error: {exc}")
        except _requests.exceptions.HTTPError as exc:
            raise ValueError(f"HTTP error: {exc}")
        except Exception as exc:
            raise ValueError(f"Unexpected fetch error: {exc}")
    else:
        # urllib fallback for environments where requests isn't installed.
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT) as resp:
                raw_bytes = resp.read(MAX_BODY_BYTES)
                elapsed   = time.perf_counter() - start
                final_url = resp.url
                encoding  = resp.headers.get_content_charset("utf-8")
                html      = raw_bytes.decode(encoding, errors="replace")
        except urllib.error.URLError as exc:
            raise ValueError(f"URL error: {exc.reason}")
        except Exception as exc:
            raise ValueError(f"Unexpected fetch error: {exc}")

    return html, final_url, round(elapsed, 3)


def normalise_url(raw: str) -> str:
    """Prepend https:// if no scheme is present."""
    raw = raw.strip()
    if raw and not raw.startswith(("http://", "https://")):
        raw = "https://" + raw
    return raw


def parse_tags(html: str) -> dict:
    """Feed raw HTML through HeadTagParser and return the tags dict."""
    parser = HeadTagParser()
    parser.feed(html)
    return parser.tags


# ── URL helpers ────────────────────────────────────────────────────────────────

def absolute_url(href: str, base_url: str) -> str:
    """Resolve a potentially relative URL against the page's base URL."""
    if not href:
        return ""
    return urljoin(base_url, href)


def domain_from_url(url: str) -> str:
    """Extract bare domain (www-stripped) for display labels."""
    try:
        parsed = urlparse(url)
        domain = parsed.netloc or parsed.path
        return re.sub(r"^www\.", "", domain)
    except Exception:
        return url


def breadcrumb_url(url: str, max_len: int = 75) -> str:
    """
    Format a URL Google-SERP-style:  domain › path › segment
    Truncates to max_len characters.
    """
    try:
        parsed = urlparse(url)
        domain = re.sub(r"^www\.", "", parsed.netloc)
        path   = parsed.path.rstrip("/")
        parts  = [p for p in path.split("/") if p]
        crumb  = domain + (" › " + " › ".join(parts) if parts else "")
        if len(crumb) > max_len:
            crumb = crumb[:max_len] + "…"
        return crumb
    except Exception:
        return url[:max_len]


def truncate(text: str, limit: int) -> tuple[str, bool]:
    """Return (truncated_text, was_truncated). Appends ellipsis on truncation."""
    if not text or len(text) <= limit:
        return text or "", False
    return text[:limit].rstrip() + "…", True


# ── Card data builder ──────────────────────────────────────────────────────────

def build_card_data(tags: dict, final_url: str) -> dict:
    """
    Consolidate raw head tags into a fully resolved, platform-specific context
    dict that the template can consume directly.

    Applies fallback priority chains, platform-specific truncations, favicon
    resolution, and health score calculation.
    """
    # ── Title resolution ──────────────────────────────────────────────────────
    og_title   = tags.get("og:title",     "").strip()
    tw_title   = tags.get("twitter:title","").strip()
    html_title = tags.get("_html_title",  "").strip()
    base_title = og_title or tw_title or html_title

    # ── Description resolution ─────────────────────────────────────────────────
    og_desc   = tags.get("og:description",      "").strip()
    tw_desc   = tags.get("twitter:description", "").strip()
    meta_desc = tags.get("description",          "").strip()

    # ── Image resolution ───────────────────────────────────────────────────────
    og_image   = tags.get("og:image",     "").strip()
    tw_image   = tags.get("twitter:image","").strip()
    base_image = og_image or tw_image

    # ── Misc ──────────────────────────────────────────────────────────────────
    canonical    = tags.get("_canonical", "").strip()
    og_url       = tags.get("og:url",     "").strip()
    display_url  = canonical or og_url or final_url
    og_site_name = tags.get("og:site_name", "").strip()
    tw_card_type = tags.get("twitter:card", "summary").strip().lower()
    tw_site      = tags.get("twitter:site", "").strip()   # @handle
    og_type      = tags.get("og:type", "website").strip()

    # Resolve favicon to absolute URL.
    favicon_raw = tags.get("_favicon", "")
    favicon     = absolute_url(favicon_raw, final_url) if favicon_raw else ""

    # Resolve image URLs.
    if base_image:
        base_image = absolute_url(base_image, final_url)

    # Resolve twitter image separately if it differs.
    tw_effective_image = tw_image or og_image
    if tw_effective_image and tw_effective_image != base_image:
        tw_effective_image = absolute_url(tw_effective_image, final_url)

    # ── Health / audit checks ─────────────────────────────────────────────────
    checks = {
        "has_og_title":       bool(og_title),
        "has_og_description": bool(og_desc),
        "has_og_image":       bool(og_image),
        "has_twitter_card":   bool(tags.get("twitter:card")),
        "has_meta_desc":      bool(meta_desc),
        "has_canonical":      bool(canonical),
        "image_likely_sized": bool(base_image),   # can't verify dimensions server-side
        "tw_card_valid":      tw_card_type in (
            "summary", "summary_large_image", "app", "player"
        ),
    }
    score     = sum(1 for v in checks.values() if v)
    max_score = len(checks)

    # ── Audit table rows ──────────────────────────────────────────────────────
    KNOWN_TAGS = [
        # (property,              value,                              is_important, group)
        ("og:title",              og_title,                           True,         "og"),
        ("og:description",        og_desc,                            True,         "og"),
        ("og:image",              og_image,                           True,         "og"),
        ("og:url",                og_url,                             False,        "og"),
        ("og:type",               tags.get("og:type", ""),            False,        "og"),
        ("og:site_name",          og_site_name,                       False,        "og"),
        ("twitter:card",          tags.get("twitter:card", ""),       True,         "twitter"),
        ("twitter:title",         tw_title,                           False,        "twitter"),
        ("twitter:description",   tw_desc,                            False,        "twitter"),
        ("twitter:image",         tw_image,                           False,        "twitter"),
        ("twitter:site",          tw_site,                            False,        "twitter"),
        ("description",           meta_desc,                          True,         "meta"),
        ("canonical",             canonical,                          True,         "meta"),
    ]
    audit = [
        {
            "property":     prop,
            "value":        value,
            "present":      bool(value),
            "is_important": is_important,
            "group":        group,
        }
        for prop, value, is_important, group in KNOWN_TAGS
    ]

    # ── Platform-specific card data ───────────────────────────────────────────

    # Google
    google_title,       google_title_trunc = truncate(base_title or html_title, LIMITS["google"]["title"])
    google_desc,        google_desc_trunc  = truncate(meta_desc or og_desc,     LIMITS["google"]["description"])
    google_url_display = breadcrumb_url(display_url, LIMITS["google"]["url"])

    # Twitter/X (both card types use same source chain)
    tw_eff_title = tw_title or og_title or html_title
    tw_eff_desc  = tw_desc  or og_desc  or meta_desc
    tw_sum_title, _ = truncate(tw_eff_title, LIMITS["twitter_summary"]["title"])
    tw_sum_desc,  _ = truncate(tw_eff_desc,  LIMITS["twitter_summary"]["description"])
    tw_lg_title,  _ = truncate(tw_eff_title, LIMITS["twitter_large"]["title"])
    tw_lg_desc,   _ = truncate(tw_eff_desc,  LIMITS["twitter_large"]["description"])
    tw_domain       = domain_from_url(display_url)

    # Facebook / OG
    fb_title,     fb_title_trunc = truncate(og_title or html_title,        LIMITS["facebook"]["title"])
    fb_desc,      fb_desc_trunc  = truncate(og_desc  or meta_desc,         LIMITS["facebook"]["description"])
    fb_site_name, _              = truncate(og_site_name or domain_from_url(display_url), LIMITS["facebook"]["site_name"])

    # LinkedIn
    li_title, li_title_trunc = truncate(og_title or tw_title or html_title, LIMITS["linkedin"]["title"])
    li_desc,  li_desc_trunc  = truncate(og_desc  or tw_desc  or meta_desc,  LIMITS["linkedin"]["description"])
    li_domain                = domain_from_url(display_url)

    return {
        # ── Raw / shared ──────────────────────────────────────────────────────
        "final_url":    final_url,
        "display_url":  display_url,
        "favicon":      favicon,
        "og_type":      og_type,
        "base_image":   base_image,
        "tw_card_type": tw_card_type,
        "tw_site":      tw_site,
        "og_site_name": og_site_name,
        "raw_tags":     tags,
        "audit":        audit,
        # ── Google ────────────────────────────────────────────────────────────
        "google_title":       google_title,
        "google_title_trunc": google_title_trunc,
        "google_desc":        google_desc,
        "google_desc_trunc":  google_desc_trunc,
        "google_url_display": google_url_display,
        # ── Twitter/X ─────────────────────────────────────────────────────────
        "tw_sum_title": tw_sum_title,
        "tw_sum_desc":  tw_sum_desc,
        "tw_lg_title":  tw_lg_title,
        "tw_lg_desc":   tw_lg_desc,
        "tw_image":     tw_effective_image,
        "tw_domain":    tw_domain,
        # ── Facebook ──────────────────────────────────────────────────────────
        "fb_title":       fb_title,
        "fb_title_trunc": fb_title_trunc,
        "fb_desc":        fb_desc,
        "fb_desc_trunc":  fb_desc_trunc,
        "fb_site_name":   fb_site_name,
        # ── LinkedIn ──────────────────────────────────────────────────────────
        "li_title":       li_title,
        "li_title_trunc": li_title_trunc,
        "li_desc":        li_desc,
        "li_desc_trunc":  li_desc_trunc,
        "li_domain":      li_domain,
        # ── Health ────────────────────────────────────────────────────────────
        "checks":    checks,
        "score":     score,
        "max_score": max_score,
        "score_pct": round((score / max_score) * 100),
    }
