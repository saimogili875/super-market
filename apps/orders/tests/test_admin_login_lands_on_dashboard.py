"""Tests for admin login landing page.

Verifies that an ADMIN logging in via RoleLoginView is redirected to the
operational dashboard (orders_admin:dashboard) and that AGENT login still
goes to orders_agent:dashboard (no regression).
"""
import pytest

from apps.accounts.models import Role, User


@pytest.fixture
def admin_user(db):
    return User.objects.create_user(username="admin_l", password="pw", role=Role.ADMIN)


@pytest.fixture
def agent_user(db):
    return User.objects.create_user(username="agent_l", password="pw", role=Role.AGENT)


LOGIN_URL = "/accounts/login/"


@pytest.mark.django_db
def test_admin_login_redirects_to_dashboard(client, admin_user):
    """An ADMIN logging in lands on the orders admin dashboard."""
    response = client.post(
        LOGIN_URL,
        {"username": "admin_l", "password": "pw"},
        follow=False,
    )
    assert response.status_code == 302
    assert response.url == "/backoffice/orders/dashboard/"


@pytest.mark.django_db
def test_agent_login_still_goes_to_agent_dashboard(client, agent_user):
    """AGENT login still redirects to the agent dashboard (no regression)."""
    response = client.post(
        LOGIN_URL,
        {"username": "agent_l", "password": "pw"},
        follow=False,
    )
    assert response.status_code == 302
    assert response.url == "/agent/"
