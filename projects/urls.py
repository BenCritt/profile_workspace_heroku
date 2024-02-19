from django.urls import path, register_converter
from django.urls.converters import HTTPSConverter
from . import views
from django.contrib.sitemaps.views import sitemap
from .sitemap import StaticViewSitemap, RootSitemap


app_name = "projects"

sitemaps = {
    "root": RootSitemap,
    "static": StaticViewSitemap,
}

urlpatterns = [
    # path("home/", views.home, name="home"),
    path("", views.home, name="home", scheme="https"),
    path("resume/", views.resume, name="resume", scheme="https"),
    path(
        "qr_code_generator/",
        views.qr_code_generator,
        name="qr_code_generator",
        scheme="https",
    ),
    path("contact/", views.contact, name="contact", scheme="https"),
    path(
        "monte_carlo_simulator/",
        views.monte_carlo_simulator,
        name="monte_carlo_simulator",
        scheme="https",
    ),
    path("weather/", views.weather, name="weather", scheme="https"),
    path("weather_results/", views.weather, name="weather_results", scheme="https"),
    path("all_projects/", views.all_projects, name="all_projects", scheme="https"),
    path("sitemap.xml", sitemap, {"sitemaps": sitemaps}, name="sitemap"),
]
