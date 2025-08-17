import os
import uuid
import gc
import tempfile
from concurrent.futures import ThreadPoolExecutor
from django.http import JsonResponse, FileResponse
from django.core.cache import cache
from django.conf import settings

# ---------------------------------------------------------------------------
# Tunables (can be overridden in settings.py)
# ---------------------------------------------------------------------------
BG_WORKERS    = getattr(settings, "SEO_BG_WORKERS", 10)     # concurrent jobs
URL_WORKERS   = getattr(settings, "SEO_URL_WORKERS", 1)    # concurrent URLs per job
SITEMAP_LIMIT = getattr(settings, "SEO_SITEMAP_LIMIT", 100)

# Shared background executor
EXECUTOR = ThreadPoolExecutor(max_workers=BG_WORKERS)

# ---- Shared HTTP session with connection pooling & retries -------------------
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

def _build_http_pool(bg_workers, url_workers):
    pool_size = max(8, int(bg_workers * max(1, url_workers) * 1.5))
    sess = requests.Session()
    sess.headers.update({
        "User-Agent": "SEO Head Checker by Ben Crittenden (+https://www.bencritt.net)",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    })
    retry = Retry(
        total=2,
        connect=2,
        read=2,
        backoff_factor=0.3,
        status_forcelist=(429, 500, 502, 503, 504),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(
        pool_connections=pool_size,
        pool_maxsize=pool_size,
        max_retries=retry,
    )
    sess.mount("http://", adapter)
    sess.mount("https://", adapter)
    return sess

_POOL = _build_http_pool(BG_WORKERS, URL_WORKERS)



def start_sitemap_processing(request=None, sitemap_url=None):
    """
    Start a background job to process a sitemap (or single URL) and write a CSV report.
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
    cache.set(task_id, {"status": "pending", "progress": 0}, timeout=1800)

    def process_task():
        urls = None
        try:
            # Choose a safe output directory; treat "" as unset.
            seo_tmp = getattr(settings, "SEO_TMP_DIR", None)
            media_root = getattr(settings, "MEDIA_ROOT", None)
            out_dir = seo_tmp or media_root or tempfile.gettempdir()
            if not out_dir:
                out_dir = tempfile.gettempdir()
            os.makedirs(out_dir, exist_ok=True)

            file_path = os.path.join(out_dir, f"seo_report_{task_id}.csv")

            # Fetch at most SITEMAP_LIMIT URLs, then write-as-you-go CSV
            urls = fetch_sitemap_urls(sitemap_url, limit=SITEMAP_LIMIT)
            process_sitemap_to_csv(urls, file_path, max_workers=URL_WORKERS, task_id=task_id)

            cache.set(task_id, {"status": "completed", "file": file_path}, timeout=1800)
        except Exception as e:
            cache.set(task_id, {"status": "error", "error": str(e)}, timeout=1800)
        finally:
            urls = None
            gc.collect()

    EXECUTOR.submit(process_task)
    return JsonResponse({"task_id": task_id}, status=202)


def fetch_sitemap_urls(sitemap_url, limit=None):
    """
    Fetch URLs from a sitemap (streaming XML); if not a sitemap, return [sitemap_url].
    Applies an in-parser cap (limit) so we don't hold a huge URL list in memory.
    """
    import requests

    if limit is None:
        limit = SITEMAP_LIMIT

    headers = {
        "User-Agent": "SEO Head Checker by Ben Crittenden (+https://www.bencritt.net)",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    }

    # Streaming fetch
    try:
        resp = _POOL.get(sitemap_url, headers=headers, timeout=(5, 15), stream=True)
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
    import requests
    from bs4 import BeautifulSoup, SoupStrainer

    headers = {
        "User-Agent": "SEO Head Checker by Ben Crittenden (+https://www.bencritt.net)",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    }
    soup = None
    resp = None

    try:
        resp = _POOL.get(url, headers=headers, timeout=(5, 15), stream=True)
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
    Write results directly to a CSV file while processing URLs in parallel.
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
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            for i, row in enumerate(pool.map(process_single_url, urls)):
                writer.writerow(row)
                if task_id:
                    cache.set(
                        task_id,
                        {"status": "processing", "progress": int(((i + 1) / total) * 100)},
                        timeout=1800,
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
    Stream the generated CSV to the client and clean up the file & cache when done.
    """
    task = cache.get(task_id)
    if not task or task.get("status") != "completed":
        return JsonResponse({"error": "File not ready or task not found"}, status=404)

    file_path = task.get("file")
    if not file_path or not os.path.exists(file_path):
        return JsonResponse({"error": "File not found"}, status=404)

    f = open(file_path, "rb")
    resp = FileResponse(
        f,
        as_attachment=True,
        filename=os.path.basename(file_path),
        content_type="text/csv",
    )

    # Cleanup after the response is closed
    original_close = resp.close

    def _close_and_cleanup():
        try:
            original_close()
        finally:
            try:
                f.close()
            finally:
                try:
                    os.remove(file_path)
                except FileNotFoundError:
                    pass
                cache.delete(task_id)
                gc.collect()

    resp.close = _close_and_cleanup
    return resp
