from django.contrib import admin
from django.urls import path, include, re_path
from django.conf.urls import handler404
from django.views.generic.base import RedirectView

handler404 = "projects.views.view_404"

# ---------------------------------------------------------------------------
# 1. Mapping of old (underscore / outdated) slugs to current (dashed) slugs.
#    NOTE: ("all_projects", "") is handled manually below to avoid a
#    double-slash destination ("/projects//").
# ---------------------------------------------------------------------------
mappings = [
    ("cron_builder", "cron-builder"),
    ("timestamp_converter", "unix-timestamp-converter"),
    ("timestamp-converter", "unix-timestamp-converter"),
    ("unix_timestamp_converter", "unix-timestamp-converter"),
    ("ai_api_cost_estimator", "ai-api-cost-estimator"),
    ("satellite_pass_predictor", "satellite-pass-predictor"),
    ("space_and_astronomy", "space-and-astronomy"),
    ("robots_analyzer", "robots-analyzer"),
    ("jsonld_validator", "jsonld-validator"),
    ("redirect_checker", "redirect-checker"),
    ("coax_cable_loss_calculator", "coax-cable-loss-calculator"),
    ("rf_exposure_calculator", "rf-exposure-calculator"),
    ("grid_square_converter", "grid-square-converter"),
    ("antenna-calculator", "antenna-length-calculator"),
    ("antenna_length_calculator", "antenna-length-calculator"),
    ("antenna_calculator", "antenna-length-calculator"),
    ("repeater_finder", "repeater-finder"),
    ("band_plan_checker", "band-plan-checker"),
    ("radio_tools", "radio-tools"),
    ("freight_margin_calculator", "freight-margin-calculator"),
    ("partial_rate_calculator", "partial-rate-calculator"),
    ("deadhead_calculator", "deadhead-calculator"),
    ("multi_stop_splitter", "multi-stop-mileage-splitter"),
    ("multi_stop_mileage_splitter", "multi-stop-mileage-splitter"),
    ("multi-stop-splitter", "multi-stop-mileage-splitter"),
    ("lane_rate_analyzer", "freight-lane-rate-analyzer"),
    ("lane-rate-analyzer", "freight-lane-rate-analyzer"),
    ("freight_lane_rate_analyzer", "freight-lane-rate-analyzer"),
    ("glass_reaction_checker", "glass-reaction-checker"),
    ("frit_mixing_calculator", "frit-mixing-calculator"),
    ("circle_cutter_calculator", "circle-cutter-calculator"),
    ("tie_down_calculator", "tie-down-calculator"),
    ("cost_per_mile_calculator", "cost-per-mile-calculator"),
    ("linear_foot_calculator", "linear-foot-calculator"),
    ("detention_layover_fee_calculator", "detention-layover-fee-calculator"),
    ("warehouse_storage_calculator", "warehouse-storage-calculator"),
    ("freight_tools", "freight-tools"),
    ("freight_class_calculator", "freight-class-calculator"),
    ("fuel_surcharge_calculator", "fuel-surcharge-calculator"),
    ("hos_trip_planner", "hos-trip-planner"),
    ("lampwork_materials", "lampwork-materials"),
    ("glass_volume_calculator", "glass-volume-calculator"),
    ("kiln_controller_utils", "kiln-controller-utils"),
    ("kiln_schedule_generator", "kiln-schedule-generator"),
    ("stained_glass_cost_estimator", "stained-glass-cost-estimator"),
    ("stained_glass_estimator", "stained-glass-cost-estimator"),
    ("stained-glass-estimator", "stained-glass-cost-estimator"),
    ("stained_glass_materials", "stained-glass-materials"),
    ("glass_artist_toolkit", "glass-artist-toolkit"),
    ("seo_tools", "seo-tools"),
    ("cookie_audit", "cookie-audit"),
    ("font_inspector", "font-inspector"),
    ("ham_radio_call_sign_lookup", "ham-radio-call-sign-lookup"),
    ("xml_splitter", "xml-splitter"),
    ("qr_code_generator", "qr-code-generator"),
    ("monte_carlo_simulator", "monte-carlo-simulator"),
    ("grade_level_analyzer", "grade-level-analyzer"),
    ("freight_safety", "freight-safety"),
    ("seo_head_checker", "seo-head-checker"),
    ("iss_tracker", "iss-tracker"),
    ("ssl_check", "ssl-check"),
    ("ip_tool", "ip-tool"),
    ("dns_tool", "dns-lookup"),
    ("it_tools", "it-tools"),
]

# ---------------------------------------------------------------------------
# 2. Build programmatic redirect patterns from the mappings above.
# ---------------------------------------------------------------------------
redirect_patterns = []

for old, new in mappings:
    destination = f"/projects/{new}/"

    # A. Redirect legacy/underscore slugs → canonical dashed URL.
    #    Only generated when old != new (avoids a self-redirect).
    if old != new:
        # /projects/old_name  OR  /projects/old_name/
        redirect_patterns.append(
            re_path(
                rf"^projects/{old}/?$",
                RedirectView.as_view(url=destination, permanent=True),
            )
        )
        # /old_name  OR  /old_name/  (root-level → /projects/ namespace)
        redirect_patterns.append(
            re_path(
                rf"^{old}/?$",
                RedirectView.as_view(url=destination, permanent=True),
            )
        )

    # B. Canonicalization for the current dashed slug.

    # /projects/new-name  (missing trailing slash) → /projects/new-name/
    # Deliberately matches WITHOUT slash only to avoid looping with the
    # include that serves the canonical /projects/new-name/ URL.
    redirect_patterns.append(
        re_path(
            rf"^projects/{new}$",
            RedirectView.as_view(url=destination, permanent=True),
        )
    )

    # /new-name  OR  /new-name/  (root-level → /projects/ namespace)
    redirect_patterns.append(
        re_path(
            rf"^{new}/?$",
            RedirectView.as_view(url=destination, permanent=True),
        )
    )

# ---------------------------------------------------------------------------
# 3. Assemble urlpatterns.
#    Order: manual redirects → programmatic redirects → app include (last).
#    Placing the include last ensures specific redirects always take
#    precedence and aren't shadowed by a broad include match.
# ---------------------------------------------------------------------------
urlpatterns = [
    # path("admin/", admin.site.urls),

    # -- Manual "all projects" redirects --
    re_path(
        r"^projects/all_projects/?$",
        RedirectView.as_view(url="/projects/", permanent=True),
    ),
    re_path(
        r"^projects/all-projects/?$",
        RedirectView.as_view(url="/projects/", permanent=True),
    ),
    re_path(
        r"^all_projects/?$",
        RedirectView.as_view(url="/projects/", permanent=True),
    ),
    re_path(
        r"^all-projects/?$",
        RedirectView.as_view(url="/projects/", permanent=True),
    ),
    # /projects (no trailing slash) → /projects/
    # Uses $ (NOT /?$) so that /projects/ itself falls through to the
    # include below and is served normally — preventing a redirect loop.
    re_path(
        r"^projects$",
        RedirectView.as_view(url="/projects/", permanent=True),
    ),

    # -- Programmatic redirects (generated from mappings) --
    *redirect_patterns,

    # -- Main app include (last, so redirects above take precedence) --
    path("", include("projects.urls")),
]
