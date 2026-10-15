"""Tests verifying that order creation and transition emit broadcast events."""
from unittest.mock import patch

import pytest
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from apps.accounts.models import User
from apps.menu.models import Category, MenuItem
from apps.orders.models import OrderStatus
from apps.orders.services import create_order, transition
from apps.tables.models import Table


@pytest.fixture
def menu_item():
    """Create a sample menu item for order creation."""
    cat = Category.objects.create(name="Realtime Cat")
    return MenuItem.objects.create(category=cat, name="Realtime Burger", price="12.00")


@pytest.fixture
def customer():
    """Create a sample customer user."""
    return User.objects.create(username="rt_cust", role="CUST")


@pytest.fixture
def admin():
    """Create a sample admin user."""
    return User.objects.create(username="rt_admin", role="ADMIN")


@pytest.fixture
def agent():
    """Create a sample agent user."""
    return User.objects.create(username="rt_agent", role="AGENT")


@pytest.fixture
def table():
    """Create a sample table."""
    return Table.objects.create(number=4)


@pytest.mark.django_db
def test_create_order_broadcasts_to_dashboard(customer, menu_item, table):
    """create_order() sends order.status PLACED to admin.dashboard."""
    layer = get_channel_layer()
    channel_name = async_to_sync(layer.new_channel)()
    async_to_sync(layer.group_add)("admin.dashboard", channel_name)

    order = create_order(
        order_type="DINE",
        customer=customer,
        table=table,
        items=[{"menu_item_id": menu_item.pk, "quantity": 1}],
    )

    msg = async_to_sync(layer.receive)(channel_name)
    assert msg["type"] == "order.status"
    assert msg["order_id"] == order.pk
    assert msg["status"] == OrderStatus.PLACED
    assert "at" in msg


@pytest.mark.django_db
def test_transition_broadcasts_to_rooms(customer, admin, agent, menu_item):
    """transition() broadcasts to order room, dashboard room, and agent room."""
    order = create_order(
        order_type="DELV",
        customer=customer,
        items=[{"menu_item_id": menu_item.pk, "quantity": 1}],
    )
    order.agent = agent
    order.save(update_fields=["agent"])

    layer = get_channel_layer()
    dash_ch = async_to_sync(layer.new_channel)()
    order_ch = async_to_sync(layer.new_channel)()
    agent_ch = async_to_sync(layer.new_channel)()

    async_to_sync(layer.group_add)("admin.dashboard", dash_ch)
    async_to_sync(layer.group_add)(f"order.{order.pk}", order_ch)
    async_to_sync(layer.group_add)(f"agent.{agent.pk}", agent_ch)

    transition(order, OrderStatus.APPROVED, admin)

    for ch in (dash_ch, order_ch, agent_ch):
        msg = async_to_sync(layer.receive)(ch)
        assert msg["type"] == "order.status"
        assert msg["order_id"] == order.pk
        assert msg["status"] == OrderStatus.APPROVED
        assert "at" in msg


@pytest.mark.django_db
def test_transition_succeeds_even_if_broadcast_fails(customer, admin, menu_item, table):
    """If channel layer is broken, order still transitions in Postgres."""
    order = create_order(
        order_type="DINE",
        customer=customer,
        table=table,
        items=[{"menu_item_id": menu_item.pk, "quantity": 1}],
    )
    with patch(
        "apps.realtime.broadcast.get_channel_layer",
        side_effect=Exception("redis down"),
    ):
        transition(order, OrderStatus.APPROVED, admin)

    order.refresh_from_db()
    assert order.status == OrderStatus.APPROVED
