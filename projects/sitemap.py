from django.urls import reverse
from django.contrib.sitemaps import Sitemap


class RootSitemap(Sitemap):
    protocol = "https"
    priority = 1.0
    changefreq = "daily"

    def items(self):
        return ["projects:home"]

    def location(self, item):
        path = reverse(item)
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
            "projects:glass_reaction_checker",
            "projects:frit_mixing_calculator",
            "projects:circle_cutter_calculator",
            "projects:freight_tools",
            "projects:freight_class_calculator",
            "projects:fuel_surcharge_calculator",
            "projects:hos_trip_planner",
            "projects:tie_down_calculator",
            "projects:cost_per_mile_calculator",
            "projects:linear_foot_calculator",
            "projects:detention_layover_fee_calculator",
            "projects:warehouse_storage_calculator",
            "projects:partial_rate_calculator",
            "projects:deadhead_calculator",
            "projects:multi_stop_splitter",
            "projects:lane_rate_analyzer",
            "projects:freight_margin_calculator",
            "projects:band_plan_checker",
            "projects:radio_tools",
            "projects:repeater_finder",
            "projects:antenna_calculator",
            "projects:grid_square_converter",
            "projects:rf_exposure_calculator",
            "projects:coax_cable_loss_calculator",
            "projects:subnet_calculator",
            "projects:email_auth_validator",
            "projects:whois_lookup",
            "projects:http_header_inspector",
            "projects:redirect_checker",
            "projects:jsonld_validator",
            "projects:robots_analyzer",
            "projects:space_and_astronomy",
            "projects:satellite_pass_predictor",
            "projects:ai_api_cost_estimator",
            "projects:timestamp_converter",
            "projects:cron_builder",
            "projects:og_previewer",
        ]

    def location(self, item):
        return reverse(item)