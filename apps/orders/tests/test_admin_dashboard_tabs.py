"""Tests for admin dashboard per-guest tabs grouping and clear-bill improvements."""
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.accounts.models import Role, User
from apps.menu.models import Category, MenuItem
from apps.orders.models import OrderStatus
from apps.tables.models import Table


@pytest.fixture
def admin_user(db):
    return User.objects.create_user(
        username="admin_tab", password="pw", role=Role.ADMIN,
        is_staff=True, is_superuser=True,
    )


@pytest.fixture
def table(db):
    return Table.objects.create(number=10, qr_token="token-10", is_active=True)


@pytest.fixture
def menu_item(db):
    cat = Category.objects.create(name="TabCat", is_active=True)
    return MenuItem.objects.create(
        category=cat, name="TabItem", price=Decimal("12.50"), is_available=True,
    )


@pytest.mark.django_db
def test_dashboard_groups_dinein_by_table_and_session(client, admin_user, table, menu_item):
    """Dashboard groups orders by table and guest session (tab), showing bill requested."""
    # Alice starts a tab and places an order
    client.post(reverse("tables:start_tab", args=[table.qr_token]), {"guest_name": "Alice"})
    client.post(
        reverse("tables:cart_add", args=[table.qr_token]),
        {"menu_item_id": menu_item.pk, "quantity": 1},
    )
    client.post(reverse("tables:place_order", args=[table.qr_token]))
    session_alice = table.sessions.get(guest_name="Alice")

    # Alice requests bill
    client.post(reverse("tables:request_bill", args=[table.qr_token]))

    # Bob starts a tab at the same table and places an order
    client.post(reverse("tables:start_tab", args=[table.qr_token]), {"guest_name": "Bob"})
    client.post(
        reverse("tables:cart_add", args=[table.qr_token]),
        {"menu_item_id": menu_item.pk, "quantity": 2},
    )
    client.post(reverse("tables:place_order", args=[table.qr_token]))
    session_bob = table.sessions.get(guest_name="Bob")

    # View admin dashboard
    client.force_login(admin_user)
    resp = client.get(reverse("orders_admin:dashboard"))
    assert resp.status_code == 200
    content = resp.content.decode()

    # Both tabs appear grouped under Counter 10
    assert "Counter 10" in content
    assert "Alice" in content
    assert "Bob" in content
    assert f"tab-card-{session_alice.pk}" in content
    assert f"tab-card-{session_bob.pk}" in content
    assert "Bill Requested" in content


@pytest.mark.django_db
def test_clear_bill_htmx_returns_tab_card_and_excludes_cancelled(
    client, admin_user, table, menu_item
):
    """Clear bill marks non-cancelled orders PAID, closes session, and returns tab card."""
    client.post(reverse("tables:start_tab", args=[table.qr_token]), {"guest_name": "Charlie"})
    client.post(
        reverse("tables:cart_add", args=[table.qr_token]),
        {"menu_item_id": menu_item.pk, "quantity": 2},
    )
    client.post(reverse("tables:place_order", args=[table.qr_token]))
    session = table.sessions.get(guest_name="Charlie")

    order = session.orders.first()
    # Create a cancelled order in the same session
    from apps.orders.models import Order
    cancelled_order = Order.objects.create(
        order_type="DINE",
        table=table,
        session=session,
        status=OrderStatus.CANCELLED,
        total_amount=Decimal("5.00"),
    )

    client.force_login(admin_user)
    clear_url = reverse("tables_admin:clear_bill", args=[session.pk])
    resp = client.post(clear_url, HTTP_HX_REQUEST="true")
    assert resp.status_code == 200
    content = resp.content.decode()

    assert (
        "Bill Cleared &amp; Session Closed" in content
        or "Bill Cleared & Session Closed" in content
    )
    session.refresh_from_db()
    assert session.closed_at is not None
    assert session.bill_requested is False

    order.refresh_from_db()
    cancelled_order.refresh_from_db()
    assert order.status == OrderStatus.PAID
    assert cancelled_order.status == OrderStatus.CANCELLED


@pytest.mark.django_db
def test_menu_admin_dashboard_has_csrf_headers(client, admin_user):
    """Menu admin dashboard includes X-CSRFToken headers for HTMX toggle buttons."""
    client.force_login(admin_user)
    resp = client.get(reverse("menu:management"))
    assert resp.status_code == 200
    content = resp.content.decode()
    assert 'hx-headers=\'{"X-CSRFToken":' in content or 'X-CSRFToken' in content
