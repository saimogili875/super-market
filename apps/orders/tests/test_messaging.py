"""Tests for order quick-messaging: persistence, length cap, escaping, broadcast."""
from decimal import Decimal

import pytest
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.core.signing import get_cookie_signer

from apps.orders.models import Message, Order, OrderStatus
from apps.orders.services import post_message

_TRACKING_SALT = "delv_tracking"


@pytest.fixture
def order(db):
    return Order.objects.create(
        order_type="DELV",
        status=OrderStatus.DISPATCHED,
        total_amount=Decimal("25.00"),
        contact_name="Lee",
        contact_phone="555-0123",
    )


def _sign_token(order):
    key = f"delv_token_{order.pk}"
    return get_cookie_signer(salt=key + _TRACKING_SALT).sign(str(order.pk))


@pytest.mark.django_db
def test_post_message_creates_and_caps_length(order):
    """A message is stored and trimmed to the model's 300-char cap."""
    long_body = "x" * 500
    message = post_message(order, None, long_body)

    assert isinstance(message, Message)
    assert message.order_id == order.pk
    assert len(message.body) == 300
    assert order.messages.count() == 1


@pytest.mark.django_db
def test_post_message_broadcasts_to_order_room(order):
    """post_message pushes an 'order.message' event to the order.<id> group."""
    layer = get_channel_layer()
    channel = async_to_sync(layer.new_channel)()
    async_to_sync(layer.group_add)(f"order.{order.pk}", channel)

    message = post_message(order, None, "I'm at the gate")

    event = async_to_sync(layer.receive)(channel)
    assert event["type"] == "order.message"
    assert event["order_id"] == order.pk
    assert event["message_id"] == message.pk
    assert event["body"] == "I'm at the gate"
    # The socket must never leak location/PII — only the short text rides along.
    assert "maps_url" not in event


@pytest.fixture
def customer_client(client, db):
    from apps.customer_auth.models import Customer
    cust = Customer.objects.create(phone="9876543210", email="msg@example.com")
    session = client.session
    session["customer_id"] = cust.pk
    session.save()
    return client


@pytest.mark.django_db
def test_message_body_is_escaped_on_render(customer_client, order):
    """Stored HTML is rendered auto-escaped on the tracking page (XSS defense)."""
    post_message(order, None, "<script>alert(1)</script>")
    customer_client.cookies[f"delv_token_{order.pk}"] = _sign_token(order)

    body = customer_client.get(f"/order/{order.pk}/track/").content.decode()

    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in body
    assert "<script>alert(1)</script>" not in body


@pytest.mark.django_db
def test_non_owner_cannot_post_message(customer_client, order):
    """Without the tracking cookie, posting a message is a 404 (anti-IDOR)."""
    response = customer_client.post(f"/order/{order.pk}/message/", {"body": "hi"})
    assert response.status_code == 404
    assert order.messages.count() == 0


@pytest.mark.django_db
def test_owner_can_post_message_via_endpoint(customer_client, order):
    """The cookie-bearing owner can post and gets the rendered bubble back."""
    customer_client.cookies[f"delv_token_{order.pk}"] = _sign_token(order)

    response = customer_client.post(f"/order/{order.pk}/message/", {"body": "On my way?"})

    assert response.status_code == 200
    assert order.messages.count() == 1
    assert "On my way?" in response.content.decode()
