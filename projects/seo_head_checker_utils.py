from __future__ import annotations

import csv
import gc
import os
import tempfile
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser
from typing import Any, Optional, List

from django.conf import settings
from django.core.cache import cache
from django.http import FileResponse, JsonResponse

# =============================================================================
# Tunables (inline — no env vars required)
# =============================================================================
BG_WORKERS = 25                 # concurrent background jobs per process
URL_WORKERS = 1                 # concurrent URLs per job (use 1 to favor user concurrency)
SITEMAP_LIMIT = 1000             # cap URLs parsed from sitemap/index
DOWNLOAD_TTL = 30 * 60          # seconds to keep CSV before cleanup
MAX_CONCURRENT_DOWNLOADS = 25   # cap simultaneous CSV downloads per process
POOL_IDLE_REAP = 120            # seconds of HTTP-pool inactivity before closing
THREAD_STACK = 256 * 1024       # per-thread stack size (bytes)
HEAD_MAX_BYTES = 512_000        # max bytes to read per page (stop after </head> or cap)
ACTIVE_JOB_SLOTS = 5            # Allow at most 5 jobs to run concurrently; the rest will queue
_ACTIVE_SEM = threading.BoundedSemaphore(ACTIVE_JOB_SLOTS)


# Lower per-thread memory; must be set before threads are created.
try:
    threading.stack_size(int(THREAD_STACK))
except (ValueError, RuntimeError):
    pass

# Cap simultaneous CSV downloads per process
_DOWNLOAD_SLOTS = threading.BoundedSemaphore(MAX_CONCURRENT_DOWNLOADS if MAX_CONCURRENT_DOWNLOADS > 0 else 1)

# =============================================================================
# Background executor (lazy) — auto-shutdown when idle so stacks are freed
# =============================================================================
_EXECUTOR: Optional[ThreadPoolExecutor] = None
_EXEC_LOCK = threading.Lock()
_ACTIVE_JOBS = 0
_ACTIVE_LOCK = threading.Lock()

def _get_executor() -> ThreadPoolExecutor:
    global _EXECUTOR
    with _EXEC_LOCK:
        if _EXECUTOR is None:
            _EXECUTOR = ThreadPoolExecutor(max_workers=BG_WORKERS, thread_name_prefix="seo-queue")
        return _EXECUTOR

def _inc_jobs() -> None:
    global _ACTIVE_JOBS
    with _ACTIVE_LOCK:
        _ACTIVE_JOBS += 1

def _dec_jobs_and_maybe_cleanup() -> None:
    """When all jobs finish, tear down threads and reap HTTP pool to free RSS."""
    global _ACTIVE_JOBS, _EXECUTOR
    idle_now = False
    with _ACTIVE_LOCK:
        _ACTIVE_JOBS = max(0, _ACTIVE_JOBS - 1)
        idle_now = (_ACTIVE_JOBS == 0)
    if idle_now:
        with _EXEC_LOCK:
            if _EXECUTOR is not None:
                try:
                    _EXECUTOR.shutdown(wait=False)
                finally:
                    _EXECUTOR = None
        _maybe_reap_pool()

# =============================================================================
# HTTP session pool (lazy + idle reap)
# =============================================================================
_POOL: Optional[Any] = None
_POOL_LOCK = threading.Lock()
_POOL_LAST_USED = 0.0

def _get_pool():
    """Create a pooled Session with retries; update last-used for idle reaping."""
    global _POOL, _POOL_LAST_USED
    if _POOL is not None:
        _POOL_LAST_USED = time.time()
        return _POOL

    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry

    pool_size = max(16, int(BG_WORKERS * max(1, URL_WORKERS) * 2.0))
    sess = requests.Session()
    sess.headers.update({
        "User-Agent": "SEO Head Checker by Ben Crittenden (+https://www.bencritt.net/)",
        # Prefer HTML/XML; avoid images to save bytes
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    })
    retry = Retry(
        total=2, connect=2, read=2,
        backoff_factor=0.3,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods={"GET", "HEAD"},
        raise_on_status=False,
    )
    adapter = HTTPAdapter(pool_connections=pool_size, pool_maxsize=pool_size, max_retries=retry)
    sess.mount("http://", adapter)
    sess.mount("https://", adapter)

    with _POOL_LOCK:
        _POOL = sess
    _POOL_LAST_USED = time.time()
    return _POOL

def _maybe_reap_pool(idle_seconds: int = POOL_IDLE_REAP) -> None:
    """Close the HTTP pool if unused for a while so sockets/buffers are freed."""
    global _POOL, _POOL_LAST_USED
    if _POOL is None:
        return
    now = time.time()
    if now - _POOL_LAST_USED < max(15, idle_seconds):
        return
    with _POOL_LOCK:
        if _POOL and (time.time() - _POOL_LAST_USED) >= idle_seconds:
            try:
                _POOL.close()
            except Exception:
                pass
            _POOL = None

# =============================================================================
# Output directory + opportunistic cleanup
# =============================================================================
def _get_out_dir() -> str:
    """
    Prefer SEO_TMP_DIR or MEDIA_ROOT if present; else system temp.
    Keeps behavior compatible with your prior version.
    """
    out_dir = getattr(settings, "SEO_TMP_DIR", None) or getattr(settings, "MEDIA_ROOT", None) or tempfile.gettempdir()
    os.makedirs(out_dir, exist_ok=True)
    return out_dir

def _cleanup_old_reports(directory: str, max_age: int = DOWNLOAD_TTL) -> None:
    """Delete old seo_report_*.csv files older than max_age seconds (best-effort)."""
    try:
        now = time.time()
        for name in os.listdir(directory):
            if not (name.startswith("seo_report_") and name.endswith(".csv")):
                continue
            path = os.path.join(directory, name)
            try:
                st = os.stat(path)
            except FileNotFoundError:
                continue
            if now - st.st_mtime > max(60, int(max_age)):
                try:
                    os.remove(path)
                except Exception:
                    pass
    except Exception:
        pass

# =============================================================================
# Download coordination: delete-on-download (supports multiple tabs)
# =============================================================================
def _dl_ref_key(task_id: str) -> str: return f"seo:dl:{task_id}:ref"
def _dl_del_key(task_id: str) -> str: return f"seo:dl:{task_id}:del"

def _inc_ref(task_id: str) -> int:
    key = _dl_ref_key(task_id)
    try:
        cache.add(key, 0, timeout=DOWNLOAD_TTL)
    except Exception:
        pass
    try:
        return cache.incr(key)
    except Exception:
        val = (cache.get(key) or 0) + 1
        cache.set(key, val, timeout=DOWNLOAD_TTL)
        return val

def _dec_ref(task_id: str) -> int:
    key = _dl_ref_key(task_id)
    try:
        return cache.decr(key)
    except Exception:
        val = max(0, (cache.get(key) or 0) - 1)
        cache.set(key, val, timeout=DOWNLOAD_TTL)
        return val

def _mark_delete_requested(task_id: str) -> None:
    cache.set(_dl_del_key(task_id), 1, timeout=DOWNLOAD_TTL)

def _delete_requested(task_id: str) -> bool:
    return bool(cache.get(_dl_del_key(task_id)))

def _clear_dl_state(task_id: str) -> None:
    cache.delete_many([_dl_ref_key(task_id), _dl_del_key(task_id), task_id])

# =============================================================================
# Memory trimming helper
# =============================================================================
def _trim_memory():
    import ctypes
    try:
        gc.collect()
        ctypes.CDLL("libc.so.6").malloc_trim(0)
    except Exception:
        pass

# =============================================================================
# Sitemap streaming
# =============================================================================
def fetch_sitemap_urls(sitemap_url: str, limit: Optional[int] = None) -> List[str]:
    """
    Fetch URLs from a sitemap (streaming). If not a sitemap, return [sitemap_url].
    Applies an in-parser cap so we don't hold a huge URL list in memory.
    """
    import requests

    if limit is None:
        limit = SITEMAP_LIMIT

    sess = _get_pool()
    try:
        resp = sess.get(sitemap_url, timeout=(5, 15), stream=True)
        resp.raise_for_status()
    except requests.exceptions.Timeout:
        raise ValueError("The request timed out. Please try again later.")
    except requests.exceptions.ConnectionError:
        raise ValueError("Failed to connect to the URL. Please check the URL.")
    except requests.exceptions.HTTPError as e:
        raise ValueError(f"HTTP error occurred: {e}")
    except requests.exceptions.RequestException as e:
        raise ValueError(f"An error occurred while fetching the URL: {e}")

    ctype = (resp.headers.get("Content-Type") or "").lower()
    try:
        if "xml" in ctype or sitemap_url.lower().endswith(".xml"):
            # Stream-parse the sitemap; stop once we have 'limit' URLs
            import xml.etree.ElementTree as ET
            resp.raw.decode_content = True  # let urllib3 decompress to the stream

            urls: List[str] = []
            cap = max(1, int(limit))
            for _, el in ET.iterparse(resp.raw, events=("end",)):
                tag = el.tag
                if isinstance(tag, str) and tag.endswith("loc") and el.text:
                    urls.append(el.text.strip())
                    if len(urls) >= cap:
                        break
                el.clear()  # free element memory promptly

            if not urls:
                raise ValueError("The provided sitemap is empty or invalid.")
            return urls
        else:
            # Not a sitemap: treat as a single page
            return [sitemap_url]
    finally:
        try:
            resp.close()
        except Exception:
            pass

# =============================================================================
# Ultra-light <head> fetch + parser
# =============================================================================
def _read_until_head(resp, limit: int = HEAD_MAX_BYTES) -> bytes:
    """Read until </head> (case-insensitive) or until limit bytes, then stop."""
    marker = b"</head"
    buf = bytearray()
    for chunk in resp.iter_content(8192):
        if not chunk:
            break
        buf += chunk
        if marker in buf.lower() or len(buf) >= limit:
            break
    return bytes(buf)

class _HeadParser(HTMLParser):
    """
    Minimal HTML head extractor: collects only what we need for the CSV.
    Much lighter than BeautifulSoup; avoids building a full tree.
    """
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.in_head = False
        self.in_title = False
        self._title_parts: List[str] = []
        self.meta_description = None
        self.meta_robots = None
        self.canonical = None
        self.charset = None
        self.viewport = None
        self.has_og = False
        self.has_twitter = False
        self.has_hreflang = False
        self.structured_count = 0
        self.has_favicon = False

    def handle_starttag(self, tag, attrs):
        tl = tag.lower()
        a = {k.lower(): (v or "") for k, v in attrs}
        if tl == "head":
            self.in_head = True
            return
        if not self.in_head:
            return

        if tl == "title":
            self.in_title = True

        elif tl == "meta":
            # charset via <meta charset="utf-8">
            if not self.charset and "charset" in a:
                self.charset = a.get("charset")
            # charset via http-equiv content-type
            if not self.charset and a.get("http-equiv", "").lower() == "content-type":
                content = a.get("content", "")
                idx = content.lower().find("charset=")
                if idx >= 0:
                    self.charset = content[idx + 8:].split(";")[0].strip()

            name = (a.get("name") or a.get("property") or "").lower()
            content = a.get("content", "")

            if name == "description" and self.meta_description is None:
                self.meta_description = content
            elif name in ("robots", "x-robots-tag") and self.meta_robots is None:
                self.meta_robots = content
            elif name.startswith("og:"):
                self.has_og = True
            elif name.startswith("twitter:"):
                self.has_twitter = True
            elif name == "viewport" and self.viewport is None:
                self.viewport = content

        elif tl == "link":
            rel = (a.get("rel") or "").lower()
            href = a.get("href", "")
            hreflang = a.get("hreflang", "")
            if "canonical" in rel and not self.canonical and href:
                self.canonical = href
            if "alternate" in rel and hreflang and href:
                self.has_hreflang = True
            if any(x in rel for x in ("icon", "shortcut icon", "apple-touch-icon", "mask-icon")) and href:
                self.has_favicon = True

        elif tl == "script":
            if (a.get("type") or "").lower() == "application/ld+json":
                self.structured_count += 1

    def handle_endtag(self, tag):
        tl = tag.lower()
        if tl == "title":
            self.in_title = False
        elif tl == "head":
            self.in_head = False

    def handle_data(self, data):
        if self.in_head and self.in_title and data:
            if sum(len(x) for x in self._title_parts) < 2048:
                self._title_parts.append(data)

    def as_row(self, url: str) -> dict[str, str]:
        title_present = bool("".join(self._title_parts).strip())
        return {
            "URL": url,
            "Status": "Success",
            "Title Tag": "Present" if title_present else "Missing",
            "Meta Description": "Present" if (self.meta_description and self.meta_description.strip()) else "Missing",
            "Canonical Tag": "Present" if (self.canonical and self.canonical.strip()) else "Missing",
            "Meta Robots Tag": "Present" if (self.meta_robots and self.meta_robots.strip()) else "Missing",
            "Open Graph Tags": "Present" if self.has_og else "Missing",
            "Twitter Card Tags": "Present" if self.has_twitter else "Missing",
            "Hreflang Tags": "Present" if self.has_hreflang else "Missing",
            "Structured Data": f"Present ({self.structured_count} scripts)" if self.structured_count else "Missing",
            "Charset Declaration": "Present" if (self.charset and self.charset.strip()) else "Missing",
            "Viewport Tag": "Present" if (self.viewport and self.viewport.strip()) else "Missing",
            "Favicon": "Present" if self.has_favicon else "Missing",
        }

# =============================================================================
# Per-URL worker (stream + tiny parser)
# =============================================================================
def process_single_url(url: str) -> dict[str, str]:
    import requests
    sess = _get_pool()
    try:
        resp = sess.get(url, timeout=(5, 15), stream=True)
        resp.raise_for_status()
    except requests.exceptions.Timeout:
        return {"URL": url, "Status": "Error: Request timed out"}
    except requests.exceptions.ConnectionError:
        return {"URL": url, "Status": "Error: Failed to connect to the URL"}
    except requests.exceptions.HTTPError as e:
        return {"URL": url, "Status": f"HTTP error occurred: {e}"}
    except requests.exceptions.RequestException as e:
        return {"URL": url, "Status": f"Request error: {e}"}

    try:
        head_bytes = _read_until_head(resp, HEAD_MAX_BYTES)
    finally:
        try:
            resp.close()
        except Exception:
            pass

    try:
        parser = _HeadParser()
        parser.feed(head_bytes.decode("utf-8", errors="ignore"))
        return parser.as_row(url)
    except Exception as e:
        return {"URL": url, "Status": f"Error while processing content: {e}"}
    finally:
        del head_bytes
        _trim_memory()

# =============================================================================
# CSV writer (incremental) with progress updates
# =============================================================================
_CSV_FIELDS = [
    "URL",
    "Status",
    "Title Tag",
    "Meta Description",
    "Canonical Tag",
    "Meta Robots Tag",
    "Open Graph Tags",
    "Twitter Card Tags",
    "Hreflang Tags",
    "Structured Data",
    "Charset Declaration",
    "Viewport Tag",
    "Favicon",
]

def process_sitemap_to_csv(urls: List[str], csv_path: str, max_workers: Optional[int] = None, task_id: Optional[str] = None):
    if max_workers is None:
        max_workers = URL_WORKERS

    total = max(1, len(urls))  # already capped by fetch_sitemap_urls
    processed = 0

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=_CSV_FIELDS)
        writer.writeheader()

        if max_workers <= 1:
            for u in urls:
                row = process_single_url(u)
                writer.writerow(row)
                processed += 1
                if task_id:
                    cache.set(task_id, {"status": "processing", "progress": int(processed * 100 / total)}, timeout=DOWNLOAD_TTL)
                if (processed % 25) == 0:
                    _trim_memory()
        else:
            with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="seo-head") as pool:
                for row in pool.map(process_single_url, urls):
                    writer.writerow(row)
                    processed += 1
                    if task_id:
                        cache.set(task_id, {"status": "processing", "progress": int(processed * 100 / total)}, timeout=DOWNLOAD_TTL)
                    if (processed % 25) == 0:
                        _trim_memory()

    _trim_memory()

# =============================================================================
# Public endpoints used by your views
# =============================================================================
def start_sitemap_processing(request=None, sitemap_url=None):
    """
    Start a background job to process a sitemap (or single URL) into a CSV.

    Accepts either:
      • direct param `sitemap_url`, or
      • HTTP POST with JSON body: {"sitemap_url": "<url>"}  (form-POST also works)

    Returns: JsonResponse(status=202, {"task_id": "<id>"})
    """
    import json, time, uuid
    from django.http import JsonResponse
    from django.core.cache import cache
    from .utils import normalize_url

    # Resolve the input URL
    url = None
    if sitemap_url:
        url = normalize_url(sitemap_url)
    elif request and request.method == "POST":
        try:
            if request.content_type and "application/json" in request.content_type.lower():
                payload = json.loads(request.body or b"{}")
                url = normalize_url(payload.get("sitemap_url"))
            else:
                # allow form posts too
                url = normalize_url(request.POST.get("sitemap_url") or request.POST.get("sitemap"))
        except Exception as e:
            return JsonResponse({"error": f"Invalid request body: {e}"}, status=400)
    else:
        return JsonResponse({"error": "Invalid request method"}, status=405)

    if not url:
        return JsonResponse({"error": "Missing or invalid sitemap_url"}, status=400)

    # Create a task id and mark as queued
    task_id = str(uuid.uuid4())
    cache.set(task_id, {"status": "queued", "progress": 0}, timeout=max(1800, DOWNLOAD_TTL))

    def _runner():
        _inc_jobs()
        # Block here until a slot is free; limits concurrent jobs
        _ACTIVE_SEM.acquire()
        try:
            # Now actually processing
            cache.set(task_id, {"status": "processing", "progress": 0}, timeout=DOWNLOAD_TTL)

            out_dir = _get_out_dir()
            _cleanup_old_reports(out_dir, DOWNLOAD_TTL)
            file_path = os.path.join(out_dir, f"seo_report_{task_id}.csv")

            # Collect (capped) URLs from the sitemap (streaming)
            urls = fetch_sitemap_urls(url, limit=SITEMAP_LIMIT)

            # Produce CSV incrementally; updates progress via cache inside
            process_sitemap_to_csv(urls, file_path, max_workers=URL_WORKERS, task_id=task_id)

            # Done
            cache.set(task_id, {"status": "completed", "file": file_path, "ts": time.time()}, timeout=DOWNLOAD_TTL)

        except Exception as e:
            cache.set(task_id, {"status": "error", "error": str(e)}, timeout=DOWNLOAD_TTL)
        finally:
            # Always release the slot and clean up memory/resources
            try:
                _trim_memory()
            finally:
                _ACTIVE_SEM.release()
                _dec_jobs_and_maybe_cleanup()

    _get_executor().submit(_runner)
    return JsonResponse({"task_id": task_id}, status=202)


def get_task_status(request, task_id: str):
    task = cache.get(task_id)
    if not task:
        return JsonResponse({"error": "Task not found"}, status=404)
    return JsonResponse(task)

def download_task_file(request, task_id: str):
    """
    Stream the generated CSV; delete after final reader (or TTL).
    Safer ordering to avoid crashes when downloads start while other jobs are queued.
    """
    task = cache.get(task_id)
    out_dir = _get_out_dir()
    derived_path = os.path.join(out_dir, f"seo_report_{task_id}.csv")
    file_path = (task or {}).get("file") or derived_path

    # If the job hasn't produced a file yet, tell the client to wait.
    status = (task or {}).get("status")
    if not os.path.exists(file_path):
        if status in {"queued", "processing"}:
            # 425 Too Early — let the front-end retry
            return JsonResponse({"error": "File not ready", "status": status}, status=425)
        return JsonResponse({"error": "File not found"}, status=404)

    # Limit concurrent downloads per process (fail fast, never “wait”)
    if not _DOWNLOAD_SLOTS.acquire(blocking=False):
        return JsonResponse({"error": "Busy, try again shortly"}, status=503)

    try:
        try:
            f = open(file_path, "rb")
        except FileNotFoundError:
            _DOWNLOAD_SLOTS.release()
            return JsonResponse({"error": "File no longer available, please retry"}, status=404)
        except OSError as e:
            _DOWNLOAD_SLOTS.release()
            return JsonResponse({"error": f"Unable to open file: {e}"}, status=503)

        # Only after a successful open do we mark & refcount
        _mark_delete_requested(task_id)
        _inc_ref(task_id)

        resp = FileResponse(
            f,
            as_attachment=True,
            filename=os.path.basename(file_path),
            content_type="text/csv",
        )
        original_close = resp.close

        def _close_and_maybe_delete():
            try:
                original_close()
            finally:
                try:
                    f.close()
                except Exception:
                    pass
                try:
                    remaining = _dec_ref(task_id)
                    if _delete_requested(task_id) and remaining <= 0:
                        try:
                            os.remove(file_path)
                        except FileNotFoundError:
                            pass
                        _clear_dl_state(task_id)
                finally:
                    _DOWNLOAD_SLOTS.release()
                    _trim_memory()
                    _maybe_reap_pool()

        resp.close = _close_and_maybe_delete
        return resp


    except Exception as e:
        # Absolute last line of defense: never bubble an exception here.
        _DOWNLOAD_SLOTS.release()
        return JsonResponse({"error": f"Unexpected download error: {type(e).__name__}"}, status=500)

