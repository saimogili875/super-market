"""Tests for Sprint 6 delivery data layer (maps URL, radius, message model, agent availability)."""
import pytest

from apps.accounts.models import AgentProfile, Role, User
from apps.accounts.services import set_agent_availability
from apps.orders.models import Message, Order
from apps.orders.services import build_maps_url, is_within_delivery_radius


def test_build_maps_url():
    """Verify build_maps_url composes SSRF-safe Google Maps URLs."""
    # With lat and lng
    assert (
        build_maps_url(lat="17.4", lng="78.4")
        == "https://www.google.com/maps/dir/?api=1&destination=17.4,78.4"
    )
    # With address
    assert (
        build_maps_url(address="123 Main St, City")
        == "https://www.google.com/maps/dir/?api=1&destination=123%20Main%20St%2C%20City"
    )
    # Empty
    assert build_maps_url() == ""


def test_is_within_delivery_radius():
    """Verify delivery radius check helper."""
    assert is_within_delivery_radius(2.5, limit_km=3.0) is True
    assert is_within_delivery_radius(3.0, limit_km=3.0) is True
    assert is_within_delivery_radius(3.1, limit_km=3.0) is False


@pytest.mark.django_db
def test_message_model():
    """Verify Message model creation and ordering."""
    customer = User.objects.create_user(
        username="cust_msg", password="password", role=Role.CUSTOMER
    )
    order = Order.objects.create(order_type="DELV", customer=customer)
    msg1 = Message.objects.create(
        order=order, sender=customer, body="Where is my food?"
    )
    msg2 = Message.objects.create(
        order=order, sender=customer, body="Arriving soon?"
    )

    messages = list(order.messages.all())
    assert len(messages) == 2
    assert messages[0] == msg1
    assert messages[1] == msg2
    assert str(msg1).startswith(f"Message #{msg1.pk} on Order #{order.pk}")


@pytest.mark.django_db
def test_set_agent_availability():
    """Verify set_agent_availability flips AgentProfile.is_available inside atomic transaction."""
    agent_user = User.objects.create_user(
        username="courier1", password="secretpassword", role=Role.AGENT
    )
    profile = set_agent_availability(agent_user, available=True)
    assert profile.is_available is True
    assert AgentProfile.objects.get(user=agent_user).is_available is True

    profile2 = set_agent_availability(agent_user, available=False)
    assert profile2.is_available is False
    assert AgentProfile.objects.get(user=agent_user).is_available is False
