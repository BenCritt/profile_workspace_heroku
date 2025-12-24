# projects/cookie_scan_utils.py
"""
Cookie Audit scanner (Playwright) with:
- low-memory crawling (blocks images/fonts/media, closes pages promptly)
- accurate cookie detection (context.cookies() + Set-Cookie + document.cookie fallback)
- per-request task isolation + queueing (no task overriding)
- progress reporting for polling endpoint
- Enforces a hard RSS wall (defaults to 250 MiB) and returns partial results immediately on breach.
"""

from __future__ import annotations

import gc
import glob
import os
import re
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from http.cookies import SimpleCookie
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
from urllib.parse import urljoin, urlparse, urlunparse

import tldextract
from django.core.cache import cache
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

# Optional: your mem utility (safe if missing)
try:
    from .mem_utils import free_memory_aggressively  # type: ignore
except Exception:
    free_memory_aggressively = None  # type: ignore


# ----------------------------
# Defaults (tune for Heroku 512MB)
# ----------------------------

DEFAULT_MAX_PAGES = 5
DEFAULT_MAX_DEPTH = 1
DEFAULT_WAIT_MS = 10000
DEFAULT_TIMEOUT_MS = 15000
DEFAULT_HEADLESS = True
DEFAULT_IGNORE_HTTPS_ERRORS = False

# Early-exit tuning (safe defaults)
# NOTE: cookie_early_exit_count is treated as "new cookies seen on THIS page"
DEFAULT_COOKIE_EARLY_EXIT_COUNT = 50      # stop waiting once we have this many NEW cookies for this page
DEFAULT_COOKIE_STABLE_ROUNDS = 1          # stop waiting once cookie count is unchanged this many steps
DEFAULT_COOKIE_WAIT_STEP_MS = 250         # polling step
DEFAULT_MIN_WAIT_MS = 200                 # always wait at least this long (best-effort) after DOMContentLoaded
DEFAULT_MAX_COOKIE_WAIT_MS = 600          # cap for cookie-wait loop (can be <= wait_ms)
DEFAULT_SKIP_LINKS_ON_EARLY_EXIT = True   # optional (we only skip links if out of time/memory)

# Hard wall-clock budget per visited URL (navigation + wait + link extraction).
# If a page is slow/heavy, we skip link extraction and move on.
DEFAULT_PER_PAGE_BUDGET_MS = 3500

# Block heavy resources to reduce memory; KEEP scripts/xhr so cookie banners & JS cookies still work.
BLOCKED_RESOURCE_TYPES = {"image", "media", "font", "stylesheet"}

# Don’t let Set-Cookie capture grow without bound (memory safety)
MAX_SET_COOKIE_OBSERVATIONS = 400

# Truncate very long Set-Cookie lines to avoid storing large payloads
MAX_SET_COOKIE_CHARS = 1024

# Link extraction cap per page (memory/time safety)
MAX_LINKS_PER_PAGE = 50


# ----------------------------
# Extra “obviously-static” URL blocking (helps reduce noise)
# ----------------------------

STATIC_PATH_PREFIXES = (
    "/static/",
    "/media/",
)
STATIC_EXACT_PATHS = (
    "/site.webmanifest",
    "/service-worker.js",
)
STATIC_FILE_EXTENSIONS = (
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".ico",
    ".css", ".map",
    ".woff", ".woff2", ".ttf", ".eot", ".otf",
)


# ----------------------------
# Task store + queueing (single dyno safe)
# ----------------------------

_TASK_TTL_SECONDS = 5 * 60  # 5 minutes
_TASK_KEY_PREFIX = "cookie_audit:task:"
_QUEUE_KEY = "cookie_audit:queue"
_ACTIVE_KEY = "cookie_audit:active_task_id"
_LOCK = threading.Lock()

# Concurrency on a 512MB / 1-dyno plan should remain 1 for Playwright scans.
MAX_CONCURRENT_SCANS = 1

# Hard RSS safety wall (MiB). Tune to 440–460 as you prefer.
DEFAULT_MAX_RSS_MB = 250


def get_rss_mb() -> Optional[float]:
    """
    Resident Set Size (RSS) in MiB, read from /proc/self/status (Linux).
    Returns None if not available.
    """
    try:
        with open("/proc/self/status", "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                # Example: "VmRSS:\t  123456 kB"
                if line.startswith("VmRSS:"):
                    parts = line.split()
                    if len(parts) >= 2:
                        kb = float(parts[1])
                        return kb / 1024.0
    except Exception:
        return None
    return None


class MemoryWallHit(RuntimeError):
    def __init__(self, rss_mb: float):
        super().__init__(f"Memory wall hit: RSS {rss_mb:.1f} MiB")
        self.rss_mb = rss_mb


# ----------------------------
# Cookie modeling + parsing
# ----------------------------

CookieKey = Tuple[str, str, str]  # (name, effective_domain, path)


@dataclass
class ParsedCookie:
    name: str
    domain: str
    path: str
    expires_human: str = ""
    secure: bool = False
    httpOnly: bool = False
    sameSite: str = ""
    party: str = "first-party"  # "first-party" | "third-party"

    # Optional provenance / debugging (keep small)
    source: str = ""  # e.g. "context.cookies", "set-cookie", "document.cookie"


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


# Alias: some callers expect cookie_key(...).
def cookie_key(name: str, domain: str, path: str, *, host_fallback: str = "") -> CookieKey:
    return make_cookie_key(name, domain, path, host_fallback=host_fallback)


def merge_cookie(existing: ParsedCookie, incoming: ParsedCookie) -> ParsedCookie:
    """
    Merge 'incoming' into 'existing' without losing info.
    Keep existing as the canonical object.
    """
    if (not existing.expires_human) and incoming.expires_human:
        existing.expires_human = incoming.expires_human

    existing.secure = bool(existing.secure or incoming.secure)
    existing.httpOnly = bool(existing.httpOnly or incoming.httpOnly)

    if (not existing.sameSite) and incoming.sameSite:
        existing.sameSite = incoming.sameSite

    if existing.party != "third-party" and incoming.party == "third-party":
        existing.party = "third-party"

    if (not existing.source) and incoming.source:
        existing.source = incoming.source

    return existing


def _expires_human_from_playwright(expires_val: Any) -> str:
    try:
        if expires_val in (None, "", -1, 0):
            return ""
        ts = float(expires_val)
        if ts <= 0:
            return ""
        return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
    except Exception:
        return ""


def parse_set_cookie_line(set_cookie_line: str) -> List[ParsedCookie]:
    line = (set_cookie_line or "").strip()
    if not line:
        return []

    if len(line) > MAX_SET_COOKIE_CHARS:
        line = line[:MAX_SET_COOKIE_CHARS] + "…"

    sc = SimpleCookie()
    try:
        sc.load(line)
    except Exception:
        return []

    out: List[ParsedCookie] = []
    for name, morsel in sc.items():
        secure = "secure" in morsel.keys()
        httponly = "httponly" in morsel.keys()

        path = morsel["path"] or "/"
        domain = (morsel["domain"] or "").lstrip(".").lower()
        same_site = morsel["samesite"] or ""
        expires = morsel["expires"] or ""

        out.append(
            ParsedCookie(
                name=name,
                domain=domain,
                path=path,
                expires_human=str(expires or ""),
                secure=bool(secure),
                httpOnly=bool(httponly),
                sameSite=str(same_site or ""),
                source="set-cookie",
            )
        )
    return out


def parse_set_cookie_header(header_value: str) -> List[ParsedCookie]:
    if not header_value:
        return []

    lines: List[str] = []
    for raw in str(header_value).splitlines():
        raw = raw.strip()
        if raw:
            lines.append(raw)

    out: List[ParsedCookie] = []
    for line in lines:
        out.extend(parse_set_cookie_line(line))
    return out


def _harvest_document_cookie(page) -> List[ParsedCookie]:
    try:
        cookie_str = page.evaluate("document.cookie")
    except Exception:
        return []

    cookie_str = (cookie_str or "").strip()
    if not cookie_str:
        return []

    out: List[ParsedCookie] = []
    for part in cookie_str.split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        name, _val = part.split("=", 1)
        name = name.strip()
        if not name:
            continue
        out.append(ParsedCookie(name=name, domain="", path="/", source="document.cookie"))
    return out


# ----------------------------
# Task store helpers
# ----------------------------

def _task_key(task_id: str) -> str:
    return f"{_TASK_KEY_PREFIX}{task_id}"


def get_cookie_audit_task(task_id: str) -> Optional[Dict[str, Any]]:
    return cache.get(_task_key(task_id))


def set_cookie_audit_task(task_id: str, data: Dict[str, Any]) -> None:
    if not isinstance(data, dict):
        raise ValueError("Task data must be a dict")
    cache.set(_task_key(task_id), data, timeout=_TASK_TTL_SECONDS)


def delete_cookie_audit_task(task_id: str) -> None:
    try:
        with _LOCK:
            q = _get_queue()
            if task_id in q:
                q = [x for x in q if x != task_id]
                _set_queue(q)

            active = cache.get(_ACTIVE_KEY)
            if active == task_id:
                cache.delete(_ACTIVE_KEY)

        cache.delete(_task_key(task_id))
    except Exception:
        pass


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
    per_page_budget_ms: int = DEFAULT_PER_PAGE_BUDGET_MS,
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
        "per_page_budget_ms": int(per_page_budget_ms),
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
            "progress": {"visited": 0, "max_pages": params["max_pages"], "current_url": "", "percent": 0},
        },
    )

    with _LOCK:
        q = _get_queue()
        q.append(task_id)
        _set_queue(q)

    _kick_queue()
    return task_id


def _kick_queue() -> None:
    with _LOCK:
        active = cache.get(_ACTIVE_KEY)
        if active:
            return

        q = _get_queue()
        if not q:
            return

        next_id = q.pop(0)
        _set_queue(q)
        cache.set(_ACTIVE_KEY, next_id, timeout=_TASK_TTL_SECONDS)
        _update_task(next_id, state="running", started_at=time.time())

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
            cur = (get_cookie_audit_task(task_id) or {}).get("progress") or {}
            cur.update(progress or {})
            _update_task(task_id, progress=cur)

        results = scan_site_for_cookies(
            start_url=params.get("start_url", ""),
            max_pages=int(params.get("max_pages", DEFAULT_MAX_PAGES)),
            max_depth=int(params.get("max_depth", DEFAULT_MAX_DEPTH)),
            wait_ms=int(params.get("wait_ms", DEFAULT_WAIT_MS)),
            timeout_ms=int(params.get("timeout_ms", DEFAULT_TIMEOUT_MS)),
            per_page_budget_ms=int(params.get("per_page_budget_ms", DEFAULT_PER_PAGE_BUDGET_MS)),
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
        _update_task(task_id, state="error", finished_at=time.time(), error=str(e))
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
    p = urlparse(url)
    return urlunparse((p.scheme, p.netloc, p.path, p.params, p.query, ""))


def _looks_like_static_url(url: str) -> bool:
    try:
        p = urlparse(url)
        path = (p.path or "").lower()
        if path in STATIC_EXACT_PATHS:
            return True
        if any(path.startswith(prefix) for prefix in STATIC_PATH_PREFIXES):
            return True
        if path.startswith("/favicon"):
            return True
        if any(path.endswith(ext) for ext in STATIC_FILE_EXTENSIONS):
            return True
        return False
    except Exception:
        return False


def extract_links_from_page(page, current_url: str, base_reg_domain: str, *, deadline_monotonic: Optional[float] = None) -> List[str]:
    out: List[str] = []
    seen: Set[str] = set()

    try:
        els = page.query_selector_all("a[href]") or []
    except Exception:
        return []

    scan_cap = min(len(els), MAX_LINKS_PER_PAGE * 4)

    for i in range(scan_cap):
        if deadline_monotonic is not None and time.monotonic() >= deadline_monotonic:
            break

        el = els[i]
        try:
            href = el.get_attribute("href")
        except Exception:
            continue

        href = (href or "").strip()
        if not href or href.startswith("#") or href.lower().startswith(("mailto:", "tel:", "javascript:")):
            continue

        abs_url = urljoin(current_url, href)
        abs_url = canonicalize_for_visit(abs_url)

        if _looks_like_static_url(abs_url):
            continue

        if not is_internal_url(abs_url, base_reg_domain):
            continue

        if abs_url not in seen:
            seen.add(abs_url)
            out.append(abs_url)
            if len(out) >= MAX_LINKS_PER_PAGE:
                break

    return out


# ----------------------------
# Playwright launch (Heroku-safe)
# ----------------------------

def _find_chromium_executable() -> Optional[str]:
    exe = (os.getenv("CHROMIUM_EXECUTABLE_PATH") or "").strip()
    if exe and os.path.exists(exe):
        return exe

    bases = [
        os.getenv("GOOGLE_CHROME_BIN", ""),
        "/app/.apt/usr/bin",
        "/app/.apt/opt/google/chrome",
        "/usr/bin",
        "/usr/local/bin",
    ]
    patterns = [
        "google-chrome",
        "google-chrome-stable",
        "chromium",
        "chromium-browser",
        "**/chrome",
        "**/chromium",
    ]

    for base in bases:
        if not base or not os.path.exists(base):
            continue
        for pat in patterns:
            hits = glob.glob(os.path.join(base, pat), recursive=True)
            for h in hits:
                if os.path.isfile(h):
                    return h
    return None


def _launch_chromium(p, *, headless: bool) -> Any:
    exe = _find_chromium_executable()

    args = [
        "--no-sandbox",
        "--disable-setuid-sandbox",
        "--disable-dev-shm-usage",
        "--disable-background-networking",
        "--disable-background-timer-throttling",
        "--disable-default-apps",
        "--disable-sync",
        "--disable-translate",
        "--metrics-recording-only",
        "--mute-audio",
        "--no-first-run",
    ]

    launch_kwargs: Dict[str, Any] = {"headless": bool(headless), "args": args, "chromium_sandbox": False}
    if exe:
        launch_kwargs["executable_path"] = exe
    return p.chromium.launch(**launch_kwargs)


# ----------------------------
# Cookie harvesting
# ----------------------------

def _classify_party(*, cookie_domain: str, host_fallback: str, base_reg_domain: str) -> str:
    effective = (cookie_domain or host_fallback).lstrip(".").lower()
    if effective and registrable_domain(effective) != base_reg_domain:
        return "third-party"
    return "first-party"


def _harvest_context_cookies_once(context, *, base_reg_domain: str, cookie_jar: Dict[CookieKey, ParsedCookie], host_fallback: str) -> None:
    try:
        raw = context.cookies()
    except Exception:
        return

    host_fallback = (host_fallback or "").lstrip(".").lower()

    for c in raw or []:
        try:
            name = str(c.get("name") or "").strip()
            if not name:
                continue

            domain = str(c.get("domain") or "").lstrip(".").lower()
            path = str(c.get("path") or "/") or "/"

            effective_domain = (domain or host_fallback).lstrip(".").lower()
            if not effective_domain:
                continue

            key = make_cookie_key(name, effective_domain, path, host_fallback=host_fallback)

            party = _classify_party(cookie_domain=effective_domain, host_fallback=host_fallback, base_reg_domain=base_reg_domain)
            expires_human = _expires_human_from_playwright(c.get("expires"))

            incoming = ParsedCookie(
                name=name,
                domain=effective_domain,
                path=path,
                expires_human=expires_human,
                secure=bool(c.get("secure")),
                httpOnly=bool(c.get("httpOnly")),
                sameSite=str(c.get("sameSite") or ""),
                party=party,
                source="context.cookies",
            )

            if key in cookie_jar:
                cookie_jar[key] = merge_cookie(cookie_jar[key], incoming)
            else:
                cookie_jar[key] = incoming

        except Exception:
            continue


# ----------------------------
# Main scanner
# ----------------------------

def scan_site_for_cookies(
    *,
    start_url: str,
    max_pages: int = DEFAULT_MAX_PAGES,
    max_depth: int = DEFAULT_MAX_DEPTH,
    wait_ms: int = DEFAULT_WAIT_MS,
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
    per_page_budget_ms: int = DEFAULT_PER_PAGE_BUDGET_MS,
    headless: bool = DEFAULT_HEADLESS,
    ignore_https_errors: bool = DEFAULT_IGNORE_HTTPS_ERRORS,
    progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    cookie_early_exit_count: int = DEFAULT_COOKIE_EARLY_EXIT_COUNT,
    cookie_stable_rounds: int = DEFAULT_COOKIE_STABLE_ROUNDS,
    cookie_wait_step_ms: int = DEFAULT_COOKIE_WAIT_STEP_MS,
    min_wait_ms: int = DEFAULT_MIN_WAIT_MS,
    max_cookie_wait_ms: int = DEFAULT_MAX_COOKIE_WAIT_MS,
    skip_links_on_early_exit: bool = DEFAULT_SKIP_LINKS_ON_EARLY_EXIT,
    max_rss_mb: int = DEFAULT_MAX_RSS_MB,
) -> Dict[str, Any]:
    start_url = normalize_url(start_url)
    if not start_url:
        raise ValueError("URL is required")

    max_pages = max(1, int(max_pages))
    max_depth = max(0, int(max_depth))
    per_page_budget_ms = max(1000, int(per_page_budget_ms))

    base_reg_domain = registrable_domain(start_url)
    if not base_reg_domain:
        raise ValueError("Could not determine base domain from URL")

    visited: Set[str] = set()
    queue: List[Tuple[str, int]] = [(canonicalize_for_visit(start_url), 0)]

    cookie_jar: Dict[CookieKey, ParsedCookie] = {}
    set_cookie_observations: Set[str] = set()

    aborted_reason = ""
    aborted_rss_mb: Optional[float] = None

    def _progress(visited_count: int, current_url: str) -> None:
        if not progress_callback:
            return
        try:
            pct = int((visited_count / max_pages) * 100)
            pct = max(0, min(99, pct)) if visited_count < max_pages else 100
            progress_callback({"visited": visited_count, "max_pages": max_pages, "current_url": current_url, "percent": pct})
        except Exception:
            pass

    def _finalize() -> Dict[str, Any]:
        cookies_out = [pc_to_dict(pc) for pc in cookie_jar.values()]
        cookies_out.sort(key=lambda x: (x.get("party", ""), x.get("domain", ""), x.get("name", ""), x.get("path", "")))

        result: Dict[str, Any] = {
            "summary": {
                "base_registrable_domain": base_reg_domain,
                "visited_urls": len(visited),
                "max_pages": max_pages,
                "cookies_detected_total": len(cookies_out),
            },
            "cookies": cookies_out,
        }

        if aborted_reason:
            result["summary"]["aborted_reason"] = aborted_reason
            result["summary"]["rss_mb_at_abort"] = aborted_rss_mb
            result["summary"]["partial_results"] = True

        return result

    with sync_playwright() as p:
        browser = _launch_chromium(p, headless=headless)
        context = browser.new_context(ignore_https_errors=bool(ignore_https_errors))

        def _check_rss_or_abort(*, page=None) -> None:
            nonlocal aborted_reason, aborted_rss_mb
            rss = get_rss_mb()
            if rss is None:
                return
            if rss >= float(max_rss_mb):
                aborted_reason = "memory_wall"
                aborted_rss_mb = rss
                try:
                    if page is not None:
                        page.close()
                except Exception:
                    pass
                try:
                    context.close()
                except Exception:
                    pass
                try:
                    browser.close()
                except Exception:
                    pass
                raise MemoryWallHit(rss)

        def _route_handler(route, request) -> None:
            try:
                rtype = (request.resource_type or "").lower()
                req_url = request.url or ""
                path = (urlparse(req_url).path or "").lower()

                if path in STATIC_EXACT_PATHS or path.startswith("/favicon"):
                    route.abort()
                    return
                if any(path.startswith(prefix) for prefix in STATIC_PATH_PREFIXES):
                    route.abort()
                    return
                if any(path.endswith(ext) for ext in STATIC_FILE_EXTENSIONS):
                    route.abort()
                    return

                if rtype in BLOCKED_RESOURCE_TYPES:
                    route.abort()
                    return

                route.continue_()
            except Exception:
                try:
                    route.continue_()
                except Exception:
                    pass

        context.route("**/*", _route_handler)

        def _on_response(resp) -> None:
            try:
                header_val = resp.header_value("set-cookie")
                if not header_val:
                    return

                host = (urlparse(resp.url).hostname or "").lower()

                for pc in parse_set_cookie_header(str(header_val)):
                    pc.domain = (pc.domain or host).lstrip(".").lower()
                    pc.path = (pc.path or "/") or "/"
                    pc.party = _classify_party(cookie_domain=pc.domain, host_fallback=host, base_reg_domain=base_reg_domain)

                    if len(set_cookie_observations) < MAX_SET_COOKIE_OBSERVATIONS:
                        set_cookie_observations.add(f"{pc.name}::{pc.domain}::{pc.path}")

                    key = make_cookie_key(pc.name, pc.domain, pc.path, host_fallback=host)
                    if key in cookie_jar:
                        cookie_jar[key] = merge_cookie(cookie_jar[key], pc)
                    else:
                        cookie_jar[key] = pc
            except Exception:
                return

        context.on("response", _on_response)

        try:
            while queue and len(visited) < max_pages:
                _check_rss_or_abort()

                url, depth = queue.pop(0)
                url = canonicalize_for_visit(url)

                if url in visited:
                    continue
                if not is_internal_url(url, base_reg_domain):
                    continue
                if _looks_like_static_url(url):
                    continue

                visited.add(url)
                _progress(len(visited), url)

                deadline = time.monotonic() + (per_page_budget_ms / 1000.0)

                page = context.new_page()
                try:
                    host = (urlparse(url).hostname or "").lower()

                    # --- Navigate (budget-bounded) ---
                    try:
                        # Only allow navigation to consume the remaining per-page budget.
                        nav_left_ms = int((deadline - time.monotonic()) * 1000.0)
                        if nav_left_ms > 250:
                            nav_timeout_ms = max(250, min(int(timeout_ms), nav_left_ms))
                            page.goto(url, wait_until="domcontentloaded", timeout=nav_timeout_ms)
                    except PlaywrightTimeoutError:
                        pass
                    except Exception:
                        pass

                    _check_rss_or_abort(page=page)

                    early_exit_reason: Optional[str] = None
                    page_cookie_start_count = len(cookie_jar)

                    target_wait_ms = max(0, int(min(wait_ms, max_cookie_wait_ms)))
                    step_ms = max(50, int(cookie_wait_step_ms))
                    stable_needed = max(1, int(cookie_stable_rounds))
                    min_wait_ms_int = max(0, int(min_wait_ms))

                    start_wait = time.monotonic()
                    end_wait = min(start_wait + (target_wait_ms / 1000.0), deadline)

                    last_count = len(cookie_jar)
                    stable = 0

                    while time.monotonic() < end_wait:
                        try:
                            page.wait_for_timeout(step_ms)
                        except Exception:
                            pass

                        _check_rss_or_abort(page=page)

                        _harvest_context_cookies_once(
                            context,
                            base_reg_domain=base_reg_domain,
                            cookie_jar=cookie_jar,
                            host_fallback=host,
                        )

                        _check_rss_or_abort(page=page)

                        cur_count = len(cookie_jar)
                        new_on_page = cur_count - page_cookie_start_count
                        waited_ms = (time.monotonic() - start_wait) * 1000.0

                        if cookie_early_exit_count > 0 and new_on_page >= cookie_early_exit_count:
                            early_exit_reason = "threshold"
                            break

                        if cur_count == last_count:
                            stable += 1
                        else:
                            last_count = cur_count
                            stable = 0

                        if stable >= stable_needed and waited_ms >= min_wait_ms_int:
                            early_exit_reason = "stable"
                            break

                    _check_rss_or_abort(page=page)
                    _harvest_context_cookies_once(context, base_reg_domain=base_reg_domain, cookie_jar=cookie_jar, host_fallback=host)
                    _check_rss_or_abort(page=page)

                    try:
                        for pc in _harvest_document_cookie(page) or []:
                            if not pc.name:
                                continue
                            pc.domain = (pc.domain or host).lstrip(".").lower()
                            pc.path = (pc.path or "/") or "/"
                            pc.party = _classify_party(cookie_domain=pc.domain, host_fallback=host, base_reg_domain=base_reg_domain)
                            key = make_cookie_key(pc.name, pc.domain, pc.path, host_fallback=host)
                            if key in cookie_jar:
                                cookie_jar[key] = merge_cookie(cookie_jar[key], pc)
                            else:
                                cookie_jar[key] = pc
                    except Exception:
                        pass

                    # Fix "only 1 page scanned":
                    # Don't skip links just because threshold hit; only skip if out of time or near memory wall.
                    # If we'd otherwise stall (queue empty) give ourselves a tiny grace window
                    # to extract a few links, even if navigation ate the budget.
                    if depth < max_depth and (time.monotonic() < deadline or (not queue and len(visited) < max_pages)):
                        time_left = deadline - time.monotonic()
                        rss_now = get_rss_mb()
                        near_wall = (rss_now is not None) and (rss_now >= float(max_rss_mb) - 10.0)

                        should_skip_links = bool(
                            skip_links_on_early_exit
                            and early_exit_reason == "threshold"
                            and (time_left < 0.25 or near_wall)
                        )

                        if not should_skip_links:
                            _check_rss_or_abort(page=page)

                            link_deadline = deadline
                            if time.monotonic() >= deadline:
                                link_deadline = time.monotonic() + 0.25  # 250ms grace extraction window

                            links = extract_links_from_page(
                                page,
                                current_url=url,
                                base_reg_domain=base_reg_domain,
                                deadline_monotonic=link_deadline,
                            )

                            for link in links:
                                if link not in visited:
                                    queue.append((link, depth + 1))

                finally:
                    try:
                        page.close()
                    except Exception:
                        pass

                try:
                    if free_memory_aggressively:
                        free_memory_aggressively()
                    gc.collect()
                except Exception:
                    pass

        except MemoryWallHit:
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

    return _finalize()


# ----------------------------
# Cookie categorization + UI formatting
# ----------------------------

def infer_cookie_type_and_purpose(cookie_name: str) -> Tuple[str, str]:
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


def to_ui_cookie(pc: "ParsedCookie") -> Dict[str, Any]:
    helper = globals().get("infer_cookie_type_and_purpose")
    if callable(helper):
        ctype, purpose = helper(getattr(pc, "name", "") or "")
    else:
        ctype, purpose = ("Unknown", "Unknown")

    return {
        "name": getattr(pc, "name", "") or "",
        "domain": getattr(pc, "domain", "") or "",
        "path": getattr(pc, "path", "") or "/",
        "expires_human": getattr(pc, "expires_human", "") or "",
        "secure": bool(getattr(pc, "secure", False)),
        "httpOnly": bool(getattr(pc, "httpOnly", False)),
        "sameSite": getattr(pc, "sameSite", "") or "",
        "party": getattr(pc, "party", "") or "",
        "cookie_type": ctype,
        "purpose": purpose,
    }


def pc_to_dict(pc: "ParsedCookie") -> Dict[str, Any]:
    return to_ui_cookie(pc)
