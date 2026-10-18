"""URL configuration for Swecha AI Shopping Assistant."""
from django.urls import path
from . import views

app_name = "swecha"

urlpatterns = [
    path("", views.assistant_page, name="assistant"),
    path("api/chat/", views.chat_api, name="chat_api"),
]
