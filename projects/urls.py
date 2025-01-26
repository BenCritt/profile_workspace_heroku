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
    # path("home/", views.home, name="home"), I only want the homepage shown at the root.
    path("robots.txt", robots_txt, name="robots_txt"),
    path("requirements.txt", requirements_txt, name="requirements_txt"),
    path("runtime.txt", runtime_txt, name="runtime_txt"),
    path("", views.home, name="home"),
    path("resume/", views.resume, name="resume"),
    path("qr_code_generator/", views.qr_code_generator, name="qr_code_generator"),
    path("contact/", views.contact, name="contact"),
    path(
        "monte_carlo_simulator/",
        views.monte_carlo_simulator,
        name="monte_carlo_simulator",
    ),
    path("weather/", views.weather, name="weather"),
    path("weather_results/", views.weather, name="weather_results"),
    path("all_projects/", views.all_projects, name="all_projects"),
    path("sitemap.xml", sitemap, {"sitemaps": sitemaps}, name="sitemap"),
    path(
        "grade_level_analyzer/",
        views.grade_level_analyzer,
        name="grade_level_analyzer",
    ),
    path("site.webmanifest", views.manifest, name="manifest"),
    path("dns_tool/", views.dns_tool, name="dns_tool"),
    path("ip_tool/", views.ip_tool, name="ip_tool"),
    path("ssl_check/", views.ssl_check, name="ssl_check"),
    path("projects/it_tools/", views.it_tools, name="it_tools"),
    path(
        "service-worker.js",
        TemplateView.as_view(
            template_name="service-worker.js", content_type="application/javascript"
        ),
    ),
    path("freight_safety/", views.freight_safety, name="freight_safety"),
    path("seo_head_checker/", views.seo_head_checker, name="seo_head_checker"),
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
    path("iss_tracker/", views.iss_tracker, name="iss_tracker"),
    path("current-iss-data/", views.current_iss_data, name="current_iss_data"),
]

"""
# I'm working on implementing redirects at the back-end due to a limit in my Cloudflare account.

from django.urls import path
from . import views
from django.contrib.sitemaps.views import sitemap
from .sitemap import StaticViewSitemap, RootSitemap
from django.views.generic.base import RedirectView
from django.views.generic import TemplateView
from .views import (
    robots_txt,
    requirements_txt,
    runtime_txt,
    start_sitemap_processing,
    get_task_status,
    download_task_file,
)

app_name = "projects"

sitemaps = {
    "root": RootSitemap,
    "static": StaticViewSitemap,
}

redirects = {
    "qr_code_generator": "/projects/qr_code_generator/",
    "monte_carlo_simulator": "/projects/monte_carlo_simulator/",
    "weather": "/projects/weather/",
    "grade_level_analyzer": "/projects/grade_level_analyzer/",
    "freight_safety": "/projects/freight_safety/",
    "seo_head_checker": "/projects/seo_head_checker/",
    "iss_tracker": "/projects/iss_tracker/",
    "ssl_check": "/projects/ssl_check/",
    "ip_tool": "/projects/ip_tool/",
    "dns_tool": "/projects/dns_tool/",
    "it_tools": "/projects/it_tools/",
    "all_projects": "/projects/all_projects/",
}


# Main URL patterns
urlpatterns = [
    # Direct paths
    path("", views.home, name="home"),
    path("resume/", views.resume, name="resume"),
    path("qr_code_generator/", views.qr_code_generator, name="qr_code_generator"),
    path("contact/", views.contact, name="contact"),
    path(
        "monte_carlo_simulator/",
        views.monte_carlo_simulator,
        name="monte_carlo_simulator",
    ),
    path("weather/", views.weather, name="weather"),
    path("weather_results/", views.weather, name="weather_results"),
    path("all_projects/", views.all_projects, name="all_projects"),
    path("sitemap.xml", sitemap, {"sitemaps": sitemaps}, name="sitemap"),
    path(
        "grade_level_analyzer/", views.grade_level_analyzer, name="grade_level_analyzer"
    ),
    path("site.webmanifest", views.manifest, name="manifest"),
    path("dns_tool/", views.dns_tool, name="dns_tool"),
    path("ip_tool/", views.ip_tool, name="ip_tool"),
    path("ssl_check/", views.ssl_check, name="ssl_check"),
    path("projects/it_tools/", views.it_tools, name="it_tools"),
    path(
        "service-worker.js",
        TemplateView.as_view(
            template_name="service-worker.js", content_type="application/javascript"
        ),
    ),
    path("freight_safety/", views.freight_safety, name="freight_safety"),
    path("seo_head_checker/", views.seo_head_checker, name="seo_head_checker"),
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
    path("iss_tracker/", views.iss_tracker, name="iss_tracker"),
    path("current-iss-data/", views.current_iss_data, name="current_iss_data"),
    path("robots.txt", robots_txt, name="robots_txt"),
    path("requirements.txt", requirements_txt, name="requirements_txt"),
    path("runtime.txt", runtime_txt, name="runtime_txt"),
]

# Add RedirectView patterns dynamically
urlpatterns += (
    [
        # Handle /projects/<key> → /projects/<key>/
        path(f"projects/{key}", RedirectView.as_view(url=value, permanent=True))
        for key, value in redirects.items()
    ]
    + [
        # Handle /<key>/ → /projects/<key>/
        path(f"{key}/", RedirectView.as_view(url=value, permanent=True))
        for key, value in redirects.items()
    ]
    + [
        # Handle /<key> → /projects/<key>/
        path(key, RedirectView.as_view(url=value, permanent=True))
        for key, value in redirects.items()
    ]
)

"""
