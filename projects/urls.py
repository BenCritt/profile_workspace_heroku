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
    # Font Inspector async endpoints
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
]
