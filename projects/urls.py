from django.urls import path
from . import views
from django.contrib.sitemaps.views import sitemap
from .sitemap import StaticViewSitemap, RootSitemap
from django.views.generic import RedirectView
from .views import robots_txt, requirements_txt, runtime_txt

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
]
