"""Analytics URL routes (mounted under the env-configurable admin path).

Namespace: analytics
"""
from django.urls import path

from . import views

app_name = "analytics"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
]
