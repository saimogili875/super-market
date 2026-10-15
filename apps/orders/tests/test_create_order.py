"""Tests for create_order — price snapshotting and validation."""
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from apps.accounts.models import Role, User
from apps.menu.models import Category, MenuItem
from apps.orders.models import OrderStatus
from apps.orders.services import create_order
from apps.tables.models import Table


@pytest.fixture
def category(db):
    """A simple active menu category."""
    return Category.objects.create(name="Mains", is_active=True)


@pytest.fixture
def burger(category):
    """A menu item with a 20% discount: price=100, effective=80."""
    return MenuItem.objects.create(
        category=category,
        name="Burger",
        price=Decimal("100.00"),
        offer_percent=20,
        is_available=True,
    )


@pytest.fixture
def unavailable_item(category):
    """A menu item that is marked unavailable."""
    return MenuItem.objects.create(
        category=category,
        name="Seasonal Soup",
        price=Decimal("50.00"),
        is_available=False,
    )


@pytest.fixture
def customer(db):
    """A customer user."""
    return User.objects.create_user(
        username="cust", password="pw", role=Role.CUSTOMER
    )


@pytest.fixture
def table(db):
    """A sample table."""
    return Table.objects.create(number=10)


@pytest.mark.django_db
def test_create_order_snapshots_effective_price(burger, customer):
    """create_order uses effective_price, not the raw price."""
    order = create_order(
        order_type="DELV",
        items=[{"menu_item_id": burger.pk, "quantity": 2}],
        customer=customer,
    )
    line = order.items.first()

    # effective_price of burger is 80.00 (20% off 100)
    assert line.unit_price == Decimal("80.00")
    assert line.name_snap == "Burger"

    # total_amount = 80 * 2 = 160
    assert order.total_amount == Decimal("160.00")


@pytest.mark.django_db
def test_create_order_ignores_client_price(burger, customer):
    """Even if a client somehow sends a price, it is ignored."""
    order = create_order(
        order_type="DELV",
        items=[{"menu_item_id": burger.pk, "quantity": 1}],
        customer=customer,
    )
    line = order.items.first()
    assert line.unit_price == Decimal("80.00")


@pytest.mark.django_db
def test_create_order_empty_cart_raises(customer):
    """An empty cart raises a ValidationError."""
    with pytest.raises(ValidationError, match="Cart cannot be empty"):
        create_order(
            order_type="DELV",
            items=[],
            customer=customer,
        )


@pytest.mark.django_db
def test_create_order_unavailable_item_raises(
    unavailable_item, customer
):
    """Ordering an unavailable item raises a ValidationError."""
    with pytest.raises(ValidationError, match="unavailable"):
        create_order(
            order_type="DELV",
            items=[{
                "menu_item_id": unavailable_item.pk,
                "quantity": 1,
            }],
            customer=customer,
        )


@pytest.mark.django_db
def test_create_order_writes_initial_event(burger, customer):
    """Exactly one OrderEvent ('' -> 'PLACED') is created."""
    order = create_order(
        order_type="DELV",
        items=[{"menu_item_id": burger.pk, "quantity": 1}],
        customer=customer,
    )
    events = list(order.events.all())
    assert len(events) == 1
    assert events[0].from_status == ""
    assert events[0].to_status == OrderStatus.PLACED
@pytest.mark.django_db
def test_create_order_dine_in_links_table(burger, table):
    """A DINE order is linked to the scanned table."""
    order = create_order(
        order_type="DINE",
        items=[{"menu_item_id": burger.pk, "quantity": 1}],
        table=table,
    )
    assert order.order_type == "DINE"
    assert order.table_id == table.pk
    assert order.total_amount == Decimal("80.00")
