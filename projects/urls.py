from django.urls import path
from . import views, iss_utils, seo_head_checker_utils, font_utils
from django.contrib.sitemaps.views import sitemap
from .sitemap import StaticViewSitemap, RootSitemap
from django.views.generic import RedirectView
from django.views.generic import TemplateView

app_name = "projects"

sitemaps = {
    "root": RootSitemap,
    "static": StaticViewSitemap,
}

urlpatterns = [
    path("projects/", views.all_projects, name="all_projects"),
    path(
        "projects/qr-code-generator/", views.qr_code_generator, name="qr_code_generator"
    ),
    path(
        "projects/monte-carlo-simulator/",
        views.monte_carlo_simulator,
        name="monte_carlo_simulator",
    ),
    path(
        "projects/grade-level-analyzer/",
        views.grade_level_analyzer,
        name="grade_level_analyzer",
    ),
    path("projects/freight-safety/", views.freight_safety, name="freight_safety"),
    path("projects/seo-head-checker/", views.seo_head_checker, name="seo_head_checker"),
    path("projects/iss-tracker/", views.iss_tracker, name="iss_tracker"),
    path("projects/ssl-check/", views.ssl_check, name="ssl_check"),
    path("projects/ip-tool/", views.ip_tool, name="ip_tool"),
    path("projects/dns-lookup/", views.dns_tool, name="dns_tool"),
    path("projects/it-tools/", views.it_tools, name="it_tools"),
    path("projects/seo-tools/", views.seo_tools, name="seo_tools"),
    path("robots.txt", views.robots_txt, name="robots_txt"),
    path("requirements.txt", views.requirements_txt, name="requirements_txt"),
    path("", views.home, name="home"),
    path("projects/weather/", views.weather, name="weather"),
    path("sitemap.xml", sitemap, {"sitemaps": sitemaps}, name="sitemap"),
    path("site.webmanifest", views.manifest, name="manifest"),
    path(
        "service-worker.js",
        TemplateView.as_view(
            template_name="service-worker.js", content_type="application/javascript"
        ),
    ),
    path(
        "start_sitemap_processing/",
        seo_head_checker_utils.start_sitemap_processing,
        name="start_sitemap_processing",
    ),
    path("get_task_status/<str:task_id>/", seo_head_checker_utils.get_task_status, name="get_task_status"),
    path(
        "download_task_file/<str:task_id>/",
        seo_head_checker_utils.download_task_file,
        name="download_task_file",
    ),
    path("current-iss-data/", iss_utils.current_iss_data, name="current_iss_data"),
    path("projects/xml-splitter/", views.xml_splitter, name="xml_splitter"),
    path("projects/ham-radio-call-sign-lookup/", views.ham_radio_call_sign_lookup, name="ham_radio_call_sign_lookup"),
    path("projects/font-inspector/", views.font_inspector, name="font_inspector"),
    path("llms.txt", views.llms_txt, name="llms_txt"),
    path("projects/font-inspector/start/", font_utils.start_font_inspector, name="start_font_inspector"),
    path("projects/font-inspector/status/<str:task_id>/", font_utils.fi_task_status, name="fi_task_status"),
    path("projects/font-inspector/rows/<str:task_id>/", font_utils.fi_rows, name="fi_rows"),
    path("projects/font-inspector/download/<str:task_id>/", font_utils.fi_download, name="fi_download"),
    path("projects/cookie-audit/", views.cookie_audit_view, name="cookie_audit"),
    path("projects/cookie-audit/start/", views.cookie_audit_start, name="cookie_audit_start"),
    path("projects/cookie-audit/status/<uuid:task_id>/", views.cookie_audit_status, name="cookie_audit_status"),
    path("projects/cookie-audit/results/<uuid:task_id>/", views.cookie_audit_results, name="cookie_audit_results"),
    path("projects/cookie-audit/download/<uuid:task_id>/", views.cookie_audit_download, name="cookie_audit_download",),
    path("privacy-cookies/", views.privacy_cookies, name="privacy_cookies"),
    path(
        "projects/glass-volume-calculator/", 
        views.glass_volume_calculator, 
        name="glass_volume_calculator"
    ),
    path(
        "projects/kiln-schedule-generator/", 
        views.kiln_schedule_generator, 
        name="kiln_schedule_generator"
    ),
    path(
        "projects/stained-glass-cost-estimator/", 
        views.stained_glass_cost_estimator, 
        name="stained_glass_cost_estimator"
    ),
    path(
        "projects/kiln-controller-utils/", 
        views.kiln_controller_utils, 
        name="kiln_controller_utils"
    ),
    path(
        "projects/stained-glass-materials/", 
        views.stained_glass_materials, 
        name="stained_glass_materials"
    ),
    path("projects/glass-artist-toolkit/", views.glass_artist_toolkit, name="glass_artist_toolkit"),
    path("projects/lampwork-materials/", views.lampwork_materials, name="lampwork_materials"),
    path("projects/freight-class-calculator/", views.freight_class_calculator, name="freight_class_calculator"),
    path("projects/fuel-surcharge-calculator/", views.fuel_surcharge_calculator, name="fuel_surcharge_calculator"),
    path("projects/hos-trip-planner/", views.hos_trip_planner, name="hos_trip_planner"),
    path("projects/freight-tools/", views.freight_tools, name="freight_tools"),
    path("projects/glass-reaction-checker/", views.glass_reaction_checker, name="glass_reaction_checker"),
    path("projects/frit-mixing-calculator/", views.frit_mixing_calculator, name="frit_mixing_calculator"),
    path("projects/circle-cutter-calculator/", views.circle_cutter_calculator, name="circle_cutter_calculator"),
    path("projects/tie-down-calculator/", views.tie_down_calculator, name="tie_down_calculator"),
    path("projects/cost-per-mile-calculator/", views.cost_per_mile_calculator, name="cost_per_mile_calculator"),
    path("projects/linear-foot-calculator/", views.linear_foot_calculator,name="linear_foot_calculator"),
    path("projects/detention-layover-fee-calculator/", views.detention_layover_fee_calculator, name="detention_layover_fee_calculator"),
    path("projects/warehouse-storage-calculator/", views.warehouse_storage_calculator, name="warehouse_storage_calculator"),
    path("projects/partial-rate-calculator/", views.partial_rate_calculator, name="partial_rate_calculator"),
    path("projects/deadhead-calculator/", views.deadhead_calculator, name="deadhead_calculator"),
    path("projects/multi-stop-mileage-splitter/", views.multi_stop_splitter, name="multi_stop_splitter"),
    path("projects/freight-lane-rate-analyzer/", views.lane_rate_analyzer, name="lane_rate_analyzer"),
    path("projects/freight-margin-calculator/", views.freight_margin_calculator, name="freight_margin_calculator"),
    path("projects/band-plan-checker/", views.band_plan_checker, name="band_plan_checker"),
    path("projects/radio-tools/", views.radio_tools, name="radio_tools"),
    path("projects/repeater-finder/", views.repeater_finder, name="repeater_finder"),
    path("projects/repeater-finder/start/", views.repeater_finder_start, name="repeater_finder_start"),
    path("projects/repeater-finder/status/<str:task_id>/", views.repeater_finder_status, name="repeater_finder_status"),
]
