from django.urls import path
from . import views

app_name = "projects"

urlpatterns = [
    path("home/", views.home, name="home"),
    path("resume/", views.resume, name="resume"),
    path("qr_code_generator/", views.qr_code_generator, name="qr_code_generator"),
    path("contact/", views.contact, name="contact"),
    path("", views.home, name="home"),
]
