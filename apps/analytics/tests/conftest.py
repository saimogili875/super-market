"""Shared fixtures for analytics tests — users and a settled-order factory."""
import datetime
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.accounts.models import Role, User
from apps.orders.models import Order
from apps.tables.models import Table


@pytest.fixture
def admin(db):
    return User.objects.create_user(username="an_admin", password="pw", role=Role.ADMIN)


@pytest.fixture
def agent(db):
    return User.objects.create_user(username="an_agent", password="pw", role=Role.AGENT)


@pytest.fixture
def customer(db):
    return User.objects.create_user(username="a_cust", password="pw", role=Role.CUSTOMER)


@pytest.fixture
def aware_dt():
    """Build a timezone-aware datetime (UTC noon by default) for a given date.

    Settlement time is stored on Order.updated_at; noon keeps test dates well
    away from any midnight/timezone boundary.
    """
    def _dt(year, month, day, hour=12):
        return timezone.make_aware(datetime.datetime(year, month, day, hour, 0))

    return _dt


@pytest.fixture
def make_order(db):
    """Factory creating an Order in a given status at a given settlement time.

    ``updated_at`` has auto_now=True, so we stamp the desired settlement time
    with a follow-up .update() (which bypasses auto_now). DINE orders get a
    Table to satisfy the order_channel_shape check constraint.
    """
    def _make(*, status="PAID", order_type="DELV", amount="10.00", when=None):
        table = None
        if order_type == "DINE":
            table = Table.objects.create(number=Table.objects.count() + 1)
        order = Order.objects.create(
            order_type=order_type,
            status=status,
            total_amount=Decimal(amount),
            table=table,
        )
        if when is not None:
            Order.objects.filter(pk=order.pk).update(updated_at=when)
            order.refresh_from_db()
        return order

    return _make
