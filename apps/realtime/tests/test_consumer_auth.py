"""Tests for WebSocket consumer authentication and authorization."""
import asyncio

import pytest
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.contrib.auth.models import AnonymousUser

from apps.accounts.models import User
from apps.orders.models import Order
from apps.realtime.routing import websocket_urlpatterns


@pytest.mark.django_db(transaction=True)
def test_dashboard_consumer_auth_rejected_for_anon():
    """Anonymous user cannot connect to dashboard WebSocket."""
    async def run():
        c = WebsocketCommunicator(URLRouter(websocket_urlpatterns), "/ws/dashboard/")
        c.scope["user"] = AnonymousUser()
        connected, _ = await c.connect()
        assert not connected
    asyncio.run(run())


@pytest.mark.django_db(transaction=True)
def test_dashboard_consumer_auth_rejected_for_agent():
    """Agent user cannot connect to admin dashboard WebSocket."""
    agent = User.objects.create(username="agent_dash", role="AGENT")

    async def run():
        c = WebsocketCommunicator(URLRouter(websocket_urlpatterns), "/ws/dashboard/")
        c.scope["user"] = agent
        connected, _ = await c.connect()
        assert not connected
    asyncio.run(run())


@pytest.mark.django_db(transaction=True)
def test_dashboard_consumer_auth_accepted_for_admin():
    """Admin user can connect to dashboard WebSocket."""
    admin = User.objects.create(username="admin_dash", role="ADMIN")

    async def run():
        c = WebsocketCommunicator(URLRouter(websocket_urlpatterns), "/ws/dashboard/")
        c.scope["user"] = admin
        connected, _ = await c.connect()
        assert connected
        await c.disconnect()
    asyncio.run(run())


@pytest.mark.django_db(transaction=True)
def test_order_consumer_auth_rejected_for_unrelated_customer():
    """A customer cannot connect to another customer's order feed."""
    owner = User.objects.create(username="owner", role="CUST")
    stranger = User.objects.create(username="stranger", role="CUST")
    from apps.tables.models import Table
    t = Table.objects.create(number=5)
    order = Order.objects.create(order_type="DINE", table=t, customer=owner)

    async def run():
        c = WebsocketCommunicator(URLRouter(websocket_urlpatterns), f"/ws/orders/{order.pk}/")
        c.scope["user"] = stranger
        connected, _ = await c.connect()
        assert not connected
    asyncio.run(run())


@pytest.mark.django_db(transaction=True)
def test_order_consumer_auth_accepted_for_owner():
    """The customer who placed the order can connect to its feed."""
    owner = User.objects.create(username="owner_ok", role="CUST")
    from apps.tables.models import Table
    t = Table.objects.create(number=6)
    order = Order.objects.create(order_type="DINE", table=t, customer=owner)

    async def run():
        c = WebsocketCommunicator(URLRouter(websocket_urlpatterns), f"/ws/orders/{order.pk}/")
        c.scope["user"] = owner
        connected, _ = await c.connect()
        assert connected
        await c.disconnect()
    asyncio.run(run())


@pytest.mark.django_db(transaction=True)
def test_agent_consumer_auth_accepted_for_agent():
    """An agent user can connect to their personal feed."""
    agent = User.objects.create(username="agent_ok", role="AGENT")

    async def run():
        c = WebsocketCommunicator(URLRouter(websocket_urlpatterns), "/ws/agent/")
        c.scope["user"] = agent
        connected, _ = await c.connect()
        assert connected
        await c.disconnect()
    asyncio.run(run())
