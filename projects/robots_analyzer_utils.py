"""
Robots Analyzer

Core logic for fetching, parsing, and analyzing a site's robots.txt.

Returns structured data including:
  - The raw text and HTTP status of the robots.txt fetch
  - A parsed list of user-agent groups with their directives
  - Sitemap references
  - Syntax warnings and SEO-relevant issues
  - Optional path-test results against common bot user-agents
"""

import re
import time
from urllib.parse import urlparse

import requests


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REQUEST_TIMEOUT = 10  # seconds

# Well-known bot user-agents to test paths against.
COMMON_BOTS = [
    "*",
    "Googlebot",
    "Bingbot",
    "Slurp",           # Yahoo
    "DuckDuckBot",
    "Baiduspider",
    "YandexBot",
    "facebookexternalhit",
    "Twitterbot",
    "AhrefsBot",
    "SemrushBot",
    "GPTBot",
    "ChatGPT-User",
    "Google-Extended",
    "CCBot",
    "Applebot",
    "anthropic-ai",
]

# Directives we recognize.
KNOWN_DIRECTIVES = {
    "user-agent",
    "disallow",
    "allow",
    "sitemap",
    "crawl-delay",
    "host",             # Yandex extension
    "clean-param",      # Yandex extension
    "request-rate",     # Non-standard but seen in the wild
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def analyze_robots(domain, test_path=""):
    """
    Fetch and analyze the robots.txt for *domain*.

    Returns a dict:
        "domain"          : str
        "robots_url"      : str — the full URL fetched
        "fetch_time"      : float — seconds
        "status_code"     : int or None
        "fetch_error"     : str or None
        "raw_text"        : str or None — the robots.txt content
        "line_count"      : int
        "groups"          : list of group dicts (see _parse_robots)
        "sitemaps"        : list of sitemap URL strings
        "issues"          : list of {"severity": "error"|"warning"|"info", "message": str}
        "path_tests"      : list of test result dicts (if test_path provided)
        "overall"         : str — "pass", "warnings", "errors"
    """
    robots_url = f"https://{domain}/robots.txt"
    raw_text, status_code, fetch_time, fetch_error = _fetch_robots(robots_url)

    result = {
        "domain": domain,
        "robots_url": robots_url,
        "fetch_time": round(fetch_time, 3),
        "status_code": status_code,
        "fetch_error": fetch_error,
        "raw_text": raw_text,
        "line_count": 0,
        "groups": [],
        "sitemaps": [],
        "issues": [],
        "path_tests": [],
        "overall": "pass",
    }

    # ── Handle fetch failures ─────────────────────────────────────────
    if fetch_error:
        result["overall"] = "errors"
        return result

    # A 404 is not a connection error but means no robots.txt exists.
    if status_code == 404:
        result["issues"].append({
            "severity": "warning",
            "message": (
                "No robots.txt found (HTTP 404). Search engines will "
                "assume the entire site is crawlable."
            ),
        })
        result["overall"] = "warnings"
        return result

    if status_code and status_code >= 400:
        result["issues"].append({
            "severity": "error",
            "message": f"robots.txt returned HTTP {status_code}.",
        })
        result["overall"] = "errors"
        return result

    # ── Parse ─────────────────────────────────────────────────────────
    lines = raw_text.splitlines()
    result["line_count"] = len(lines)
    groups, sitemaps, parse_issues = _parse_robots(lines)
    result["groups"] = groups
    result["sitemaps"] = sitemaps
    result["issues"].extend(parse_issues)

    # ── Post-parse analysis ───────────────────────────────────────────
    result["issues"].extend(_analyze_groups(groups, sitemaps, domain))

    # ── Path testing ──────────────────────────────────────────────────
    if test_path:
        result["path_tests"] = _test_path(groups, test_path)

    # ── Overall verdict ───────────────────────────────────────────────
    if any(i["severity"] == "error" for i in result["issues"]):
        result["overall"] = "errors"
    elif any(i["severity"] == "warning" for i in result["issues"]):
        result["overall"] = "warnings"
    else:
        result["overall"] = "pass"

    return result


# ---------------------------------------------------------------------------
# Fetching
# ---------------------------------------------------------------------------


def _fetch_robots(url):
    """
    Fetch robots.txt.
    Returns (text, status_code, elapsed, error_or_None).
    """
    try:
        start = time.monotonic()
        resp = requests.get(
            url,
            timeout=REQUEST_TIMEOUT,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (compatible; BenCrittRobotsAnalyzer/1.0; "
                    "+https://www.bencritt.net/projects/robots-analyzer/)"
                ),
                "Accept": "text/plain,*/*;q=0.8",
            },
            allow_redirects=True,
        )
        elapsed = time.monotonic() - start

        # If we were redirected away from robots.txt to an HTML page,
        # the file effectively doesn't exist.
        content_type = resp.headers.get("Content-Type", "")
        if resp.status_code == 200 and "text/html" in content_type:
            return None, resp.status_code, elapsed, (
                "The server returned an HTML page instead of a plain-text "
                "robots.txt. This usually means no robots.txt exists and "
                "the server redirected to a default page."
            )

        return resp.text, resp.status_code, elapsed, None

    except requests.exceptions.Timeout:
        return None, None, REQUEST_TIMEOUT, (
            f"Request timed out after {REQUEST_TIMEOUT}s."
        )
    except requests.exceptions.ConnectionError as exc:
        err = str(exc)
        if "NameResolutionError" in err or "getaddrinfo" in err:
            return None, None, 0, f"DNS resolution failed for {urlparse(url).hostname}."
        return None, None, 0, f"Connection error: {_trunc(err, 200)}"
    except requests.exceptions.RequestException as exc:
        return None, None, 0, f"Request failed: {_trunc(str(exc), 200)}"


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def _parse_robots(lines):
    """
    Parse robots.txt lines into structured groups.

    Returns (groups, sitemaps, issues).

    Each group dict:
        "user_agents" : list of str
        "rules"       : list of {"directive": str, "path": str, "line": int}
        "crawl_delay" : float or None
    """
    groups = []
    sitemaps = []
    issues = []

    current_group = None

    for line_num, raw_line in enumerate(lines, start=1):
        # Strip BOM on first line.
        if line_num == 1:
            raw_line = raw_line.lstrip("\ufeff")

        # Remove inline comments.
        line = raw_line.split("#", 1)[0].strip()

        if not line:
            continue

        # Split on the first colon.
        if ":" not in line:
            issues.append({
                "severity": "warning",
                "message": f"Line {line_num}: Unrecognized syntax \"{_trunc(raw_line.strip(), 80)}\".",
            })
            continue

        directive_raw, _, value = line.partition(":")
        directive = directive_raw.strip().lower()
        value = value.strip()

        # ── Sitemap (can appear anywhere, outside groups) ─────────
        if directive == "sitemap":
            if value:
                sitemaps.append(value)
            else:
                issues.append({
                    "severity": "warning",
                    "message": f"Line {line_num}: Empty Sitemap directive.",
                })
            continue

        # ── Host (Yandex, outside groups) ─────────────────────────
        if directive == "host":
            continue  # Accepted but not grouped.

        # ── User-agent starts a new group ─────────────────────────
        if directive == "user-agent":
            if not value:
                issues.append({
                    "severity": "warning",
                    "message": f"Line {line_num}: Empty User-agent value.",
                })
                continue

            # If we're already building a group that only has user-agents
            # (no rules yet), this is an additional user-agent for the
            # same group (multi-UA block).
            if current_group and not current_group["rules"] and current_group["crawl_delay"] is None:
                current_group["user_agents"].append(value)
            else:
                # Start a new group.
                current_group = {
                    "user_agents": [value],
                    "rules": [],
                    "crawl_delay": None,
                }
                groups.append(current_group)
            continue

        # ── Everything below requires an active group ─────────────
        if current_group is None:
            issues.append({
                "severity": "warning",
                "message": (
                    f"Line {line_num}: Directive \"{directive_raw.strip()}\" "
                    f"appears before any User-agent."
                ),
            })
            continue

        # ── Allow / Disallow ──────────────────────────────────────
        if directive in ("allow", "disallow"):
            current_group["rules"].append({
                "directive": directive,
                "path": value,
                "line": line_num,
            })
            continue

        # ── Crawl-delay ───────────────────────────────────────────
        if directive == "crawl-delay":
            try:
                current_group["crawl_delay"] = float(value)
            except ValueError:
                issues.append({
                    "severity": "warning",
                    "message": f"Line {line_num}: Invalid Crawl-delay value \"{value}\".",
                })
            continue

        # ── Other known but non-standard directives ───────────────
        if directive in KNOWN_DIRECTIVES:
            continue

        # ── Unknown directive ─────────────────────────────────────
        issues.append({
            "severity": "warning",
            "message": (
                f"Line {line_num}: Unknown directive "
                f"\"{_trunc(directive_raw.strip(), 40)}\"."
            ),
        })

    return groups, sitemaps, issues


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------


def _analyze_groups(groups, sitemaps, domain):
    """
    Examine the parsed groups for common SEO issues.
    Returns a list of issue dicts.
    """
    issues = []

    if not groups:
        issues.append({
            "severity": "warning",
            "message": "No User-agent groups found. The file may be empty or contain only comments.",
        })
        return issues

    # Check for a wildcard (*) group.
    has_wildcard = any(
        "*" in g["user_agents"] for g in groups
    )
    if not has_wildcard:
        issues.append({
            "severity": "info",
            "message": (
                "No wildcard User-agent: * group. Only explicitly listed "
                "bots will match rules; all others will crawl freely."
            ),
        })

    # Check for Disallow: / on wildcard (blocks entire site).
    for group in groups:
        if "*" in group["user_agents"]:
            for rule in group["rules"]:
                if rule["directive"] == "disallow" and rule["path"] == "/":
                    # Check if there's a counteracting Allow.
                    has_allow = any(
                        r["directive"] == "allow" and r["path"]
                        for r in group["rules"]
                    )
                    if not has_allow:
                        issues.append({
                            "severity": "error",
                            "message": (
                                "Wildcard (*) Disallow: / blocks the ENTIRE site "
                                "from all crawlers with no Allow exceptions."
                            ),
                        })
                    else:
                        issues.append({
                            "severity": "warning",
                            "message": (
                                "Wildcard (*) Disallow: / blocks the entire site, "
                                "but some paths are re-allowed. Verify the Allow "
                                "rules cover all pages you want indexed."
                            ),
                        })

    # Check for contradictory rules within a single group.
    for group in groups:
        allow_paths = {r["path"] for r in group["rules"] if r["directive"] == "allow"}
        disallow_paths = {r["path"] for r in group["rules"] if r["directive"] == "disallow"}
        overlap = allow_paths & disallow_paths
        if overlap:
            ua_label = ", ".join(group["user_agents"])
            for path in sorted(overlap):
                issues.append({
                    "severity": "warning",
                    "message": (
                        f"User-agent {ua_label}: Path \"{path}\" is both "
                        f"Allowed and Disallowed. The longer (more specific) "
                        f"rule wins, but this is confusing."
                    ),
                })

    # Check for empty Disallow (effectively allows everything).
    for group in groups:
        empty_disallows = [
            r for r in group["rules"]
            if r["directive"] == "disallow" and r["path"] == ""
        ]
        if empty_disallows and len(group["rules"]) == len(empty_disallows):
            ua_label = ", ".join(group["user_agents"])
            issues.append({
                "severity": "info",
                "message": (
                    f"User-agent {ua_label}: Only contains empty Disallow "
                    f"directives. This explicitly allows full crawling."
                ),
            })

    # Check for AI bot blocking.
    ai_bots_blocked = []
    ai_bot_names = {"gptbot", "chatgpt-user", "google-extended", "ccbot", "anthropic-ai"}
    for group in groups:
        for ua in group["user_agents"]:
            if ua.lower() in ai_bot_names:
                has_disallow = any(
                    r["directive"] == "disallow" and r["path"]
                    for r in group["rules"]
                )
                if has_disallow:
                    ai_bots_blocked.append(ua)
    if ai_bots_blocked:
        issues.append({
            "severity": "info",
            "message": (
                f"AI crawler restrictions detected for: "
                f"{', '.join(ai_bots_blocked)}."
            ),
        })

    # Check for sitemap references.
    if not sitemaps:
        issues.append({
            "severity": "warning",
            "message": (
                "No Sitemap directive found. Including a Sitemap reference "
                "in robots.txt helps search engines discover your XML sitemap."
            ),
        })

    # Validate sitemap URLs.
    for sm in sitemaps:
        if not sm.startswith(("http://", "https://")):
            issues.append({
                "severity": "warning",
                "message": f"Sitemap \"{_trunc(sm, 80)}\" is not an absolute URL.",
            })

    # Warn about very high crawl-delay.
    for group in groups:
        if group["crawl_delay"] is not None and group["crawl_delay"] > 10:
            ua_label = ", ".join(group["user_agents"])
            issues.append({
                "severity": "warning",
                "message": (
                    f"User-agent {ua_label}: Crawl-delay of "
                    f"{group['crawl_delay']}s is very high. This may "
                    f"significantly slow indexing."
                ),
            })

    return issues


# ---------------------------------------------------------------------------
# Path Testing
# ---------------------------------------------------------------------------


def _test_path(groups, test_path):
    """
    Test whether a specific path would be allowed or disallowed for
    each of the COMMON_BOTS.

    Returns a list of dicts:
        "bot"       : str
        "result"    : "allowed" | "disallowed" | "no_match"
        "reason"    : str — the matching rule or explanation
    """
    results = []

    for bot in COMMON_BOTS:
        matching_group = _find_matching_group(groups, bot)

        if matching_group is None:
            results.append({
                "bot": bot,
                "result": "allowed",
                "reason": "No matching User-agent group (defaults to allowed).",
            })
            continue

        verdict, matched_rule = _evaluate_path(matching_group, test_path)
        results.append({
            "bot": bot,
            "result": verdict,
            "reason": matched_rule,
        })

    return results


def _find_matching_group(groups, bot_name):
    """
    Find the most specific group matching *bot_name*.
    Exact match takes priority over wildcard (*).
    """
    wildcard_group = None
    for group in groups:
        for ua in group["user_agents"]:
            if ua == "*":
                wildcard_group = group
            elif ua.lower() == bot_name.lower():
                return group
    return wildcard_group


def _evaluate_path(group, test_path):
    """
    Evaluate a path against a group's rules using standard robots.txt
    precedence: the longest matching pattern wins.  On a tie in length,
    Allow wins over Disallow.

    Returns (verdict_str, reason_str).
    """
    best_match = None
    best_length = -1

    for rule in group["rules"]:
        pattern = rule["path"]

        # Empty Disallow means "allow everything".
        if rule["directive"] == "disallow" and pattern == "":
            continue

        if _path_matches(pattern, test_path):
            pattern_len = len(pattern)
            # Longer pattern wins; on tie, Allow wins.
            if (pattern_len > best_length) or (
                pattern_len == best_length
                and rule["directive"] == "allow"
            ):
                best_match = rule
                best_length = pattern_len

    if best_match is None:
        return "allowed", "No matching rule (defaults to allowed)."

    if best_match["directive"] == "allow":
        return "allowed", f"Matched Allow: {best_match['path']} (line {best_match['line']})."
    else:
        return "disallowed", f"Matched Disallow: {best_match['path']} (line {best_match['line']})."


def _path_matches(pattern, path):
    """
    Test whether *path* matches the robots.txt *pattern*.

    Supports:
      - Prefix matching (default)
      - * wildcard (matches any sequence of characters)
      - $ anchor (must match end of path)
    """
    if not pattern:
        return False

    # Build a regex from the pattern.
    regex_parts = []
    i = 0
    while i < len(pattern):
        char = pattern[i]
        if char == "*":
            regex_parts.append(".*")
        elif char == "$" and i == len(pattern) - 1:
            regex_parts.append("$")
        else:
            regex_parts.append(re.escape(char))
        i += 1

    # If pattern doesn't end with $, it's a prefix match.
    if not pattern.endswith("$"):
        regex_parts.append(".*")

    regex_str = "^" + "".join(regex_parts)

    try:
        return bool(re.match(regex_str, path))
    except re.error:
        return False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _trunc(text, max_len):
    """Truncate and append ellipsis if text exceeds max_len."""
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"
