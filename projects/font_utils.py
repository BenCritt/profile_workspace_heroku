"""
Font Inspector
=================================================


This module powers the Font Inspector app my website.
It fetches a web page, discovers all stylesheets, parses 
`@font-face` blocks and `font-family` declarations, and then
infers where each font comes from (e.g., Google Fonts, Adobe Fonts, a
commercial catalogue, or self‑hosted). Finally,  and offers guidance
regarding license requirements.

Layout overview
---------------
1. **Imports & configuration** — global constants, regexes, and logging tweaks.
2. **Normalization helpers** — functions that make font names easier to match.
3. **Font Awesome classifier** — quick path for FA family names.
4. **Google Fonts loader** — pulls the official family list or uses a fallback.
5. **Lookup maps** — known catalogues, system fonts, CDN hosts, etc.
6. **HTTP helpers** — safe, timeout‑bound fetch with user‑friendly errors.
7. **CSS collectors/parsers** — gather CSS, resolve `@import`, harvest families.
8. **License/source inference** — logic that decides source and licensing.
9. **Report builders** — table/CSV helpers the UI consumes.
10. **Async task API** — queue, status polling, CSV streaming (Django views).


Key design goals
----------------
- **Resilience**: real‑world CSS can be malformed. We use both a structured
parser (`cssutils` / `tinycss2`) *and* regex fallbacks.
- **Safety**: all network operations have timeouts; user‑facing error messages
are concise and helpful.
- **Portability**: works on servers (e.g., Heroku) where the filesystem is
ephemeral; CSVs are created under `/tmp` by default.
- **Determinism**: normalization collapses stylistic suffixes (e.g., `-Bold`,
`Italic`) so names like `Roboto`, `Roboto-Regular`, `Roboto Bold` all map to
the same canonical key during lookups.


"""

# ───────────────────────── imports ─────────────────────────
# Standard library modules — built into Python
import io # In‑memory byte/char buffers; used to build CSVs without touching disk
import csv # Read/write CSV (comma‑separated values) files
import json # Encode/decode JSON (for Google Fonts cache)
import logging # Adjust verbosity of 3rd‑party libraries like cssutils
import os # Environment variables, filesystem paths, etc.
import pathlib # High‑level path objects (Path)
import re # Regular expressions for string matching and extraction
import sys # Interacts with the Python runtime (not heavily used here)
import time # Timing & caching (e.g., cache file freshness in seconds)
import ipaddress # Validate whether a host string is a public IP
import socket # Low‑level networking exceptions and utilities


# 3rd‑party libraries — installed via requirements
import cssutils # CSS Document Object Model (DOM) parsing; nice for @font-face
import requests # HTTP client for fetching HTML/CSS with timeouts
import tinycss2 # Low‑level CSS parser; good for scanning declarations
from functools import lru_cache # Decorator for memoizing expensive calls
from pathlib import Path # Convenient alias to pathlib.Path
from urllib.parse import urljoin, urlparse # Build/inspect URLs
from bs4 import BeautifulSoup # HTML parser to find <link rel="stylesheet"> and <style>
from cssutils import parseString as parse_css # Alias: cssutils.parseString → parse_css
from rich.console import Console # Pretty table output
from rich.table import Table # Pretty table output
from tinycss2 import serialize # Turn parsed value tokens back into string form

# ───────────────────────── config ──────────────────────────
# A custom user agent string helps explain who is making the HTTP request.
# Some servers log this; a descriptive UA makes your intent obvious and polite.
# Some online apps lie with their user agent (e.g., "Mozilla/5.0" or "curl/7.68.0") to circumvent blocks.
# I prefer to be honest and upfront about what this tool is.
USER_AGENT   = "Font Inspector by Ben Crittenden (+https://www.bencritt.net)"

# HTTP timeout, in seconds, for all requests.
# Heroku will crash my app after 39 seconds.
HTTP_TIMEOUT = 20

# Default path to write CSV reports to.
# Eslewhere in my code, more is injected into the file name to avoid overwrites between requests.
CSV_PATH     = Path("font_report.csv")

# Quiet down cssutils so it does not flood logs with warnings for messy CSS.
cssutils.log.setLevel(logging.CRITICAL)

# cssutils serializer validation can be strict.
# Disable that to be lenien with real‑world styles found on the web.
cssutils.ser.prefs.validate = False

# Precompiled regular expressions — faster and clearer than ad‑hoc re.search calls.
# Matches url(...) values inside CSS, capturing the URL content.
URL_RE    = re.compile(r"url\(\s*[\"']?(.*?)[\"']?\s*\)", re.I)

# Matches @import url(...) statements so we can follow nested CSS imports.
IMPORT_RE = re.compile(r"@import\s+url\(\s*[\"']?(.*?)[\"']?\s*\)", re.I)

# ─────────────────── helpers / normalisation ───────────────
# Many font families publish many file names with weight/style suffixes (e.g., Roboto-BoldItalic).
# To improve matching against catalogue names strip those suffixes while building a "normalized" key: lowercased and with spaces/dashes removed.
SUFFIX_RX = (
    r"(?:thin|extralight|ultralight|light|regular|book|medium|"
    r"semibold|demibold|bold|extrabold|black|heavy|italic|oblique|obl|boldcond|boldcondobl|condensed|light|thin|bolditalic|"
    r"var|vf|free|normal|trial|variable|\d+)$"
)

# STYLE_RX detects trailing weight/style tokens so we can remove them.
STYLE_RX  = rf"-?{SUFFIX_RX}(?:italic|oblique)?$"

# Some families also use width variants like Condensed/Expanded.
CONDENSED = r"(?:extra|ultra)?(?:semi)?(?:condensed|expanded|wide)$"

def norm(txt: str) -> str:
    """Return a *normalized* key for a family name.

    Steps:
    1) Lower‑case the string and trim outer whitespace.
    2) Remove trailing weight/style suffixes like "-Bold", "Regular", 
    numeric suffixes (e.g., 400), and tags like "var", "vf", "trial".
    3) Remove width tags like "Condensed" or "Expanded".
    4) Remove all spaces and dashes so there is one canonical form.

    Examples
    --------
    >>> norm("Roboto-Bold Italic")
    'roboto'
    >>> norm("Open Sans Var")
    'opensans'
    """
    txt = txt.lower().strip()
    txt = re.sub(STYLE_RX, "", txt)          # kill weight/style suffix
    txt = re.sub(rf"-?{CONDENSED}", "", txt) # kill condensed/expanded
    return re.sub(r"[\s\-]+", "", txt)       # remove spaces & dashes

# ────────── Font Awesome quick classifier ───────────
# Font Awesome ships as multiple families/weights with distinctive naming.
# It is common across the web, so this special‑cases it for faster, clearer results.
def classify_fa(lf: str) -> tuple[str | None, str | None]:
    """
    Quick path for Font Awesome family/stack names.


    Parameters
    ----------
    lf : str
    A *normalized* family string (typically `norm(family)`), or a lower‑case
    label such as "fa-duotone-900" coming from class‑based stacks.


    Returns
    -------
    (source_label, license_required) : tuple[str|None, str|None]
    - For FA **Free** sets → ("Font Awesome Free", "No")
    - For FA **Pro** sets → ("Font Awesome Pro", "Yes")
    - If not Font Awesome → (None, None)


    Handles both CSS family names (e.g., "Font Awesome 6 Duotone") *and*
    class‑style aliases (e.g., "fa-sharp-solid-900").
    """
    # Free sets (brands/regular/solid) are labeled as "No" license required.
    if lf.startswith(("fa-solid-", "fa-regular-", "fa-brands-")):
        return "Font Awesome Free", "No"

    # Paid weights/sets
    if lf.startswith(("fa-duotone-", "fa-light-", "fa-thin-", "fa-sharp-")):
        return "Font Awesome Pro", "Yes"

    if lf.startswith("fontawesome") and "pro" in lf:
        return "Font Awesome Pro", "Yes"

    # Textual hints for Pro
    if lf.startswith("fontawesome6") and ("duotone" in lf or "sharp" in lf):
        return "Font Awesome Pro", "Yes"

    # Pretty “official” names
    if lf.startswith(("font awesome 6 duotone",
                      "font awesome 6 sharp",
                      "font awesome 6 pro")):
        return "Font Awesome Pro", "Yes"

    return None, None

# ───────────────── Google font catalogue loader ────────────
# This is a fallback list in case the Google Web Fonts API is not available.
HARD_CODED_GOOGLE_FONTS = {
  "abel", "abhaya libre", "abril fatface", "aclonica", "acme", "actor",
  "adamina", "advent pro", "aguafina script", "aladin", "alata", "alatsi",
  "albert sans", "aldrich", "alef", "alegreya", "alegreya sans", "aleo",
  "alex brush", "alfa slab one", "alice", "alike angular", "alkalami", "allerta",
  "allerta stencil", "allison", "allura", "almarai", "almendra", "almendra display",
  "amaranth", "amata", "amatic sc", "amethysta", "amiko", "amiri",
  "amita", "anaheim", "andika", "annie use your telescope", "anonymous pro", "antic",
  "antic didone", "antic slab", "anton", "antonio", "archivo", "archivo black",
  "archivo expanded", "archivo narrow", "aref ruqaa", "arima", "armata", "arsenal",
  "asap", "asap condensed", "asetcon", "assistant", "astloch", "asul",
  "athiti", "atkinson hyperlegible", "atkinson hyperlegible mono", "atomic age", "aubrey", "audiowide",
  "average", "averia libre", "averia sans libre", "averia serif libre", "azeret mono", "b612",
  "b612 mono", "bad script", "bahiana", "bai jamjuree", "baijamjuree", "baloo 2",
  "baloo bhai 2", "baloo bhaijaan 2", "baloo chettan 2", "baloo da 2", "baloo paaji 2", "baloo thambi 2",
  "balsamiq sans", "barlow", "barlow condensed", "barlow semi condensed", "barriecito", "basic",
  "baskervville", "battambang", "bayon", "be vietnam", "be vietnam pro", "bebas neue",
  "belgrano", "bellota", "bellota text", "benchnine", "bentham", "besley",
  "bhutuka expanded one", "big shouldered display", "big shouldered inline display", "big shouldered text", "bigelow rules", "bigshot one",
  "bilbo", "biorhyme", "biorhyme expanded", "bitter", "bitter pro", "bitter variable",
  "black han sans", "black ops one", "blinker", "bodoni moda", "bona nova", "boogaloo",
  "bowlby one", "bowlby one sc", "braah one", "brawler", "bree serif", "brygada 1918",
  "bubbler one", "buda", "buenard", "bungee", "bungee hairline", "bungee inline",
  "bungee outline", "bungee shade", "cabin", "cabin condensed", "cairo", "cairo play",
  "cardo", "carme", "carrois gothic", "carrois gothic sc", "catamaran", "caveat",
  "chewy", "chilanka", "chivo", "chivo mono", "cinzel", "cinzel decorative",
  "comfortaa", "commissioner", "concert one", "content", "cookie", "cormorant",
  "cormorant garamond", "cormorant infant", "cormorant sc", "cormorant upright", "cousine", "coustard",
  "crimson pro", "crimson text", "croissant one", "cuprum", "cutive", "cutive mono",
  "dancing script", "dm mono", "dm sans", "dm serif display", "dm serif text", "domine",
  "eagle lake", "eb garamond", "electrolize", "encode sans", "encode sans condensed", "encode sans expanded",
  "epilogue", "exo", "exo 2", "faustina", "figtree", "fira code",
  "fira sans", "firma sans", "fjalla one", "fjord one", "francois one", "fraunces",
  "fredoka", "fredoka one", "fugaz one", "gabarito", "gelasio", "gloock",
  "golos text", "golos ui", "gothic a1", "great vibes", "guise", "hanken grotesk",
  "heebo", "hepta slab", "hind", "hind colombo", "hind madurai", "hind siliguri",
  "hind vadodara", "hubballi", "ibarra real nova", "ibm plex mono", "ibm plex sans", "ibm plex sans arabic",
  "ibm plex serif", "inconsolata", "inika", "instrument mono", "instrument sans", "instrument serif",
  "inter", "inter tight", "jaldi", "jetbrains mono", "josefin sans", "josefin slab",
  "jost", "kanit", "karla", "kaushan script", "khand", "krona one",
  "lato", "latto", "league spartan", "lexend", "lexend deca", "lexend exa",
  "lexend giga", "lexend mega", "lexend peta", "lexend tera", "lexend zetta", "libre bodoni",
  "libre caslon display", "libre caslon text", "libre franklin", "literata", "lobster", "lora",
  "manrope", "martel", "martian mono", "maven pro", "merriweather", "merriweather sans",
  "montagu slab", "montserrat", "montserrat alternates", "montserrat subrayada", "mukta", "mukta mahee",
  "mukta vaani", "mulish", "nanum gothic", "nanum gothic coding", "nanum myeongjo", "nanum pen script",
  "neuton", "news cycle", "newsreader", "noticia text", "noto sans", "noto sans arabic",
  "noto sans bengali", "noto sans devanagari", "noto sans display", "noto sans hebrew", "noto sans jp", "noto sans kr",
  "noto sans mono", "noto sans sc", "noto sans tc", "noto sans thai", "noto serif", "noto serif arabic",
  "noto serif devanagari", "noto serif hebrew", "noto serif jp", "noto serif sc", "noto serif tc", "noto serif thai",
  "nunito", "nunito sans", "old standard tt", "open sans", "oswald", "outfit",
  "overlock", "overpass", "overpass mono", "oxygen", "oxygen mono", "pacifico",
  "petrona", "philosopher", "pioppins", "play", "playball", "playfair",
  "playfair display", "plus jakarta sans", "poiret one", "pontano sans", "popins", "poppins",
  "pragati narrow", "prata", "prompt", "proza libre", "pt mono", "pt sans",
  "pt sans caption", "pt sans narrow", "pt serif", "public sans", "puritan", "questrial",
  "quicksand", "raleway", "raleway dots", "readex pro", "red hat display", "red hat mono",
  "red hat text", "reem kufi", "righteous", "roboto", "roboto condensed", "roboto flex",
  "roboto mono", "roboto serif", "roboto slab", "rokkitt", "rubik", "rubik bubbles",
  "rubik dirt", "rubik glitch", "rubik iso", "rubik scribble", "rubik spray paint", "rubik vinyl",
  "ruda", "ruluko", "sacramento", "sarabun", "sarala", "satisfy",
  "sen", "sintony", "sora", "source code pro", "source sans 3", "source serif 4",
  "space grotesk", "space mono", "spartan", "spectral", "spline sans", "spline sans mono",
  "sriracha", "staatliches", "state machine", "suez one", "syne", "tajawal",
  "tangerine", "teko", "tektur", "telex", "tenor sans", "text me one",
  "thasadith", "titillium web", "trade winds", "ubuntu", "ubuntu condensed", "ubuntu mono",
  "unbounded", "unica one", "urbanist", "varela", "varela round", "varta",
  "vazirmatn", "viaoda libre", "vidaloka", "viri", "vollkorn", "vt323",
  "work sans", "worksans", "yanone kaffeesatz", "yantramanav", "yatra one", "yeseva one",
  "young serif", "yrsa", "ysabeau", "ysabeau infant", "ysabeau office", "zilla slab",
  "zilla slab highlight"
}


def _fetch_google_fonts(api_key: str) -> set[str]:
    """Call the official Google Web Fonts API and return a set of family names.

    Notes
    -----
    - `requests.get(...).json()` returns a Python dict; we take the `items`
    array and lower‑case each `family`.
    - Honor the global `HTTP_TIMEOUT` to avoid hanging API calls.
    """
    api_key = os.environ.get("GOOGLE_FONT_KEY")
    url = f"https://www.googleapis.com/webfonts/v1/webfonts?key={api_key}"
    items = requests.get(url, timeout=HTTP_TIMEOUT).json()["items"]
    return {item["family"].lower() for item in items}

@lru_cache(maxsize=1)
def load_google_font_families() -> set[str]:
    """
    Load the set of Google Font family names (lower‑cased).

    Strategy (in order):
    1) If `GOOGLE_FONT_KEY` is available → fetch fresh list via API and cache it
    under `~/.cache/gf_families.json` (for ~24h freshness).
    2) Else, if a recent cache file exists → use it.
    3) Else → fall back to the HARD_CODED_GOOGLE_FONTS list.

    `@lru_cache(maxsize=1)` ensures this runs at most once per process.
    """
    cache_file = pathlib.Path.home() / ".cache" / "gf_families.json"
    api_key = os.environ.get("GOOGLE_FONT_KEY")

    if api_key:
        try:
            fams = _fetch_google_fonts(api_key)
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(json.dumps(sorted(fams)))
            return fams
        except Exception as exc:
            print("[warn] Web Fonts API failed – using cache/fallback:", exc)

    # Use cache if present and younger than 24 hours
    if cache_file.exists() and time.time() - cache_file.stat().st_mtime < 86400:
        return set(json.loads(cache_file.read_text()))

    # Final fallback
    return {f.lower() for f in HARD_CODED_GOOGLE_FONTS}

# ───────────────────── lookup maps ─────────────────────────
# Precompute quick reference structures for classification/inference.
GOOGLE_FONTS       = load_google_font_families()

# Common icon fonts that are known to be free/open
FREE_ICON_FONTS    = {
    "bootstrap icons","font awesome","fontawesome","fontawesomewebfont",
    "glyphicons","glyphiconshalflings","material icons","material symbols",
    "feather","heroicons","phosphor","fa-brands-400","videojs",
    "eleganticons","dripicons-v2","kiko","wc_gc","sw-icon-font",
    "woocommerce","vc_grid_v1","vcpb-plugin-icons",
}

# FAMILY_SOURCE_MAP maps normalized family names to a human‑readable source label.
FAMILY_SOURCE_MAP: dict[str,str] = (
    {norm(f): "Google Fonts"      for f in GOOGLE_FONTS}         |
    {norm(f): "Font Awesome Free" for f in FREE_ICON_FONTS}       |
    {
        # Hand‑picked corrections and aliases
        norm("bootstrap icons")      : "Bootstrap Icons",
        norm("glyphicons halflings") : "Bootstrap Glyphicons",
        norm("material icons")       : "Google Material Icons",
        norm("material symbols")     : "Google Material Symbols",
        norm("source code pro")      : "Adobe Source / Google",
        norm("fira code")            : "Mozilla Fira / Google",
        norm("font awesome 6 free"): "Font Awesome Free",
        norm("font awesome 6 brands"): "Font Awesome Free",
        norm("font awesome 5 free"): "Font Awesome Free",
        norm("font awesome 5 brands"): "Font Awesome Free",
        norm("open sans var")      : "Google Fonts",
        norm("roboto flex")        : "Google Fonts",
        norm("bebas"): "Google Fonts",
        norm("slick"): "MIT / Slick Carousel",
        # Font Awesome
        norm("fa-brands-400"): "Font Awesome Free",
        # WooCommerce glyph set
        norm("wc_gc"): "WooCommerce Icons",
        norm("sw-icon-font"): "WooCommerce Icons",
        # Dripicons
        norm("dripicons-v2"): "Dripicons Free",
        # Elegant Themes
        norm("ElegantIcons"): "Elegant Icons",
        # Kiko
        norm("Kiko"): "Kiko Icons",
        # Linea packs (all map to same label)
        **{norm(f): "Linea Icons" for f in (
            "linea-arrows-10","linea-basic-10","linea-basic-elaboration-10",
            "linea-ecommerce-10","linea-music-10",
            "linea-software-10","linea-weather-10",
        )},
        # Visual Composer
        norm("vc_grid_v1"): "VC / WPBakery Icons",
        norm("vcpb-plugin-icons"): "VC / WPBakery Icons",
        norm("VideoJS"): "VideoJS Icons",
        norm("NOAVideo"): "NOA Video (Nintendo)",
        norm("Source Sans Pro Topnav"): "Adobe Source / Google",
        norm("Source Sans Pro"): "Adobe Source / Google (OFL)",
        norm("Google Sans Mono"): "Google Sans (Proprietary)",
        norm("Google Symbols Subset Subset"): "Google Material Symbols",
        norm("FreeSans"): "GNU FreeFont",
        norm("Nimbus Sans L"): "URW Nimbus Sans",
    }
)

# Typemates catalogue — specifically labelled commercial families.
TYPEMATES_FAMILIES = """
Alison
Altona
Alright
Bridge Head
Bridge Text
Cera
Cera Pro
Cera Compact
Cera Brush
Comspot
Conto
Conto Slab
Conto Narrow
Conto Compressed
Dockland
Finador
Matter
Matter SQ
Matter Horn
Output
Output Sans
Pensum
Quadraat Slab
Rabiola
Urby
Urby Soft
""".strip().splitlines()

# Add them to the main map so they immediately classify as commercial.
for name in TYPEMATES_FAMILIES:
    FAMILY_SOURCE_MAP[norm(name)] = "Typemates (Commercial)"

# Build a tolerant regex that matches any Typemates base name with optional
# suffixes (e.g., "Pro", "Variable", etc.). This helps catch file‑name variants.
BASES = [norm(n) for n in TYPEMATES_FAMILIES]
TYPEMATES_RE = re.compile(
    r"^(?:"
    + "|".join(sorted(set(BASES)))               # any base name …
    + r")"
    r"(?:pro|var|vf|variable|trial)?"             # optional tag
    r".*",                                        # anything else
    re.I,
)

def is_typemates(lf: str) -> bool:
    return bool(TYPEMATES_RE.match(lf))

# Common system font families that ship with certain operating systems.
# These are generally safe to ignore, as they do not require licenses unless they are self‑hosted.
SYSTEM_FONTS = {
    norm(f) for f in (
        # Windows / macOS / Linux classics
        "arial","arial narrow","helvetica","times new roman","courier new",
        "courier","cambria","georgia","verdana","trebuchet ms","tahoma",
        "segoe ui","franklin gothic medium","consolas","menlo","monaco",
        "baskerville","liberation sans","liberation serif","liberation mono",
        "helveticaneue","andalemono","monospace", "sansserif",
        # Apple & emoji stacks
        "san francisco","-apple-system","blinkmacsystemfont",
        "apple color emoji","segoe ui emoji","segoe ui symbol",
        "sf pro text","sfmono-regular",
        # Android / “web‑safe”
        "droid sans","droid serif",
    )
}

# Known *open‑source* and *commercial* font hosting domains. We 
# Use substring checks such as "fonts.gstatic.com" in hostnames to infer source/provider.
OPEN_SOURCE_HOSTS = {
    "fonts.googleapis.com","fonts.gstatic.com",     # Google
    "fonts.bunny.net",                              # Bunny CDN
    "brick.im","cdn.fontshare.com","fontlibrary.org",
    "cdn.jsdelivr.net","cdnjs.cloudflare.com",
    "kit.fontawesome.com","cdn.fontawesome.com",
}

COMMERCIAL_HOSTS = {
    "use.typekit.net","use.adobe.com","fonts.adobe.com",
    "fast.fonts.net","static.myfonts.net","fontspring.net",
    "cloud.typography.com","static.typemates.com",
}

# Human‑readable labels for the above hosts (for the "font_source" column).
# These are the lables shown in the on page report and in the downloaded CSV.
SOURCE_MAP = {
    # open-source CDNs
    "fonts.gstatic.com"   : "Google Fonts",
    "fonts.googleapis.com": "Google Fonts",
    "fonts.bunny.net"     : "Bunny Fonts",
    "brick.im"            : "Brick CDN",
    "cdn.fontshare.com"   : "Fontshare CDN",
    "fontlibrary.org"     : "FontLibrary",
    # commercial/subscription
    "use.typekit.net"     : "Adobe Fonts",
    "use.adobe.com"       : "Adobe Fonts",
    "fonts.adobe.com"     : "Adobe Fonts",
    "fast.fonts.net"      : "Monotype / MyFonts",
    "static.myfonts.net"  : "Monotype / MyFonts",
    "fontspring.net"      : "Fontspring",
    "cloud.typography.com": "Hoefler Cloud.Typography",
    "static.typemates.com": "Typemates (Commercial)",
}

# ───────────────────── HTTP helpers ────────────────────────
# Wrap `requests.get` to enforce a timeout and raise for non‑2xx status codes.
def fetch(url: str, sess: requests.Session) -> str:
    """Fetch a URL as text or raise an informative exception.

    Parameters
    ----------
    url : str
    Absolute URL to request.
    sess : requests.Session
    Reusable HTTP session (connection pooling, default headers).

    Returns
    -------
    str
    Response body decoded as text (`r.text` uses charset from headers).
    """
    r = sess.get(url, timeout=HTTP_TIMEOUT)
    r.raise_for_status() # Convert HTTP 4xx/5xx into `requests.exceptions.HTTPError`.
    return r.text

def pull_imports(css: str, base: str, sess) -> list[str]:
    """Follow nested `@import url(...)` chains depth‑first.

    Why this matters: many CSS files are split and stitched via `@import`. 
    Only canning the top-level sheets will miss '@font-face" declarations.

    Returns a list of raw CSS texts fetched from imported URLs. 
    
    Duplicates and cycles are prevented with a `seen` set. 
    
    Any unreachable import is skipped.
    """
    stack, out, seen = [css], [], set()
    while stack:
        txt = stack.pop()
        for ref in IMPORT_RE.findall(txt):
            url = urljoin(base, ref) # Resolve relative import href against page origin.
            if url in seen:          # Avoid loops in case of circular imports.
                continue
            seen.add(url)
            try:
                fetched = fetch(url, sess)
                out.append(fetched)
                stack.append(fetched) # Depth‑first: may itself contain @imports.
            except requests.RequestException:
                # Unreachable import — non‑fatal, just skip.
                pass
    return out

# ───────────────────── user-friendly errors ─────────────────────
# A tiny error type used to signal messages we want to show to the end user as‑is.
class _UserFacingError(Exception):
    """Intentional, friendly error to show directly to the user."""
    pass

def _validate_public_host(url: str) -> str:
    """Validate the hostname looks public and return it.

    - If the host is a literal IP address, ensure it is *global* (not private).
    - If the host is a domain, ensure it is IDNA‑encodable and looks like a
    public domain (contains a dot).
    - Raise `_UserFacingError` for any problem so the caller can convert this to
    a concise tip for the UI.
    """
    p = urlparse(url)
    host = p.hostname or ""
    if not host:
        raise _UserFacingError("That URL doesn’t include a host. Try something like “bencritt.net”.")
    # Literal IP?
    try:
        ip = ipaddress.ip_address(host)
        if not ip.is_global:
            raise _UserFacingError("That address is private or local and can’t be scanned from this server.")
        return host
    except ValueError:
        # Not an IP → treat as domain
        try:
            host.encode("idna")  # validate punycode-encodable
        except UnicodeError:
            raise _UserFacingError("The domain contains characters we couldn’t interpret. Try ASCII/punycode.")
        if "." not in host:
            raise _UserFacingError("That host doesn’t look like a public domain. Please include a full domain like “bencritt.net”.")
        return host

def _friendly_error_message(url: str, exc: Exception) -> str:
    """Map low‑level exceptions to short, actionable messages for users.

    We convert a variety of `requests`/socket errors into concise English
    messages so the UI can show the most helpful hint.
    """
    host = (urlparse(url).hostname or url).strip("/")

    # Show intentionally raised messages verbatim
    if isinstance(exc, _UserFacingError):
        return str(exc)

    # requests/urllib3 family
    if isinstance(exc, requests.exceptions.ConnectTimeout):
        return f"{host} didn’t respond within {HTTP_TIMEOUT}s."
    if isinstance(exc, requests.exceptions.ReadTimeout):
        return f"{host} took too long to send data."
    if isinstance(exc, requests.exceptions.TooManyRedirects):
        return f"{host} redirected too many times (possible redirect loop)."
    if isinstance(exc, requests.exceptions.SSLError):
        return f"Couldn’t establish a secure HTTPS connection to {host} (certificate or TLS issue)."
    if isinstance(exc, requests.exceptions.InvalidURL) or isinstance(exc, requests.exceptions.MissingSchema) or isinstance(exc, requests.exceptions.InvalidSchema):
        return "That doesn’t look like a valid URL. Include “https://”, e.g., https://bencritt.net."
    if isinstance(exc, requests.exceptions.HTTPError):
        r = exc.response
        code = getattr(r, "status_code", "?")
        reason = getattr(r, "reason", "") or ""
        # Friendly hint for common blocks
        if code in (401, 403):
            return f"The site responded with HTTP {code} {reason}. Access is restricted, so we can’t scan it."
        if code == 404:
            return f"The page wasn’t found (HTTP 404)."
        return f"The site responded with HTTP {code} {reason}."

    if isinstance(exc, requests.exceptions.ConnectionError):
        s = str(exc).lower()
        if "name or service not known" in s or "temporary failure in name resolution" in s or "failed to resolve" in s or "nodename nor servname provided" in s:
            return f"DNS lookup failed for {host}. Check the domain name."
        if "connection refused" in s:
            return f"{host} refused the connection."
        return f"Couldn’t connect to {host}."

    # Socket / encoding odds and ends
    if isinstance(exc, socket.gaierror):
        return f"DNS lookup failed for {host}."
    if isinstance(exc, UnicodeError):
        return "The URL contains characters we couldn’t interpret."

    # Fallback
    return f"Unexpected error while fetching {host}: {exc}"


# ───────────────────── CSS collector ───────────────────────
def gather_css(html: str, base: str, sess) -> list[tuple[str,str]]:
    """Collect raw CSS texts from a page, including inline `<style>` and
    external stylesheets referenced by `<link rel="stylesheet">`.

    Returns a list of `(css_text, supplier_host)` pairs. The `supplier_host`
    tells us where the CSS was fetched from (e.g., `fonts.googleapis.com`).

    We also follow nested `@import` rules so deeply imported `@font-face` blocks
    are discovered.
    """
    soup = BeautifulSoup(html, "html.parser")
    out  : list[tuple[str,str]] = []

    def add(txt: str, host: str):
        # Push the CSS text found, and any nested imports fetched from that CSS
        out.append((txt, host))
        out.extend((t, host) for t in pull_imports(txt, base, sess))

    root_host = urlparse(base).hostname or ""

    # 1) Inline style blocks
    for tag in soup.find_all("style"):
        add(tag.string or "", root_host)

    # 2) External stylesheets
    for link in soup.find_all("link", href=True):
        rels = link.get("rel") or []
        if "stylesheet" in rels or link.get("as", "").lower() == "style":
            css_url = urljoin(base, link["href"])
            try:
                add(fetch(css_url, sess), urlparse(css_url).hostname or root_host)
            except requests.RequestException:
                # Skip broken links silently; we want best‑effort results.
                pass
    return out

# ─────────────────── family ↔ host map ─────────────────────
def families_and_hosts(blocks: list[tuple[str,str]]) -> dict[str,set[str]]:
    """
    Parse a list of CSS blocks and harvest distinct font families and hosts.

    Parameters
    ----------
    blocks : list[(css_text, supplier_host)]
    Each tuple contains the raw CSS text and the host it was fetched from.

    Returns
    -------
    dict[str, set[str]]
    A mapping `{family → {hosts}}` where `hosts` contains the lowercase
    hostnames seen in `src:` URLs inside `@font-face` *and* the supplier
    host (where the CSS itself came from). This redundancy helps infer the
    source even when a provider hides actual file hosts behind CSS.

    Implementation details
    ----------------------
    - **Strategy A (preferred)**: use `cssutils` to walk the stylesheet and find
    `FONT_FACE_RULE` blocks; extract `font-family` and `src:` URLs.
    - **Strategy B (fallback)**: regex search for `@font-face { ... }` blocks
    and a `font-family:` line within them.
    - **Strategy C**: use `tinycss2` to parse all qualified rules and collect
    `font-family` stacks used in normal CSS (not just `@font-face`). This
    catches designer‑specified stacks even if actual webfont files are missing.
    """
    fam_map: dict[str,set[str]] = {}

    # Generic family keyword blacklist.
    # Ignore these since they are not specific families, but CSS keywords.
    GENERIC = {
        "serif","sans-serif","monospace","cursive","fantasy","system-ui",
        "ui-sans-serif","ui-serif","ui-monospace","emoji","math","fangsong",
        "inherit","initial","unset","star","sans-serif!","tofu",
    }
    FONTFACE_RE = re.compile(r"@font-face\s*{(.*?)}", re.I | re.S)
    FAMILY_RE = re.compile(r"font-family\s*:\s*([^;]+);", re.I)

    def real(tok: str) -> bool:
        """Return True if `tok` looks like a real family name, not a keyword.

        Trim quotes/whitespace and reject CSS variables, generic families,
        and anything that looks like a loose "*-serif" pattern.
        """
        t = tok.strip("'\" ").rstrip("!").strip().lower()
        if not t or t.startswith(("var(","--")):
            return False
        if t in GENERIC:
            return False
        if re.fullmatch(r"[a-z\-]*serif", t):   # anything that ends with “serif”
            return False
        return True

    for css_text, supplier in blocks:
        sup = (supplier or "").lower()

        # (A) @font-face via cssutils
        try:
            sheet = parse_css(css_text)
        except Exception:
            sheet = None

        parsed = False
        if sheet:
            for rule in sheet:
                if rule.type == rule.FONT_FACE_RULE:
                    fam_raw = rule.style.getPropertyValue("font-family")
                    if fam_raw and real(fam_raw):
                        # fam = fam_raw.strip("'\" ")
                        fam = fam_raw.strip("'\" ").rstrip(")\"") # Some websites have malformed font-family values.  This accounts for that to keep the report clean.
                        hosts = fam_map.setdefault(fam, set())
                        hosts.add(sup)
                        src_prop = rule.style.getPropertyValue("src") or ""
                        for url in URL_RE.findall(src_prop):
                            host = urlparse(
                                "https:" + url[2:] if url.startswith("//") else url
                            ).hostname
                            if host:
                                hosts.add(host.lower())
                        parsed = True

        # (B) regex fallback if cssutils failed
        if not parsed:
            for block in FONTFACE_RE.findall(css_text):
                fam_m = FAMILY_RE.search(block)
                if not fam_m:
                    continue
                fam_raw = fam_m.group(1)
                if not real(fam_raw):
                    continue
                # fam = fam_raw.strip("'\" ")
                fam = fam_raw.strip("'\" ").rstrip(")\"") # Some websites have malformed font-family values.  This accounts for that to keep the report clean.
                hosts = fam_map.setdefault(fam, set())
                hosts.add(sup)
                for url in URL_RE.findall(block):
                    host = urlparse(
                        "https:" + url[2:] if url.startswith("//") else url
                    ).hostname
                    if host:
                        hosts.add(host.lower())

        # (C) font-family stacks in regular rules
        for tok in tinycss2.parse_stylesheet(
            css_text, skip_comments=True, skip_whitespace=True
        ):
            if tok.type != "qualified-rule":
                continue
            for decl in tinycss2.parse_declaration_list(
                tok.content, skip_whitespace=True, skip_comments=True
            ):
                if decl.type == "declaration" and decl.name == "font-family":
                    for fam_tok in serialize(decl.value).split(","):
                        if real(fam_tok):
                            # fam = fam_tok.strip("'\" ")
                            fam = fam_tok.strip("'\" ").rstrip(")\"") # Some websites have malformed font-family values.  This accounts for that to keep the report clean.
                            fam_map.setdefault(fam, set()).add(sup)

    return fam_map

# ───────────────────── licence logic ───────────────────────
def needs_license(family: str, hosts: set[str]) -> str:
    """Return "Yes"/"No"/"Unknown" for whether a webfont license is **likely** required.

    This is a heuristic based on:
    - whether the family is known open source (Google Fonts, free icon sets)
    - whether the family appears in a known commercial catalogue (e.g., Typemates)
    - whether the font files are served from open‑source CDNs vs. commercial CDNs
    - special cases like Font Awesome Pro, Google Sans (proprietary)

    Important: this does not replace legal review; it is an **inference**.
    """
    lf = norm(family)

    # Font Awesome override
    _, lic = classify_fa(lf)
    if lic:
        return lic
    
    # Typemates families are commercial.
    if is_typemates(lf):
        return "Yes"

    low_hosts = {h.lower() for h in hosts}

    # Known proprietary Google family (not the same as "Google Fonts")
    if lf == norm("Google Sans Mono"):
        return "Yes"
    
    # Known open families (Google Fonts + curated list) → no license required for use
    if lf in FAMILY_SOURCE_MAP:
        return "No"
    
    # System‑installed families do not redistribute font files via your site
    if lf in SYSTEM_FONTS:
        return "No"
    
    # If any host matches an open‑source CDN, call it "No"
    if any(any(src in h for h in low_hosts) for src in OPEN_SOURCE_HOSTS):
        return "No"
    
    # If any host matches a commercial service, call it "Yes"
    if any(any(com in h for h in low_hosts) for com in COMMERCIAL_HOSTS):
        return "Yes"
    
    # Otherwise, we cannot be sure
    return "Unknown"

def is_same_site(hosts: set[str], page_host: str) -> bool:
    """Return True if every host ends with the page’s registrable domain.

    Example: for `tandemloc.com`, hosts like `cdn.tandemloc.com` and
    `static.tandemloc.com` would count as the *same site*. This is a weaker
    check than full PSL (Public Suffix List) parsing but works well enough.
    """
    if not hosts:
        return False
    root = ".".join(page_host.split(".")[-2:])  # e.g. tandemloc.com
    return all(root in h for h in hosts)

def font_source(family: str,
                hosts: set[str],
                page_host: str) -> str:
    """Return a human‑readable label describing where the font seems to come from.


    Decision order:
    1) **Font Awesome** / **Typemates** explicit overrides
    2) **System font** (no webfont files distributed)
    3) **Family catalogue** hits (Google Fonts, icon packs, curated aliases)
    – adds "(self‑hosted)" if all sources belong to the same site
    4) **CDN host** substring matches (e.g., fonts.gstatic.com → Google Fonts)
    5) Otherwise **Self‑hosted** with host list, or **Unknown source**
    """
    lf           = norm(family)

    # Font Awesome override — also implies a licensing decision elsewhere
    label, _ = classify_fa(lf)
    if label:
        return label
    
    # Typemates override — explicit commercial catalogue
    if is_typemates(lf):
        return "Typemates (Commercial)"

    hosts_lower  = {h.lower() for h in hosts}
    
    # Catchall for Linea Icons variants
    if lf.startswith("linea-"):
        return "Linea Icons"

    # 1) System family → clearly "System font"
    if lf in SYSTEM_FONTS:
        return "System font"

    # 2) Known catalogue entries
    if lf in FAMILY_SOURCE_MAP:
        label = FAMILY_SOURCE_MAP[lf]
        # If all referenced hosts belong to the same registrable domain as the
        # page itself, we annotate that it is self‑hosted (not fetched from a
        # 3rd‑party CDN). This can matter for performance/privacy and sometimes
        # licensing (some vendors allow self‑hosting only with paid plans).
        if hosts_lower and _all_same_site(hosts_lower, page_host):
            label += " (self-hosted)"
        return label

    # 3) Host substring matches (provider CDNs)
    for h in hosts_lower:
        for pat, label in SOURCE_MAP.items():
            if pat in h:
                return label

    # 4) Fallbacks
    if hosts_lower:
        # Join hostnames in a stable order to avoid flicker in UI diffs
        return f"Self-hosted ({', '.join(sorted(hosts_lower))})"
    return "Unknown source"


def _all_same_site(hosts: set[str], page_host: str) -> bool:
    """Return True if every host ends with the page’s registrable domain.


    This helper is duplicated (similar to `is_same_site`) so it can be used
    early without importing the other function; both implement the same logic.
    """
    if not hosts:
        return False
    root = ".".join(page_host.split(".")[-2:])   # example.com
    return all(root in h for h in hosts)


# ─────────────────── build the whole report ────────────────
def make_report(page_url: str) -> list[dict]:
    """Convenience function that runs the full pipeline synchronously.

    Steps:
    1) Create an HTTP session with a custom User‑Agent.
    2) Fetch the HTML of `page_url`.
    3) Gather all CSS (inline + external + nested `@import`).
    4) Extract `{family → hosts}`.
    5) For each family, infer `license_required` and `font_source`.
    6) Return a list of row dicts, sorted by family name.


    The async Django endpoints below call a *progress‑aware* version of this
    logic so the UI can show a progress bar and stream a CSV download when done.
    """
    sess       = requests.Session()
    sess.headers["User-Agent"] = USER_AGENT
    html       = fetch(page_url, sess)
    fam_map    = families_and_hosts(gather_css(html, page_url, sess))
    page_host  = urlparse(page_url).hostname or ""

    rows = []
    for fam, hosts in fam_map.items():
        rows.append({
            "website"         : page_host, 
            "family"          : fam,
            "license_required": needs_license(fam, hosts),
            "font_source"     : font_source(fam, hosts, page_host),  
        })
    return sorted(rows, key=lambda r: r["family"].lower())

# ───────────────────── output helpers ──────────────────────
def print_table(rows: list[dict]) -> None:
    """Pretty‑print a table of results to the terminal using `rich`."""
    tab = Table(title="Fonts detected")
    tab.add_column("website")
    tab.add_column("family")
    tab.add_column("license_required")
    tab.add_column("font_source")
    for r in rows:
        tab.add_row(
            r["website"],            # column 1 – website
            r["family"],             # column 2 – family
            r["license_required"],   # column 3 – license_required
            r["font_source"],        # column 4 – font_source
    )

    Console().print(tab)

def save_csv(rows: list[dict]) -> None:
    """Write `rows` into the module‑level `CSV_PATH` on disk (UTF‑8)."""
    with CSV_PATH.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "website",          # 1
                "family",           # 2
                "license_required", # 3
                "font_source",      # 4
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

def report_to_csv(rows: list[dict]) -> io.BytesIO:
    """Return the CSV representation of `rows` as an in‑memory BytesIO object.

    Useful when a web endpoint should stream a file **without** leaving it on
    disk. The caller can send this buffer directly as a HTTP response body.
    """
    buffer = io.StringIO()
    writer = csv.DictWriter(
        buffer,
        fieldnames=["website", "family", "license_required", "font_source"],
    )
    writer.writeheader()
    writer.writerows(rows)
    out = io.BytesIO(buffer.getvalue().encode())
    out.seek(0) # Reset read pointer so the caller can read from the start
    return out

# ─────────────────────────────────────────────────────────────────────────────
# Font Inspector — async task/queue API (SEO Head Checker style)
# Append this block at the END of projects/font_utils.py (keep your existing code above).
# ─────────────────────────────────────────────────────────────────────────────
# The section below integrates with **Django** to provide non‑blocking scans:
# users post a URL, we create a task, process it in a background thread, and
# expose status endpoints the frontend can poll. When finished, the CSV can be
# downloaded via a streaming response.

import csv as _csv
import os as _os
import threading as _threading
import time as _time
import uuid as _uuid
from dataclasses import dataclass as _dataclass, asdict as _asdict
from typing import Optional

from django.core.cache import caches as _caches
from django.http import (
    JsonResponse as _JsonResponse,
    StreamingHttpResponse as _StreamingHttpResponse,
    Http404 as _Http404,
    HttpResponseBadRequest as _HttpResponseBadRequest,
)
from django.views.decorators.cache import cache_control as _cache_control
from django.views.decorators.http import require_POST as _require_POST

# Optional memory‑trimming decorator (no‑op if not present in this project)
try:
    from .decorators import trim_memory_after as _trim_memory_after
except Exception:  # pragma: no cover
    def _trim_memory_after(func):
        return func

# Where CSVs live (ephemeral disk is fine on Heroku)
_FI_TASK_DIR = _os.environ.get("FI_TASK_DIR", "/tmp/fi_tasks")
_os.makedirs(_FI_TASK_DIR, exist_ok=True)

# Cache (dedicated alias if available)
try:
    _fi_cache = _caches["fontinspector"]
except Exception:  # pragma: no cover
    _fi_cache = _caches["default"]

# Concurrency / queue settings
_FI_MAX_CONCURRENCY = int(_os.environ.get("FI_MAX_CONCURRENCY", "2"))
_FI_TASK_TTL_SECS  = 60 * 60        # keep task status up to 1 hour
_FI_FILE_TTL_SECS  = 30 * 60        # delete files ≥ 30 minutes old

# Cache keys — prefixes keep the cache namespace tidy
def _k_task(task_id: str) -> str: return f"fi:task:{task_id}"
_K_RUNNING = "fi:running"   # int
_K_QUEUE   = "fi:queue"     # list[str]
_K_LAST_CLEAN = "fi:last_clean"

@_dataclass
class _Task:
    """Lightweight task record stored in Django cache.

    We persist enough fields to drive the UI: status, progress, a human message,
    and timing metrics. `csv_path` is kept server‑side only and removed from the
    JSON response to avoid leaking filesystem details.
    """
    id: str
    url: str
    status: str         # "QUEUED" | "RUNNING" | "DONE" | "ERROR"
    progress: int       # 0..100
    message: str
    csv_path: Optional[str] = None
    rows_count: int = 0
    created_ts: float = 0.0
    started_ts: float = 0.0
    finished_ts: float = 0.0

    def to_json(self) -> dict:
        d = _asdict(self)
        d.pop("csv_path", None)  # don’t leak server paths
        return d

# ───────────────────────────────── helpers ──────────────────────────────────
def _now() -> float:
    """Current UNIX timestamp (seconds)."""
    return _time.time()

def _coerce_int(x, default=0) -> int:
    """Best‑effort integer conversion with a default on failure."""
    try:
        return int(x)
    except Exception:
        return default

def _get_running() -> int:
    return _coerce_int(_fi_cache.get(_K_RUNNING, 0))

def _set_running(n: int):
    _fi_cache.set(_K_RUNNING, max(0, int(n)), timeout=_FI_TASK_TTL_SECS)

def _queue_push(task_id: str):
    q = _fi_cache.get(_K_QUEUE) or []
    q.append(task_id)
    _fi_cache.set(_K_QUEUE, q, timeout=_FI_TASK_TTL_SECS)

def _queue_pop() -> Optional[str]:
    q = _fi_cache.get(_K_QUEUE) or []
    if not q:
        return None
    task_id = q.pop(0) # FIFO
    _fi_cache.set(_K_QUEUE, q, timeout=_FI_TASK_TTL_SECS)
    return task_id

def _queue_position(task_id: str) -> int:
    q = _fi_cache.get(_K_QUEUE) or []
    try:
        return q.index(task_id) + 1 # 1‑based for humans
    except ValueError:
        return 0

def _save_task(task: _Task):
    _fi_cache.set(_k_task(task.id), task, timeout=_FI_TASK_TTL_SECS)

def _load_task(task_id: str) -> _Task:
    t = _fi_cache.get(_k_task(task_id))
    if not t:
        raise _Http404("Unknown task id")
    return t

def _update_progress(task_id: str, pct: int, msg: str = ""):
    t = _load_task(task_id)
    t.progress = max(0, min(100, int(pct)))
    if msg:
        t.message = msg
    _save_task(t)

def _cleanup_old_files():
    """Delete old CSVs and run at most once every ~120 seconds.

    Since Heroku’s filesystem is ephemeral and small, we aggressively purge
    stale files from the task directory. We also store a `last_clean` timestamp
    in cache to avoid doing this on every request.
    """
    # run at most once every 120 seconds
    last = _coerce_int(_fi_cache.get(_K_LAST_CLEAN, 0), 0)
    if _now() - last < 120:
        return
    _fi_cache.set(_K_LAST_CLEAN, int(_now()), timeout=_FI_TASK_TTL_SECS)

    cutoff = _now() - _FI_FILE_TTL_SECS
    try:
        for name in _os.listdir(_FI_TASK_DIR):
            path = _os.path.join(_FI_TASK_DIR, name)
            try:
                st = _os.stat(path)
            except FileNotFoundError:
                continue
            if st.st_mtime < cutoff:
                try:
                    _os.remove(path)
                except Exception:
                    pass
    except Exception:
        pass

def _csv_write_to_disk(rows: list[dict], to_path: str):
    """Write rows to `to_path` as CSV with a fixed header order."""
    with open(to_path, "w", newline="", encoding="utf-8") as fh:
        w = _csv.DictWriter(
            fh,
            fieldnames=["website", "family", "license_required", "font_source"],
        )
        w.writeheader()
        w.writerows(rows)

def _start_next_if_possible():
    """If capacity allows, start the next queued task in a daemon thread."""
    if _get_running() >= _FI_MAX_CONCURRENCY:
        return
    nxt = _queue_pop()
    if not nxt:
        return
    t = _load_task(nxt)
    t.status = "RUNNING"
    t.started_ts = _now()
    _save_task(t)
    _set_running(_get_running() + 1)
    _threading.Thread(target=_run_task, args=(nxt,), daemon=True).start()

# ─────────────────────────── execution with progress ─────────────────────────
def _run_task(task_id: str):
    """
    Worker function that performs the scan with milestone progress updates.


    Milestone percentages (approximate):
    5% start
    15% fetched HTML
    50% downloaded styles & nested @import (proportional)
    85% parsed families
    95% writing CSV
    100% done


    Errors are translated into short user‑friendly messages (e.g., timeouts,
    DNS failures, invalid URLs).
    """
    # ───── Local helpers (scoped to worker; keep imports minimal) ─────
    class _Friendly(Exception):
        """Intentional, friendly error to show directly to the user."""
        pass

    def _humanize(url: str, exc: Exception) -> str:
        """Translate lower‑level exceptions into concise UI messages."""
        import socket
        import requests as _rq
        from urllib.parse import urlparse as _up
        host = (_up(url).hostname or url).strip("/")

        # show intentionally raised messages verbatim
        if isinstance(exc, _Friendly):
            return str(exc)

        # requests/urllib3 family
        if isinstance(exc, _rq.exceptions.ConnectTimeout):
            secs = HTTP_TIMEOUT
            return f"{host} didn’t respond within {secs}s."
        if isinstance(exc, _rq.exceptions.ReadTimeout):
            return f"{host} took too long to send data."
        if isinstance(exc, _rq.exceptions.TooManyRedirects):
            return f"{host} redirected too many times (possible redirect loop)."
        if isinstance(exc, _rq.exceptions.SSLError):
            return f"Couldn’t establish a secure HTTPS connection to {host} (certificate or TLS issue)."
        if isinstance(exc, (_rq.exceptions.InvalidURL, _rq.exceptions.MissingSchema, _rq.exceptions.InvalidSchema)):
            return "That doesn’t look like a valid URL. Include “https://”, e.g., https://bencritt.net"
        if isinstance(exc, _rq.exceptions.HTTPError):
            r = exc.response
            code = getattr(r, "status_code", "?")
            reason = getattr(r, "reason", "") or ""
            if code in (401, 403):
                return f"The site responded with HTTP {code} {reason}. Access is restricted, so we can’t scan it."
            if code == 404:
                return "The page wasn’t found (HTTP 404)."
            return f"The site responded with HTTP {code} {reason}."
        if isinstance(exc, _rq.exceptions.ConnectionError):
            s = str(exc).lower()
            if ("name or service not known" in s or
                "temporary failure in name resolution" in s or
                "failed to resolve" in s or
                "nodename nor servname provided" in s):
                return f"DNS lookup failed for {host}. Check the domain name."
            if "connection refused" in s:
                return f"{host} refused the connection."
            return f"Couldn’t connect to {host}."

        # socket / encoding odds and ends
        if isinstance(exc, socket.gaierror):
            return f"DNS lookup failed for {host}."
        if isinstance(exc, UnicodeError):
            return "The URL contains characters we couldn’t interpret."

        # fallback
        return f"Unexpected error while fetching {host}: {exc}"

    def _normalize_if_possible(raw_url: str) -> str:
        # Prefer your utils.normalize_url if present; otherwise add https:// when missing.
        try:
            if "normalize_url" in globals() and callable(globals()["normalize_url"]):
                return normalize_url(raw_url)  # type: ignore[name-defined]
        except Exception:
            pass
        p = urlparse(raw_url)
        if not p.scheme:
            return "https://" + raw_url.lstrip("/")
        return raw_url

    def _validate_public_host_or_raise(url: str):
        """Like `_validate_public_host` but raises local `_Friendly` errors."""
        import ipaddress
        p = urlparse(url)
        host = p.hostname or ""
        if not host:
            raise _Friendly("That URL doesn’t include a host. Try something like “https://bencritt.net”.")
        # Literal IP?
        try:
            ip = ipaddress.ip_address(host)
            if not ip.is_global:
                raise _Friendly("That address is private or local and can’t be scanned from this server.")
            return
        except ValueError:
            # Not an IP → validate domain-ish
            try:
                host.encode("idna")
            except UnicodeError:
                raise _Friendly("The domain contains characters we couldn’t interpret. Try ASCII/punycode.")
            if "." not in host:
                raise _Friendly("That host doesn’t look like a public domain. Please include a full domain like “bencritt.net”.")

    # ──────────────────────────────────────────────────────────────────────────────────────────────
    try:
        task = _load_task(task_id)
    except Exception:
        _set_running(_get_running() - 1)
        return

    url_for_error_context = task.url  # keep original for clearer error messages

    try:
        _cleanup_old_files()

        # Normalize URL (adds scheme if missing) and validate host *before* network I/O.
        task.url = _normalize_if_possible(task.url)
        url_for_error_context = task.url
        _validate_public_host_or_raise(task.url)

        _update_progress(task_id, 5, "Starting…")

        # Use your existing pipeline (imports already defined earlier in this file)
        sess = requests.Session()
        sess.headers["User-Agent"] = USER_AGENT

        _update_progress(task_id, 10, "Fetching page HTML…")
        html = fetch(task.url, sess)

        _update_progress(task_id, 15, "Collecting stylesheets…")
        soup = BeautifulSoup(html, "html.parser")
        root_host = urlparse(task.url).hostname or ""

        style_tags = list(soup.find_all("style"))
        link_tags = [
            l for l in soup.find_all("link", href=True)
            if "stylesheet" in (l.get("rel") or []) or (l.get("as", "").lower() == "style")
        ]

        total_fetches = len(style_tags) + len(link_tags)
        done_fetches = 0
        css_blocks: list[tuple[str, str]] = []

        def _bump_fetch(msg: str):
            nonlocal done_fetches
            done_fetches += 1
            # Map downloads proportionally into the 15→50% region
            pct = 15 + int(35 * (done_fetches / max(total_fetches or 1, 1)))  # 15→50
            _update_progress(task_id, pct, msg)

        # inline styles
        for tag in style_tags:
            css_txt = tag.string or ""
            css_blocks.append((css_txt, root_host))
            _bump_fetch("Collected inline styles…")

        # Linked styles + their nested imports
        for link in link_tags:
            css_url = urljoin(task.url, link["href"])
            try:
                css = fetch(css_url, sess)
                host = urlparse(css_url).hostname or root_host
                css_blocks.append((css, host))
                for imported in pull_imports(css, task.url, sess):
                    css_blocks.append((imported, host))
                _bump_fetch("Downloaded stylesheet…")
            except requests.RequestException:
                _bump_fetch("Skipped unreachable stylesheet…")

        # Parse & build rows
        _update_progress(task_id, 60, "Analyzing fonts…")
        fam_map = families_and_hosts(css_blocks)
        page_host = urlparse(task.url).hostname or ""

        rows: list[dict] = []
        fams = sorted(fam_map.items(), key=lambda kv: kv[0].lower())
        total_parse = len(fams)
        for i, (fam, hosts) in enumerate(fams, 1):
            rows.append({
                "website": page_host,
                "family": fam,
                "license_required": needs_license(fam, hosts),
                "font_source": font_source(fam, hosts, page_host),
            })
            pct = 50 + int(35 * (i / total_parse)) if total_parse else 85
            _update_progress(task_id, min(pct, 85))

        # Write CSV to disk
        _update_progress(task_id, 95, "Preparing CSV…")
        task.rows_count = len(rows)
        fname = f"font_report_{task.id}.csv"
        fpath = _os.path.join(_FI_TASK_DIR, fname)
        _csv_write_to_disk(rows, fpath)
        task.csv_path = fpath

        # Finish
        task.status = "DONE"
        task.progress = 100
        task.message = "Complete."
        task.finished_ts = _now()
        _save_task(task)

    except Exception as exc:
        # Error path: store friendly message and mark the task as finished
        task.status = "ERROR"
        task.message = _humanize(url_for_error_context, exc)
        task.progress = 100
        task.finished_ts = _now()
        _save_task(task)
    finally:
        _set_running(_get_running() - 1)
        _start_next_if_possible()


# ───────────────────────────── public endpoints ──────────────────────────────
@_require_POST
@_trim_memory_after
@_cache_control(no_cache=True, must_revalidate=True, no_store=True)
def start_font_inspector(request):
    """Start a scan for the given URL.

    Returns JSON `{task_id, status, queue_position}` immediately so the
    frontend can show either a **running** state or the **queued** position.
    """
    url = (request.POST.get("url") or "").strip()
    if not url:
        return _HttpResponseBadRequest("Missing url")

    # Normalize URL (use your utils; fall back to adding https:// if no scheme)
    try:
        from .utils import normalize_url as _normalize_url
        url = _normalize_url(url)
    except Exception:
        import re as _re
        if not _re.match(r"^https?://", url, flags=_re.I):
            url = "https://" + url

    _cleanup_old_files()

    task_id = _uuid.uuid4().hex
    task = _Task(
        id=task_id,
        url=url,
        status="QUEUED",
        progress=0,
        message="Waiting for a worker…",
        created_ts=_now(),
    )
    _save_task(task)

    if _get_running() >= _FI_MAX_CONCURRENCY:
        _queue_push(task_id)
        return _JsonResponse({
            "task_id": task_id,
            "status": "QUEUED",
            "queue_position": _queue_position(task_id),
        })

    # Run immediately
    task.status = "RUNNING"
    task.started_ts = _now()
    _save_task(task)
    _set_running(_get_running() + 1)
    _threading.Thread(target=_run_task, args=(task_id,), daemon=True).start()
    return _JsonResponse({"task_id": task_id, "status": "RUNNING", "queue_position": 0})


@_trim_memory_after
@_cache_control(no_cache=True, must_revalidate=True, no_store=True)
def fi_task_status(request, task_id: str):
    """Poll the status of a task. Returns JSON with progress and messages."""
    _cleanup_old_files()
    t = _load_task(task_id)
    out = t.to_json()
    out["queue_position"] = _queue_position(task_id) if t.status == "QUEUED" else 0
    return _JsonResponse(out)

@_trim_memory_after
@_cache_control(no_cache=True, must_revalidate=True, no_store=True)
def fi_rows(request, task_id: str):
    """Return JSON rows parsed back from the on‑disk CSV for in‑page rendering.

    We **do not** delete the CSV here — only when the user downloads it — so
    the UI can request rows multiple times while a detail panel is open.
    """
    _cleanup_old_files()
    t = _load_task(task_id)
    path = t.csv_path
    if not path or not _os.path.exists(path):
        raise _Http404("File no longer available")
    rows = []
    with open(path, newline="", encoding="utf-8") as fh:
        r = _csv.DictReader(fh)
        for row in r:
            rows.append({
                "website": row.get("website", ""),
                "family": row.get("family", ""),
                "license_required": row.get("license_required", ""),
                "font_source": row.get("font_source", ""),
            })
    return _JsonResponse({"rows": rows, "count": len(rows)})

@_trim_memory_after
@_cache_control(no_cache=True, must_revalidate=True, no_store=True)
def fi_download(request, task_id: str):
    """Stream the CSV file to the client **and delete it from disk afterwards**.

    The generator pattern ensures constant memory usage while sending the file
    in chunks. After streaming finishes (or on error), we attempt to remove the
    file and clear the `csv_path` from the task record.
    """
    _cleanup_old_files()
    t = _load_task(task_id)
    path = t.csv_path
    if not path or not _os.path.exists(path):
        raise _Http404("File no longer available")

    def _gen():
        try:
            with open(path, "rb") as f:
                while True:
                    chunk = f.read(64 * 1024)
                    if not chunk:
                        break
                    yield chunk
        finally:
            try:
                _os.remove(path)
            except Exception:
                pass
            try:
                t2 = _load_task(task_id)
                t2.csv_path = None
                _save_task(t2)
            except Exception:
                pass

    filename = f"font_report_{task_id}.csv"
    resp = _StreamingHttpResponse(_gen(), content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="{filename}"'
    return resp
