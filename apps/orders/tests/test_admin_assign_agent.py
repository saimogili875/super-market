"""Tests for the assign_agent view (admin dashboard)."""
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.accounts.models import Role, User
from apps.accounts.services import set_agent_availability
from apps.menu.models import Category, MenuItem
from apps.orders.services import create_order


@pytest.fixture
def burger(db):
    category = Category.objects.create(name="Mains", is_active=True)
    return MenuItem.objects.create(
        category=category,
        name="Burger",
        price=Decimal("50.00"),
        is_available=True,
    )


@pytest.fixture
def admin_user(db):
    return User.objects.create_user(username="admin_a", password="pw", role=Role.ADMIN)


@pytest.fixture
def available_agent(db):
    agent = User.objects.create_user(username="agent_a", password="pw", role=Role.AGENT)
    set_agent_availability(agent, available=True)
    return agent


@pytest.fixture
def delivery_order(burger):
    return create_order(
        order_type="DELV",
        items=[{"menu_item_id": burger.pk, "quantity": 1}],
    )


@pytest.mark.django_db
def test_admin_assign_agent_view_success(client, admin_user, available_agent, delivery_order):
    """Assigning an agent via the view sets the agent and returns the updated card."""
    client.force_login(admin_user)
    
    url = reverse("orders_admin:assign", args=[delivery_order.pk])
    response = client.post(url, {"agent_id": available_agent.pk})
    
    assert response.status_code == 200
    
    delivery_order.refresh_from_db()
    assert delivery_order.agent == available_agent
    
    # Check that the returned HTML has the updated agent name
    html = response.content.decode()
    assert "🛵 Agent: agent_a" in html or "agent_a" in html


@pytest.mark.django_db
def test_admin_dashboard_empty_agent_state(client, admin_user, delivery_order):
    """When no agents are available, the dashboard shows the empty state message."""
    client.force_login(admin_user)
    
    url = reverse("orders_admin:dashboard")
    response = client.get(url)
    
    assert response.status_code == 200
    html = response.content.decode()
    
    # Delivery order assign control should show the empty state message
    assert "No available agents" in html
    assert "enable one in Agents" in html
    no_agents_split = html.split("No available agents")[0]
    assert "<form" not in no_agents_split.split("assign-control")[-1]


@pytest.mark.django_db
def test_admin_reassign_agent_view_success(client, admin_user, available_agent, delivery_order):
    """Reassigning an order to a second agent updates the agent and retains the assign control."""
    agent_b = User.objects.create_user(username="agent_b", password="pw", role=Role.AGENT)
    set_agent_availability(agent_b, available=True)

    client.force_login(admin_user)

    url = reverse("orders_admin:assign", args=[delivery_order.pk])
    # Initial assignment
    res1 = client.post(url, {"agent_id": available_agent.pk})
    assert res1.status_code == 200
    html1 = res1.content.decode()
    assert 'name="agent_id"' in html1
    assert "Reassign" in html1

    # Reassignment to second agent
    res2 = client.post(url, {"agent_id": agent_b.pk})
    assert res2.status_code == 200
    delivery_order.refresh_from_db()
    assert delivery_order.agent == agent_b

    html2 = res2.content.decode()
    assert "agent_b" in html2
    assert 'name="agent_id"' in html2
    assert "Reassign" in html2

