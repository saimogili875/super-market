"""Anti-IDOR + workflow tests for the agent delivery dashboard.

An agent may only see and act on orders assigned to them, and may only walk
the DISPATCH -> ARRIVED -> COLLECT arc that state.py grants the AGENT role.
"""
from decimal import Decimal

import pytest

from apps.accounts.models import AgentProfile, Role, User
from apps.orders.models import Order, OrderStatus


@pytest.fixture
def agent_a(db):
    return User.objects.create_user(username="agent_a", password="pw", role=Role.AGENT)


@pytest.fixture
def agent_b(db):
    return User.objects.create_user(username="agent_b", password="pw", role=Role.AGENT)


def _delivery(agent, status=OrderStatus.DISPATCHED):
    """Create a delivery order directly in a given status, assigned to *agent*."""
    return Order.objects.create(
        order_type="DELV",
        status=status,
        agent=agent,
        total_amount=Decimal("20.00"),
        contact_name="Pat",
        contact_phone="555-0100",
    )


@pytest.mark.django_db
def test_dashboard_shows_only_own_orders(client, agent_a, agent_b):
    """Agent A's dashboard lists their order but never agent B's."""
    mine = _delivery(agent_a)
    theirs = _delivery(agent_b)

    client.force_login(agent_a)
    response = client.get("/agent/")

    assert response.status_code == 200
    body = response.content.decode()
    assert f"order-card-{mine.pk}" in body
    assert f"order-card-{theirs.pk}" not in body


@pytest.mark.django_db
def test_cannot_transition_another_agents_order(client, agent_a, agent_b):
    """Posting a status change on agent B's order returns 404 for agent A."""
    theirs = _delivery(agent_b)

    client.force_login(agent_a)
    response = client.post(
        f"/agent/orders/{theirs.pk}/status", {"to_status": OrderStatus.ARRIVED}
    )

    assert response.status_code == 404
    theirs.refresh_from_db()
    assert theirs.status == OrderStatus.DISPATCHED


@pytest.mark.django_db
@pytest.mark.django_db
def test_agent_walks_dispatch_arrived_collect_paid(client, agent_a):
    """The agent may advance DISPATCH -> ARRIVED -> COLLECT -> PAID, one legal step each."""
    order = _delivery(agent_a, status=OrderStatus.DISPATCHED)
    client.force_login(agent_a)

    r1 = client.post(
        f"/agent/orders/{order.pk}/status", {"to_status": OrderStatus.ARRIVED}
    )
    assert r1.status_code == 200
    order.refresh_from_db()
    assert order.status == OrderStatus.ARRIVED

    r2 = client.post(
        f"/agent/orders/{order.pk}/status", {"to_status": OrderStatus.COLLECTED}
    )
    assert r2.status_code == 200
    order.refresh_from_db()
    assert order.status == OrderStatus.COLLECTED

    r3 = client.post(
        f"/agent/orders/{order.pk}/status", {"to_status": OrderStatus.PAID}
    )
    assert r3.status_code == 200
    order.refresh_from_db()
    assert order.status == OrderStatus.PAID


@pytest.mark.django_db
def test_illegal_jump_is_blocked(client, agent_a):
    """Skipping ARRIVED (DISPATCH -> COLLECT) is rejected and changes nothing."""
    order = _delivery(agent_a, status=OrderStatus.DISPATCHED)
    client.force_login(agent_a)

    response = client.post(
        f"/agent/orders/{order.pk}/status", {"to_status": OrderStatus.COLLECTED}
    )

    assert response.status_code == 403
    order.refresh_from_db()
    assert order.status == OrderStatus.DISPATCHED


@pytest.mark.django_db
def test_availability_toggle_flips_flag(client, agent_a):
    """POST /agent/availability flips the agent's AgentProfile.is_available."""
    client.force_login(agent_a)

    on = client.post("/agent/availability", {"available": "true"})
    assert on.status_code == 200
    assert AgentProfile.objects.get(user=agent_a).is_available is True

    off = client.post("/agent/availability", {"available": "false"})
    assert off.status_code == 200
    assert AgentProfile.objects.get(user=agent_a).is_available is False
