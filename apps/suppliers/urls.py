"""URL routes for suppliers and procurement."""
from django.urls import path
from . import views

app_name = "suppliers"

urlpatterns = [
    path("", views.supplier_list, name="list"),
    path("po/<int:pk>/receive/", views.receive_po, name="receive_po"),
]
