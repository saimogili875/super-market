"""Tests verifying that dine-in operations emit broadcasts to table.<qr_token>."""
import pytest
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from apps.accounts.models import User
from apps.menu.models import Category, MenuItem
from apps.orders.models import OrderStatus
from apps.orders.services import add_item_to_order, create_order, transition
from apps.tables.models import Table
from apps.tables.services import start_tab
from apps.tables.views import clear_bill


@pytest.fixture
def menu_item():
    cat = Category.objects.create(name="Table RT Cat")
    return MenuItem.objects.create(category=cat, name="Table Pizza", price="15.00")


@pytest.fixture
def admin_user():
    return User.objects.create_superuser(username="tbl_admin", password="password", role="ADMIN")


@pytest.fixture
def table():
    return Table.objects.create(number=10)


@pytest.mark.django_db
def test_create_order_broadcasts_to_table_qr_token_group(menu_item, table):
    """create_order sends order.status to group 'table.<qr_token>'."""
    layer = get_channel_layer()
    channel_name = async_to_sync(layer.new_channel)()
    group = f"table.{table.qr_token}"
    async_to_sync(layer.group_add)(group, channel_name)

    order = create_order(
        order_type="DINE",
        table=table,
        items=[{"menu_item_id": menu_item.pk, "quantity": 1}],
    )

    msg = async_to_sync(layer.receive)(channel_name)
    assert msg["type"] == "order.status"
    assert msg["order_id"] == order.pk
    assert msg["status"] == OrderStatus.PLACED


@pytest.mark.django_db
def test_transition_broadcasts_to_table_qr_token_group(menu_item, table, admin_user):
    """transition sends status update to group 'table.<qr_token>'."""
    order = create_order(
        order_type="DINE",
        table=table,
        items=[{"menu_item_id": menu_item.pk, "quantity": 1}],
    )

    layer = get_channel_layer()
    channel_name = async_to_sync(layer.new_channel)()
    group = f"table.{table.qr_token}"
    async_to_sync(layer.group_add)(group, channel_name)

    transition(order, OrderStatus.APPROVED, actor=admin_user)

    msg = async_to_sync(layer.receive)(channel_name)
    assert msg["type"] == "order.status"
    assert msg["order_id"] == order.pk
    assert msg["status"] == OrderStatus.APPROVED


@pytest.mark.django_db
def test_add_item_to_order_broadcasts_to_table_qr_token_group(menu_item, table):
    """add_item_to_order sends update to group 'table.<qr_token>'."""
    order = create_order(
        order_type="DINE",
        table=table,
        items=[{"menu_item_id": menu_item.pk, "quantity": 1}],
    )

    layer = get_channel_layer()
    channel_name = async_to_sync(layer.new_channel)()
    group = f"table.{table.qr_token}"
    async_to_sync(layer.group_add)(group, channel_name)

    add_item_to_order(order, menu_item.pk, quantity=1)

    msg = async_to_sync(layer.receive)(channel_name)
    assert msg["type"] == "order.status"
    assert msg["order_id"] == order.pk


@pytest.mark.django_db
def test_clear_bill_broadcasts_to_table_qr_token_group(rf, menu_item, table, admin_user):
    """clear_bill view broadcasts 'table.paid' to group 'table.<qr_token>'."""
    session = start_tab(table, guest_name="Alice")
    order = create_order(
        order_type="DINE",
        table=table,
        session=session,
        items=[{"menu_item_id": menu_item.pk, "quantity": 1}],
    )

    layer = get_channel_layer()
    channel_name = async_to_sync(layer.new_channel)()
    group = f"table.{table.qr_token}"
    async_to_sync(layer.group_add)(group, channel_name)

    request = rf.post(f"/tables/sessions/{session.pk}/clear/")
    request.user = admin_user
    clear_bill(request, session.pk)

    received_types = []
    for _ in range(2):
        try:
            msg = async_to_sync(layer.receive)(channel_name)
            received_types.append(msg["type"])
        except Exception:
            break

    assert "table.paid" in received_types
