"""URL routing for the menu app."""
from django.urls import path

from . import views, views_admin

app_name = "menu"

urlpatterns = [
    path(
        "dashboard/",
        views_admin.menu_management,
        name="management",
    ),
    path(
        "items/<int:pk>/toggle-availability/",
        views.toggle_availability,
        name="toggle_availability",
    ),
    # Category CRUD
    path("categories/new/", views_admin.category_create, name="category_create"),
    path("categories/<int:pk>/edit/", views_admin.category_edit, name="category_edit"),
    # Menu-item CRUD
    path("items/new/", views_admin.item_create, name="item_create"),
    path("items/<int:pk>/edit/", views_admin.item_edit, name="item_edit"),
    path("items/<int:pk>/delete/", views_admin.item_delete, name="item_delete"),
]
