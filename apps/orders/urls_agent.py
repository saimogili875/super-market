"""Agent delivery-dashboard URL routes (login required, role=AGENT).

Namespace: orders_agent
"""
from django.urls import path

from . import views_agent

app_name = "orders_agent"

urlpatterns = [
    path("", views_agent.dashboard, name="dashboard"),
    path("orders/<int:pk>/status", views_agent.update_status, name="update_status"),
    path("availability", views_agent.toggle_availability, name="toggle_availability"),
]
