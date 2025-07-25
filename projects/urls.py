from django.urls import path
from . import views
from django.contrib.sitemaps.views import sitemap
from .sitemap import StaticViewSitemap, RootSitemap
from django.views.generic import RedirectView
from .views import robots_txt, requirements_txt, runtime_txt
from django.views.generic import TemplateView
from .views import start_sitemap_processing, get_task_status, download_task_file

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
    path("robots.txt", robots_txt, name="robots_txt"),
    path("requirements.txt", requirements_txt, name="requirements_txt"),
    path("runtime.txt", runtime_txt, name="runtime_txt"),
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
        start_sitemap_processing,
        name="start_sitemap_processing",
    ),
    path("get_task_status/<str:task_id>/", get_task_status, name="get_task_status"),
    path(
        "download_task_file/<str:task_id>/",
        download_task_file,
        name="download_task_file",
    ),
    path("current-iss-data/", views.current_iss_data, name="current_iss_data"),
    path("projects/xml-splitter/", views.xml_splitter, name="xml_splitter"),
    path("projects/ham-radio-call-sign-lookup/", views.ham_radio_call_sign_lookup, name="ham_radio_call_sign_lookup"),
]
