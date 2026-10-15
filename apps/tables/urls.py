"""URL patterns for public dining table endpoints."""
from django.urls import path

from . import views

app_name = "tables"

urlpatterns = [
    path("t/<str:qr_token>/", views.table_menu, name="menu"),
    path("t/<str:qr_token>/start", views.start_tab_view, name="start_tab"),
    path("t/<str:qr_token>/receipt", views.receipt_view, name="receipt"),
    path("t/<str:qr_token>/cart/add", views.cart_add, name="cart_add"),
    path("t/<str:qr_token>/order", views.place_order, name="place_order"),
    path("t/<str:qr_token>/order/add-items", views.add_items, name="add_items"),
    path("t/<str:qr_token>/bill", views.request_bill, name="request_bill"),
    path("t/<str:qr_token>/status", views.table_status, name="status"),
]
