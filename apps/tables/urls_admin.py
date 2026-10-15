"""URL patterns for admin-scoped dining table endpoints."""
from django.urls import path

from . import views, views_admin

app_name = "tables_admin"

urlpatterns = [
    path("dashboard/", views_admin.tables_management, name="management"),
    path("new/", views_admin.table_create, name="table_create"),
    path("<int:pk>/edit/", views_admin.table_edit, name="table_edit"),
    path("<int:pk>/deactivate/", views_admin.table_deactivate, name="table_deactivate"),
    path("sessions/", views_admin.sessions_list, name="sessions"),
    path("clear-bill/<int:session_id>/", views.clear_bill, name="clear_bill"),
]
