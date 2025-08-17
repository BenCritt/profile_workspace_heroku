# seo_head_checker_utils.py

import os
import uuid
import gc
import tempfile
import time
import threading
import requests
from typing import Optional
from concurrent.futures import ThreadPoolExecutor

from django.http import JsonResponse, FileResponse
from django.core.cache import cache
from django.conf import settings

# -----------------------------------------------------------------------------
# Tunables (override in settings.py if desired)
# -----------------------------------------------------------------------------
BG_WORKERS    = getattr(settings, "SEO_BG_WORKERS", 10)         # concurrent jobs per process
URL_WORKERS   = getattr(settings, "SEO_URL_WORKERS", 1)          # concurrent URLs per job
SITEMAP_LIMIT = getattr(settings, "SEO_SITEMAP_LIMIT", 100)      # cap URLs per sitemap
DOWNLOAD_TTL  = getattr(settings, "SEO_DOWNLOAD_TTL", 30 * 60)   # 30 minutes
MAX_CONCURRENT_DOWNLOADS = getattr(settings, "SEO_MAX_CONCURRENT_DOWNLOADS", 12)

# Shared background executor for jobs
EXECUTOR = ThreadPoolExecutor(max_workers=BG_WORKERS)

# -----------------------------------------------------------------------------
# Shared HTTP session with connection pooling & retries (lazy init)
# -----------------------------------------------------------------------------
_POOL: Optional["requests.Session"] = None

def _get_pool():
    """Build once on first use (keeps baseline memory low)."""
    global _POOL
    if _POOL is not None:
        return _POOL
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry

    # Pool size ~ jobs * per-job URLs, with headroom
    pool_size = max(16, int(BG_WORKERS * max(1, URL_WORKERS) * 2.0))

    sess = requests.Session()
    sess.headers.update({
        "User-Agent": "SEO Head Checker by Ben Crittenden (+https://www.bencritt.net)",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    })
    retry = Retry(
        total=2, connect=2, read=2,
        backoff_factor=0.3,
        status_forcelist=(429, 500, 502, 503, 504),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(pool_connections=pool_size, pool_maxsize=pool_size, max_retries=retry)
    sess.mount("http://", adapter)
    sess.mount("https://", adapter)
    _POOL = sess
    return _POOL

# Cap concurrent downloads per process to avoid FD spikes
_DOWNLOAD_SLOTS = threading.BoundedSemaphore(MAX_CONCURRENT_DOWNLOADS)

# -----------------------------------------------------------------------------
# Output directory + periodic cleanup
# -----------------------------------------------------------------------------
def _get_out_dir() -> str:
    """Return a safe, writable directory to store CSVs (never '')."""
    seo_tmp = getattr(settings, "SEO_TMP_DIR", None)
    media_root = getattr(settings, "MEDIA_ROOT", None)
    out_dir = (seo_tmp or media_root or tempfile.gettempdir()) or tempfile.gettempdir()
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
        # Never let cleanup crash the request path
        pass

# -----------------------------------------------------------------------------
# Download coordination: "delete on download" that tolerates multiple tabs
# -----------------------------------------------------------------------------
def _dl_ref_key(task_id: str) -> str: return f"seo:dl:{task_id}:ref"
def _dl_del_key(task_id: str) -> str: return f"seo:dl:{task_id}:del"

def _inc_ref(task_id: str) -> int:
    # Create the counter if missing, then INCR
    key = _dl_ref_key(task_id)
    try: cache.add(key, 0, timeout=DOWNLOAD_TTL)
    except Exception: pass
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

# -----------------------------------------------------------------------------
# Public endpoints
# -----------------------------------------------------------------------------
def start_sitemap_processing(request=None, sitemap_url=None):
    """
    Start a background job to process a sitemap (or single URL) and write a CSV.
    Accepts either:
      • direct param `sitemap_url`, or
      • POST JSON body: {"sitemap_url": "<url>"}
    Returns JsonResponse(status=202, data={"task_id": ...}).
    """
    import json
    from .utils import normalize_url

    # Resolve input
    if sitemap_url is None:
        if not request or request.method != "POST":
            return JsonResponse({"error": "Invalid request method"}, status=405)
        try:
            data = json.loads(request.body or b"{}")
            sitemap_url = normalize_url(data.get("sitemap_url"))
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=400)
    else:
        sitemap_url = normalize_url(sitemap_url)

    if not sitemap_url:
        return JsonResponse({"error": "Missing or invalid sitemap_url"}, status=400)

    task_id = str(uuid.uuid4())
    cache.set(task_id, {"status": "pending", "progress": 0}, timeout=max(1800, DOWNLOAD_TTL))

    def process_task():
        urls = None
        try:
            out_dir = _get_out_dir()
            _cleanup_old_reports(out_dir, DOWNLOAD_TTL)  # opportunistic purge
            file_path = os.path.join(out_dir, f"seo_report_{task_id}.csv")

            urls = fetch_sitemap_urls(sitemap_url, limit=SITEMAP_LIMIT)
            process_sitemap_to_csv(urls, file_path, max_workers=URL_WORKERS, task_id=task_id)

            cache.set(
                task_id,
                {"status": "completed", "file": file_path, "ts": time.time()},
                timeout=DOWNLOAD_TTL,
            )
        except Exception as e:
            cache.set(task_id, {"status": "error", "error": str(e)}, timeout=DOWNLOAD_TTL)
        finally:
            urls = None
            gc.collect()

    EXECUTOR.submit(process_task)
    return JsonResponse({"task_id": task_id}, status=202)

def fetch_sitemap_urls(sitemap_url, limit=None):
    """
    Fetch URLs from a sitemap (streaming). If not a sitemap, return [sitemap_url].
    Applies an in-parser cap so we don't hold a huge URL list in memory.
    """
    import requests  # for exception classes

    if limit is None:
        limit = SITEMAP_LIMIT

    headers = {
        "User-Agent": "SEO Head Checker by Ben Crittenden (+https://www.bencritt.net)",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    }

    try:
        resp = _get_pool().get(sitemap_url, headers=headers, timeout=(5, 15), stream=True)
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

            urls = []
            capped = max(1, int(limit))
            for _, el in ET.iterparse(resp.raw, events=("end",)):
                tag = el.tag
                if isinstance(tag, str) and tag.endswith("loc") and el.text:
                    urls.append(el.text.strip())
                    if len(urls) >= capped:
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

def _read_until_head(resp, limit=512_000):
    """
    Read up to and including </head> (or until limit bytes), then stop.
    Works with requests.get(..., stream=True).
    """
    end = b"</head>"
    buf = bytearray()
    for chunk in resp.iter_content(8192):
        buf += chunk
        if end in buf or len(buf) >= limit:
            break
    return bytes(buf)

def process_single_url(url):
    """
    Fetch a page and check SEO-related elements in <head> only (memory-friendly).
    Returns a dict for CSV output.
    """
    import requests  # for exception classes
    from bs4 import BeautifulSoup, SoupStrainer

    headers = {
        "User-Agent": "SEO Head Checker by Ben Crittenden (+https://www.bencritt.net)",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    }
    soup = None
    resp = None

    try:
        resp = _get_pool().get(url, headers=headers, timeout=(5, 15), stream=True)
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
        html_head = _read_until_head(resp)
        only_head = SoupStrainer("head")
        soup = BeautifulSoup(html_head, "html.parser", parse_only=only_head)

        head = soup.find("head")
        if not head:
            return {"URL": url, "Status": "No <head> section"}

        def is_present(tag_name, **attrs):
            return "Present" if head.find(tag_name, attrs=attrs) else "Missing"

        structured_scripts = head.find_all("script", type="application/ld+json")
        structured_count = len(structured_scripts) if structured_scripts else 0

        open_graph_present = bool(
            head.find("meta", attrs={"property": lambda p: p and p.startswith("og:")})
        )
        twitter_card_present = bool(
            head.find("meta", attrs={"name": lambda p: p and p.startswith("twitter:")})
        )

        return {
            "URL": url,
            "Status": "Success",
            "Title Tag": "Present" if head.title else "Missing",
            "Meta Description": is_present("meta", name="description"),
            "Canonical Tag": is_present("link", rel="canonical"),
            "Meta Robots Tag": is_present("meta", name="robots"),
            "Open Graph Tags": "Present" if open_graph_present else "Missing",
            "Twitter Card Tags": "Present" if twitter_card_present else "Missing",
            "Hreflang Tags": (
                "Present" if head.find("link", rel="alternate", hreflang=True) else "Missing"
            ),
            "Structured Data": (
                f"Present ({structured_count} scripts)" if structured_count > 0 else "Missing"
            ),
            "Charset Declaration": is_present("meta", charset=True),
            "Viewport Tag": is_present("meta", name="viewport"),
            "Favicon": is_present("link", rel="icon"),
        }
    except Exception as e:
        return {"URL": url, "Status": f"Error while processing content: {e}"}
    finally:
        if soup:
            del soup
        if resp is not None:
            try:
                resp.close()
            except Exception:
                pass
        gc.collect()

def process_sitemap_to_csv(urls, csv_path, max_workers=None, task_id=None):
    """
    Write results directly to a CSV file while processing URLs in parallel (or serially).
    Keeps memory flat by not accumulating a giant results list.
    """
    import csv
    from concurrent.futures import ThreadPoolExecutor

    if max_workers is None:
        max_workers = URL_WORKERS

    total = max(1, len(urls))  # already capped by fetch_sitemap_urls
    with open(csv_path, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(
            csvfile,
            fieldnames=[
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
            ],
        )
        writer.writeheader()
        if max_workers == 1:
            # No per-job threadpool: fewer threads per job => more concurrent users
            for i, u in enumerate(urls):
                row = process_single_url(u)
                writer.writerow(row)
                if task_id:
                    cache.set(
                        task_id,
                        {"status": "processing", "progress": int(((i + 1) / total) * 100)},
                        timeout=DOWNLOAD_TTL,
                    )
        else:
            with ThreadPoolExecutor(max_workers=max_workers) as pool:
                for i, row in enumerate(pool.map(process_single_url, urls)):
                    writer.writerow(row)
                    if task_id:
                        cache.set(
                            task_id,
                            {"status": "processing", "progress": int(((i + 1) / total) * 100)},
                            timeout=DOWNLOAD_TTL,
                        )
    gc.collect()

def get_task_status(request, task_id):
    """Return the current status/progress or error for a given task_id from cache."""
    task = cache.get(task_id)
    if not task:
        return JsonResponse({"error": "Task not found"}, status=404)
    return JsonResponse(task)

def download_task_file(request, task_id):
    """
    Stream the generated CSV to the client.
    Semantics: delete on download (after *all* concurrent downloads finish), or after TTL.
    Also limits concurrent downloads per process to avoid FD spikes.
    """
    # Resolve file path from cache or derive by convention (multi-process resilient)
    task = cache.get(task_id)
    out_dir = _get_out_dir()
    derived_path = os.path.join(out_dir, f"seo_report_{task_id}.csv")
    file_path = (task or {}).get("file") or derived_path

    if not os.path.exists(file_path):
        return JsonResponse({"error": "File not ready or not found"}, status=404)

    # Mark that deletion should happen after downloads complete & take a read "lease"
    _mark_delete_requested(task_id)
    _inc_ref(task_id)

    # Back-pressure: limit concurrent downloads per process
    acquired = _DOWNLOAD_SLOTS.acquire(timeout=30)
    if not acquired:
        # If very busy, ask client to retry shortly
        _dec_ref(task_id)
        return JsonResponse({"error": "Busy, try again shortly"}, status=503)

    try:
        f = open(file_path, "rb")
    except Exception:
        _DOWNLOAD_SLOTS.release()
        _dec_ref(task_id)
        raise

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
            finally:
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
                    gc.collect()

    resp.close = _close_and_maybe_delete
    return resp
