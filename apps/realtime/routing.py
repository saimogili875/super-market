"""WebSocket URL routing for the real-time layer.

These patterns are mounted under the "websocket" protocol in config/asgi.py.
"""
from django.urls import path

from . import consumers

websocket_urlpatterns = [
    path("ws/orders/<int:order_id>/", consumers.OrderConsumer.as_asgi()),
    path("ws/tables/<str:qr_token>/", consumers.TableConsumer.as_asgi()),
    path("ws/dashboard/", consumers.DashboardConsumer.as_asgi()),
    path("ws/agent/", consumers.AgentConsumer.as_asgi()),
]
