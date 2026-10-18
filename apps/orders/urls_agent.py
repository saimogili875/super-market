"""Agent delivery-dashboard URL routes (login required, role=AGENT).

Namespace: orders_agent
"""
from django.urls import path

from . import views_agent

app_name = "orders_agent"

urlpatterns = [
    # Dashboard (Home)
    path("", views_agent.dashboard, name="dashboard"),

    # Orders List & Details
    path("orders/", views_agent.orders_list, name="orders"),
    path("orders/<int:pk>/", views_agent.order_detail, name="order_detail"),
    path("orders/<int:pk>/status", views_agent.update_status, name="update_status"),
    path("orders/<int:pk>/action/", views_agent.order_action, name="order_action"),
    path("orders/<int:pk>/complete/", views_agent.delivery_complete, name="delivery_complete"),
    path("orders/<int:pk>/receipt/", views_agent.order_receipt, name="order_receipt"),

    # Operational Features
    path("availability", views_agent.toggle_availability, name="toggle_availability"),
    path("earnings/", views_agent.earnings_view, name="earnings"),
    path("notifications/", views_agent.notifications_view, name="notifications"),
    path("profile/", views_agent.profile_view, name="profile"),

    # Dedicated Mobile Login
    path("login/", views_agent.agent_login, name="login"),
]
