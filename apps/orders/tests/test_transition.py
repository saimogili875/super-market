"""Tests for services.transition — role enforcement and audit events."""
from decimal import Decimal

import pytest
from django.core.exceptions import PermissionDenied, ValidationError

from apps.accounts.models import Role, User
from apps.accounts.services import set_agent_availability
from apps.menu.models import Category, MenuItem
from apps.orders.models import OrderStatus
from apps.orders.services import assign_agent, create_order, transition



@pytest.fixture
def category(db):
    """A simple active menu category."""
    return Category.objects.create(name="Mains", is_active=True)


@pytest.fixture
def burger(category):
    """A basic available menu item."""
    return MenuItem.objects.create(
        category=category,
        name="Burger",
        price=Decimal("50.00"),
        is_available=True,
    )


@pytest.fixture
def admin_user(db):
    """A user with the ADMIN role."""
    return User.objects.create_user(
        username="admin_t", password="pw", role=Role.ADMIN
    )


@pytest.fixture
def agent_user(db):
    """A user with the AGENT role."""
    return User.objects.create_user(
        username="agent_t", password="pw", role=Role.AGENT
    )


@pytest.fixture
def placed_order(burger):
    """A freshly placed delivery order."""
    return create_order(
        order_type="DELV",
        items=[{"menu_item_id": burger.pk, "quantity": 1}],
    )


@pytest.mark.django_db
def test_transition_allowed_updates_status(placed_order, admin_user):
    """An allowed transition updates the order status."""
    updated = transition(placed_order, "APPROVED", admin_user)
    assert updated.status == OrderStatus.APPROVED


@pytest.mark.django_db
def test_transition_allowed_appends_event(placed_order, admin_user):
    """An allowed transition appends an OrderEvent."""
    transition(placed_order, "APPROVED", admin_user)

    # Should now have 2 events: initial PLACED + APPROVED
    events = list(placed_order.events.order_by("at"))
    assert len(events) == 2
    latest = events[-1]
    assert latest.from_status == OrderStatus.PLACED
    assert latest.to_status == OrderStatus.APPROVED
    assert latest.actor == admin_user


@pytest.mark.django_db
def test_transition_disallowed_raises(placed_order, agent_user):
    """A disallowed transition raises PermissionDenied."""
    with pytest.raises(PermissionDenied):
        transition(placed_order, "APPROVED", agent_user)


@pytest.mark.django_db
def test_transition_disallowed_no_side_effects(
    placed_order, agent_user
):
    """A disallowed transition leaves status and events unchanged."""
    initial_event_count = placed_order.events.count()

    with pytest.raises(PermissionDenied):
        transition(placed_order, "APPROVED", agent_user)

    placed_order.refresh_from_db()
    assert placed_order.status == OrderStatus.PLACED
    assert placed_order.events.count() == initial_event_count


@pytest.mark.django_db
def test_transition_dispatch_requires_assigned_agent(
    placed_order, admin_user, agent_user
):
    """Transitioning to DISPATCH raises ValidationError if order.agent is None, and succeeds after assignment."""
    set_agent_availability(agent_user, available=True)
    transition(placed_order, OrderStatus.APPROVED, admin_user)
    transition(placed_order, OrderStatus.IN_KITCHEN, admin_user)
    transition(placed_order, OrderStatus.READY, admin_user)

    assert placed_order.agent_id is None
    with pytest.raises(ValidationError, match="Assign a delivery agent before dispatching."):
        transition(placed_order, OrderStatus.DISPATCHED, admin_user)

    updated = assign_agent(placed_order, agent_user, admin_user)
    assert updated.status == OrderStatus.DISPATCHED


@pytest.mark.django_db
def test_dinein_order_cannot_transition_to_delivery_status(burger, admin_user):
    """Dine-in orders raise ValidationError if attempting transition to DISPATCH, ARRIVED, or COLLECT."""
    from apps.tables.models import Table
    from apps.tables.services import start_tab

    table = Table.objects.create(number=99)
    session = start_tab(table, guest_name="Dine User")
    dine_order = create_order(
        order_type="DINE",
        table=table,
        session=session,
        items=[{"menu_item_id": burger.pk, "quantity": 1}],
    )

    transition(dine_order, OrderStatus.APPROVED, admin_user)
    transition(dine_order, OrderStatus.IN_KITCHEN, admin_user)
    transition(dine_order, OrderStatus.READY, admin_user)

    with pytest.raises(ValidationError, match="Dine-in order .* cannot transition to delivery status"):
        transition(dine_order, OrderStatus.DISPATCHED, admin_user)


@pytest.mark.django_db
def test_dinein_order_cannot_be_assigned_agent(burger, admin_user, agent_user):
    """Assigning a delivery agent to a DINE order raises PermissionDenied."""
    from apps.tables.models import Table
    from apps.tables.services import start_tab

    table = Table.objects.create(number=98)
    session = start_tab(table, guest_name="Dine User 2")
    dine_order = create_order(
        order_type="DINE",
        table=table,
        session=session,
        items=[{"menu_item_id": burger.pk, "quantity": 1}],
    )

    set_agent_availability(agent_user, available=True)
    with pytest.raises(PermissionDenied, match="Only delivery orders can be assigned a delivery agent."):
        assign_agent(dine_order, agent_user, admin_user)


