"""Admin-scoped account/agent management routes (mounted under the admin path).

Namespace: accounts_admin
"""
from django.urls import path

from . import views_admin

app_name = "accounts_admin"

urlpatterns = [
    path("", views_admin.agents, name="agents"),
    path("create/", views_admin.agent_create, name="agent_create"),
    path("<int:pk>/availability/", views_admin.agent_toggle_availability, name="agent_toggle"),
    path("<int:pk>/deactivate/", views_admin.agent_deactivate, name="agent_deactivate"),
    path("users/", views_admin.users, name="users"),
]
