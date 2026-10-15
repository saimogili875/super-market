"""Tests for the order_channel_shape DB constraint.

The CheckConstraint ensures:
  - DINE orders require a table (not null).
  - DELIVERY orders must have table = null.
"""
from decimal import Decimal

import pytest
from django.db import IntegrityError

from apps.orders.models import Order, OrderStatus
from apps.tables.models import Table


@pytest.fixture
def table():
    """Create a sample Table."""
    return Table.objects.create(number=1)


@pytest.mark.django_db
def test_dine_in_requires_table():
    """A DINE order with table=None violates the constraint."""
    with pytest.raises(IntegrityError):
        Order.objects.create(
            order_type="DINE",
            table=None,
            status=OrderStatus.PLACED,
            total_amount=Decimal("0"),
        )


@pytest.mark.django_db
def test_delivery_rejects_table(table):
    """A DELV order with a table violates the constraint."""
    with pytest.raises(IntegrityError):
        Order.objects.create(
            order_type="DELV",
            table=table,
            status=OrderStatus.PLACED,
            total_amount=Decimal("0"),
        )


@pytest.mark.django_db
def test_dine_in_with_table_ok(table):
    """A valid DINE order with a table succeeds."""
    order = Order.objects.create(
        order_type="DINE",
        table=table,
        status=OrderStatus.PLACED,
        total_amount=Decimal("0"),
    )
    assert order.pk is not None


@pytest.mark.django_db
def test_delivery_without_table_ok():
    """A valid DELV order with table=None succeeds."""
    order = Order.objects.create(
        order_type="DELV",
        table=None,
        status=OrderStatus.PLACED,
        total_amount=Decimal("0"),
    )
    assert order.pk is not None
