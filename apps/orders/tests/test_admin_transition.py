"""Tests for the admin transition endpoint.

Verifies that the thin POST endpoint delegates to services.transition correctly:
valid transitions succeed and write an OrderEvent, invalid ones are rejected,
and non-admin users get 403.
"""
from decimal import Decimal

import pytest
from django.core.exceptions import PermissionDenied
from django.urls import reverse

from apps.accounts.models import Role, User
from apps.accounts.services import set_agent_availability
from apps.menu.models import Category, MenuItem
from apps.orders.models import OrderEvent, OrderStatus
from apps.orders.services import assign_agent, create_order, transition
from apps.orders.views_admin import _action_buttons



@pytest.fixture
def burger(db):
    category = Category.objects.create(name="Mains", is_active=True)
    return MenuItem.objects.create(
        category=category, name="Burger", price=Decimal("50.00"), is_available=True,
    )


@pytest.fixture
def admin_user(db):
    return User.objects.create_user(username="admin_t", password="pw", role=Role.ADMIN)


@pytest.fixture
def agent_user(db):
    return User.objects.create_user(username="agent_t", password="pw", role=Role.AGENT)


@pytest.fixture
def placed_order(burger):
    """A freshly placed delivery order (status=PLACED)."""
    return create_order(
        order_type="DELV",
        items=[{"menu_item_id": burger.pk, "quantity": 2}],
    )


def _transition_url(pk):
    return f"/backoffice/orders/{pk}/transition/"


@pytest.mark.django_db
def test_valid_transition_succeeds(client, admin_user, placed_order):
    """PLACED -> APPROVED is allowed for ADMIN; writes an OrderEvent."""
    client.force_login(admin_user)
    event_count_before = OrderEvent.objects.filter(order=placed_order).count()

    response = client.post(
        _transition_url(placed_order.pk), {"to_status": "APPROVED"},
    )

    assert response.status_code == 200
    placed_order.refresh_from_db()
    assert placed_order.status == OrderStatus.APPROVED
    assert OrderEvent.objects.filter(order=placed_order).count() == event_count_before + 1

    latest = OrderEvent.objects.filter(order=placed_order).order_by("at").last()
    assert latest.from_status == "PLACED"
    assert latest.to_status == "APPROVED"
    assert latest.actor == admin_user


@pytest.mark.django_db
def test_invalid_transition_rejected(client, admin_user, placed_order):
    """PLACED -> READY is not in the ADMIN state table; must be rejected."""
    client.force_login(admin_user)

    response = client.post(
        _transition_url(placed_order.pk), {"to_status": "READY"},
    )

    assert response.status_code == 403
    placed_order.refresh_from_db()
    assert placed_order.status == OrderStatus.PLACED


@pytest.mark.django_db
def test_non_admin_gets_403(client, agent_user, placed_order):
    """An AGENT cannot use the admin transition endpoint."""
    client.force_login(agent_user)

    response = client.post(
        _transition_url(placed_order.pk), {"to_status": "APPROVED"},
    )

    assert response.status_code == 403
    placed_order.refresh_from_db()
    assert placed_order.status == OrderStatus.PLACED


@pytest.mark.django_db
def test_missing_order_returns_404(client, admin_user):
    """Transitioning a non-existent order returns 404."""
    client.force_login(admin_user)

    response = client.post(
        _transition_url(99999), {"to_status": "APPROVED"},
    )

    assert response.status_code == 404


@pytest.mark.django_db
def test_action_buttons_read_only_post_agent_assignment(client, admin_user, agent_user, placed_order):
    """Before agent assignment, admin retains controls. Once assigned, admin gets read-only + Emergency cancel."""
    set_agent_availability(agent_user, available=True)
    transition(placed_order, OrderStatus.APPROVED, admin_user)

    # Pre-assignment: Admin gets normal buttons
    buttons_before = _action_buttons(placed_order)
    target_values_before = [b["value"] for b in buttons_before]
    assert OrderStatus.APPROVED not in target_values_before
    assert OrderStatus.PAID in target_values_before
    assert OrderStatus.CANCELLED in target_values_before

    # Post-assignment: Admin gets emergency cancel only (no forward-moving buttons)
    assign_agent(placed_order, agent_user, admin_user)
    buttons_after = _action_buttons(placed_order)
    assert len(buttons_after) == 1
    assert buttons_after[0]["value"] == OrderStatus.CANCELLED
    assert buttons_after[0]["label"] == "Emergency cancel"

    client.force_login(admin_user)
    resp_after = client.get(reverse("orders_admin:dashboard"))
    assert resp_after.status_code == 200
    assert b"Emergency cancel" in resp_after.content


@pytest.mark.django_db
def test_admin_cannot_clear_delivery_payment_collect_to_paid(client, admin_user, agent_user, placed_order):
    """Admin attempting COLLECT -> PAID on a DELV order is blocked (403 PermissionDenied)."""
    set_agent_availability(agent_user, available=True)
    transition(placed_order, OrderStatus.APPROVED, admin_user)
    transition(placed_order, OrderStatus.IN_KITCHEN, admin_user)
    transition(placed_order, OrderStatus.READY, admin_user)
    assign_agent(placed_order, agent_user, admin_user)
    transition(placed_order, OrderStatus.ARRIVED, agent_user)
    transition(placed_order, OrderStatus.COLLECTED, agent_user)

    client.force_login(admin_user)
    response = client.post(_transition_url(placed_order.pk), {"to_status": "PAID"})
    assert response.status_code == 403
    placed_order.refresh_from_db()
    assert placed_order.status == OrderStatus.COLLECTED


@pytest.mark.django_db
def test_assigned_agent_clears_payment_unassigned_agent_blocked(agent_user, placed_order, admin_user):
    """Assigned agent can do COLLECT -> PAID, but unassigned agent raises PermissionDenied."""
    other_agent = User.objects.create_user(username="agent_other", password="pw", role=Role.AGENT)
    set_agent_availability(agent_user, available=True)
    transition(placed_order, OrderStatus.APPROVED, admin_user)
    transition(placed_order, OrderStatus.IN_KITCHEN, admin_user)
    transition(placed_order, OrderStatus.READY, admin_user)
    assign_agent(placed_order, agent_user, admin_user)
    transition(placed_order, OrderStatus.ARRIVED, agent_user)
    transition(placed_order, OrderStatus.COLLECTED, agent_user)

    # Unassigned agent is blocked
    with pytest.raises(PermissionDenied):
        transition(placed_order, OrderStatus.PAID, actor=other_agent)

    # Assigned agent succeeds
    updated = transition(placed_order, OrderStatus.PAID, actor=agent_user)
    assert updated.status == OrderStatus.PAID


@pytest.mark.django_db
def test_dine_in_orders_unaffected_by_agent_read_only_rules(admin_user, burger):
    """Dine-in (DINE) orders retain normal admin action buttons including PAID."""
    from apps.tables.models import Table
    table = Table.objects.create(number=99)
    dine_order = create_order(order_type="DINE", table=table, items=[{"menu_item_id": burger.pk, "quantity": 1}])
    
    buttons = _action_buttons(dine_order)
    target_values = [b["value"] for b in buttons]
    assert OrderStatus.APPROVED in target_values
    assert OrderStatus.PAID in target_values
    assert OrderStatus.CANCELLED in target_values

    updated = transition(dine_order, OrderStatus.PAID, actor=admin_user)
    assert updated.status == OrderStatus.PAID

