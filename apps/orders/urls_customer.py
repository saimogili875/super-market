"""Customer delivery ordering URL routes.

Namespace: orders_customer
"""
from django.urls import include, path

from . import views_customer

app_name = "orders_customer"

urlpatterns = [
    path("auth/", include(("apps.customer_auth.urls", "customer_auth"), namespace="customer_auth")),
    path("menu/", views_customer.delivery_menu, name="menu"),
    path("cart/", views_customer.delivery_cart_view, name="cart"),
    path("cart/add", views_customer.cart_add, name="cart_add"),
    path("cart/update", views_customer.cart_update, name="cart_update"),
    path("cart/remove", views_customer.cart_update, name="cart_remove"),
    path("checkout/", views_customer.delivery_checkout, name="checkout"),
    path("my-orders/", views_customer.order_history, name="my_orders"),
    path("track/", views_customer.track_current, name="track_current"),
    path("settings/", views_customer.customer_settings, name="settings"),
    path("<int:pk>/track/", views_customer.track_order, name="track"),
    path("<int:pk>/message/", views_customer.post_order_message, name="message"),
]
