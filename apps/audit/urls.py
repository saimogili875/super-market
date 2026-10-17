"""URL routing for audit log app."""
from django.urls import path
from . import views

app_name = "audit"

urlpatterns = [
    path("", views.audit_list, name="list"),
]
