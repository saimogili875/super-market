"""Tests verifying that clear_bill is atomic and handles transition errors gracefully."""
import pytest
from unittest.mock import patch
from django.core.exceptions import PermissionDenied
from django.contrib.messages.storage.fallback import FallbackStorage

from apps.accounts.models import User
from apps.menu.models import Category, MenuItem
from apps.orders.models import OrderStatus
from apps.orders.services import create_order
from apps.tables.models import Table
from apps.tables.services import start_tab
from apps.tables.views import clear_bill


@pytest.fixture
def admin_user():
    return User.objects.create_superuser(username="clear_admin", password="password", role="ADMIN")


@pytest.fixture
def table():
    return Table.objects.create(number=20)


@pytest.fixture
def menu_item():
    cat = Category.objects.create(name="Atomic Cat")
    return MenuItem.objects.create(category=cat, name="Atomic Burger", price="10.00")


@pytest.mark.django_db
def test_clear_bill_atomic_rollback_on_error(rf, table, menu_item, admin_user):
    """If transition raises PermissionDenied, clear_bill rolls back all order changes."""
    session = start_tab(table, guest_name="Bob")
    order1 = create_order(
        order_type="DINE",
        table=table,
        session=session,
        items=[{"menu_item_id": menu_item.pk, "quantity": 1}],
    )
    order2 = create_order(
        order_type="DINE",
        table=table,
        session=session,
        items=[{"menu_item_id": menu_item.pk, "quantity": 1}],
    )

    request = rf.post(f"/tables/sessions/{session.pk}/clear/", HTTP_HX_REQUEST="true")
    request.user = admin_user
    request.session = {}
    setattr(request, "_messages", FallbackStorage(request))

    def mock_transition(order, target_status, actor):
        if order.pk == order2.pk:
            raise PermissionDenied("Order cannot be paid.")
        order.status = target_status
        order.save()

    with patch("apps.tables.views.transition", side_effect=mock_transition):
        response = clear_bill(request, session.pk)

    assert response.status_code == 400
    assert b"Cannot clear bill" in response.content

    # Assert database state rolled back atomically (order1 is NOT left as PAID, session remains open)
    order1.refresh_from_db()
    order2.refresh_from_db()
    session.refresh_from_db()

    assert order1.status == OrderStatus.PLACED
    assert order2.status == OrderStatus.PLACED
    assert session.closed_at is None
