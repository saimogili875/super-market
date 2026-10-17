"""Core app URLs."""
from django.urls import path
from . import views

app_name = "core"

urlpatterns = [
    path("settings/", views.admin_settings, name="admin_settings"),
]
