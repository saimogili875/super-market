"""Integration tests for dining table guest views and admin bill clearance."""
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.accounts.models import Role, User
from apps.menu.models import Category, MenuItem
from apps.orders.models import OrderStatus
from apps.tables.models import Table


@pytest.fixture
def table(db):
    """Create an active table."""
    return Table.objects.create(number=1, is_active=True)


@pytest.fixture
def menu_item(db):
    """Create an available menu item."""
    cat = Category.objects.create(name="Drinks", is_active=True)
    return MenuItem.objects.create(
        category=cat,
        name="Lemonade",
        price=Decimal("5.00"),
        is_available=True,
    )


@pytest.fixture
def admin_user(db):
    """Create an admin user."""
    return User.objects.create_user(
        username="admin_tbl", password="pw", role=Role.ADMIN
    )


@pytest.fixture
def agent_user(db):
    """Create an agent user."""
    return User.objects.create_user(
        username="agent_tbl", password="pw", role=Role.AGENT
    )


@pytest.mark.django_db
def test_table_menu_renders_start_tab_when_no_session(client, table, menu_item):
    """GET /t/<token>/ renders start tab form when no session cookie exists."""
    url = reverse("tables:menu", args=[table.qr_token])
    resp = client.get(url)
    assert resp.status_code == 200
    assert b"Start Pickup Order" in resp.content or b"Welcome to Counter" in resp.content


@pytest.mark.django_db
def test_start_tab_creates_session_and_cookie(client, table, menu_item):
    """POST /t/<token>/start creates TableSession and sets signed cookie."""
    url = reverse("tables:start_tab", args=[table.qr_token])
    resp = client.post(url, {"guest_name": "Alice"})
    assert resp.status_code == 302
    assert table.sessions.filter(guest_name="Alice", closed_at__isnull=True).exists()

    menu_resp = client.get(reverse("tables:menu", args=[table.qr_token]))
    assert menu_resp.status_code == 200
    assert b"Lemonade" in menu_resp.content


@pytest.mark.django_db
def test_cart_add_and_place_order(client, table, menu_item):
    """Adding item to cart and placing order creates Order attached to session."""
    client.post(reverse("tables:start_tab", args=[table.qr_token]), {"guest_name": "Test"})
    add_url = reverse("tables:cart_add", args=[table.qr_token])
    resp = client.post(add_url, {"menu_item_id": menu_item.pk, "quantity": 2})
    assert resp.status_code == 200
    assert b"2 items" in resp.content or b"Est. Total: $10.00" in resp.content

    order_url = reverse("tables:place_order", args=[table.qr_token])
    resp2 = client.post(order_url)
    assert resp2.status_code == 200
    session = table.sessions.get(closed_at__isnull=True)
    assert session.orders.count() == 1
    order = session.orders.first()
    assert order.total_amount == Decimal("10.00")
    assert order.table == table


@pytest.mark.django_db
def test_request_bill_sets_flag(client, table, menu_item):
    """POST /t/<token>/bill requests bill without closing session."""
    client.post(reverse("tables:start_tab", args=[table.qr_token]), {"guest_name": "Test"})
    bill_url = reverse("tables:request_bill", args=[table.qr_token])
    resp = client.post(bill_url)
    assert resp.status_code == 200
    assert b"Bill requested" in resp.content or b"View Receipt" in resp.content
    session = table.sessions.get()
    assert session.closed_at is None


@pytest.mark.django_db
def test_clear_bill_admin_only(client, table, menu_item, admin_user, agent_user):
    """Admin endpoint marks orders PAID and closes session."""
    client.post(reverse("tables:start_tab", args=[table.qr_token]), {"guest_name": "Test"})
    # Place an order
    client.post(
        reverse("tables:cart_add", args=[table.qr_token]),
        {"menu_item_id": menu_item.pk, "quantity": 1},
    )
    client.post(reverse("tables:place_order", args=[table.qr_token]))
    session = table.sessions.get(closed_at__isnull=True)

    clear_url = reverse("tables_admin:clear_bill", args=[session.pk])

    # Agent cannot clear bill
    client.force_login(agent_user)
    resp_agent = client.post(clear_url)
    assert resp_agent.status_code == 403
    session.refresh_from_db()
    assert session.closed_at is None

    # Admin can clear bill
    client.force_login(admin_user)
    resp_admin = client.post(clear_url)
    assert resp_admin.status_code in (200, 302)
    session.refresh_from_db()
    assert session.closed_at is not None
    assert all(o.status == OrderStatus.PAID for o in session.orders.all())


@pytest.mark.django_db
def test_bill_not_requested_until_button_posted(client, table, menu_item):
    """Bill requested flag is False on load and True only after POSTing to /bill."""
    client.post(reverse("tables:start_tab", args=[table.qr_token]), {"guest_name": "Bob"})
    status_url = reverse("tables:status", args=[table.qr_token])
    resp = client.get(status_url)
    assert b"Bill requested" not in resp.content
    assert not client.session.get(f"bill_req_{table.sessions.first().pk}", False)

    bill_url = reverse("tables:request_bill", args=[table.qr_token])
    resp2 = client.post(bill_url)
    assert b"Bill requested" in resp2.content or b"View Receipt" in resp2.content


@pytest.mark.django_db
def test_receipt_page_renders_itemized_total_and_excludes_cancelled(
    client, table, menu_item, admin_user
):
    """Receipt page renders itemized total and excludes CANCELLED orders."""
    client.post(reverse("tables:start_tab", args=[table.qr_token]), {"guest_name": "Charlie"})
    client.post(
        reverse("tables:cart_add", args=[table.qr_token]),
        {"menu_item_id": menu_item.pk, "quantity": 2},
    )
    client.post(reverse("tables:place_order", args=[table.qr_token]))

    # Place a second order and cancel it
    client.post(
        reverse("tables:cart_add", args=[table.qr_token]),
        {"menu_item_id": menu_item.pk, "quantity": 1},
    )
    client.post(reverse("tables:place_order", args=[table.qr_token]))

    session = table.sessions.get()
    order2 = session.orders.order_by("-created_at").first()
    from apps.orders.services import transition
    transition(order2, OrderStatus.CANCELLED, admin_user)

    receipt_url = reverse("tables:receipt", args=[table.qr_token])
    resp = client.get(receipt_url)
    assert resp.status_code == 200
    assert b"\xe2\x82\xb95.00" in resp.content  # Unit price column
    assert b"\xe2\x82\xb910.00" in resp.content # Line total & tab total
    assert session.total == Decimal("10.00")


@pytest.mark.django_db
def test_receipt_page_404s_for_non_owner(client, table, menu_item):
    """Accessing receipt without valid session cookie returns 404."""
    receipt_url = reverse("tables:receipt", args=[table.qr_token])
    resp = client.get(receipt_url)
    assert resp.status_code == 404


@pytest.mark.django_db
def test_simultaneous_open_tabs_guest_isolation(table, menu_item):
    """Two clients on the same table keep separate tabs, orders, totals, and receipts."""
    from django.test import Client
    client_a = Client()
    client_b = Client()

    client_a.post(reverse("tables:start_tab", args=[table.qr_token]), {"guest_name": "Alice"})
    client_b.post(reverse("tables:start_tab", args=[table.qr_token]), {"guest_name": "Bob"})

    assert table.sessions.filter(closed_at__isnull=True).count() == 2

    client_a.post(
        reverse("tables:cart_add", args=[table.qr_token]),
        {"menu_item_id": menu_item.pk, "quantity": 2},
    )
    client_a.post(reverse("tables:place_order", args=[table.qr_token]))

    client_b.post(
        reverse("tables:cart_add", args=[table.qr_token]),
        {"menu_item_id": menu_item.pk, "quantity": 3},
    )
    client_b.post(reverse("tables:place_order", args=[table.qr_token]))

    session_a = table.sessions.get(guest_name="Alice")
    session_b = table.sessions.get(guest_name="Bob")
    assert session_a.total == Decimal("10.00")
    assert session_b.total == Decimal("15.00")

    resp_a = client_a.get(reverse("tables:receipt", args=[table.qr_token]))
    assert b"\xe2\x82\xb910.00" in resp_a.content
    assert b"Alice" in resp_a.content

    resp_b = client_b.get(reverse("tables:receipt", args=[table.qr_token]))
    assert b"\xe2\x82\xb915.00" in resp_b.content
    assert b"Bob" in resp_b.content


@pytest.mark.django_db
def test_receipt_view_unit_price_regression(client, table, menu_item):
    """Regression test for Bug #8: Ensure receipt_view renders line item unit_price formatted with money filter."""
    from apps.core.templatetags.currency import money

    menu_item.price = Decimal("14.75")
    menu_item.save()

    client.post(reverse("tables:start_tab", args=[table.qr_token]), {"guest_name": "Dave"})
    client.post(
        reverse("tables:cart_add", args=[table.qr_token]),
        {"menu_item_id": menu_item.pk, "quantity": 1},
    )
    client.post(reverse("tables:place_order", args=[table.qr_token]))

    receipt_url = reverse("tables:receipt", args=[table.qr_token])
    resp = client.get(receipt_url)
    assert resp.status_code == 200

    expected_formatted_price = money(Decimal("14.75"))
    assert expected_formatted_price.encode("utf-8") in resp.content

