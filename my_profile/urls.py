from django.contrib import admin
from django.urls import path, include, re_path
from django.conf.urls import handler404
from django.views.generic.base import RedirectView

handler404 = "projects.views.view_404"

urlpatterns = [
    # path("admin/", admin.site.urls),
    path(
        "", include("projects.urls")
    ),  # Ensures "" is home, "/projects/" is all_projects
    # Redirects.
    re_path(
        r"^projects/all_projects/?$",
        RedirectView.as_view(url="/projects/", permanent=True),
    ),
    re_path(
        r"^projects/all-projects/?$",
        RedirectView.as_view(url="/projects/", permanent=True),
    ),
    re_path(
        r"^all_projects/?$",
        RedirectView.as_view(url="/projects/", permanent=True),
    ),
    re_path(
        r"^all-projects/?$",
        RedirectView.as_view(url="/projects/", permanent=True),
    ),
    re_path(r"^projects/?$", RedirectView.as_view(url="/projects/", permanent=True)),
]

# Mapping of old (underscore) URLs to new (dashed) URLs
mappings = [
    ("ham_radio_call_sign_lookup", "ham-radio-call-sign-lookup"),
    ("xml_splitter", "xml-splitter"),
    ("qr_code_generator", "qr-code-generator"),
    ("monte_carlo_simulator", "monte-carlo-simulator"),
    ("grade_level_analyzer", "grade-level-analyzer"),
    ("freight_safety", "freight-safety"),
    ("seo_head_checker", "seo-head-checker"),
    ("iss_tracker", "iss-tracker"),
    ("ssl_check", "ssl-check"),
    ("ip_tool", "ip-tool"),
    ("dns_tool", "dns-lookup"),
    ("it_tools", "it-tools"),
    ("all_projects", ""),
]

# Generate URL patterns for each mapping
for old, new in mappings:
    urlpatterns.extend(
        [
            # Handle URLs with the "projects/" prefix
            re_path(
                rf"^projects/{old}$",
                RedirectView.as_view(url=f"/projects/{new}/", permanent=True),
            ),
            re_path(
                rf"^projects/{old}/$",
                RedirectView.as_view(url=f"/projects/{new}/", permanent=True),
            ),
            re_path(
                rf"^projects/{new}$",
                RedirectView.as_view(url=f"/projects/{new}/", permanent=True),
            ),
            re_path(
                rf"^projects/{new}/$",
                RedirectView.as_view(url=f"/projects/{new}/", permanent=True),
            ),
            # Handle URLs without the "projects/" prefix
            re_path(
                rf"^{old}$",
                RedirectView.as_view(url=f"/projects/{new}/", permanent=True),
            ),
            re_path(
                rf"^{old}/$",
                RedirectView.as_view(url=f"/projects/{new}/", permanent=True),
            ),
            re_path(
                rf"^{new}$",
                RedirectView.as_view(url=f"/projects/{new}/", permanent=True),
            ),
            re_path(
                rf"^{new}/$",
                RedirectView.as_view(url=f"/projects/{new}/", permanent=True),
            ),
        ]
    )
"""
# Redirect non-trailing slash URLs to trailing slash versions.
# Temporarily commenting out, as this might cause redirect loops.
urlpatterns.append(
    re_path(
        r"^(?P<path>.*[^/])$", RedirectView.as_view(url="/%(path)s/", permanent=True)
    )
)
"""
