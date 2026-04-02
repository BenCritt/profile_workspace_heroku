# views/__init__.py
#
# ============================================================================
# PACKAGE OVERVIEW
# ============================================================================
# This file turns the `views/` directory into a proper Python package and
# serves as its public re-export surface.
#
# BACKGROUND — WHY THIS FILE EXISTS:
#   The original codebase used a single monolithic views.py file.  As the
#   tool count grew past 50, that file became unwieldy to navigate and edit.
#   It was split into per-category modules:
#
#       views_core.py          — home, all_projects, manifest, sitemap helpers
#       views_it_tools.py      — IT/SysAdmin tool views
#       views_seo_tools.py     — SEO Professional Toolkit views
#       views_freight_tools.py — Freight Professional Toolkit views
#       views_glass_tools.py   — Glass Artist Toolkit views
#       views_radio_tools.py   — Radio Hobbyist Toolkit views
#       views_space_tools.py   — Space & Astronomy Toolkit views
#       views_misc.py          — Standalone miscellaneous tool views
#
#   urls.py was written to do `from . import views` (or equivalently
#   `from .views import some_view`).  Rather than rewrite all those import
#   paths, every public view function is re-exported here so the existing
#   urls.py continues to work unchanged.
#
# RULE: This file must contain ONLY import/re-export statements.
#       Business logic, constants, and helper functions belong in their
#       respective sub-modules.
#
# MAINTENANCE CHECKLIST:
#   When you add a new view function to any sub-module:
#     1. Add it to the `from .views_<category> import (...)` block below.
#     2. Add its name to __all__ in the matching section.
#   When you add a new sub-module entirely:
#     1. Create a new `from .views_<category> import (...)` block.
#     2. Add a new __all__ section for it.
# ============================================================================


# ----------------------------------------------------------------------------
# Core / Site-wide views
# ----------------------------------------------------------------------------
# home          — the portfolio landing page
# all_projects  — the full tool/project listing
# view_404      — custom 404 handler (registered in urls.py / settings.py)
# manifest      — serves /manifest.json for PWA support
# llms_txt      — serves /llms.txt (machine-readable site summary for AI crawlers)
# robots_txt    — serves /robots.txt (rendered from template, not static file)
# requirements_txt — serves /requirements.txt for transparency / llms context
# privacy_cookies  — privacy & cookie policy page
from .views_core import (
    home,
    all_projects,
    view_404,
    manifest,
    llms_txt,
    robots_txt,
    requirements_txt,
    privacy_cookies,
)

# ----------------------------------------------------------------------------
# IT & SysAdmin Toolkit views
# ----------------------------------------------------------------------------
# cookie_audit_*      — 5-endpoint async cookie audit tool (start/poll/download)
# it_tools            — hub page listing all IT tools
# Network/domain:     dns_tool, ip_tool, ssl_check, subnet_calculator,
#                     email_auth_validator, whois_lookup,
#                     http_header_inspector, redirect_checker_view,
#                     jsonld_validator_view, robots_analyzer_view
# File/utility:       font_inspector, xml_splitter
# Sysadmin helpers:   cron_builder, timestamp_converter
from .views_it_tools import (
    # Cookie Audit — async crawl pipeline (5 endpoints total)
    cookie_audit_view,    # renders the main form page
    cookie_audit_start,   # POST: kicks off the background crawl task
    cookie_audit_status,  # GET: polls task progress by task_id
    cookie_audit_results, # GET: fetches completed scan results
    cookie_audit_download,# GET: streams the results CSV to the browser
    # IT Toolkit hub page
    it_tools,
    # Network & domain analysis tools
    dns_tool,
    ip_tool,
    ssl_check,
    subnet_calculator,
    email_auth_validator,
    whois_lookup,
    http_header_inspector,
    redirect_checker_view,
    jsonld_validator_view,
    robots_analyzer_view,
    # File & encoding utilities
    font_inspector,
    xml_splitter,
    # Sysadmin command/time helpers
    cron_builder,
    timestamp_converter,
)

# ----------------------------------------------------------------------------
# SEO Professional Toolkit views
# ----------------------------------------------------------------------------
# seo_tools               — hub page
# seo_head_checker        — main form page for the sitemap/head auditor
# start_sitemap_processing— POST: launches Celery task to crawl sitemap URLs
# get_task_status         — GET: polls Celery task progress
# download_task_file      — GET: streams the completed audit CSV
# grade_level_analyzer    — Flesch-Kincaid / SMOG / Gunning Fog readability tool
# og_previewer            — Open Graph & Twitter Card social preview tool
from .views_seo_tools import (
    seo_tools,
    seo_head_checker,
    start_sitemap_processing,
    get_task_status,
    download_task_file,
    grade_level_analyzer,
    og_previewer,
)

# ----------------------------------------------------------------------------
# Freight Professional Toolkit views
# ----------------------------------------------------------------------------
# freight_tools              — hub page
# freight_class_calculator   — NMFC class from dims/weight (density method)
# fuel_surcharge_calculator  — carrier FSC based on DOE index
# hos_trip_planner           — FMCSA Hours of Service itinerary generator
# freight_safety             — FMCSA carrier safety lookup (by USDOT number)
# tie_down_calculator        — FMCSA-compliant tie-down count / WLL calculator
# cost_per_mile_calculator   — trucker CPM breakdown (fixed + variable costs)
# linear_foot_calculator     — LTL trailer linear foot & density visualizer
# detention_layover_fee_calculator — dwell time fee estimator
# warehouse_storage_calculator     — pallet/sqft storage cost calculator
# partial_rate_calculator    — partial TL rate from pallet count vs FTL base
# deadhead_calculator        — deadhead miles & cost vs loaded revenue
# multi_stop_splitter        — per-leg mileage split for multi-stop routes
# lane_rate_analyzer         — RPM breakdown with FSC for a given lane
# freight_margin_calculator  — gross margin / GP between customer & carrier
from .views_freight_tools import (
    freight_tools,
    freight_class_calculator,
    fuel_surcharge_calculator,
    hos_trip_planner,
    freight_safety,
    tie_down_calculator,
    cost_per_mile_calculator,
    linear_foot_calculator,
    detention_layover_fee_calculator,
    warehouse_storage_calculator,
    partial_rate_calculator,
    deadhead_calculator,
    multi_stop_splitter,
    lane_rate_analyzer,
    freight_margin_calculator,
    accessorial_fee_calculator,
)

# ----------------------------------------------------------------------------
# Glass Artist Toolkit views
# ----------------------------------------------------------------------------
# glass_artist_toolkit        — hub page
# glass_volume_calculator     — volume & weight for various glass blank shapes
# kiln_schedule_generator     — firing schedule by brand/project/thickness
# stained_glass_cost_estimator— labor + material cost estimator for commissions
# kiln_controller_utils       — temperature unit converter + ramp time calculator
# stained_glass_materials     — lead/copper foil/solder material estimator
# lampwork_materials          — rod/tube weight calculator for torchwork beads
# glass_reaction_checker      — silver/sulfur reaction lookup between glass codes
# frit_mixing_calculator      — frit-to-medium ratio for painting/screen work
# circle_cutter_calculator    — compass-cutter pivot offset for circles/ovals
from .views_glass_tools import (
    glass_artist_toolkit,
    glass_volume_calculator,
    kiln_schedule_generator,
    stained_glass_cost_estimator,
    kiln_controller_utils,
    stained_glass_materials,
    lampwork_materials,
    glass_reaction_checker,
    frit_mixing_calculator,
    circle_cutter_calculator,
)

# ----------------------------------------------------------------------------
# Radio Hobbyist Toolkit views
# ----------------------------------------------------------------------------
# radio_tools               — hub page
# ham_radio_call_sign_lookup— QRZ/HamDB callsign lookup (with fallback)
# band_plan_checker         — frequency → US amateur band + license privileges
# repeater_finder           — 3-endpoint async repeater search pipeline
# antenna_calculator        — dipole/quarter-wave/Yagi length from frequency
# grid_square_converter     — Maidenhead grid ↔ lat/lon ↔ ZIP code
# rf_exposure_calculator    — FCC OET Bulletin 65 MPE distance/compliance tool
# coax_cable_loss_calculator— per-100-ft coax loss by cable type & frequency
from .views_radio_tools import (
    radio_tools,
    ham_radio_call_sign_lookup,
    band_plan_checker,
    repeater_finder,
    repeater_finder_start,    # POST AJAX: starts the repeater search task
    repeater_finder_status,   # GET  AJAX: polls task status by task_id
    antenna_calculator,
    grid_square_converter,
    rf_exposure_calculator,
    coax_cable_loss_calculator,
)

# ----------------------------------------------------------------------------
# Space & Astronomy Toolkit views
# ----------------------------------------------------------------------------
# space_and_astronomy   — hub page
# iss_tracker           — real-time ISS position + next visible pass events
# satellite_pass_predictor — TLE-based satellite rise/culminate/set predictor
# lunar_phase_calendar  — monthly lunar phase grid with optional rise/set times
# night_sky_planner     — comprehensive dark-window, planet, and satellite report
#
# NOTE: _format_local_times is a private helper used only inside
# views_space_tools.py.  It is intentionally NOT exported here.
from .views_space_tools import (
    space_and_astronomy,
    iss_tracker,
    satellite_pass_predictor,
    lunar_phase_calendar,
    night_sky_planner,
)

# ----------------------------------------------------------------------------
# Miscellaneous standalone tool views
# ----------------------------------------------------------------------------
# qr_code_generator    — text/URL → downloadable QR code PNG
# monte_carlo_simulator— probability distribution simulator (PDF output)
# weather              — ZIP-code weather forecast via OpenWeatherMap API
# ai_api_cost_estimator— token count + multi-provider API cost estimator
from .views_misc import (
    qr_code_generator,
    monte_carlo_simulator,
    weather,
    ai_api_cost_estimator,
    job_fit_analyzer,
    job_fit_analyzer_status,
)


# ----------------------------------------------------------------------------
# __all__
# ----------------------------------------------------------------------------
# Explicit public API declaration.  This controls what `from .views import *`
# exposes and serves as an authoritative inventory of every routable view.
# Keep this in sync with the import blocks above.
# ----------------------------------------------------------------------------
__all__ = [
    # ── Core ──────────────────────────────────────────────────────────────
    "home", "all_projects", "view_404", "manifest",
    "llms_txt", "robots_txt", "requirements_txt", "privacy_cookies",

    # ── IT Tools ──────────────────────────────────────────────────────────
    "cookie_audit_view", "cookie_audit_start", "cookie_audit_status",
    "cookie_audit_results", "cookie_audit_download",
    "it_tools", "dns_tool", "ip_tool", "ssl_check",
    "subnet_calculator", "email_auth_validator", "whois_lookup",
    "http_header_inspector", "redirect_checker_view",
    "jsonld_validator_view", "robots_analyzer_view",
    "font_inspector", "xml_splitter", "cron_builder", "timestamp_converter",

    # ── SEO Tools ─────────────────────────────────────────────────────────
    "seo_tools", "seo_head_checker", "start_sitemap_processing",
    "get_task_status", "download_task_file", "grade_level_analyzer",
    "og_previewer",

    # ── Freight Tools ─────────────────────────────────────────────────────
    "freight_tools", "freight_class_calculator", "fuel_surcharge_calculator",
    "hos_trip_planner", "freight_safety", "tie_down_calculator",
    "cost_per_mile_calculator", "linear_foot_calculator",
    "detention_layover_fee_calculator", "warehouse_storage_calculator",
    "partial_rate_calculator", "deadhead_calculator", "multi_stop_splitter",
    "lane_rate_analyzer", "freight_margin_calculator", "accessorial_fee_calculator",

    # ── Glass Tools ───────────────────────────────────────────────────────
    "glass_artist_toolkit", "glass_volume_calculator", "kiln_schedule_generator",
    "stained_glass_cost_estimator", "kiln_controller_utils",
    "stained_glass_materials", "lampwork_materials", "glass_reaction_checker",
    "frit_mixing_calculator", "circle_cutter_calculator",

    # ── Radio Tools ───────────────────────────────────────────────────────
    "radio_tools", "ham_radio_call_sign_lookup", "band_plan_checker",
    "repeater_finder", "repeater_finder_start", "repeater_finder_status",
    "antenna_calculator", "grid_square_converter",
    "rf_exposure_calculator", "coax_cable_loss_calculator",

    # ── Space Tools ───────────────────────────────────────────────────────
    "space_and_astronomy", "iss_tracker", "satellite_pass_predictor",
    "lunar_phase_calendar", "night_sky_planner",

    # ── Misc ──────────────────────────────────────────────────────────────
    "qr_code_generator", "monte_carlo_simulator", "weather",
    "ai_api_cost_estimator","job_fit_analyzer", "job_fit_analyzer_status",
]