"""Customer delivery ordering URL routes.

Namespace: orders_customer
"""
from django.urls import include, path

from . import views_customer

app_name = "orders_customer"

urlpatterns = [
    path("auth/", include(("apps.customer_auth.urls", "customer_auth"), namespace="customer_auth")),
    path("menu/", views_customer.delivery_menu, name="menu"),
    path("product/<int:pk>/", views_customer.product_detail, name="product_detail"),
    path("cart/", views_customer.delivery_cart_view, name="cart"),
    path("cart/add", views_customer.cart_add, name="cart_add"),
    path("cart/update", views_customer.cart_update, name="cart_update"),
    path("cart/remove", views_customer.cart_update, name="cart_remove"),
    path("cart/coupon/apply", views_customer.cart_apply_coupon, name="cart_apply_coupon"),
    path("cart/coupon/remove", views_customer.cart_remove_coupon, name="cart_remove_coupon"),
    path("checkout/", views_customer.delivery_checkout, name="checkout"),
    path("my-orders/", views_customer.order_history, name="my_orders"),
    path("track/", views_customer.track_current, name="track_current"),
    path("settings/", views_customer.customer_settings, name="settings"),
    path("wishlist/", views_customer.wishlist_view, name="wishlist"),
    path("wishlist/toggle/<int:pk>/", views_customer.wishlist_toggle, name="wishlist_toggle"),
    path("addresses/", views_customer.customer_addresses, name="addresses"),
    path("addresses/add", views_customer.address_add, name="address_add"),
    path("addresses/<int:pk>/delete", views_customer.address_delete, name="address_delete"),
    path("addresses/<int:pk>/default", views_customer.address_set_default, name="address_set_default"),
    path("location/set", views_customer.set_location, name="set_location"),
    path("<int:pk>/track/", views_customer.track_order, name="track"),
    path("<int:pk>/message/", views_customer.post_order_message, name="message"),
]
