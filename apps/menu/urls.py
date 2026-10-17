"""URL routing for the menu app."""
from django.urls import path

from . import views, views_admin

app_name = "menu"

urlpatterns = [
    path(
        "dashboard/",
        views_admin.supermarket_dashboard,
        name="dashboard",
    ),
    path(
        "products/",
        views_admin.menu_management,
        name="management",
    ),
    path(
        "inventory/",
        views_admin.inventory_management,
        name="inventory",
    ),
    path(
        "import-export/",
        views_admin.import_export_view,
        name="import_export",
    ),
    path(
        "menu/dashboard/",
        views_admin.supermarket_dashboard,
    ),
    path(
        "items/<int:pk>/toggle-availability/",
        views.toggle_availability,
        name="toggle_availability",
    ),
    path(
        "menu/items/<int:pk>/toggle-availability/",
        views.toggle_availability,
    ),
    # Category CRUD
    path("categories/new/", views_admin.category_create, name="category_create"),
    path("categories/<int:pk>/edit/", views_admin.category_edit, name="category_edit"),
    path("menu/categories/new/", views_admin.category_create),
    path("menu/categories/<int:pk>/edit/", views_admin.category_edit),
    # Menu-item CRUD
    path("items/new/", views_admin.item_create, name="item_create"),
    path("items/<int:pk>/edit/", views_admin.item_edit, name="item_edit"),
    path("items/<int:pk>/delete/", views_admin.item_delete, name="item_delete"),
    path("menu/items/new/", views_admin.item_create),
    path("menu/items/<int:pk>/edit/", views_admin.item_edit),
    path("menu/items/<int:pk>/delete/", views_admin.item_delete),
]
