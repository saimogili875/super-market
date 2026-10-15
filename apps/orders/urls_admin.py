"""Admin-only order URL routes (mounted under the env-configurable admin path).

Namespace: orders_admin
"""
from django.urls import path

from . import views_admin

app_name = "orders_admin"

urlpatterns = [
    path("dashboard/", views_admin.dashboard, name="dashboard"),
    path("<int:pk>/detail/", views_admin.order_detail, name="detail"),
    path("<int:pk>/assign/", views_admin.assign_order, name="assign"),
    path("<int:pk>/transition/", views_admin.transition_order, name="transition"),
    path("<int:pk>/card/", views_admin.order_card, name="order_card"),
]
