"""Tests verifying OrderConsumer websocket authentication via signed delv_token cookie."""
import pytest
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.core.signing import get_cookie_signer

from apps.menu.models import Category, MenuItem
from apps.orders.services import create_order
from apps.realtime.routing import websocket_urlpatterns


@pytest.fixture
def menu_item():
    cat = Category.objects.create(name="Websocket Delivery Cat")
    return MenuItem.objects.create(category=cat, name="Delivery Burger", price="12.00")


@pytest.mark.django_db(transaction=True)
def test_order_consumer_accepts_valid_signed_delivery_cookie(menu_item):
    """Delivery customer with valid signed delv_token_<order_id> cookie can connect to WebSocket."""
    order = create_order(
        order_type="DELV",
        items=[{"menu_item_id": menu_item.pk, "quantity": 1}],
        contact_name="Delivery User",
        contact_phone="9876543210",
    )

    cookie_key = f"delv_token_{order.pk}"
    signed_cookie_val = get_cookie_signer(salt=cookie_key + "delv_tracking").sign(str(order.pk))
    cookie_header = f"{cookie_key}={signed_cookie_val}"

    async def _test():
        communicator = WebsocketCommunicator(
            URLRouter(websocket_urlpatterns),
            f"/ws/orders/{order.pk}/",
            headers=[(b"cookie", cookie_header.encode("utf-8"))],
        )
        communicator.scope["cookies"] = {cookie_key: signed_cookie_val}
        connected, _ = await communicator.connect()
        assert connected is True
        await communicator.disconnect()

    import asyncio
    asyncio.run(_test())


@pytest.mark.django_db(transaction=True)
def test_order_consumer_accepts_valid_signed_cookie_and_receives_broadcasts(menu_item):
    """Valid signed delv_token cookie allows connecting and receiving broadcasts from order group."""
    from channels.layers import get_channel_layer
    channel_layer = get_channel_layer()

    order = create_order(
        order_type="DELV",
        items=[{"menu_item_id": menu_item.pk, "quantity": 1}],
        contact_name="Delivery User",
        contact_phone="9876543210",
    )

    cookie_key = f"delv_token_{order.pk}"
    signed_cookie_val = get_cookie_signer(salt=cookie_key + "delv_tracking").sign(str(order.pk))
    cookie_header = f"{cookie_key}={signed_cookie_val}"

    async def _test():
        communicator = WebsocketCommunicator(
            URLRouter(websocket_urlpatterns),
            f"/ws/orders/{order.pk}/",
            headers=[(b"cookie", cookie_header.encode("utf-8"))],
        )
        connected, _ = await communicator.connect()
        assert connected is True

        # Send broadcast to the order group
        await channel_layer.group_send(
            f"order.{order.pk}",
            {"type": "order_status", "status": "KITCHEN", "status_display": "In kitchen"},
        )

        response = await communicator.receive_json_from()
        assert response["status"] == "KITCHEN"

        await communicator.disconnect()

    import asyncio
    asyncio.run(_test())


@pytest.mark.django_db(transaction=True)
def test_order_consumer_rejects_unauthenticated_without_signed_cookie(menu_item):
    """Unauthenticated client without signed cookie is rejected by OrderConsumer."""
    order = create_order(
        order_type="DELV",
        items=[{"menu_item_id": menu_item.pk, "quantity": 1}],
        contact_name="Delivery User",
        contact_phone="9876543210",
    )

    async def _test():
        communicator = WebsocketCommunicator(
            URLRouter(websocket_urlpatterns),
            f"/ws/orders/{order.pk}/",
        )
        connected, _ = await communicator.connect()
        assert connected is False
        await communicator.disconnect()

    import asyncio
    asyncio.run(_test())


@pytest.mark.django_db(transaction=True)
def test_order_consumer_rejects_tampered_cookie(menu_item):
    """Client with a tampered or invalid cookie is rejected by OrderConsumer."""
    order = create_order(
        order_type="DELV",
        items=[{"menu_item_id": menu_item.pk, "quantity": 1}],
        contact_name="Delivery User",
        contact_phone="9876543210",
    )

    cookie_key = f"delv_token_{order.pk}"
    tampered_cookie_val = "tampered_signature_value"
    cookie_header = f"{cookie_key}={tampered_cookie_val}"

    async def _test():
        communicator = WebsocketCommunicator(
            URLRouter(websocket_urlpatterns),
            f"/ws/orders/{order.pk}/",
            headers=[(b"cookie", cookie_header.encode("utf-8"))],
        )
        communicator.scope["cookies"] = {cookie_key: tampered_cookie_val}
        connected, _ = await communicator.connect()
        assert connected is False
        await communicator.disconnect()

    import asyncio
    asyncio.run(_test())
