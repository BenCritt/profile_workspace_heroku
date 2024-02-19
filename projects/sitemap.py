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
        return "/", "https"  # This is the root URL


class StaticViewSitemap(sitemaps.Sitemap):
    priority = 0.5
    changefreq = "weekly"

    def items(self):
        return [
            "resume",
            "all_projects",
            "qr_code_generator",
            "monte_carlo_simulator",
            "weather",
            "contact",
        ]  # Add more URLs as needed

    def location(self, item):
        return reverse("projects:" + item, scheme="https")
