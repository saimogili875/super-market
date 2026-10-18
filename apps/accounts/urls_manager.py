"""URL routing for Store Manager & Staff Portal.

Namespace: manager
"""
from django.urls import path
from . import views_manager

app_name = "manager"

urlpatterns = [
    # Authentication
    path("login/", views_manager.manager_login, name="login"),
    path("logout/", views_manager.manager_logout, name="logout"),

    # Dashboards
    path("", views_manager.manager_dashboard, name="dashboard"),
    path("dashboard/", views_manager.manager_dashboard, name="dashboard_alias"),
    path("staff-dashboard/", views_manager.staff_dashboard, name="staff_dashboard"),

    # Orders Pipeline & Pick/Pack Checklist
    path("orders/", views_manager.orders_list, name="orders"),
    path("orders/<int:pk>/", views_manager.order_detail, name="order_detail"),
    path("orders/<int:order_pk>/pick/<int:item_pk>/", views_manager.order_toggle_pick, name="order_toggle_pick"),
    path("orders/<int:pk>/action/", views_manager.order_action, name="order_action"),

    # Inventory & Stock Adjustments
    path("inventory/", views_manager.inventory_list, name="inventory"),
    path("inventory/adjust/", views_manager.inventory_adjust, name="inventory_adjust"),
    path("inventory/requests/", views_manager.stock_requests_list, name="stock_requests"),
    path("inventory/requests/<int:pk>/action/", views_manager.stock_request_action, name="stock_request_action"),

    # Products Catalog
    path("products/", views_manager.products_list, name="products"),
    path("products/add/", views_manager.product_add, name="product_add"),
    path("products/<int:pk>/edit/", views_manager.product_edit, name="product_edit"),
    path("products/<int:pk>/toggle/", views_manager.product_toggle, name="product_toggle"),

    # Categories
    path("categories/", views_manager.categories_list, name="categories"),
    path("categories/add/", views_manager.category_add, name="category_add"),
    path("categories/<int:pk>/edit/", views_manager.category_edit, name="category_edit"),
    path("categories/<int:pk>/toggle/", views_manager.category_toggle, name="category_toggle"),

    # Stock Movements & Low Stock
    path("movements/", views_manager.movements_list, name="movements"),
    path("low-stock/", views_manager.low_stock_list, name="low_stock"),
    path("low-stock/<int:pk>/review/", views_manager.low_stock_review, name="low_stock_review"),

    # Suppliers Directory
    path("suppliers/", views_manager.suppliers_list, name="suppliers"),

    # Staff Management (Manager Only)
    path("staff/", views_manager.staff_list, name="staff"),
    path("staff/create/", views_manager.staff_create, name="staff_create"),
    path("staff/<int:pk>/edit/", views_manager.staff_edit, name="staff_edit"),
    path("staff/<int:pk>/toggle/", views_manager.staff_toggle, name="staff_toggle"),

    # Staff Task Management
    path("tasks/", views_manager.tasks_list, name="tasks"),
    path("tasks/create/", views_manager.task_create, name="task_create"),
    path("tasks/<int:pk>/update/", views_manager.task_update_status, name="task_update_status"),
    path("tasks/<int:pk>/cancel/", views_manager.task_cancel, name="task_cancel"),

    # Shifts & Attendance
    path("attendance/", views_manager.attendance_view, name="attendance"),
    path("attendance/check/", views_manager.attendance_check, name="attendance_check"),
    path("shifts/create/", views_manager.shift_create, name="shift_create"),

    # Reports, Notifications & Settings
    path("reports/", views_manager.reports_view, name="reports"),
    path("notifications/", views_manager.notifications_view, name="notifications"),
    path("settings/", views_manager.settings_view, name="settings"),
]
