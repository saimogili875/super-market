"""Order detail page + board render tests.

Rendering the operational board exercises the order_card partial's
{% url 'orders_admin:detail' %} reverse, so these also guard against the
NoReverseMatch class that previously 500'd the dashboard.
"""
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.accounts.models import Role, User
from apps.menu.models import Category, MenuItem
from apps.orders.services import create_order


@pytest.fixture
def admin_user(db):
    return User.objects.create_user(
        username="detail_admin", password="pw", role=Role.ADMIN,
        is_staff=True, is_superuser=True,
    )


@pytest.fixture
def customer_user(db):
    return User.objects.create_user(username="detail_cust", password="pw", role=Role.CUSTOMER)


@pytest.fixture
def delivery_order(db):
    cat = Category.objects.create(name="DetailCat", is_active=True)
    mi = MenuItem.objects.create(
        category=cat, name="DetailItem", price=Decimal("5.00"), is_available=True,
    )
    return create_order(
        order_type="DELV",
        items=[{"menu_item_id": mi.pk, "quantity": 2}],
        contact_name="Ann", contact_phone="555",
        maps_url="https://www.google.com/maps/dir/?api=1&destination=1,2",
    )


@pytest.mark.django_db
def test_dashboard_and_detail_return_200_for_admin(client, admin_user, delivery_order):
    """Board renders (reversing orders_admin:detail per card) and detail opens."""
    client.force_login(admin_user)

    board = client.get(reverse("orders_admin:dashboard"))
    assert board.status_code == 200
    # The Details link (reverse of orders_admin:detail) must be present.
    assert reverse("orders_admin:detail", args=[delivery_order.pk]).encode() in board.content

    detail = client.get(reverse("orders_admin:detail", args=[delivery_order.pk]))
    assert detail.status_code == 200
    assert b"Ann" in detail.content  # contact name rendered
    assert b"Open location in Google Maps" in detail.content  # maps link rendered


@pytest.mark.django_db
def test_detail_requires_admin(client, customer_user, delivery_order):
    """A non-admin hitting the detail page is denied (403/redirect), never 200."""
    client.force_login(customer_user)
    resp = client.get(reverse("orders_admin:detail", args=[delivery_order.pk]))
    assert resp.status_code in (302, 403)
