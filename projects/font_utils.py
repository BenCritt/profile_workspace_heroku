import io
import csv
import json
import logging
import os
import pathlib
import re
import sys
import time
from functools import lru_cache
from pathlib import Path
from urllib.parse import urljoin, urlparse
import cssutils
import requests
import tinycss2
from bs4 import BeautifulSoup
from cssutils import parseString as parse_css
from rich.console import Console
from rich.table import Table
from tinycss2 import serialize

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

# ─────────────────────────────────────────────────────────────────────────────
# Font Inspector — async task/queue API (SEO Head Checker style)
# Append this block at the END of projects/font_utils.py (keep your existing code above).
# ─────────────────────────────────────────────────────────────────────────────
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

# Cache keys
def _k_task(task_id: str) -> str: return f"fi:task:{task_id}"
_K_RUNNING = "fi:running"   # int
_K_QUEUE   = "fi:queue"     # list[str]
_K_LAST_CLEAN = "fi:last_clean"

@_dataclass
class _Task:
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
    return _time.time()

def _coerce_int(x, default=0) -> int:
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
    task_id = q.pop(0)
    _fi_cache.set(_K_QUEUE, q, timeout=_FI_TASK_TTL_SECS)
    return task_id

def _queue_position(task_id: str) -> int:
    q = _fi_cache.get(_K_QUEUE) or []
    try:
        return q.index(task_id) + 1
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
    with open(to_path, "w", newline="", encoding="utf-8") as fh:
        w = _csv.DictWriter(
            fh,
            fieldnames=["website", "family", "license_required", "font_source"],
        )
        w.writeheader()
        w.writerows(rows)

def _start_next_if_possible():
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
    Real progress:
      5%  start
     15%  fetched HTML
     50%  downloaded styles & nested @import (proportional)
     85%  parsed families
     95%  writing CSV
    100%  done
    """
    try:
        task = _load_task(task_id)
    except Exception:
        _set_running(_get_running() - 1)
        return

    try:
        _cleanup_old_files()
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
        link_tags  = [l for l in soup.find_all("link", href=True)
                      if "stylesheet" in (l.get("rel") or []) or (l.get("as","").lower() == "style")]

        total_fetches = len(style_tags) + len(link_tags)
        done_fetches  = 0
        css_blocks: list[tuple[str, str]] = []

        def _bump_fetch(msg: str):
            nonlocal done_fetches
            done_fetches += 1
            pct = 15 + int(35 * (done_fetches / max(total_fetches or 1, 1)))  # 15→50
            _update_progress(task_id, pct, msg)

        # inline styles
        for tag in style_tags:
            css_txt = tag.string or ""
            css_blocks.append((css_txt, root_host))
            _bump_fetch("Collected inline styles…")

        # linked styles (and nested @import)
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
        fam_map   = families_and_hosts(css_blocks)
        page_host = urlparse(task.url).hostname or ""

        rows: list[dict] = []
        fams = sorted(fam_map.items(), key=lambda kv: kv[0].lower())
        total_parse = len(fams)
        for i, (fam, hosts) in enumerate(fams, 1):
            rows.append({
                "website": page_host,
                "family": fam,
                "license_required": needs_license(fam, hosts),
                "font_source":      font_source(fam, hosts, page_host),
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
        task.status = "ERROR"
        task.message = f"Error: {exc}"
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
    """Start a scan for the given URL. Returns JSON {task_id, status, queue_position}."""
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
    """Poll status. Returns JSON with {status, progress, message, rows_count, queue_position}."""
    _cleanup_old_files()
    t = _load_task(task_id)
    out = t.to_json()
    out["queue_position"] = _queue_position(task_id) if t.status == "QUEUED" else 0
    return _JsonResponse(out)

@_trim_memory_after
@_cache_control(no_cache=True, must_revalidate=True, no_store=True)
def fi_rows(request, task_id: str):
    """
    Return JSON rows from the CSV (for rendering the table in-page).
    We DO NOT delete the CSV here; deletion happens on actual download.
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
    """
    Stream the CSV file; delete from disk after streaming (and clear the cache path).
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
