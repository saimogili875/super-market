"""End-to-end dine-in flow tests under REAL CSRF enforcement.

These prove two things at once:
  1. CSRF protection on the dine-in HTMX POST endpoints is real — a POST without a
     token is rejected with 403 (the bug that made "+ Add" silently do nothing).
  2. The body-level ``hx-headers`` CSRF token added to templates/tables/base.html is
     exactly what lets the authenticated HTMX flow succeed: sending the token the same
     way the attribute does (the ``X-CSRFToken`` header) drives the whole flow to 200.

Unlike the CSRF-exempt default test client, these use ``Client(enforce_csrf_checks=True)``
— the same protection a real browser hits.
"""
from decimal import Decimal

import pytest
from django.test import Client
from django.urls import reverse

from apps.menu.models import Category, MenuItem
from apps.orders.models import OrderStatus
from apps.tables.models import Table


@pytest.fixture
def table(db):
    """An active dining table."""
    return Table.objects.create(number=7, is_active=True)


@pytest.fixture
def menu_item(db):
    """An available $8.50 item (no offer, so effective_price == price)."""
    cat = Category.objects.create(name="Mains", is_active=True)
    return MenuItem.objects.create(
        category=cat, name="Burger", price=Decimal("8.50"), is_available=True,
    )


@pytest.fixture
def csrf_client():
    """A client that enforces CSRF exactly like a real browser."""
    return Client(enforce_csrf_checks=True)


def _load_menu_and_get_token(client, table):
    """GET the dine-in menu, assert the body-level hx-headers is present, return token.

    Rendering the page sets the csrftoken cookie (via {{ csrf_token }} inside the
    hx-headers attribute); we return that cookie value to replay as the header.
    """
    resp = client.get(reverse("tables:menu", args=[table.qr_token]))
    assert resp.status_code == 200
    # The base template must carry the body-level HTMX CSRF header so EVERY dine-in
    # POST (including fragments swapped into #main-content) is covered.
    assert b"hx-headers" in resp.content
    assert b"X-CSRFToken" in resp.content
    return client.cookies["csrftoken"].value


@pytest.mark.django_db
def test_cart_add_without_csrf_is_rejected(csrf_client, table, menu_item):
    """A POST WITHOUT a CSRF token is rejected (403) — the protection is real."""
    # Establish a session + csrftoken cookie first, then POST with NO token header.
    token = _load_menu_and_get_token(csrf_client, table)
    csrf_client.post(
        reverse("tables:start_tab", args=[table.qr_token]),
        {"guest_name": "Test"},
        **{"HTTP_X_CSRFTOKEN": token},
    )
    resp = csrf_client.post(
        reverse("tables:cart_add", args=[table.qr_token]),
        {"menu_item_id": menu_item.pk, "quantity": 1},
    )
    assert resp.status_code == 403


@pytest.mark.django_db
def test_full_dinein_flow_with_csrf(csrf_client, table, menu_item):
    """cart_add -> place_order -> add_items -> request_bill all succeed WITH the token."""
    token = _load_menu_and_get_token(csrf_client, table)
    hdr = {"HTTP_X_CSRFTOKEN": token}
    csrf_client.post(
        reverse("tables:start_tab", args=[table.qr_token]),
        {"guest_name": "Test"},
        **hdr,
    )

    # 1) Add to cart -> updated cart bar fragment with the correct server-side total.
    resp = csrf_client.post(
        reverse("tables:cart_add", args=[table.qr_token]),
        {"menu_item_id": menu_item.pk, "quantity": 2},
        **hdr,
    )
    assert resp.status_code == 200
    assert b"Est. Total: \xe2\x82\xb917.00" in resp.content  # 2 x ₹8.50

    # 2) Place order -> a DINE Order bound to the table's OPEN session, correct total.
    resp = csrf_client.post(reverse("tables:place_order", args=[table.qr_token]), **hdr)
    assert resp.status_code == 200
    session = table.sessions.get(closed_at__isnull=True)
    assert session.orders.count() == 1
    order = session.orders.first()
    assert order.order_type == "DINE"
    assert order.table == table
    assert order.session == session
    assert order.total_amount == Decimal("17.00")

    # 3) Add more items -> a second order APPENDED to the SAME open session (one tab).
    csrf_client.post(
        reverse("tables:cart_add", args=[table.qr_token]),
        {"menu_item_id": menu_item.pk, "quantity": 1},
        **hdr,
    )
    resp = csrf_client.post(reverse("tables:add_items", args=[table.qr_token]), **hdr)
    assert resp.status_code == 200
    session.refresh_from_db()
    assert session.orders.count() == 2
    assert table.sessions.filter(closed_at__isnull=True).count() == 1  # still one open tab

    # 4) Request bill -> flags the tab WITHOUT marking PAID or closing the session.
    resp = csrf_client.post(reverse("tables:request_bill", args=[table.qr_token]), **hdr)
    assert resp.status_code == 200
    assert b"Bill requested" in resp.content or b"View Receipt" in resp.content
    session.refresh_from_db()
    assert session.closed_at is None
    assert all(o.status != OrderStatus.PAID for o in session.orders.all())
