"""URL routing for coupons app."""
from django.urls import path
from . import views

app_name = "coupons"

urlpatterns = [
    path("", views.coupon_list, name="list"),
]
