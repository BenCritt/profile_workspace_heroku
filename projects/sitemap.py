from django.urls import reverse
from django.contrib.sitemaps import Sitemap


class RootSitemap(Sitemap):
    protocol = "https"
    priority = 1.0
    changefreq = "daily"

    # MUST be a method
    def items(self):
        return ["projects:home"]

    def location(self, item):
        # Get the path.
        path = reverse(item)
        # Remove the trailing slash.
        if path == "/":
            return ""
        return path


class StaticViewSitemap(Sitemap):
    protocol = "https"
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
            "projects:xml_splitter",
            "projects:ham_radio_call_sign_lookup",
            "projects:font_inspector",
            "projects:cookie_audit",
            "projects:seo_tools",
            "projects:glass_volume_calculator",
            "projects:kiln_controller_utils",
            "projects:kiln_schedule_generator",
            "projects:stained_glass_cost_estimator",
            "projects:stained_glass_materials",
            "projects:glass_artist_toolkit",
            "projects:lampwork_materials",
        ]

    def location(self, item):
        return reverse(item)
