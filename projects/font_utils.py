# ───────────────────────────────────────────────────────────
from __future__ import annotations
import io, threading, queue, uuid, time, csv, json, logging, os, pathlib, re, sys, cssutils, requests, tinycss2
from functools import lru_cache
from pathlib import Path
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
from cssutils import parseString as parse_css
from rich.console import Console
from rich.table import Table
from tinycss2 import serialize
from typing import Any, Dict, Optional
from django.http import JsonResponse, FileResponse, Http404, HttpRequest
from django.views.decorators.http import require_POST
from django.utils.timezone import now
from .forms import FontInspectorForm

# ───────────────────────── config ──────────────────────────
USER_AGENT   = "Font Inspector by Ben Crittenden (+https://www.bencritt.net)"
HTTP_TIMEOUT = 10
CSV_PATH     = Path("font_report.csv")

# silence cssutils chatter
cssutils.log.setLevel(logging.CRITICAL)
cssutils.ser.prefs.validate = False

URL_RE    = re.compile(r"url\(\s*[\"']?(.*?)[\"']?\s*\)", re.I)
IMPORT_RE = re.compile(r"@import\s+url\(\s*[\"']?(.*?)[\"']?\s*\)", re.I)

# ─────────────────── helpers / normalisation ───────────────
SUFFIX_RX = (
    r"(?:thin|extralight|ultralight|light|regular|book|medium|"
    r"semibold|demibold|bold|extrabold|black|heavy|italic|oblique|obl|boldcond|boldcondobl|condensed|light|thin|bolditalic|"
    r"var|vf|free|normal|trial|variable|\d+)$"
)
STYLE_RX  = rf"-?{SUFFIX_RX}(?:italic|oblique)?$"
CONDENSED = r"(?:extra|ultra)?(?:semi)?(?:condensed|expanded|wide)$"

def norm(txt: str) -> str:
    """lower-case and strip spaces/dashes/weights for robust matching"""
    txt = txt.lower().strip()
    txt = re.sub(STYLE_RX, "", txt)          # kill weight/style suffix
    txt = re.sub(rf"-?{CONDENSED}", "", txt) # kill condensed/expanded
    return re.sub(r"[\s\-]+", "", txt)       # remove spaces & dashes

# ────────── Font Awesome quick classifier ───────────
def classify_fa(lf: str) -> tuple[str | None, str | None]:
    """
    Return (source_label, license) for Font Awesome families,
    or (None, None) if not Font Awesome.
    Handles:
      * fa-duotone-900, fa-thin-100, fa-sharp-solid-900
      * 'Font Awesome 6 Duotone', 'Font Awesome 6 Sharp', 'Font Awesome 6 Pro'
    """
    # free sets already handled elsewhere
    if lf.startswith(("fa-solid-", "fa-regular-", "fa-brands-")):
        return "Font Awesome Free", "No"

    if lf.startswith(("fa-duotone-", "fa-light-", "fa-thin-", "fa-sharp-")):
        return "Font Awesome Pro", "Yes"

    if lf.startswith("fontawesome") and "pro" in lf:
        return "Font Awesome Pro", "Yes"

    if lf.startswith("fontawesome6") and ("duotone" in lf or "sharp" in lf):
        return "Font Awesome Pro", "Yes"

    # Pretty “official” names (spaces kept for clarity)
    if lf.startswith(("font awesome 6 duotone",
                      "font awesome 6 sharp",
                      "font awesome 6 pro")):
        return "Font Awesome Pro", "Yes"

    return None, None

# ───────────────── Google font catalogue loader ────────────
HARD_CODED_GOOGLE_FONTS = {
  "abel",
  "abhaya libre",
  "abril fatface",
  "aclonica",
  "acme",
  "actor",
  "adamina",
  "advent pro",
  "aguafina script",
  "aladin",
  "alata",
  "alatsi",
  "albert sans",
  "aldrich",
  "alef",
  "alegreya",
  "alegreya sans",
  "aleo",
  "alex brush",
  "alfa slab one",
  "alice",
  "alike angular",
  "alkalami",
  "allerta",
  "allerta stencil",
  "allison",
  "allura",
  "almarai",
  "almendra",
  "almendra display",
  "amaranth",
  "amata",
  "amatic sc",
  "amethysta",
  "amiko",
  "amiri",
  "amita",
  "anaheim",
  "andika",
  "annie use your telescope",
  "anonymous pro",
  "antic",
  "antic didone",
  "antic slab",
  "anton",
  "antonio",
  "archivo",
  "archivo black",
  "archivo expanded",
  "archivo narrow",
  "aref ruqaa",
  "arima",
  "armata",
  "arsenal",
  "asap",
  "asap condensed",
  "asetcon",
  "assistant",
  "astloch",
  "asul",
  "athiti",
  "atkinson hyperlegible",
  "atkinson hyperlegible mono",
  "atomic age",
  "aubrey",
  "audiowide",
  "average",
  "averia libre",
  "averia sans libre",
  "averia serif libre",
  "azeret mono",
  "b612",
  "b612 mono",
  "bad script",
  "bahiana",
  "bai jamjuree",
  "baijamjuree",
  "baloo 2",
  "baloo bhai 2",
  "baloo bhaijaan 2",
  "baloo chettan 2",
  "baloo da 2",
  "baloo paaji 2",
  "baloo thambi 2",
  "balsamiq sans",
  "barlow",
  "barlow condensed",
  "barlow semi condensed",
  "barriecito",
  "basic",
  "baskervville",
  "battambang",
  "bayon",
  "be vietnam",
  "be vietnam pro",
  "bebas neue",
  "belgrano",
  "bellota",
  "bellota text",
  "benchnine",
  "bentham",
  "besley",
  "bhutuka expanded one",
  "big shouldered display",
  "big shouldered inline display",
  "big shouldered text",
  "bigelow rules",
  "bigshot one",
  "bilbo",
  "biorhyme",
  "biorhyme expanded",
  "bitter",
  "bitter pro",
  "bitter variable",
  "black han sans",
  "black ops one",
  "blinker",
  "bodoni moda",
  "bona nova",
  "boogaloo",
  "bowlby one",
  "bowlby one sc",
  "braah one",
  "brawler",
  "bree serif",
  "brygada 1918",
  "bubbler one",
  "buda",
  "buenard",
  "bungee",
  "bungee hairline",
  "bungee inline",
  "bungee outline",
  "bungee shade",
  "cabin",
  "cabin condensed",
  "cairo",
  "cairo play",
  "cardo",
  "carme",
  "carrois gothic",
  "carrois gothic sc",
  "catamaran",
  "caveat",
  "chewy",
  "chilanka",
  "chivo",
  "chivo mono",
  "cinzel",
  "cinzel decorative",
  "comfortaa",
  "commissioner",
  "concert one",
  "content",
  "cookie",
  "cormorant",
  "cormorant garamond",
  "cormorant infant",
  "cormorant sc",
  "cormorant upright",
  "cousine",
  "coustard",
  "crimson pro",
  "crimson text",
  "croissant one",
  "cuprum",
  "cutive",
  "cutive mono",
  "dancing script",
  "dm mono",
  "dm sans",
  "dm serif display",
  "dm serif text",
  "domine",
  "eagle lake",
  "eb garamond",
  "electrolize",
  "encode sans",
  "encode sans condensed",
  "encode sans expanded",
  "epilogue",
  "exo",
  "exo 2",
  "faustina",
  "figtree",
  "fira code",
  "fira sans",
  "firma sans",
  "fjalla one",
  "fjord one",
  "francois one",
  "fraunces",
  "fredoka",
  "fredoka one",
  "fugaz one",
  "gabarito",
  "gelasio",
  "gloock",
  "golos text",
  "golos ui",
  "gothic a1",
  "great vibes",
  "guise",
  "hanken grotesk",
  "heebo",
  "hepta slab",
  "hind",
  "hind colombo",
  "hind madurai",
  "hind siliguri",
  "hind vadodara",
  "hubballi",
  "ibarra real nova",
  "ibm plex mono",
  "ibm plex sans",
  "ibm plex sans arabic",
  "ibm plex serif",
  "inconsolata",
  "inika",
  "instrument mono",
  "instrument sans",
  "instrument serif",
  "inter",
  "inter tight",
  "jaldi",
  "jetbrains mono",
  "josefin sans",
  "josefin slab",
  "jost",
  "kanit",
  "karla",
  "kaushan script",
  "khand",
  "krona one",
  "lato",
  "latto",
  "league spartan",
  "lexend",
  "lexend deca",
  "lexend exa",
  "lexend giga",
  "lexend mega",
  "lexend peta",
  "lexend tera",
  "lexend zetta",
  "libre bodoni",
  "libre caslon display",
  "libre caslon text",
  "libre franklin",
  "literata",
  "lobster",
  "lora",
  "manrope",
  "martel",
  "martian mono",
  "maven pro",
  "merriweather",
  "merriweather sans",
  "montagu slab",
  "montserrat",
  "montserrat alternates",
  "montserrat subrayada",
  "mukta",
  "mukta mahee",
  "mukta vaani",
  "mulish",
  "nanum gothic",
  "nanum gothic coding",
  "nanum myeongjo",
  "nanum pen script",
  "neuton",
  "news cycle",
  "newsreader",
  "noticia text",
  "noto sans",
  "noto sans arabic",
  "noto sans bengali",
  "noto sans devanagari",
  "noto sans display",
  "noto sans hebrew",
  "noto sans jp",
  "noto sans kr",
  "noto sans mono",
  "noto sans sc",
  "noto sans tc",
  "noto sans thai",
  "noto serif",
  "noto serif arabic",
  "noto serif devanagari",
  "noto serif hebrew",
  "noto serif jp",
  "noto serif sc",
  "noto serif tc",
  "noto serif thai",
  "nunito",
  "nunito sans",
  "old standard tt",
  "open sans",
  "oswald",
  "outfit",
  "overlock",
  "overpass",
  "overpass mono",
  "oxygen",
  "oxygen mono",
  "pacifico",
  "petrona",
  "philosopher",
  "pioppins",
  "play",
  "playball",
  "playfair",
  "playfair display",
  "plus jakarta sans",
  "poiret one",
  "pontano sans",
  "popins",
  "poppins",
  "pragati narrow",
  "prata",
  "prompt",
  "proza libre",
  "pt mono",
  "pt sans",
  "pt sans caption",
  "pt sans narrow",
  "pt serif",
  "public sans",
  "puritan",
  "questrial",
  "quicksand",
  "raleway",
  "raleway dots",
  "readex pro",
  "red hat display",
  "red hat mono",
  "red hat text",
  "reem kufi",
  "righteous",
  "roboto",
  "roboto condensed",
  "roboto flex",
  "roboto mono",
  "roboto serif",
  "roboto slab",
  "rokkitt",
  "rubik",
  "rubik bubbles",
  "rubik dirt",
  "rubik glitch",
  "rubik iso",
  "rubik scribble",
  "rubik spray paint",
  "rubik vinyl",
  "ruda",
  "ruluko",
  "sacramento",
  "sarabun",
  "sarala",
  "satisfy",
  "sen",
  "sintony",
  "sora",
  "source code pro",
  "source sans 3",
  "source serif 4",
  "space grotesk",
  "space mono",
  "spartan",
  "spectral",
  "spline sans",
  "spline sans mono",
  "sriracha",
  "staatliches",
  "state machine",
  "suez one",
  "syne",
  "tajawal",
  "tangerine",
  "teko",
  "tektur",
  "telex",
  "tenor sans",
  "text me one",
  "thasadith",
  "titillium web",
  "trade winds",
  "ubuntu",
  "ubuntu condensed",
  "ubuntu mono",
  "unbounded",
  "unica one",
  "urbanist",
  "varela",
  "varela round",
  "varta",
  "vazirmatn",
  "viaoda libre",
  "vidaloka",
  "viri",
  "vollkorn",
  "vt323",
  "work sans",
  "worksans",
  "yanone kaffeesatz",
  "yantramanav",
  "yatra one",
  "yeseva one",
  "young serif",
  "yrsa",
  "ysabeau",
  "ysabeau infant",
  "ysabeau office",
  "zilla slab",
  "zilla slab highlight"
}


def _fetch_google_fonts(api_key: str) -> set[str]:
    api_key = os.environ.get("GOOGLE_FONT_KEY")
    url = f"https://www.googleapis.com/webfonts/v1/webfonts?key={api_key}"
    items = requests.get(url, timeout=10).json()["items"]
    return {item["family"].lower() for item in items}

@lru_cache(maxsize=1)
def load_google_font_families() -> set[str]:
    """
    1) live Google Web Fonts API if GOOGLE_FONTS_API_KEY is set
    2) ~/.cache/gf_families.json (≤24 h)
    3) baked-in 350-family fallback
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

    if cache_file.exists() and time.time() - cache_file.stat().st_mtime < 86400:
        return set(json.loads(cache_file.read_text()))

    return {f.lower() for f in HARD_CODED_GOOGLE_FONTS}

# ───────────────────── lookup maps ─────────────────────────
GOOGLE_FONTS       = load_google_font_families()
FREE_ICON_FONTS    = {
    "bootstrap icons","font awesome","fontawesome","fontawesomewebfont",
    "glyphicons","glyphiconshalflings","material icons","material symbols",
    "feather","heroicons","phosphor","fa-brands-400","videojs",
    "eleganticons","dripicons-v2","kiko","wc_gc","sw-icon-font",
    "woocommerce","vc_grid_v1","vcpb-plugin-icons",
}

FAMILY_SOURCE_MAP: dict[str,str] = (
    {norm(f): "Google Fonts"      for f in GOOGLE_FONTS}         |
    {norm(f): "Font Awesome Free" for f in FREE_ICON_FONTS}       |
    {
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

# ── Typemates commercial catalogue ─────────────────────────
# ── Typemates catalogue ────────────────────────────────────
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

# add them to FAMILY_SOURCE_MAP
for name in TYPEMATES_FAMILIES:
    FAMILY_SOURCE_MAP[norm(name)] = "Typemates (Commercial)"

# build one tolerant regex
BASES = [norm(n) for n in TYPEMATES_FAMILIES]
TYPEMATES_RE = re.compile(
    r"^(?:"
    + "|".join(sorted(set(BASES)))               # any base name …
    + r")"
    r"(?:pro|var|vf|variable|trial)?"             # … optional tag
    r".*",                                        # … anything else
    re.I,
)

def is_typemates(lf: str) -> bool:
    return bool(TYPEMATES_RE.match(lf))


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
def fetch(url: str, sess: requests.Session) -> str:
    r = sess.get(url, timeout=HTTP_TIMEOUT)
    r.raise_for_status()
    return r.text

def pull_imports(css: str, base: str, sess) -> list[str]:
    """follow nested @import chains depth-first"""
    stack, out, seen = [css], [], set()
    while stack:
        txt = stack.pop()
        for ref in IMPORT_RE.findall(txt):
            url = urljoin(base, ref)
            if url in seen:               # avoid loops
                continue
            seen.add(url)
            try:
                fetched = fetch(url, sess)
                out.append(fetched)
                stack.append(fetched)
            except requests.RequestException:
                pass
    return out

# ───────────────────── CSS collector ───────────────────────
def gather_css(html: str, base: str, sess) -> list[tuple[str,str]]:
    """Return [(raw_css, supplier_host), …]"""
    soup = BeautifulSoup(html, "html.parser")
    out  : list[tuple[str,str]] = []

    def add(txt: str, host: str):
        out.append((txt, host))
        out.extend((t, host) for t in pull_imports(txt, base, sess))

    root_host = urlparse(base).hostname or ""
    for tag in soup.find_all("style"):
        add(tag.string or "", root_host)

    for link in soup.find_all("link", href=True):
        rels = link.get("rel") or []
        if "stylesheet" in rels or link.get("as", "").lower() == "style":
            css_url = urljoin(base, link["href"])
            try:
                add(fetch(css_url, sess), urlparse(css_url).hostname or root_host)
            except requests.RequestException:
                pass
    return out

# ─────────────────── family ↔ host map ─────────────────────
def families_and_hosts(blocks: list[tuple[str,str]]) -> dict[str,set[str]]:
    """
    Harvest {family → {hosts}} from <style> + linked CSS.
    Combines cssutils parsing with regex fallbacks for robustness.
    """
    fam_map: dict[str,set[str]] = {}
    GENERIC = {
        "serif","sans-serif","monospace","cursive","fantasy","system-ui",
        "ui-sans-serif","ui-serif","ui-monospace","emoji","math","fangsong",
        "inherit","initial","unset","star","sans-serif!","tofu",
    }
    FONTFACE_RE = re.compile(r"@font-face\s*{(.*?)}", re.I | re.S)
    # FAMILY_RE   = re.compile(r"font-family\s*:\s*([^;]+);", re.I)
    FAMILY_RE = re.compile(r"font-family\s*:\s*([^;]+);", re.I)

    def real(tok: str) -> bool:
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
    lf = norm(family)

    # Font Awesome override
    _, lic = classify_fa(lf)
    if lic:
        return lic
    
    if is_typemates(lf):
        return "Yes"

    low_hosts = {h.lower() for h in hosts}

    if lf == norm("Google Sans Mono"):
        return "Yes"
    if lf in FAMILY_SOURCE_MAP:
        return "No"
    if lf in SYSTEM_FONTS:
        return "No"
    if any(any(src in h for h in low_hosts) for src in OPEN_SOURCE_HOSTS):
        return "No"
    if any(any(com in h for h in low_hosts) for com in COMMERCIAL_HOSTS):
        return "Yes"
    return "Unknown"

def is_same_site(hosts: set[str], page_host: str) -> bool:
    """True if every host string ends with the page’s registrable domain."""
    if not hosts:
        return False
    root = ".".join(page_host.split(".")[-2:])  # e.g. tandemloc.com
    return all(root in h for h in hosts)

def font_source(family: str,
                hosts: set[str],
                page_host: str) -> str:
    """
    Determine human-readable rights source.

    1) system font →
    2) family catalogue map →
    3) host substring map →
    4) self-hosted / unknown
    """
    lf           = norm(family)

    # Font Awesome override
    label, _ = classify_fa(lf)
    if label:
        return label
    
    # Typemates override
    if is_typemates(lf):
        return "Typemates (Commercial)"

    hosts_lower  = {h.lower() for h in hosts}
    
    # Catchall for Linea Icons
    if lf.startswith("linea-"):
        return "Linea Icons"

    # 1) operating-system stack fonts
    if lf in SYSTEM_FONTS:
        return "System font"

    # 2) known open-source catalogues / icon sets
    if lf in FAMILY_SOURCE_MAP:
        label = FAMILY_SOURCE_MAP[lf]

        # add “(self-hosted)” when every src host is the page’s domain
        if hosts_lower and _all_same_site(hosts_lower, page_host):
            label += " (self-hosted)"
        return label

    # 3) matching CDN host
    for h in hosts_lower:
        for pat, label in SOURCE_MAP.items():
            if pat in h:
                return label

    # 4) fallback
    if hosts_lower:
        return f"Self-hosted ({', '.join(sorted(hosts_lower))})"
    return "Unknown source"


def _all_same_site(hosts: set[str], page_host: str) -> bool:
    """
    True if every host ends with the page’s registrable domain
    (foo.example.com, cdn.example.com  →  example.com)
    """
    if not hosts:
        return False
    root = ".".join(page_host.split(".")[-2:])   # example.com
    return all(root in h for h in hosts)


# ─────────────────── build the whole report ────────────────
def make_report(page_url: str) -> list[dict]:
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
    tab = Table(title="Fonts detected")
    tab.add_column("website")
    tab.add_column("family")
    tab.add_column("license_required")
    tab.add_column("font_source")
    for r in rows:
        tab.add_row(
            r["website"],            # 1 – website
            r["family"],             # 2 – family
            r["license_required"],   # 3 – license_required
            r["font_source"],        # 4 – font_source
    )

    Console().print(tab)

def save_csv(rows: list[dict]) -> None:
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
    buffer = io.StringIO()
    writer = csv.DictWriter(
        buffer,
        fieldnames=["website", "family", "license_required", "font_source"],
    )
    writer.writeheader()
    writer.writerows(rows)
    out = io.BytesIO(buffer.getvalue().encode())
    out.seek(0)
    return out

class _Task:
    __slots__ = ("id","status","progress","message","created_at","url","rows","error")
    def __init__(self, url: str):
        self.id = str(uuid.uuid4())
        self.status   = "queued"    # queued | running | done | error
        self.progress = 0
        self.message  = "Queued"
        self.created_at = now()
        self.url = url
        self.rows = None
        self.error = None

_TASKS: Dict[str,_Task] = {}
_QUEUE: "queue.Queue[_Task]" = queue.Queue(maxsize=20)
_WORKER_STARTED = False
_LOCK = threading.Lock()

def _queue_pos(task_id: str) -> Optional[int]:
    t = _TASKS.get(task_id)
    if not t: return None
    if t.status != "queued": return 0
    # count how many queued tasks were created before this one
    earlier = sum(1 for x in _TASKS.values() if x.status=="queued" and x.created_at < t.created_at)
    return earlier

def _worker():
    while True:
        task = _QUEUE.get()
        try:
            task.status, task.progress, task.message = "running", 5, "Validating URL…"
            time.sleep(0.05)
            task.progress, task.message = 25, "Fetching page…"
            rows = make_report(task.url)  # may raise
            task.progress, task.message = 80, "Analyzing fonts & licenses…"
            time.sleep(0.05)
            task.rows = rows or []
            task.status, task.progress, task.message = "done", 100, "Ready"
        except Exception as e:
            task.status, task.progress, task.message = "error", 100, "Failed"
            task.error = str(e)
        finally:
            _QUEUE.task_done()

def _ensure_worker():
    global _WORKER_STARTED
    with _LOCK:
        if not _WORKER_STARTED:
            th = threading.Thread(target=_worker, name="font-scan-worker", daemon=True)
            th.start()
            _WORKER_STARTED = True

@require_POST
def start_font_scan(request: HttpRequest):
    """POST: validate URL, enqueue, return task id + initial status."""
    form = FontInspectorForm(request.POST or None)
    if not form.is_valid():
        return JsonResponse({"ok": False, "errors": form.errors.get_json_data()}, status=400)
    _ensure_worker()
    if _QUEUE.full():
        return JsonResponse({"ok": False, "error": "The queue is currently full. Please try again shortly."}, status=429)
    url = form.cleaned_data["url"]
    t = _Task(url=url)
    _TASKS[t.id] = t
    _QUEUE.put(t)
    return JsonResponse({
        "ok": True,
        "task_id": t.id,
        "status": t.status,
        "progress": t.progress,
        "message": t.message,
        "queue_position": _queue_pos(t.id),
    })

def get_font_task_status(request: HttpRequest, task_id: str):
    """GET: return live status/progress; include preview + download URL when done."""
    task_id = str(task_id)
    t = _TASKS.get(task_id)
    if not t:
        raise Http404("Unknown task")
    payload: Dict[str,Any] = {
        "ok": True,
        "task_id": t.id,
        "status": t.status,
        "progress": t.progress,
        "message": t.message,
        "queue_position": _queue_pos(task_id),
    }
    if t.status == "done":
        payload["rows"] = (t.rows or [])[:500]  # small preview
        payload["download_url"] = f"/projects/font_scan_download/{t.id}/"
    if t.status == "error":
        payload["error"] = t.error or "Unknown error"
    return JsonResponse(payload)

def download_font_task_file(request: HttpRequest, task_id: str):
    """GET: serve CSV when task is done."""
    task_id = str(task_id)
    t = _TASKS.get(task_id)
    if not t or t.status not in ("done", "error"):
        raise Http404("Result not ready")
    if t.status == "error":
        return JsonResponse({"ok": False, "error": t.error or "Unknown error"}, status=400)
    csv_io = report_to_csv(t.rows or [])
    return FileResponse(csv_io, as_attachment=True,
                        filename=f"font_report_{task_id}.csv",
                        content_type="text/csv")
