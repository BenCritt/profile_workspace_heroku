# projects/cookie_scan_utils.py
"""
Cookie Audit scanner (Playwright) with:
- low-memory crawling (blocks images/fonts/media, closes pages promptly)
- accurate cookie detection (context.cookies() + Set-Cookie fallback)
- per-request task isolation + queueing (no task overriding)
- progress reporting for polling endpoint
"""

from __future__ import annotations

import gc
import os
import re
import time
import uuid
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
from urllib.parse import urljoin, urlparse, urlunparse

from django.core.cache import cache

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

import tldextract

# Optional: your mem utility (safe if missing)
try:
    from .mem_utils import free_memory_aggressively  # type: ignore
except Exception:
    free_memory_aggressively = None  # type: ignore


# ----------------------------
# Defaults (tune for Heroku 512MB)
# ----------------------------

DEFAULT_MAX_PAGES = 5          # keep small for 512MB dyno; raise cautiously
DEFAULT_MAX_DEPTH = 1          # depth=1 catches typical nav/footer links
DEFAULT_WAIT_MS = 1500         # post-load wait to allow JS-set cookies
DEFAULT_TIMEOUT_MS = 20000     # page.goto timeout
DEFAULT_HEADLESS = True
DEFAULT_IGNORE_HTTPS_ERRORS = False

# Hard wall-clock budget per visited URL (navigation + wait + link extraction).
# If a page is slow/heavy, we skip link extraction and move on.
DEFAULT_PER_PAGE_BUDGET_MS = 8000

# Block heavy resources to reduce memory; KEEP scripts/xhr so cookie banners & JS cookies still work.
BLOCKED_RESOURCE_TYPES = {"image", "media", "font", "stylesheet"}

# Don’t let Set-Cookie capture grow without bound (memory safety)
MAX_SET_COOKIE_OBSERVATIONS = 400

# Truncate very long Set-Cookie lines to avoid storing large payloads
MAX_SET_COOKIE_CHARS = 1024

# Link extraction cap per page (memory/time safety)
MAX_LINKS_PER_PAGE = 200


# ----------------------------
# Task store + queueing (single dyno safe)
# ----------------------------

_TASK_TTL_SECONDS = 15 * 60  # 15 minutes
_TASK_KEY_PREFIX = "cookie_audit:task:"
_QUEUE_KEY = "cookie_audit:queue"
_ACTIVE_KEY = "cookie_audit:active_task_id"
_LOCK = threading.Lock()

# Concurrency on a 512MB / 1-dyno plan should remain 1 for Playwright scans.
# Extra concurrent scans = extra Chromium processes = OOM.
MAX_CONCURRENT_SCANS = 1

# Cookie identity: (name, effective_domain, path)
CookieKey = Tuple[str, str, str]

def make_cookie_key(
    name: str,
    domain: str,
    path: str,
    *,
    host_fallback: str = "",
) -> CookieKey:
    n = (name or "").strip()
    d = (domain or "").lstrip(".").lower()
    h = (host_fallback or "").lstrip(".").lower()
    p = (path or "/") or "/"
    if p and not p.startswith("/"):
        p = "/" + p

    effective_domain = d or h
    return (n, effective_domain, p)

def merge_cookie(existing: ParsedCookie, incoming: ParsedCookie) -> None:
    """
    Merge 'incoming' into 'existing' without losing info.
    Keep existing as the canonical object.
    """

    # Fill Expires if we don't have one yet
    if (not existing.expires_human) and incoming.expires_human:
        existing.expires_human = incoming.expires_human

    # Prefer "true" for boolean flags if either saw it
    existing.secure = bool(existing.secure or incoming.secure)
    existing.httpOnly = bool(existing.httpOnly or incoming.httpOnly)

    # Fill SameSite if missing
    if (not existing.sameSite) and incoming.sameSite:
        existing.sameSite = incoming.sameSite

    # Party: if either classifies as third-party, keep that
    if existing.party != "third-party" and incoming.party == "third-party":
        existing.party = "third-party"

def _task_key(task_id: str) -> str:
    return f"{_TASK_KEY_PREFIX}{task_id}"


def get_cookie_audit_task(task_id: str) -> Optional[Dict[str, Any]]:
    return cache.get(_task_key(task_id))


def _set_task(task_id: str, data: Dict[str, Any]) -> None:
    cache.set(_task_key(task_id), data, timeout=_TASK_TTL_SECONDS)


def _update_task(task_id: str, **patch: Any) -> None:
    task = get_cookie_audit_task(task_id) or {}
    task.update(patch)
    _set_task(task_id, task)


def _get_queue() -> List[str]:
    q = cache.get(_QUEUE_KEY)
    return list(q) if isinstance(q, list) else []


def _set_queue(q: List[str]) -> None:
    cache.set(_QUEUE_KEY, q, timeout=_TASK_TTL_SECONDS)


def _queue_position(task_id: str) -> Optional[int]:
    q = _get_queue()
    if task_id in q:
        return q.index(task_id) + 1
    return None


def start_cookie_audit_task(
    url: str,
    *,
    max_pages: int = DEFAULT_MAX_PAGES,
    max_depth: int = DEFAULT_MAX_DEPTH,
    wait_ms: int = DEFAULT_WAIT_MS,
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
    per_page_budget_ms: int = DEFAULT_PER_PAGE_BUDGET_MS,  # ✅ ADD
    headless: bool = DEFAULT_HEADLESS,
    ignore_https_errors: bool = DEFAULT_IGNORE_HTTPS_ERRORS,
) -> str:
    task_id = str(uuid.uuid4())

    params = {
        "start_url": normalize_url(url),
        "max_pages": int(max_pages),
        "max_depth": int(max_depth),
        "wait_ms": int(wait_ms),
        "timeout_ms": int(timeout_ms),
        "per_page_budget_ms": int(per_page_budget_ms),  # ✅ ADD
        "headless": bool(headless),
        "ignore_https_errors": bool(ignore_https_errors),
    }

    _set_task(
        task_id,
        {
            "id": task_id,
            "state": "queued",
            "created_at": time.time(),
            "params": params,
            "progress": {
                "visited": 0,
                "max_pages": params["max_pages"],
                "current_url": "",
                "percent": 0,
            },
        },
    )

    with _LOCK:
        q = _get_queue()
        q.append(task_id)
        _set_queue(q)

    _kick_queue()
    return task_id


def _kick_queue() -> None:
    """
    Start the next queued job if we have capacity.
    """
    with _LOCK:
        active = cache.get(_ACTIVE_KEY)
        if active:
            return  # already running (concurrency=1)

        q = _get_queue()
        if not q:
            return

        next_id = q.pop(0)
        _set_queue(q)
        cache.set(_ACTIVE_KEY, next_id, timeout=_TASK_TTL_SECONDS)

        _update_task(
            next_id,
            state="running",
            started_at=time.time(),
        )

    # Run scan outside lock
    threading.Thread(target=_run_task, args=(next_id,), daemon=True).start()


def _finish_task(task_id: str) -> None:
    with _LOCK:
        active = cache.get(_ACTIVE_KEY)
        if active == task_id:
            cache.delete(_ACTIVE_KEY)
    _kick_queue()


def _run_task(task_id: str) -> None:
    task = get_cookie_audit_task(task_id) or {}
    params = task.get("params") or {}

    try:
        def progress_cb(progress: Dict[str, Any]) -> None:
            # merge progress into task safely
            cur = (get_cookie_audit_task(task_id) or {}).get("progress") or {}
            cur.update(progress or {})
            _update_task(task_id, progress=cur)

        results = scan_site_for_cookies(
            start_url=params.get("start_url", ""),
            max_pages=int(params.get("max_pages", DEFAULT_MAX_PAGES)),
            max_depth=int(params.get("max_depth", DEFAULT_MAX_DEPTH)),
            wait_ms=int(params.get("wait_ms", DEFAULT_WAIT_MS)),
            timeout_ms=int(params.get("timeout_ms", DEFAULT_TIMEOUT_MS)),
            per_page_budget_ms=int(params.get("per_page_budget_ms", DEFAULT_PER_PAGE_BUDGET_MS)),  # ✅ ADD
            headless=bool(params.get("headless", DEFAULT_HEADLESS)),
            ignore_https_errors=bool(params.get("ignore_https_errors", DEFAULT_IGNORE_HTTPS_ERRORS)),
            progress_callback=progress_cb,
        )

        _update_task(
            task_id,
            state="done",
            finished_at=time.time(),
            results=results,
            progress={
                "visited": results["summary"]["visited_urls"],
                "max_pages": results["summary"]["max_pages"],
                "current_url": "",
                "percent": 100,
            },
        )

    except Exception as e:
        _update_task(
            task_id,
            state="error",
            finished_at=time.time(),
            error=str(e),
        )
    finally:
        try:
            if free_memory_aggressively:
                free_memory_aggressively()
            gc.collect()
        except Exception:
            pass
        _finish_task(task_id)


# ----------------------------
# URL + domain helpers
# ----------------------------

_TLDX = tldextract.TLDExtract(cache_dir="/tmp/tldextract", suffix_list_urls=None)


def normalize_url(raw: str) -> str:
    raw = (raw or "").strip()
    if not raw:
        return raw
    if not re.match(r"^https?://", raw, flags=re.I):
        raw = "https://" + raw
    return raw


def _host_from_url(url_or_host: str) -> str:
    s = (url_or_host or "").strip()
    if "://" in s:
        return (urlparse(s).hostname or "").lower()
    return s.split("/")[0].split(":")[0].lower()


def registrable_domain(url_or_host: str) -> str:
    host = _host_from_url(url_or_host)
    if not host:
        return ""
    ext = _TLDX(host)
    return ext.registered_domain or host


def is_internal_url(candidate_url: str, base_reg_domain: str) -> bool:
    try:
        p = urlparse(candidate_url)
        if p.scheme not in ("http", "https"):
            return False
        cand_reg = registrable_domain(p.hostname or "")
        return bool(cand_reg) and cand_reg == base_reg_domain
    except Exception:
        return False


def canonicalize_for_visit(url: str) -> str:
    """
    Remove fragments; keep query (some sites gate cookie banners by query).
    """
    p = urlparse(url)
    return urlunparse((p.scheme, p.netloc, p.path, p.params, p.query, ""))


def extract_links_from_page(
    page,
    current_url: str,
    base_reg_domain: str,
    *,
    deadline_monotonic: Optional[float] = None,
) -> List[str]:
    """
    Fast link extraction that:
    - avoids eval_on_selector_all (can be slow on huge DOMs)
    - respects an optional monotonic() deadline
    """
    out: List[str] = []
    seen: Set[str] = set()

    try:
        els = page.query_selector_all("a[href]") or []
    except Exception:
        return []

    # Hard cap how much DOM we even look at (safety on mega-pages)
    # (MAX_LINKS_PER_PAGE is your output cap; this is an input cap.)
    scan_cap = min(len(els), MAX_LINKS_PER_PAGE * 4)

    for i in range(scan_cap):
        if deadline_monotonic is not None and time.monotonic() >= deadline_monotonic:
            break

        el = els[i]
        try:
            href = (el.get_attribute("href") or "").strip()
        except Exception:
            continue

        if not href:
            continue

        abs_url = href if re.match(r"^https?://", href, flags=re.I) else urljoin(current_url, href)
        abs_url = canonicalize_for_visit(abs_url)

        if abs_url in seen:
            continue
        seen.add(abs_url)

        if is_internal_url(abs_url, base_reg_domain):
            out.append(abs_url)
            if len(out) >= MAX_LINKS_PER_PAGE:
                break

    return out

# ----------------------------
# Cookie parsing + enrichment
# ----------------------------

@dataclass
class ParsedCookie:
    name: str
    domain: str
    path: str = "/"
    expires_human: str = ""
    secure: bool = False
    httpOnly: bool = False
    sameSite: str = ""
    party: str = "first-party"
    cookie_type: str = "Unknown"
    purpose: str = "Unknown"


def parse_set_cookie_line(line: str, *, host_fallback: str = "") -> Optional[ParsedCookie]:
    """
    Parse a Set-Cookie header line (without storing value).
    """
    if not line:
        return None
    parts = [p.strip() for p in line.split(";") if p.strip()]
    if not parts:
        return None

    # name=value is first
    nv = parts[0]
    if "=" not in nv:
        return None
    name = nv.split("=", 1)[0].strip()
    if not name:
        return None

    attrs = {}
    for p in parts[1:]:
        if "=" in p:
            k, v = p.split("=", 1)
            attrs[k.strip().lower()] = v.strip()
        else:
            attrs[p.strip().lower()] = True

    domain = str(attrs.get("domain") or "").lstrip(".").lower()
    if not domain and host_fallback:
        domain = host_fallback.lstrip(".").lower()
    path = str(attrs.get("path") or "/")
    secure = bool(attrs.get("secure") is True)
    http_only = bool(attrs.get("httponly") is True)
    same_site = str(attrs.get("samesite") or "")

    expires_human = ""
    # We keep it simple: show Expires/Max-Age raw-ish (no heavy date parsing)
    if "expires" in attrs:
        expires_human = str(attrs["expires"])
    elif "max-age" in attrs:
        expires_human = f"Max-Age={attrs['max-age']}"

    return ParsedCookie(
        name=name,
        domain=domain,
        path=path,
        expires_human=expires_human,
        secure=secure,
        httpOnly=http_only,
        sameSite=same_site,
    )


def infer_cookie_type_and_purpose(cookie_name: str) -> Tuple[str, str]:
    """
    Very lightweight heuristic. Extend as you like.
    """
    n = (cookie_name or "").lower()

    if any(k in n for k in ("_ga", "_gid", "_gat", "gtm", "gcl_", "utm")):
        return ("Analytics", "Analytics / measurement")
    if any(k in n for k in ("session", "sid", "phpsessid", "jsessionid")):
        return ("Necessary", "Session management")
    if any(k in n for k in ("csrf", "xsrf")):
        return ("Necessary", "Security (CSRF protection)")
    if any(k in n for k in ("consent", "cookie", "cmp", "optanon", "onetrust")):
        return ("Necessary", "Consent preferences")
    return ("Unknown", "Unknown")


def to_ui_cookie(pc: ParsedCookie) -> Dict[str, Any]:
    ctype, purpose = infer_cookie_type_and_purpose(pc.name)
    return {
        "name": pc.name,
        "domain": pc.domain or "",
        "expires_human": pc.expires_human or "",
        "secure": bool(pc.secure),
        "httpOnly": bool(pc.httpOnly),
        "sameSite": pc.sameSite or "",
        "party": pc.party,
        "cookie_type": ctype,
        "purpose": purpose,
    }


# ----------------------------
# Playwright launch (Heroku-safe)
# ----------------------------

import glob
import os
from typing import Any, Dict, Optional


def _find_chromium_executable() -> Optional[str]:
    """
    Try to locate a Chromium/Chrome binary in common Heroku buildpack locations.
    Returns a full path if found, otherwise None.
    """
    # 1) Preferred: explicit env var (Thomas-Boi buildpack often sets this)
    exe = (os.getenv("CHROMIUM_EXECUTABLE_PATH") or "").strip()
    if exe and os.path.exists(exe):
        return exe

    # 2) If PLAYWRIGHT_BROWSERS_PATH is set, search inside it
    bases = []
    pwp = (os.getenv("PLAYWRIGHT_BROWSERS_PATH") or "").strip()
    if pwp:
        bases.append(pwp)

    # 3) Common Heroku locations used by Playwright buildpacks
    bases.extend([
        "/app/.playwright",
        "/app/.cache/ms-playwright",
        "/app/.cache/playwright",
    ])

    # Look for the common binaries Playwright uses
    patterns = [
        "**/chrome-headless-shell",      # newer Playwright headless shell
        "**/chrome",                    # chrome-linux/chrome
        "**/Chromium.app/**/Chromium",  # (not for Heroku, but harmless)
    ]

    for base in bases:
        if not base or not os.path.exists(base):
            continue
        for pat in patterns:
            hits = glob.glob(os.path.join(base, pat), recursive=True)
            # Pick the first real file that is executable-ish
            for h in hits:
                if os.path.isfile(h):
                    return h

    return None


def _launch_chromium(p, *, headless: bool) -> Any:
    """
    Heroku-friendly + lower-memory launch:
    - Prefer buildpack-installed Chromium when available.
    - Fall back to Playwright-managed Chromium for local dev (if installed).
    """
    exe = _find_chromium_executable()

    args = [
        "--no-sandbox",
        "--disable-setuid-sandbox",
        "--disable-dev-shm-usage",  # IMPORTANT on Heroku
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
    ]

    launch_kwargs: Dict[str, Any] = {
        "headless": bool(headless),
        "args": args,
        "chromium_sandbox": False,
    }

    if exe:
        launch_kwargs["executable_path"] = exe
    else:
        # On Heroku, we *expect* a buildpack-installed browser.
        # If we didn't find one, fail with a clearer message than Playwright's.
        if os.getenv("DYNO"):
            raise RuntimeError(
                "No Chromium executable found on Heroku. "
                "Your Playwright buildpack likely did not install browsers, or the cache is stale. "
                "Ensure PLAYWRIGHT_BUILDPACK_BROWSERS=chromium is set, "
                "and that the playwright buildpack is installed, then purge cache + redeploy."
            )

    # Encourage temp files to go to /tmp
    os.environ.setdefault("TMPDIR", "/tmp")
    os.environ.setdefault("TEMP", "/tmp")
    os.environ.setdefault("TMP", "/tmp")

    return p.chromium.launch(**launch_kwargs)

from datetime import datetime, timezone

def _expires_human_from_playwright(expires_val) -> str:
    """
    Playwright cookie 'expires' can be:
      - -1 / 0 / None  => session cookie (or not provided)
      - number         => unix epoch seconds
      - sometimes a string (depending on wrappers/serialization)
    Returns a small, human-friendly string with minimal overhead.
    """
    if expires_val is None:
        return ""

    # Coerce to float safely
    try:
        exp = float(expires_val)
    except (TypeError, ValueError):
        # If it's some unexpected type, don't crash; keep it blank
        return ""

    # Session cookies are often represented as 0 or -1
    if exp <= 0:
        return "Session"

    # Convert epoch seconds to a stable UTC string
    try:
        return datetime.fromtimestamp(exp, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
    except (OverflowError, OSError, ValueError):
        # Out-of-range epoch
        return ""


def _harvest_context_cookies_once(
    context,
    *,
    cookie_jar: Dict[CookieKey, "ParsedCookie"],
    base_reg_domain: str,
    host_fallback: str = "",
) -> None:
    """
    Pull cookies from the Playwright context exactly once and add them to cookie_jar.

    Keys by (name, effective_domain, path) where effective_domain is:
      - cookie domain if present
      - otherwise host_fallback (host-only cookies)
    """
    try:
        all_cookies = context.cookies()
    except Exception:
        return

    host_fallback = (host_fallback or "").lstrip(".").lower()

    for c in all_cookies:
        try:
            name = (c.get("name") or "").strip()
            if not name:
                continue

            raw_domain = (c.get("domain") or "")
            domain = raw_domain.lstrip(".").lower()

            raw_path = c.get("path")
            path = str(raw_path) if raw_path else "/"
            if not path.startswith("/"):
                path = "/" + path

            # Build a stable key and skip if already present
            key = make_cookie_key(name, domain, path, host_fallback=host_fallback)
            if key in cookie_jar:
                continue

            # Party classification based on effective domain (domain or host fallback)
            effective_domain = (domain or host_fallback).lstrip(".").lower()
            party = "first-party"
            if effective_domain and registrable_domain(effective_domain) != base_reg_domain:
                party = "third-party"

            expires_human = _expires_human_from_playwright(c.get("expires"))

            pc = ParsedCookie(
                name=name,
                domain=effective_domain,  # store effective domain so host-only cookies are usable
                path=path,
                expires_human=expires_human,
                secure=bool(c.get("secure")),
                httpOnly=bool(c.get("httpOnly")),
                sameSite=str(c.get("sameSite") or ""),
                party=party,
            )

            cookie_jar[key] = pc

        except Exception:
            # Defensive: don't let one malformed cookie crash the scan
            continue


# ----------------------------
# Main scanner (single implementation)
# ----------------------------
def scan_site_for_cookies(
    *,
    start_url: str,
    max_pages: int = DEFAULT_MAX_PAGES,
    max_depth: int = DEFAULT_MAX_DEPTH,
    wait_ms: int = DEFAULT_WAIT_MS,
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
    per_page_budget_ms: int = DEFAULT_PER_PAGE_BUDGET_MS,  # ✅ ADD
    headless: bool = DEFAULT_HEADLESS,
    ignore_https_errors: bool = DEFAULT_IGNORE_HTTPS_ERRORS,
    progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> Dict[str, Any]:
    """
    Crawl up to max_pages within max_depth and return a cookie report.
    Enforces a HARD wall-clock budget per visited URL so one page can't hang the crawl.
    """
    start_url = normalize_url(start_url)
    if not start_url:
        raise ValueError("URL is required")

    max_pages = max(1, int(max_pages))
    max_depth = max(0, int(max_depth))
    per_page_budget_ms = max(1000, int(per_page_budget_ms))  # never < 1s

    base_reg_domain = registrable_domain(start_url)
    visited: Set[str] = set()
    queue: List[Tuple[str, int]] = [(canonicalize_for_visit(start_url), 0)]

    cookie_jar: Dict[CookieKey, ParsedCookie] = {}
    set_cookie_observations: List[Tuple[str, str]] = []
    set_cookie_seen: Set[Tuple[str, str]] = set()

    def emit_progress(current_url: str) -> None:
        if not progress_callback:
            return
        v = len(visited)
        pct = int(min(100, (v / max_pages) * 100)) if max_pages else 0
        progress_callback(
            {"visited": v, "max_pages": max_pages, "current_url": current_url or "", "percent": pct}
        )

    with sync_playwright() as pw:
        browser = _launch_chromium(pw, headless=headless)
        context = browser.new_context(ignore_https_errors=ignore_https_errors)

        def _route_handler(route):
            try:
                if route.request.resource_type in BLOCKED_RESOURCE_TYPES:
                    return route.abort()
            except Exception:
                pass
            return route.continue_()

        context.route("**/*", _route_handler)

        def _on_response(resp):
            if len(set_cookie_observations) >= MAX_SET_COOKIE_OBSERVATIONS:
                return
            try:
                header_val = resp.header_value("set-cookie")
            except Exception:
                return
            if not header_val:
                return

            host = (urlparse(resp.url).hostname or "").lower()
            try:
                for raw_line in header_val.splitlines():
                    line = (raw_line or "").strip()
                    if not line:
                        continue

                    short_line = line[:MAX_SET_COOKIE_CHARS]
                    seen_key = (short_line, host)
                    if seen_key in set_cookie_seen:
                        continue

                    set_cookie_seen.add(seen_key)
                    set_cookie_observations.append(seen_key)

                    if len(set_cookie_observations) >= MAX_SET_COOKIE_OBSERVATIONS:
                        break
            except Exception:
                return

        context.on("response", _on_response)

        try:
            page = context.new_page()
            # Keep defaults sane; we still pass explicit timeouts to goto.
            page.set_default_navigation_timeout(int(timeout_ms))

            try:
                while queue and len(visited) < max_pages:
                    url, depth = queue.pop(0)
                    url = canonicalize_for_visit(url)

                    if url in visited or depth > max_depth:
                        continue

                    visited.add(url)
                    emit_progress(url)

                    # ✅ hard deadline for this URL
                    deadline = time.monotonic() + (per_page_budget_ms / 1000.0)

                    def remaining_ms() -> int:
                        return int(max(0.0, (deadline - time.monotonic()) * 1000))

                    try:
                        nav_timeout = min(int(timeout_ms), remaining_ms())
                        if nav_timeout <= 0:
                            continue

                        # ✅ commit returns earlier than domcontentloaded on heavy SPAs
                        page.goto(url, wait_until="commit", timeout=nav_timeout)

                        # small post-load wait (but never beyond the budget)
                        if wait_ms:
                            wm = min(int(wait_ms), remaining_ms())
                            if wm > 0:
                                page.wait_for_timeout(wm)

                        # best-effort: stop runaway network/JS activity
                        try:
                            page.evaluate("() => { try { window.stop && window.stop(); } catch(e) {} }")
                        except Exception:
                            pass

                        # only extract links if we have time left
                        if depth < max_depth and len(visited) < max_pages and remaining_ms() >= 250:
                            links = extract_links_from_page(
                                page,
                                url,
                                base_reg_domain,
                                deadline_monotonic=deadline,
                            )
                            for link in links:
                                if link not in visited and len(queue) < (max_pages * 3):
                                    queue.append((link, depth + 1))

                    except PlaywrightTimeoutError:
                        # ✅ timeout = skip this URL, keep crawling
                        pass
                    except Exception:
                        # ✅ never let a single page crash the scan
                        pass
                    finally:
                        try:
                            page.goto("about:blank", wait_until="commit", timeout=1000)
                        except Exception:
                            pass

                    try:
                        if free_memory_aggressively:
                            free_memory_aggressively()
                        gc.collect()
                    except Exception:
                        pass

                _harvest_context_cookies_once(
                    context,
                    cookie_jar=cookie_jar,
                    base_reg_domain=base_reg_domain,
                    host_fallback=_host_from_url(start_url),
                )

            finally:
                try:
                    page.close()
                except Exception:
                    pass

        finally:
            try:
                context.close()
            except Exception:
                pass
            try:
                browser.close()
            except Exception:
                pass

    # Merge Set-Cookie observations
    for line, host in set_cookie_observations:
        pc = parse_set_cookie_line(line, host_fallback=host)
        if not pc:
            continue

        if pc.domain and registrable_domain(pc.domain) != base_reg_domain:
            pc.party = "third-party"
        else:
            pc.party = "first-party"

        key = make_cookie_key(pc.name, pc.domain, pc.path, host_fallback=host)
        if key in cookie_jar:
            merge_cookie(cookie_jar[key], pc)
        else:
            cookie_jar[key] = pc

    cookies_out = [to_ui_cookie(pc) for pc in cookie_jar.values()]
    cookies_out.sort(key=lambda x: (x.get("party", ""), x.get("domain", ""), x.get("name", "")))

    return {
        "summary": {
            "base_registrable_domain": base_reg_domain,
            "visited_urls": len(visited),
            "max_pages": max_pages,
            "cookies_detected_total": len(cookies_out),
        },
        "cookies": cookies_out,
    }
