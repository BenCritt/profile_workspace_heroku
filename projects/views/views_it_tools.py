# views/views_it_tools.py
#
# IT Professional Toolkit views:
#   Cookie Audit (5 endpoints), Font Inspector, XML Splitter,
#   DNS, IP, SSL, Subnet, Email Auth, WHOIS, HTTP Headers,
#   Redirect Checker, JSON-LD Validator, Robots Analyzer,
#   Cron Builder, Timestamp Converter, IT Tools hub.
#
# All relative imports use ".." to step up from the views/ package to
# the parent app directory.

import os

from django.shortcuts import render
from django.http import HttpResponse, JsonResponse, HttpResponseNotFound, FileResponse
from django.views.decorators.cache import cache_control
from django.views.decorators.http import require_POST, require_GET
from django.views.decorators.csrf import ensure_csrf_cookie
from django.urls import reverse

from ..decorators import trim_memory_after


# ===========================================================================
# IT Tools Hub
# ===========================================================================

@trim_memory_after
@ensure_csrf_cookie
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def it_tools(request):
    return render(request, "projects/it_tools.html")


# ===========================================================================
# Cookie Audit  (5 endpoints)
# ===========================================================================

@trim_memory_after
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
@require_GET
def cookie_audit_view(request):
    """
    Renders the Cookie Audit form page (URL input only).
    No session-stored task_id — results/progress are driven by JS
    calling the start/status/results endpoints below.
    """
    from ..forms import CookieAuditForm
    from .. import cookie_scan_utils  # noqa: imported for side-effects / type checking

    form = CookieAuditForm()
    # Make optional advanced fields non-required so the user only needs to supply a URL.
    for field_name in (
        "max_pages", "max_depth", "wait_ms",
        "timeout_ms", "headless", "ignore_https_errors",
    ):
        if field_name in form.fields:
            form.fields[field_name].required = False

    return render(request, "projects/cookie_audit.html", {"form": form})


@trim_memory_after
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
@require_POST
def cookie_audit_start(request):
    # Maintenance Mode — pending hosting migration.
    return JsonResponse(
        {"error": "This tool is temporarily suspended."},
        status=503,
    )
    from ..forms import CookieAuditForm
    from .. import cookie_scan_utils

    """
    Starts a scan and returns immediately with a task_id (JSON).
    Does NOT store task_id in session (prevents tab/user overwrite).
    """
    form = CookieAuditForm(request.POST)
    for field_name in (
        "max_pages", "max_depth", "wait_ms",
        "timeout_ms", "headless", "ignore_https_errors",
    ):
        if field_name in form.fields:
            form.fields[field_name].required = False

    if not form.is_valid():
        return JsonResponse(
            {"error": "Please enter a valid website URL.", "form_errors": form.errors},
            status=400,
        )

    url = form.cleaned_data["url"]
    task_id = cookie_scan_utils.start_cookie_audit_task(url)

    return JsonResponse(
        {
            "task_id": task_id,
            "status_url":   reverse("projects:cookie_audit_status",  args=[task_id]),
            "results_url":  reverse("projects:cookie_audit_results", args=[task_id]),
            "download_url": reverse("projects:cookie_audit_download", args=[task_id]),
        }
    )


@trim_memory_after
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
@require_GET
def cookie_audit_status(request, task_id):
    """
    Polling endpoint for progress/status.
    Always returns JSON so the frontend never crashes parsing HTML as JSON.
    """
    from .. import cookie_scan_utils

    try:
        task = cookie_scan_utils.get_cookie_audit_task(str(task_id))

        if not task:
            return JsonResponse({"state": "unknown"}, status=404)

        if not isinstance(task, dict):
            return JsonResponse(
                {"state": "error", "error": "Task data corrupted (non-dict)."},
                status=500,
            )

        payload = {
            "state":    task.get("state", "unknown"),
            "progress": task.get("progress") or {},
        }

        if payload["state"] == "error":
            payload["error"] = task.get("error") or "Unknown error"

        if "queue_position" in task:
            payload["queue_position"] = task.get("queue_position")

        return JsonResponse(payload)

    except Exception as exc:
        return JsonResponse(
            {"state": "error", "error": f"{type(exc).__name__}: {exc}"},
            status=500,
        )


@trim_memory_after
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
@require_GET
def cookie_audit_results(request, task_id):
    """
    Returns results JSON once the scan is done.
    We do NOT pop/remove results here because the CSV download endpoint needs them.
    """
    from .. import cookie_scan_utils

    try:
        task = cookie_scan_utils.get_cookie_audit_task(str(task_id))

        if not task:
            return JsonResponse({"state": "unknown"}, status=404)

        if not isinstance(task, dict):
            return JsonResponse(
                {"state": "error", "error": "Task data corrupted (non-dict)."},
                status=500,
            )

        state = task.get("state", "unknown")
        payload = {"state": state}

        if state == "done":
            payload["results"] = task.get("results") or {}
        elif state == "error":
            payload["error"] = task.get("error") or "Unknown error"
        else:
            payload["progress"] = task.get("progress") or {}
            payload["queue_position"] = task.get("queue_position", None)

        return JsonResponse(payload)

    except Exception as exc:
        return JsonResponse(
            {"state": "error", "error": f"{type(exc).__name__}: {exc}"},
            status=500,
        )


@trim_memory_after
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
@require_GET
def cookie_audit_download(request, task_id):
    import time

    from .. import cookie_scan_utils
    from .. import csv_utils

    # Best-effort cleanup of stale exports (30 min).
    csv_utils.cleanup_old_files(export_subdir="cookie_audit", max_age_seconds=30 * 60)

    task_id_str = str(task_id)
    task = cookie_scan_utils.get_cookie_audit_task(task_id_str)
    if not task or not isinstance(task, dict):
        return HttpResponseNotFound("Task not found.")

    if task.get("state") != "done":
        return HttpResponseNotFound("Results not ready yet.")

    csv_meta   = task.get("csv") or {}
    path       = (csv_meta.get("path") or "").strip()
    filename   = (csv_meta.get("filename") or "cookie_audit.csv").strip()
    created_at = float(csv_meta.get("created_at") or 0.0)

    # Expire after 30 minutes even if never downloaded.
    if created_at and (time.time() - created_at) >= 30 * 60:
        try:
            if path:
                os.remove(path)
        except Exception:
            pass
        path = ""

    if not path or not os.path.exists(path):
        return HttpResponseNotFound(
            "CSV file expired or missing. Please run the scan again."
        )

    # Mark as consumed so it can't be downloaded multiple times.
    task["csv"] = None
    task["csv_downloaded_at"] = time.time()
    cookie_scan_utils.set_cookie_audit_task(task_id_str, task)

    return csv_utils.file_response_with_cleanup(
        path=path,
        download_filename=filename,
        content_type="text/csv",
    )


# ===========================================================================
# Font Inspector
# ===========================================================================

@trim_memory_after
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def font_inspector(request):
    from ..forms import FontInspectorForm

    form = FontInspectorForm()
    return render(request, "projects/font_inspector.html", {"form": form})


# ===========================================================================
# XML Splitter
# ===========================================================================

@trim_memory_after
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def xml_splitter(request):
    from ..forms import XMLUploadForm
    from ..xml_splitter_utils import split_xml_to_zip
    from django.http import StreamingHttpResponse

    form = XMLUploadForm(request.POST or None, request.FILES or None)

    if request.method == "POST" and form.is_valid():
        try:
            zip_io = split_xml_to_zip(form.cleaned_data["file"])
        except ValueError as err:
            form.add_error("file", str(err))
        else:
            # Build download filename: original_name_split.zip
            download_name = (
                form.cleaned_data["file"].name.rsplit(".", 1)[0] + "_split.zip"
            )
            response = StreamingHttpResponse(zip_io, content_type="application/zip")
            response["Content-Disposition"] = (
                f'attachment; filename="{download_name}"'
            )
            return response

    return render(request, "projects/xml_splitter.html", {"form": form})


# ===========================================================================
# DNS Lookup Tool
# ===========================================================================

@trim_memory_after
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def dns_tool(request):
    from ..forms import DomainForm
    from ..dns_tool_utils import fetch_dns_records, normalize_domain

    results = {}
    error_message = None
    form = DomainForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        domain = normalize_domain(form.cleaned_data["domain"])
        results, error_message = fetch_dns_records(domain)

    return render(
        request,
        "projects/dns_tool.html",
        {"form": form, "results": results, "error_message": error_message},
    )


# ===========================================================================
# IP Address Lookup Tool
# ===========================================================================

@trim_memory_after
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def ip_tool(request):
    from ..forms import IPForm
    from ..ip_tool_utils import lookup_ptr, geolocate_ip, check_blacklists

    results = {}
    error_message = None
    form = IPForm()

    if request.method == "POST":
        form = IPForm(request.POST)
        if form.is_valid():
            ip_address = form.cleaned_data["ip_address"]
            results["PTR"]         = lookup_ptr(ip_address)
            results["Geolocation"] = geolocate_ip(ip_address)
            results["Blacklist"]   = check_blacklists(ip_address)

    response = render(
        request,
        "projects/ip_tool.html",
        {"form": form, "results": results, "error_message": error_message},
    )
    # Extra anti-caching headers (preserved from original).
    response["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response["Pragma"]  = "no-cache"
    response["Expires"] = "0"
    return response


# ===========================================================================
# SSL Verification Tool
# ===========================================================================

@trim_memory_after
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def ssl_check(request):
    from ..forms import SSLCheckForm
    from ..ssl_utils import verify_ssl

    form   = SSLCheckForm()
    result = None
    url    = None

    if request.method == "POST":
        form = SSLCheckForm(request.POST)
        if form.is_valid():
            url    = form.cleaned_data["url"]
            result = verify_ssl(url)

    response = render(
        request,
        "projects/ssl_check.html",
        {"form": form, "result": result, "url": url},
    )
    response["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response["Pragma"]  = "no-cache"
    response["Expires"] = "0"
    return response


# ===========================================================================
# Subnet / CIDR Calculator
# ===========================================================================

@trim_memory_after
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def subnet_calculator(request):
    from ..forms import SubnetCalculatorForm
    from ..subnet_calculator_utils import calculate_subnet_details

    form    = SubnetCalculatorForm(request.POST or None)
    context = {"form": form}

    if request.method == "POST" and form.is_valid():
        ip   = form.cleaned_data["ip_address"]
        cidr = form.cleaned_data["cidr"]
        results, error = calculate_subnet_details(ip, cidr)
        if error:
            form.add_error(None, error)
        else:
            context["results"] = results

    return render(request, "projects/subnet_calculator.html", context)


# ===========================================================================
# SPF / DKIM / DMARC Validator
# ===========================================================================

@trim_memory_after
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def email_auth_validator(request):
    from ..forms import EmailAuthForm
    from ..email_auth_utils import validate_email_auth

    form    = EmailAuthForm(request.POST or None)
    context = {"form": form}

    if request.method == "POST" and form.is_valid():
        domain   = form.cleaned_data["domain"]
        selector = form.cleaned_data["dkim_selector"]
        context["results"] = validate_email_auth(domain, selector)
        context["domain"]  = domain

    return render(request, "projects/email_auth_validator.html", context)


# ===========================================================================
# WHOIS Lookup Tool
# ===========================================================================

@trim_memory_after
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def whois_lookup(request):
    from ..forms import WhoisForm
    from ..whois_utils import perform_whois_lookup

    form    = WhoisForm(request.POST or None)
    context = {"form": form}

    if request.method == "POST" and form.is_valid():
        domain  = form.cleaned_data["domain"]
        results = perform_whois_lookup(domain)

        if "error" in results:
            context["error_message"] = results["error"]
        else:
            context["results"] = results
            context["domain"]  = domain

    return render(request, "projects/whois_lookup.html", context)


# ===========================================================================
# HTTP Header Inspector
# ===========================================================================

@trim_memory_after
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def http_header_inspector(request):
    from ..forms import HttpHeaderForm
    from ..http_headers_utils import fetch_http_headers

    form    = HttpHeaderForm(request.POST or None)
    context = {"form": form}

    if request.method == "POST" and form.is_valid():
        url     = form.cleaned_data["url"]
        results = fetch_http_headers(url)

        if "error" in results:
            context["error_message"] = results["error"]
        else:
            context["results"]    = results
            context["target_url"] = url

    return render(request, "projects/http_header_inspector.html", context)


# ===========================================================================
# Redirect Chain Checker
# ===========================================================================

@trim_memory_after
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def redirect_checker_view(request):
    """
    GET : Display the empty Redirect Chain Checker form.
    POST: Validate the URL, trace the redirect chain, render results.
    """
    from ..forms import RedirectCheckerForm
    from ..redirect_checker_utils import trace_redirects

    form   = RedirectCheckerForm()
    result = None

    if request.method == "POST":
        form = RedirectCheckerForm(request.POST)
        if form.is_valid():
            url    = form.cleaned_data["url"]
            result = trace_redirects(url)

    return render(
        request,
        "projects/redirect_checker.html",
        {"form": form, "result": result},
    )


# ===========================================================================
# JSON-LD Structured Data Validator
# ===========================================================================

@trim_memory_after
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def jsonld_validator_view(request):
    """
    GET : Display the empty JSON-LD Validator form.
    POST: Validate the URL, extract and validate JSON-LD, render results.
    """
    from ..forms import JsonLdValidatorForm
    from ..jsonld_validator_vutils import validate_jsonld

    form   = JsonLdValidatorForm()
    result = None

    if request.method == "POST":
        form = JsonLdValidatorForm(request.POST)
        if form.is_valid():
            url    = form.cleaned_data["url"]
            result = validate_jsonld(url)

    return render(
        request,
        "projects/jsonld_validator.html",
        {"form": form, "result": result},
    )


# ===========================================================================
# Robots.txt Analyzer
# ===========================================================================

@trim_memory_after
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def robots_analyzer_view(request):
    """
    GET : Display the empty Robots.txt Analyzer form.
    POST: Validate the domain, fetch and analyze robots.txt, render results.
    """
    from ..forms import RobotsAnalyzerForm
    from ..robots_analyzer_utils import analyze_robots

    form   = RobotsAnalyzerForm()
    result = None

    if request.method == "POST":
        form = RobotsAnalyzerForm(request.POST)
        if form.is_valid():
            domain    = form.cleaned_data["domain"]
            test_path = form.cleaned_data.get("test_path", "")
            result    = analyze_robots(domain, test_path)

    return render(
        request,
        "projects/robots_analyzer.html",
        {"form": form, "result": result},
    )


# ===========================================================================
# Cron Expression Builder & Validator
# ===========================================================================

@trim_memory_after
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def cron_builder(request):
    """
    GET  → render the empty builder with preset library and blank form.
    POST → validate, parse, and return description + next-run schedule.
    """
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
    from ..forms import CronBuilderForm
    from ..cron_builder_utils import (
        COMMON_TIMEZONES,
        PRESETS,
        DEFAULT_RUNS,
        CRONITER_AVAILABLE,
        get_cron_description,
        generate_next_runs,
        build_field_breakdown,
        validate_cron_expression,
    )

    base_context = {
        "timezones":          COMMON_TIMEZONES,
        "presets":            PRESETS,
        "num_runs":           DEFAULT_RUNS,
        "tz_selected":        "America/Chicago",
        "croniter_available": CRONITER_AVAILABLE,
    }

    if not CRONITER_AVAILABLE:
        base_context["library_error"] = (
            "The 'croniter' library is not installed. "
            "Add croniter>=1.4.1 to requirements.txt and redeploy."
        )
        return render(request, "projects/cron_builder.html", base_context)

    form = CronBuilderForm(
        request.POST or None,
        initial={"tz_select": "America/Chicago", "num_runs": DEFAULT_RUNS},
    )
    base_context["form"] = form

    if request.method != "POST":
        return render(request, "projects/cron_builder.html", base_context)

    if not form.is_valid():
        return render(request, "projects/cron_builder.html", base_context)

    # Validated data
    expression = form.cleaned_data["cron_expression"]
    tz_str     = form.cleaned_data["tz_select"]
    num_runs   = form.cleaned_data["num_runs"]

    base_context["expression"] = expression
    base_context["tz_selected"] = tz_str
    base_context["num_runs"]   = num_runs

    # Cron syntax validation
    is_valid, error_msg = validate_cron_expression(expression)
    if not is_valid:
        base_context["error"] = error_msg
        return render(request, "projects/cron_builder.html", base_context)

    # Timezone lookup
    try:
        tz = ZoneInfo(tz_str)
    except (ZoneInfoNotFoundError, KeyError):
        base_context["error"] = (
            f"Unknown timezone: '{tz_str}'. Please select from the list."
        )
        return render(request, "projects/cron_builder.html", base_context)

    # Build outputs
    try:
        description     = get_cron_description(expression)
        next_runs       = generate_next_runs(expression, tz, num_runs)
        field_breakdown = build_field_breakdown(expression)
    except Exception as exc:
        base_context["error"] = (
            f"Unexpected error while processing expression: {exc}"
        )
        return render(request, "projects/cron_builder.html", base_context)

    if not next_runs:
        base_context["warning"] = (
            "No upcoming runs were found for this expression. "
            "It may reference dates that have already passed or are unreachable."
        )

    base_context.update({
        "description":     description,
        "next_runs":       next_runs,
        "field_breakdown": field_breakdown,
    })

    return render(request, "projects/cron_builder.html", base_context)


# ===========================================================================
# Unix Timestamp Converter (Epoch ↔ Human)
# ===========================================================================

@trim_memory_after
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
def timestamp_converter(request):
    """
    GET  → render the empty form, pre-populated with the current epoch.
    POST → process either epoch→human or human→epoch conversion.
    """
    import datetime
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
    from ..forms import EpochToHumanForm, HumanToEpochForm
    from ..timestamp_converter_utils import (
        COMMON_TIMEZONES,
        safe_epoch_to_dt,
        build_tz_table,
        relative_time,
        get_current_epoch,
    )

    current_epoch, current_epoch_ms = get_current_epoch()

    context = {
        "timezones":        COMMON_TIMEZONES,
        "current_epoch":    current_epoch,
        "current_epoch_ms": current_epoch_ms,
        "mode":             "epoch_to_human",   # default tab
        "tz_selected":      "America/Chicago",
    }

    if request.method != "POST":
        context["form_epoch"] = EpochToHumanForm()
        context["form_human"] = HumanToEpochForm(
            initial={"tz_select": "America/Chicago"}
        )
        return render(request, "projects/timestamp_converter.html", context)

    mode = request.POST.get("mode", "epoch_to_human")
    context["mode"] = mode

    # Mode A: Epoch → Human
    if mode == "epoch_to_human":
        form = EpochToHumanForm(request.POST)
        context["form_epoch"] = form
        context["form_human"] = HumanToEpochForm(
            initial={"tz_select": "America/Chicago"}
        )

        if not form.is_valid():
            context["error"] = form.errors.get("epoch_input", ["Invalid input."])[0]
            return render(request, "projects/timestamp_converter.html", context)

        raw = form.cleaned_data["epoch_input"]
        context["epoch_input"] = raw

        try:
            dt_utc, epoch_clean = safe_epoch_to_dt(raw)
        except ValueError as exc:
            context["error"] = str(exc)
            return render(request, "projects/timestamp_converter.html", context)

        context.update({
            "epoch_clean": int(epoch_clean),
            "epoch_ms":    int(epoch_clean * 1000),
            "iso8601_utc": dt_utc.isoformat(),
            "relative":    relative_time(epoch_clean),
            "tz_table":    build_tz_table(dt_utc, COMMON_TIMEZONES),
        })

    # Mode B: Human → Epoch
    elif mode == "human_to_epoch":
        form = HumanToEpochForm(request.POST)
        context["form_epoch"] = EpochToHumanForm()
        context["form_human"] = form

        tz_str = request.POST.get("tz_select", "America/Chicago").strip()
        context["tz_selected"] = tz_str

        if not form.is_valid():
            for field_errors in form.errors.values():
                context["error"] = field_errors[0]
                break
            return render(request, "projects/timestamp_converter.html", context)

        date_obj = form.cleaned_data["date_input"]   # datetime.date
        time_str = form.cleaned_data["time_input"]   # "HH:MM:SS"
        tz_str   = form.cleaned_data["tz_select"]

        context["date_input"]  = date_obj.strftime("%Y-%m-%d")
        context["time_input"]  = time_str[:5]         # trim to HH:MM for the input
        context["tz_selected"] = tz_str

        try:
            tz = ZoneInfo(tz_str)
        except (ZoneInfoNotFoundError, KeyError):
            context["error"] = f"Unknown timezone: '{tz_str}'."
            return render(request, "projects/timestamp_converter.html", context)

        try:
            dt_naive = datetime.datetime.strptime(
                f"{date_obj.strftime('%Y-%m-%d')} {time_str}",
                "%Y-%m-%d %H:%M:%S",
            )
        except ValueError:
            context["error"] = (
                "Could not parse date/time. "
                "Expected YYYY-MM-DD and HH:MM or HH:MM:SS."
            )
            return render(request, "projects/timestamp_converter.html", context)

        dt_aware     = dt_naive.replace(tzinfo=tz)
        epoch_result = int(dt_aware.timestamp())
        dt_utc       = dt_aware.astimezone(ZoneInfo("UTC"))

        context.update({
            "epoch_result": epoch_result,
            "epoch_ms":     epoch_result * 1000,
            "iso8601_utc":  dt_utc.isoformat(),
            "relative":     relative_time(epoch_result),
            "tz_table":     build_tz_table(dt_utc, COMMON_TIMEZONES),
        })

    else:
        context["error"] = "Invalid mode. Please use the form buttons."

    return render(request, "projects/timestamp_converter.html", context)
