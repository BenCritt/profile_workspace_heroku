# Import necessary Django modules and classes for sitemaps.
from django.contrib import sitemaps
from django.urls import reverse
from django.contrib.sitemaps import Sitemap


# Define a sitemap for the root URL of the website.
class RootSitemap(Sitemap):
    # Set the priority to the maximum (1.0) as this is the homepage.
    priority = 1.0
    # Indicate that the homepage changes daily.
    changefreq = "daily"

    # Define the items that will be included in this sitemap - only the homepage in this case.
    def items(self):
        return ["home"]  # This is the homepage.

    # Define how to determine the location (URL) for each item in the sitemap.
    def location(self, item):
        return "/"  # This is the root URL


# Define a sitemap for static views within the site.
class StaticViewSitemap(sitemaps.Sitemap):
    # Set a default priority for these pages, lower than the homepage.
    priority = 0.5
    # These pages are expected to change weekly.
    changefreq = "weekly"

    # List the named URL patterns for static pages to be included in the sitemap.
    def items(self):
        return [
            "all_projects",
            "qr_code_generator",
            "monte_carlo_simulator",
            "weather",
            "grade_level_analyzer",
            "dns_tool",
            "ip_tool",
            "ssl_check",
            "it_tools",
            "freight_safety",
        ]

    # Define how to determine the location (URL) for each item, using the 'reverse' function to find URLs by their name.
    def location(self, item):
        return reverse("projects:" + item)  # Dynamically create URLs for each item.
