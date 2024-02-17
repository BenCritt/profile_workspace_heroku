from django.urls import path
from . import views
from django.conf.urls import handler404
from projects.views import view_404

handler404 = view_404

app_name = "projects"

urlpatterns = [
    path("home/", views.home, name="home"),
    path("resume/", views.resume, name="resume"),
    path("qr_code_generator/", views.qr_code_generator, name="qr_code_generator"),
    path("contact/", views.contact, name="contact"),
    path("", views.home, name="home"),
    path(
        "monte_carlo_simulator/",
        views.monte_carlo_simulator,
        name="monte_carlo_simulator",
    ),
    path("weather/", views.weather, name="weather"),
    path("weather_results/", views.weather, name="weather"),
    path("all_projects/", views.all_projects, name="all_projects"),
]
