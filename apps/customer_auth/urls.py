from django.urls import path
from . import views

app_name = "customer_auth"

urlpatterns = [
    path("login/", views.customer_login, name="login"),
    path("signup/", views.customer_signup, name="signup"),
    path("verify-otp/", views.verify_otp, name="verify_otp"),
    path("resend-otp/", views.resend_otp, name="resend_otp"),
    path("logout/", views.customer_logout, name="logout"),
]
