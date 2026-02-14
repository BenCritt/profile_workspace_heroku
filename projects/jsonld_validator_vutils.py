"""
jsonld_validator/utils.py

Core logic for extracting and validating JSON-LD / structured data
from a web page.  Fetches the HTML, parses out every
<script type="application/ld+json"> block, then checks each one for:

  - Valid JSON syntax
  - Presence of required schema.org top-level keys (@context, @type)
  - Common required/recommended properties per schema.org type
  - @graph handling (array of entities in a single block)
  - Actionable warnings for SEO best practices
"""

import json
import time
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REQUEST_TIMEOUT = 15  # seconds

# Per-type property expectations.
# "required" → missing = error.  "recommended" → missing = warning.
# This is intentionally not exhaustive; it covers the types most commonly
# encountered in technical SEO audits.
SCHEMA_PROPERTY_RULES = {
    "Article": {
        "required": ["headline", "author"],
        "recommended": ["datePublished", "image", "publisher", "description"],
    },
    "NewsArticle": {
        "required": ["headline", "author", "datePublished"],
        "recommended": ["image", "publisher", "description"],
    },
    "BlogPosting": {
        "required": ["headline", "author"],
        "recommended": ["datePublished", "image", "publisher", "description"],
    },
    "WebPage": {
        "required": ["name"],
        "recommended": ["url", "description"],
    },
    "WebSite": {
        "required": ["name", "url"],
        "recommended": [],
    },
    "Organization": {
        "required": ["name"],
        "recommended": ["url", "logo", "sameAs"],
    },
    "LocalBusiness": {
        "required": ["name", "address"],
        "recommended": ["telephone", "openingHoursSpecification", "geo", "url"],
    },
    "Person": {
        "required": ["name"],
        "recommended": ["url", "sameAs", "jobTitle"],
    },
    "Product": {
        "required": ["name"],
        "recommended": ["image", "description", "offers", "brand", "sku"],
    },
    "SoftwareApplication": {
        "required": ["name"],
        "recommended": [
            "applicationCategory",
            "operatingSystem",
            "offers",
            "description",
        ],
    },
    "FAQPage": {
        "required": ["mainEntity"],
        "recommended": [],
    },
    "BreadcrumbList": {
        "required": ["itemListElement"],
        "recommended": [],
    },
    "CollectionPage": {
        "required": ["name"],
        "recommended": ["url", "description", "mainEntity"],
    },
    "ItemList": {
        "required": ["itemListElement"],
        "recommended": ["name"],
    },
    "Event": {
        "required": ["name", "startDate", "location"],
        "recommended": ["endDate", "description", "image", "organizer"],
    },
    "Recipe": {
        "required": ["name", "recipeIngredient", "recipeInstructions"],
        "recommended": ["image", "author", "prepTime", "cookTime"],
    },
    "Review": {
        "required": ["reviewRating", "author", "itemReviewed"],
        "recommended": ["reviewBody", "datePublished"],
    },
    "HowTo": {
        "required": ["name", "step"],
        "recommended": ["image", "totalTime", "estimatedCost"],
    },
    "VideoObject": {
        "required": ["name", "uploadDate", "thumbnailUrl"],
        "recommended": ["description", "contentUrl", "duration"],
    },
    "Offer": {
        "required": ["price", "priceCurrency"],
        "recommended": ["availability", "url"],
    },
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def validate_jsonld(url):
    """
    Fetch a web page and validate all JSON-LD blocks found on it.

    Returns a dict:
        "url"           : str — the URL that was fetched
        "fetch_time"    : float — seconds to fetch the page
        "status_code"   : int or None
        "fetch_error"   : str or None
        "blocks"        : list of block result dicts (see _validate_block)
        "block_count"   : int — total <script type="application/ld+json"> tags
        "entity_count"  : int — total individual entities (including @graph items)
        "error_count"   : int — total errors across all blocks
        "warning_count" : int — total warnings across all blocks
        "overall"       : str — "pass", "warnings", or "errors"
    """
    page_html, status_code, fetch_time, fetch_error = _fetch_page(url)

    result = {
        "url": url,
        "fetch_time": round(fetch_time, 3),
        "status_code": status_code,
        "fetch_error": fetch_error,
        "blocks": [],
        "block_count": 0,
        "entity_count": 0,
        "error_count": 0,
        "warning_count": 0,
        "overall": "pass",
    }

    if fetch_error:
        result["overall"] = "errors"
        return result

    # Extract raw JSON-LD script contents.
    raw_blocks = _extract_jsonld_blocks(page_html)
    result["block_count"] = len(raw_blocks)

    if not raw_blocks:
        result["blocks"] = []
        result["overall"] = "warnings"
        result["warning_count"] = 1
        return result

    for idx, raw in enumerate(raw_blocks, start=1):
        block_result = _validate_block(raw, block_number=idx)
        result["blocks"].append(block_result)
        result["entity_count"] += block_result["entity_count"]
        result["error_count"] += block_result["error_count"]
        result["warning_count"] += block_result["warning_count"]

    # Determine overall health.
    if result["error_count"] > 0:
        result["overall"] = "errors"
    elif result["warning_count"] > 0:
        result["overall"] = "warnings"
    else:
        result["overall"] = "pass"

    return result


# ---------------------------------------------------------------------------
# Fetching
# ---------------------------------------------------------------------------


def _fetch_page(url):
    """
    Fetch the HTML content of a URL.
    Returns (html_str, status_code, elapsed_seconds, error_str_or_None).
    """
    try:
        start = time.monotonic()
        resp = requests.get(
            url,
            timeout=REQUEST_TIMEOUT,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (compatible; BenCrittJSONLDValidator/1.0; "
                    "+https://www.bencritt.net/projects/jsonld-validator/)"
                ),
                "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
            },
        )
        elapsed = time.monotonic() - start
        resp.raise_for_status()
        return resp.text, resp.status_code, elapsed, None

    except requests.exceptions.Timeout:
        return None, None, REQUEST_TIMEOUT, (
            f"Request timed out after {REQUEST_TIMEOUT}s."
        )
    except requests.exceptions.ConnectionError as exc:
        err = str(exc)
        if "NameResolutionError" in err or "getaddrinfo" in err:
            parsed = urlparse(url)
            return None, None, 0, (
                f"DNS resolution failed for {parsed.hostname}."
            )
        return None, None, 0, f"Connection error: {_trunc(err, 200)}"
    except requests.exceptions.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else None
        return None, status, 0, (
            f"HTTP error: {status} {exc.response.reason if exc.response is not None else ''}."
        )
    except requests.exceptions.RequestException as exc:
        return None, None, 0, f"Request failed: {_trunc(str(exc), 200)}"


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------


def _extract_jsonld_blocks(html):
    """
    Parse HTML and return a list of raw strings from every
    <script type="application/ld+json"> tag.
    """
    soup = BeautifulSoup(html, "html.parser")
    scripts = soup.find_all("script", attrs={"type": "application/ld+json"})
    return [tag.string.strip() for tag in scripts if tag.string]


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _validate_block(raw_json, block_number):
    """
    Validate a single JSON-LD block.

    Returns a dict:
        "block_number"  : int
        "raw"           : str (the raw JSON text, truncated for display)
        "parsed"        : str (pretty-printed JSON, or None on parse failure)
        "parse_error"   : str or None
        "entities"      : list of entity result dicts
        "entity_count"  : int
        "error_count"   : int
        "warning_count" : int
    """
    block = {
        "block_number": block_number,
        "raw": raw_json,
        "parsed": None,
        "parse_error": None,
        "entities": [],
        "entity_count": 0,
        "error_count": 0,
        "warning_count": 0,
    }

    # ── Step 1: Parse JSON ────────────────────────────────────────────
    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        block["parse_error"] = f"Invalid JSON: {exc.msg} (line {exc.lineno}, col {exc.colno})."
        block["error_count"] = 1
        return block

    block["parsed"] = json.dumps(data, indent=2, ensure_ascii=False)

    # ── Step 2: Flatten into individual entities ──────────────────────
    entities = _flatten_entities(data)
    block["entity_count"] = len(entities)

    # ── Step 3: Validate each entity ──────────────────────────────────
    for ent_data in entities:
        ent_result = _validate_entity(ent_data)
        block["entities"].append(ent_result)
        block["error_count"] += len(ent_result["errors"])
        block["warning_count"] += len(ent_result["warnings"])

    return block


def _flatten_entities(data):
    """
    Given parsed JSON-LD data, return a flat list of individual entity dicts.
    Handles:
      - A single object with @type
      - An object with @graph (array of entities)
      - A bare array of objects (less common but valid)
    """
    entities = []

    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                entities.extend(_flatten_entities(item))
        return entities

    if not isinstance(data, dict):
        return entities

    # If this object has @graph, recurse into the graph items.
    if "@graph" in data:
        graph = data["@graph"]
        if isinstance(graph, list):
            for item in graph:
                if isinstance(item, dict):
                    # Inherit @context from parent if child doesn't specify one.
                    if "@context" not in item and "@context" in data:
                        item["_inherited_context"] = data["@context"]
                    entities.extend(_flatten_entities(item))
        return entities

    # Otherwise, this object is itself an entity.
    entities.append(data)
    return entities


def _validate_entity(entity):
    """
    Validate a single schema.org entity dict.

    Returns:
        "type"     : str — the @type value (or "Unknown")
        "id"       : str or None — the @id value if present
        "name"     : str or None — a display-friendly name/headline
        "errors"   : list of str
        "warnings" : list of str
        "properties" : list of {"key": str, "status": "present"|"missing_required"|"missing_recommended"}
    """
    errors = []
    warnings = []

    # ── @context ──────────────────────────────────────────────────────
    context = entity.get("@context") or entity.get("_inherited_context")
    if not context:
        errors.append("Missing @context. Expected \"https://schema.org\".")
    elif isinstance(context, str) and "schema.org" not in context.lower():
        warnings.append(
            f"@context is \"{context}\". Expected \"https://schema.org\"."
        )

    # ── @type ─────────────────────────────────────────────────────────
    raw_type = entity.get("@type", "Unknown")
    # @type can be a string or a list (multi-typed entities).
    if isinstance(raw_type, list):
        entity_type = raw_type[0] if raw_type else "Unknown"
        display_type = ", ".join(raw_type)
    else:
        entity_type = raw_type
        display_type = raw_type

    if entity_type == "Unknown":
        errors.append("Missing @type property.")

    entity_id = entity.get("@id")

    # Try to find a human-readable name.
    display_name = (
        entity.get("name")
        or entity.get("headline")
        or entity.get("title")
        or entity_id
    )

    # ── Per-type property checks ──────────────────────────────────────
    rules = SCHEMA_PROPERTY_RULES.get(entity_type, {})
    required_props = rules.get("required", [])
    recommended_props = rules.get("recommended", [])

    property_results = []

    for prop in required_props:
        if _has_property(entity, prop):
            property_results.append({"key": prop, "status": "present"})
        else:
            property_results.append({"key": prop, "status": "missing_required"})
            errors.append(f"Missing required property \"{prop}\" for {display_type}.")

    for prop in recommended_props:
        if _has_property(entity, prop):
            property_results.append({"key": prop, "status": "present"})
        else:
            property_results.append({"key": prop, "status": "missing_recommended"})
            warnings.append(f"Recommended property \"{prop}\" is missing for {display_type}.")

    # ── Extra heuristic checks ────────────────────────────────────────
    # Check for http vs https in @context.
    if isinstance(context, str) and context == "http://schema.org":
        warnings.append(
            "@context uses \"http://schema.org\". Google recommends "
            "\"https://schema.org\"."
        )

    # Check if @id is present (helps with entity linking).
    if not entity_id and entity_type not in ("BreadcrumbList", "ItemList", "Offer", "ListItem"):
        warnings.append(
            f"No @id on this {display_type}. Adding @id improves "
            f"entity linking across blocks."
        )

    return {
        "type": display_type,
        "id": entity_id,
        "name": display_name,
        "errors": errors,
        "warnings": warnings,
        "properties": property_results,
    }


def _has_property(entity, prop):
    """
    Check whether a property is meaningfully present on an entity.
    Considers the property missing if the value is None, empty string,
    empty list, or empty dict.
    """
    val = entity.get(prop)
    if val is None:
        return False
    if isinstance(val, str) and not val.strip():
        return False
    if isinstance(val, (list, dict)) and not val:
        return False
    return True


def _trunc(text, max_len):
    """Truncate and append ellipsis if text exceeds max_len."""
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"
