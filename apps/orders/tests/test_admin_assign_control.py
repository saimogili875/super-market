"""The delivery assign control shows a populated <select> or an empty message."""
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.accounts.models import AgentProfile, Role, User
from apps.menu.models import Category, MenuItem
from apps.orders.services import create_order


@pytest.fixture
def admin_user(db):
    return User.objects.create_user(
        username="board_admin", password="pw", role=Role.ADMIN,
        is_staff=True, is_superuser=True,
    )


@pytest.fixture
def delivery_order(db):
    cat = Category.objects.create(name="C", is_active=True)
    mi = MenuItem.objects.create(category=cat, name="X", price=Decimal("5.00"), is_available=True)
    return create_order(order_type="DELV", items=[{"menu_item_id": mi.pk, "quantity": 1}],
                        contact_name="Ann")


@pytest.mark.django_db
def test_board_populates_agent_select_when_available(client, admin_user, delivery_order):
    """An available agent appears in the assign <select> on the board."""
    agent = User.objects.create_user(username="drv1", password="pw", role=Role.AGENT)
    AgentProfile.objects.create(user=agent, is_available=True)
    client.force_login(admin_user)
    resp = client.get(reverse("orders_admin:dashboard"))
    assert resp.status_code == 200
    assert b'name="agent_id"' in resp.content
    assert b"drv1" in resp.content


@pytest.mark.django_db
def test_board_shows_empty_message_when_no_agents(client, admin_user, delivery_order):
    """With no available agent, the board shows the 'No available agents' message."""
    client.force_login(admin_user)
    resp = client.get(reverse("orders_admin:dashboard"))
    assert resp.status_code == 200
    assert b"No available agents" in resp.content
