# In sitemap.py

from django.contrib import sitemaps
from django.urls import reverse
from django.contrib.sitemaps import Sitemap


class RootSitemap(Sitemap):
    priority = 1.0
    changefreq = "daily"

    def items(self):
        return ["home"]  # This is the homepage.

    def location(self, item):
        return "/"  # This is the root URL


class StaticViewSitemap(sitemaps.Sitemap):
    priority = 0.5
    changefreq = "weekly"

    def items(self):
        return [
            "/projects/resume/",
            "/projects/all_projects/",
            "/projects/qr_code_generator/",
            "/projects/monte_carlo_simulator/",
            "/projects/weather/",
            "/projects/contact/",
        ]  # Add more URLs as needed

    def location(self, item):
        return reverse(item)
