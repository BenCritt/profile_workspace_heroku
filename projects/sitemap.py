from django.urls import reverse
from django.contrib.sitemaps import Sitemap


class RootSitemap(Sitemap):
    priority = 1.0
    changefreq = "daily"

    # MUST be a method
    def items(self):
        return ["projects:home"]

    def location(self, item):
        return reverse(item)


class StaticViewSitemap(Sitemap):
    priority = 0.5
    changefreq = "weekly"

    def items(self):
        return [
            "projects:all_projects",
            "projects:qr_code_generator",
            "projects:monte_carlo_simulator",
            "projects:weather",
            "projects:grade_level_analyzer",
            "projects:dns_tool",
            "projects:ip_tool",
            "projects:ssl_check",
            "projects:it_tools",
            "projects:freight_safety",
            "projects:seo_head_checker",
            "projects:iss_tracker",
            "projects:xml_splitter",      # underscore, not hyphen
        ]

    def location(self, item):
        return reverse(item)
