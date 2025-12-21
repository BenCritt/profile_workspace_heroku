"""
cookie_scan_utils.py

Cookie scanner + lightweight background job runner (in-process) WITH QUEUEING.

Adds:
- Global FIFO queue in Django cache
- Only one running scan at a time (Playwright is heavy)
- queued tasks get queue_position (1-based); active task uses 0

Heroku Playwright:
- Uses CHROMIUM_EXECUTABLE_PATH if set (from your buildpack setup)
- Falls back to default Playwright launch for local dev
"""

from __future__ import annotations

import gc
import os
import re
import threading
import uuid
from collections import deque
from datetime import datetime, timezone
from typing import Any, Callable, Deque, Dict, List, Optional, Set, Tuple
from urllib.parse import urljoin, urlparse

import tldextract
from django.core.cache import cache
from playwright.sync_api import sync_playwright

# ----------------------------
# Defaults (single source of truth)
# ----------------------------

# Conservative defaults to reduce Heroku timeout risk
DEFAULT_MAX_PAGES = 10
DEFAULT_MAX_DEPTH = 1

DEFAULT_WAIT_MS = 1500
DEFAULT_TIMEOUT_MS = 20000
DEFAULT_HEADLESS = True
DEFAULT_IGNORE_HTTPS_ERRORS = False

DEFAULT_USER_AGENT = "Cookie Audit by Ben Crittenden (+https://www.bencritt.net)"

# Cache/job settings
_COOKIE_TASK_TTL_SECONDS = 60 * 30  # 30 minutes
_COOKIE_TASK_KEY_PREFIX = "cookie_audit:task:"
_COOKIE_EXECUTOR_MAX_WORKERS = 1  # keep low: Playwright is heavy

# Queue keys (stored in cache)
_COOKIE_QUEUE_KEY = "cookie_audit:queue"           # list[str] task_ids
_COOKIE_ACTIVE_TASK_KEY = "cookie_audit:active"    # str task_id (or empty)
_COOKIE_QUEUE_LOCK = threading.Lock()

try:
    from concurrent.futures import ThreadPoolExecutor

    _COOKIE_EXECUTOR = ThreadPoolExecutor(max_workers=_COOKIE_EXECUTOR_MAX_WORKERS)
except Exception:
    _COOKIE_EXECUTOR = None


def _task_key(task_id: str) -> str:
    return f"{_COOKIE_TASK_KEY_PREFIX}{task_id}"


def _utc_iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_set_task(task_id: str, patch: Dict[str, Any]) -> None:
    """
    Merge `patch` into the existing task dict and write back to cache.
    """
    key = _task_key(task_id)
    current = cache.get(key) or {}
    current.update(patch)
    cache.set(key, current, timeout=_COOKIE_TASK_TTL_SECONDS)


# ----------------------------
# Queue helpers
# ----------------------------

def _get_queue() -> List[str]:
    q = cache.get(_COOKIE_QUEUE_KEY)
    if isinstance(q, list):
        return [str(x) for x in q]
    return []


def _set_queue(q: List[str]) -> None:
    cache.set(_COOKIE_QUEUE_KEY, q, timeout=_COOKIE_TASK_TTL_SECONDS)


def _get_active_task_id() -> Optional[str]:
    v = cache.get(_COOKIE_ACTIVE_TASK_KEY)
    v = str(v) if v else ""
    return v or None


def _set_active_task_id(task_id: Optional[str]) -> None:
    cache.set(_COOKIE_ACTIVE_TASK_KEY, task_id or "", timeout=_COOKIE_TASK_TTL_SECONDS)


def _prune_queue(q: List[str]) -> List[str]:
    """
    Remove queued task ids that have expired / no longer exist in cache.
    """
    kept: List[str] = []
    for tid in q:
        if cache.get(_task_key(tid)) is not None:
            kept.append(tid)
    return kept


def _refresh_queue_positions(q: List[str]) -> None:
    """
    Store queue_position on each queued task (1-based).
    """
    for idx, tid in enumerate(q, start=1):
        _safe_set_task(tid, {"queue_position": idx})


def _dispatch_next_if_idle() -> None:
    """
    Start the next task if none is currently running.
    """
    if _COOKIE_EXECUTOR is None:
        return

    with _COOKIE_QUEUE_LOCK:
        active = _get_active_task_id()
        if active:
            return

        q = _prune_queue(_get_queue())
        if not q:
            _set_queue([])
            _set_active_task_id(None)
            return

        next_task_id = q.pop(0)
        _set_queue(q)
        _set_active_task_id(next_task_id)

        # Update remaining positions and set active position = 0
        _refresh_queue_positions(q)
        _safe_set_task(next_task_id, {"queue_position": 0, "state": "running", "started_at": _utc_iso_now()})

        task = cache.get(_task_key(next_task_id)) or {}
        params = task.get("params") or {}

        fut = _COOKIE_EXECUTOR.submit(_run_cookie_audit_task_from_params, next_task_id, params)

        def _done_callback(_f) -> None:
            # Clear active and run next
            try:
                with _COOKIE_QUEUE_LOCK:
                    if _get_active_task_id() == next_task_id:
                        _set_active_task_id(None)
            finally:
                _dispatch_next_if_idle()

        fut.add_done_callback(_done_callback)


# ----------------------------
# Public API (used by your views)
# ----------------------------

def start_cookie_audit_task(
    start_url: str,
    *,
    max_pages: int = DEFAULT_MAX_PAGES,
    max_depth: int = DEFAULT_MAX_DEPTH,
    wait_ms: int = DEFAULT_WAIT_MS,
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
    headless: bool = DEFAULT_HEADLESS,
    ignore_https_errors: bool = DEFAULT_IGNORE_HTTPS_ERRORS,
) -> str:
    """
    Enqueue a scan and return a task id immediately.
    """
    task_id = str(uuid.uuid4())

    initial = {
        "task_id": task_id,
        "state": "queued",  # queued | running | done | error
        "created_at": _utc_iso_now(),
        "queue_position": None,
        "progress": {
            "visited": 0,
            "max_pages": int(max_pages),
            "current_url": "",
            "percent": 0,
        },
        "error": None,
        "results": None,
        "params": {
            "start_url": start_url,
            "max_pages": int(max_pages),
            "max_depth": int(max_depth),
            "wait_ms": int(wait_ms),
            "timeout_ms": int(timeout_ms),
            "headless": bool(headless),
            "ignore_https_errors": bool(ignore_https_errors),
        },
    }
    cache.set(_task_key(task_id), initial, timeout=_COOKIE_TASK_TTL_SECONDS)

    if _COOKIE_EXECUTOR is None:
        _safe_set_task(
            task_id,
            {
                "state": "error",
                "error": "Background executor could not be created.",
                "finished_at": _utc_iso_now(),
            },
        )
        return task_id

    # Enqueue
    with _COOKIE_QUEUE_LOCK:
        q = _prune_queue(_get_queue())
        q.append(task_id)
        _set_queue(q)
        _refresh_queue_positions(q)

    # Try to start immediately if nothing is running
    _dispatch_next_if_idle()
    return task_id


def get_cookie_audit_task(task_id: str) -> Optional[Dict[str, Any]]:
    return cache.get(_task_key(task_id))


# ----------------------------
# Task runner
# ----------------------------

ProgressCallback = Callable[[Dict[str, Any]], None]


def _run_cookie_audit_task_from_params(task_id: str, params: Dict[str, Any]) -> None:
    """
    Run using the params stored in cache.
    NOTE: state/started_at is set by dispatcher before calling this.
    """

    def progress_cb(progress: Dict[str, Any]) -> None:
        visited = int(progress.get("visited", 0))
        mp = int(progress.get("max_pages", int(params.get("max_pages", DEFAULT_MAX_PAGES))))
        percent = int(progress.get("percent", 0))
        _safe_set_task(
            task_id,
            {
                "progress": {
                    "visited": visited,
                    "max_pages": mp,
                    "current_url": progress.get("current_url", "") or "",
                    "percent": percent,
                }
            },
        )

    try:
        results = scan_site_for_cookies(
            start_url=str(params.get("start_url") or ""),
            max_pages=int(params.get("max_pages", DEFAULT_MAX_PAGES)),
            max_depth=int(params.get("max_depth", DEFAULT_MAX_DEPTH)),
            wait_ms=int(params.get("wait_ms", DEFAULT_WAIT_MS)),
            timeout_ms=int(params.get("timeout_ms", DEFAULT_TIMEOUT_MS)),
            headless=bool(params.get("headless", DEFAULT_HEADLESS)),
            ignore_https_errors=bool(params.get("ignore_https_errors", DEFAULT_IGNORE_HTTPS_ERRORS)),
            progress_callback=progress_cb,
        )
        _safe_set_task(
            task_id,
            {
                "state": "done",
                "results": results,
                "finished_at": _utc_iso_now(),
                "progress": {
                    "visited": int(results["summary"].get("visited_urls", 0)),
                    "max_pages": int(params.get("max_pages", DEFAULT_MAX_PAGES)),
                    "current_url": "",
                    "percent": 100,
                },
            },
        )
    except Exception as exc:
        _safe_set_task(
            task_id,
            {
                "state": "error",
                "error": str(exc),
                "finished_at": _utc_iso_now(),
            },
        )
    finally:
        gc.collect()


# ----------------------------
# Cookie scanning logic
# ----------------------------

def _normalize_url(url: str) -> str:
    url = (url or "").strip()
    if not url:
        return ""
    if not re.match(r"^https?://", url, re.IGNORECASE):
        url = "https://" + url
    return url


def _registrable_domain(url_or_host: str) -> str:
    """
    Return the registrable domain (e.g., example.com, example.co.uk) for a URL or hostname.
    """
    s = (url_or_host or "").strip()
    if not s:
        return ""

    host = urlparse(s).hostname if "://" in s else s
    host = (host or "").lower().strip(".")
    if not host:
        return ""

    try:
        ext = tldextract.extract(host)
        return (ext.registered_domain or host).lower()
    except Exception:
        if host.startswith("www."):
            host = host[4:]
        return host


def _should_follow_link(base_reg_domain: str, link: str) -> bool:
    """
    Allow crawling across subdomains as long as registrable domain matches.
    """
    if not link:
        return False

    try:
        parsed = urlparse(link)
        if parsed.scheme.lower() not in ("http", "https"):
            return False
    except Exception:
        return False

    link_reg = _registrable_domain(link)
    return bool(base_reg_domain) and link_reg == base_reg_domain


def _cookie_type_and_purpose(name: str) -> Tuple[str, str]:
    """
    Very lightweight heuristic categorization.
    """
    n = (name or "").lower()

    analytics = ("_ga", "_gid", "_gat", "amplitude", "mixpanel", "mp_", "optimizely", "_hj", "hotjar")
    marketing = ("_fbp", "_fbc", "gcl_", "utm", "ttclid", "pin_", "criteo", "doubleclick", "ads", "adroll")
    auth = ("session", "sess", "csrftoken", "csrf", "auth", "jwt", "token", "logged", "remember")
    prefs = ("lang", "locale", "theme", "dark", "consent", "cookie_consent", "gdpr", "ccpa")

    if any(k in n for k in auth):
        return ("Strictly necessary", "Authentication / session security (login, CSRF, session state).")
    if any(k in n for k in prefs):
        return ("Functional", "Stores preferences (language, theme) or consent choices.")
    if any(k in n for k in analytics):
        return ("Analytics", "Measures site usage and performance (analytics).")
    if any(k in n for k in marketing):
        return ("Marketing", "Advertising / remarketing / campaign attribution.")
    return ("Unclassified", "Purpose not identified by heuristic (review manually).")


def _human_expires(expires: Any) -> str:
    if not expires:
        return "Session"
    try:
        if isinstance(expires, (int, float)) and expires > 0:
            dt = datetime.fromtimestamp(float(expires), tz=timezone.utc)
            return dt.strftime("%Y-%m-%d %H:%M:%S UTC")
    except Exception:
        pass
    return str(expires)


def _launch_chromium(p, *, headless: bool):
    """
    Heroku-friendly launch:
    - If CHROMIUM_EXECUTABLE_PATH exists (buildpack), use it.
    - Otherwise, local dev: use Playwright-managed Chromium.
    """
    exe = (os.getenv("CHROMIUM_EXECUTABLE_PATH") or "").strip()
    launch_kwargs: Dict[str, Any] = {"headless": bool(headless)}
    if exe:
        launch_kwargs["executable_path"] = exe
    return p.chromium.launch(**launch_kwargs)


def scan_site_for_cookies(
    *,
    start_url: str,
    max_pages: int = DEFAULT_MAX_PAGES,
    max_depth: int = DEFAULT_MAX_DEPTH,
    wait_ms: int = DEFAULT_WAIT_MS,
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
    headless: bool = DEFAULT_HEADLESS,
    ignore_https_errors: bool = DEFAULT_IGNORE_HTTPS_ERRORS,
    progress_callback: Optional[ProgressCallback] = None,
) -> Dict[str, Any]:
    """
    Crawl up to `max_pages` pages and report cookies observed by the browser context.
    """
    start_url = _normalize_url(start_url)
    if not start_url:
        raise ValueError("Start URL is empty.")

    max_pages = max(1, int(max_pages))
    max_depth = max(0, int(max_depth))
    wait_ms = max(0, int(wait_ms))
    timeout_ms = max(1000, int(timeout_ms))

    base_domain = _registrable_domain(start_url)

    visited: Set[str] = set()
    queue: Deque[Tuple[str, int]] = deque([(start_url, 0)])

    cookie_jar: Dict[Tuple[str, str], Dict[str, Any]] = {}  # (name, domain) -> cookie dict

    def emit_progress(current_url: str, visited_count: int) -> None:
        if not progress_callback:
            return
        pct = int(min(100, round((visited_count / max_pages) * 100)))
        progress_callback(
            {
                "visited": visited_count,
                "max_pages": max_pages,
                "current_url": current_url,
                "percent": pct,
            }
        )

    with sync_playwright() as p:
        browser = _launch_chromium(p, headless=headless)

        context = browser.new_context(
            ignore_https_errors=ignore_https_errors,
            user_agent=DEFAULT_USER_AGENT,
        )
        page = context.new_page()

        try:
            while queue and len(visited) < max_pages:
                url, depth = queue.popleft()
                if url in visited:
                    continue

                visited.add(url)
                emit_progress(url, len(visited))

                # Navigate
                page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)

                if wait_ms:
                    page.wait_for_timeout(wait_ms)

                # Read cookies from the browser context after navigation
                cookies = context.cookies()
                for c in cookies:
                    name = c.get("name") or ""
                    domain = c.get("domain") or ""
                    key = (name, domain)

                    if key not in cookie_jar:
                        cookie_type, purpose = _cookie_type_and_purpose(name)

                        party = "First-party"
                        try:
                            cd = c.get("domain") or ""
                            cd = cd[1:] if cd.startswith(".") else cd
                            if cd and cd != base_domain and not cd.endswith("." + base_domain):
                                party = "Third-party"
                        except Exception:
                            pass

                        cookie_jar[key] = {
                            "name": name,
                            "domain": c.get("domain") or "",
                            "path": c.get("path") or "",
                            "httpOnly": bool(c.get("httpOnly", False)),
                            "secure": bool(c.get("secure", False)),
                            "sameSite": (c.get("sameSite") or ""),
                            "expires": c.get("expires"),
                            "expires_human": _human_expires(c.get("expires")),
                            "cookie_type": cookie_type,
                            "purpose": purpose,
                            "party": party,
                        }

                # Expand links
                if len(visited) < max_pages and depth < max_depth:
                    try:
                        hrefs = page.eval_on_selector_all("a[href]", "els => els.map(a => a.href)")
                    except Exception:
                        hrefs = []

                    for href in hrefs or []:
                        if not href:
                            continue

                        next_url = href.strip()
                        if not re.match(r"^https?://", next_url, re.IGNORECASE):
                            next_url = urljoin(url, next_url)

                        if not _should_follow_link(base_domain, next_url):
                            continue

                        if next_url not in visited:
                            queue.append((next_url, depth + 1))

            emit_progress("", len(visited))

        finally:
            try:
                context.close()
            finally:
                browser.close()

    cookies_list = list(cookie_jar.values())
    cookies_list.sort(key=lambda x: (x.get("party", ""), x.get("name", "")))

    return {
        "summary": {
            "start_url": start_url,
            "base_registrable_domain": base_domain,
            "visited_urls": len(visited),
            "cookies_detected_total": len(cookies_list),
            "max_pages": max_pages,
            "max_depth": max_depth,
        },
        "cookies": cookies_list,
    }
