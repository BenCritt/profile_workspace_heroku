# views/views_seo_tools.py
#
# ============================================================================
# SEO Professional Toolkit — View Layer
# ============================================================================
# Contains all Django view functions for the SEO Professional Toolkit category.
# Domain logic (readability scoring, OG tag parsing, sitemap crawling) lives
# in the respective utils modules; these views handle HTTP mechanics only.
#
# Tools in this module:
#   seo_tools            — Hub/landing page for the whole category
#   seo_head_checker     — Sitemap-driven <head> tag auditor (async, Celery-backed)
#   grade_level_analyzer — Flesch-Kincaid / SMOG / Gunning Fog readability scorer
#   og_previewer         — Fetches a URL and renders its OG / Twitter card preview
#
# ============================================================================
# ASYNC PIPELINE: SEO HEAD CHECKER
# ============================================================================
# The SEO Head Checker crawls every URL in a sitemap.xml file, fetches each
# page's <head>, and audits it for title tags, meta descriptions, canonical
# links, Open Graph tags, robots directives, etc.  This can take anywhere from
# seconds (small site) to several minutes (site with hundreds of URLs).
#
# To avoid HTTP timeouts, the crawl is handled asynchronously via Celery:
#
#   seo_head_checker  (GET)        → renders the form page (SitemapForm)
#   start_sitemap_processing (POST)→ validates form, enqueues Celery task,
#                                    returns {"task_id": "..."} JSON to JS
#   get_task_status  (GET)         → polls Celery task progress; JS calls
#                                    this on a timer until status=="complete"
#   download_task_file (GET)       → streams the completed CSV to the browser
#
# The three task-management endpoints are thin wrappers around functions in
# seo_head_checker_utils.py.  The actual task dispatch, status storage, and
# file generation all live there.  Keeping this view module as a shim means
# the Celery machinery can evolve independently of the HTTP layer.
#
# WHY MODULE-SCOPE IMPORT FOR TASK HELPERS?
#   The three forwarding functions (_start_sitemap_processing, etc.) are
#   imported at module scope (top of file) rather than inside each view.
#   This is intentional — it mirrors the original monolithic views.py pattern
#   and means any import errors in seo_head_checker_utils surface at worker
#   startup time, not buried inside a first-request failure.
# ============================================================================

from django.shortcuts import render
from django.views.decorators.cache import cache_control
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import ensure_csrf_cookie

from ..decorators import trim_memory_after

# Module-scope import of the Celery task forwarding helpers.
# These are the only views in the project where utils are imported at module
# scope; see the module docstring above for the rationale.
from ..seo_head_checker_utils import (
    start_sitemap_processing as _start_sitemap_processing,
    get_task_status          as _get_task_status,
    download_task_file       as _download_task_file,
)


# ===========================================================================
# SEO Tools Hub
# ===========================================================================
# Static landing page — card grid linking to every SEO tool.
# @ensure_csrf_cookie primes the CSRF token for any subsequent AJAX POSTs
# (e.g. the sitemap processing start request fired from the hub's quick-links).
# ===========================================================================

@trim_memory_after
@ensure_csrf_cookie
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def seo_tools(request):
    return render(request, "projects/seo_tools.html")


# ===========================================================================
# SEO Head Checker  (form page — ENDPOINT 1 of 4)
# ===========================================================================
# Renders the initial form page where the user enters a sitemap URL and
# configures audit options.  No crawl is initiated here; the form's submit
# button fires an AJAX POST to start_sitemap_processing instead.
#
# GET only.  If someone hits this endpoint via POST (e.g. a direct curl),
# they get the empty form back, which is harmless.
# ===========================================================================

@trim_memory_after
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def seo_head_checker(request):
    from ..forms import SitemapForm

    return render(
        request,
        "projects/seo_head_checker.html",
        {"form": SitemapForm()},
    )


# ===========================================================================
# Start Sitemap Processing  (ENDPOINT 2 of 4 — AJAX POST)
# ===========================================================================
# Accepts a POST from the JS on the seo_head_checker page.
# Validates the submitted SitemapForm server-side (the JS also validates
# client-side, but server-side validation is the authoritative check).
# If valid, delegates to seo_head_checker_utils._start_sitemap_processing()
# which enqueues the Celery task and returns a task_id.
#
# @require_POST enforces POST-only; any other method gets a 405 response.
# @trim_memory_after is applied so any temporary objects created during
# validation are released after the JSON response is sent.
# ===========================================================================

@require_POST
@trim_memory_after
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def start_sitemap_processing(request):
    # Forwards directly to the utils layer, which returns a JsonResponse.
    return _start_sitemap_processing(request=request)


# ===========================================================================
# Get Task Status  (ENDPOINT 3 of 4 — AJAX GET)
# ===========================================================================
# Polls the status of a running (or completed) sitemap audit task.
# task_id is a UUID captured from the URL pattern, e.g.:
#   path("seo/head-checker/status/<str:task_id>/", views.get_task_status)
#
# The JS on the results page calls this every N seconds until it receives
# status == "complete" or status == "error", then stops polling.
#
# Returns JSON:
#   {"status": "pending", "progress": 42, "total": 120}
#   {"status": "complete", "download_url": "/seo/head-checker/download/<id>/"}
#   {"status": "error", "message": "..."}
# ===========================================================================

@trim_memory_after
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def get_task_status(request, task_id):
    return _get_task_status(request, task_id)


# ===========================================================================
# Download Task File  (ENDPOINT 4 of 4)
# ===========================================================================
# Streams the completed audit CSV to the browser as a file download.
# task_id identifies which completed task's output file to serve.
#
# The utils layer handles locating the file (temp storage, Django cache, or
# the Celery result backend depending on configuration) and constructing a
# streaming FileResponse or HttpResponse with the appropriate headers.
# ===========================================================================

@trim_memory_after
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def download_task_file(request, task_id):
    return _download_task_file(request, task_id)


# ===========================================================================
# Grade Level Text Analyzer
# ===========================================================================
# Scores a block of text against multiple standard readability formulas:
#   - Flesch Reading Ease     (higher = easier; 60–70 is "standard")
#   - Flesch-Kincaid Grade    (US grade level equivalent)
#   - Gunning Fog Index       (years of education required)
#   - SMOG Grade              (Simple Measure of Gobbledygook)
#   - Coleman-Liau Index      (character-based, no syllable counting)
#   - Automated Readability   (character + word based)
#
# All scoring lives in grade_level_utils.calculate_grade_levels().
#
# NOTE: @trim_memory_after is applied TWICE.  This is an intentional
# double-decoration preserved from the original monolithic views.py where it
# was used experimentally to ensure two rounds of cleanup for this view, which
# can process large text inputs.  It is functionally equivalent to calling the
# cleanup logic twice but is otherwise harmless.
#
# GET  → empty TextForm.
# POST → validates; scores text; injects "text" (original input) and "results"
#        (scored dict) into context.  On invalid POST, "text" is recovered from
#        request.POST so the user's input is preserved in the textarea.
# ===========================================================================

@trim_memory_after
@trim_memory_after   # double-decoration intentional; see module note above
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def grade_level_analyzer(request):
    from ..forms import TextForm
    from ..grade_level_utils import calculate_grade_levels

    form    = TextForm()
    context = {}

    if request.method == "POST":
        form = TextForm(request.POST)

        if form.is_valid():
            input_text      = form.cleaned_data["text"]
            context["text"] = input_text
            context["results"] = calculate_grade_levels(input_text)
        else:
            # The only validation failure is an empty submission.
            # Preserve whatever the user typed so they don't lose their work.
            context["text"] = request.POST.get("text", "")

    context["form"] = form
    return render(request, "projects/grade_level_analyzer.html", context)


# ===========================================================================
# Open Graph & Social Card Previewer
# ===========================================================================
# Fetches a URL, parses its <head> for Open Graph / Twitter Card / standard
# meta tags, and renders a visual preview of how the page would appear when
# shared on social platforms (Facebook, LinkedIn, Twitter/X, etc.).
#
# PROCESSING PIPELINE (POST only):
#   1. Normalise URL  → ensure scheme (https://) is present
#   2. Validate URL   → check for both scheme and netloc components
#   3. fetch_head_html() → HTTP GET with timeout; returns (html, final_url, elapsed)
#      "final_url" reflects any redirects so relative URL resolution is correct.
#   4. parse_tags()   → BeautifulSoup extraction of all relevant meta tags
#   5. build_card_data() → assemble platform-specific card preview dicts
#
# Each step has its own error path that sets context["error"] and returns early.
# This provides specific, actionable error messages rather than a single generic
# "something went wrong" catch-all.
#
# CONTEXT KEYS on success:
#   elapsed   — round-trip fetch time in seconds (shown as performance metric)
#   final_url — post-redirect URL (may differ from what the user entered)
#   + keys from card_data spread via **card_data:
#     og_card      — Open Graph preview dict
#     twitter_card — Twitter/X card dict
#     generic      — title, description, canonical for platforms without OG
#
# CONTEXT KEYS always present:
#   requests_available — bool; if the `requests` library is missing (unlikely
#                        in production), the template shows an "unavailable" banner
#   url_input          — the raw string the user submitted (repopulates the field)
#   form               — OGPreviewerForm (unbound initial or with initial value)
#   error              — error string, or absent on success
#
# GET  → empty form, requests_available flag.
# ===========================================================================

@trim_memory_after
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def og_previewer(request):
    from urllib.parse import urlparse
    from ..forms import OGPreviewerForm
    from ..og_previewer_utils import (
        REQUESTS_AVAILABLE,
        build_card_data,
        fetch_head_html,
        normalise_url,
        parse_tags,
    )

    context: dict = {
        "requests_available": REQUESTS_AVAILABLE,
        "url_input":          "",
        "form":               OGPreviewerForm(),
    }

    if request.method != "POST":
        # GET — render the blank form and nothing else.
        return render(request, "projects/og_previewer.html", context)

    raw_url = request.POST.get("url_input", "").strip()
    context["url_input"] = raw_url
    # Populate the form with the submitted URL so it remains in the input on
    # re-render (whether for error display or for successful results).
    context["form"]      = OGPreviewerForm(initial={"url_input": raw_url})

    if not raw_url:
        context["error"] = "Please enter a URL."
        return render(request, "projects/og_previewer.html", context)

    # Step 1: Normalise — prepend https:// if scheme is missing.
    url    = normalise_url(raw_url)
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        # urlparse couldn't extract a valid scheme + host after normalisation.
        context["error"] = (
            "That doesn't look like a valid URL. Please include a domain name."
        )
        return render(request, "projects/og_previewer.html", context)

    # Step 2: Fetch the page — may raise ValueError on blocked/bad responses.
    try:
        html, final_url, elapsed = fetch_head_html(url)
    except ValueError as exc:
        context["error"] = str(exc)
        return render(request, "projects/og_previewer.html", context)

    # Step 3: Parse the <head> for meta tags.
    try:
        tags = parse_tags(html)
    except Exception as exc:
        context["error"] = f"Failed to parse page HTML: {exc}"
        return render(request, "projects/og_previewer.html", context)

    # Step 4: Assemble platform-specific card preview dicts from the raw tags.
    try:
        card_data = build_card_data(tags, final_url)
    except Exception as exc:
        context["error"] = f"Unexpected error building card data: {exc}"
        return render(request, "projects/og_previewer.html", context)

    # All steps succeeded — merge card data and timing metadata into context.
    context.update({
        "elapsed":   elapsed,
        "final_url": final_url,
        **card_data,   # spreads og_card, twitter_card, generic, etc.
    })

    return render(request, "projects/og_previewer.html", context)