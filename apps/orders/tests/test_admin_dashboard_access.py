"""Tests for admin dashboard access control.

Verifies that the dashboard view is accessible only to ADMIN users and returns
403 for AGENT/CUSTOMER roles, while anonymous users are redirected to login.
"""
import pytest

from apps.accounts.models import Role, User


@pytest.fixture
def admin_user(db):
    return User.objects.create_user(username="admin_d", password="pw", role=Role.ADMIN)


@pytest.fixture
def agent_user(db):
    return User.objects.create_user(username="agent_d", password="pw", role=Role.AGENT)


@pytest.fixture
def customer_user(db):
    return User.objects.create_user(username="cust_d", password="pw", role=Role.CUSTOMER)


DASHBOARD_URL = "/backoffice/orders/dashboard/"


@pytest.mark.django_db
def test_admin_gets_200(client, admin_user):
    """An ADMIN user can access the dashboard."""
    client.force_login(admin_user)
    response = client.get(DASHBOARD_URL)
    assert response.status_code == 200


@pytest.mark.django_db
def test_agent_gets_403(client, agent_user):
    """An AGENT user is denied access to the admin dashboard."""
    client.force_login(agent_user)
    response = client.get(DASHBOARD_URL)
    assert response.status_code == 403


@pytest.mark.django_db
def test_customer_gets_403(client, customer_user):
    """A CUSTOMER user is denied access to the admin dashboard."""
    client.force_login(customer_user)
    response = client.get(DASHBOARD_URL)
    assert response.status_code == 403


@pytest.mark.django_db
def test_anonymous_redirected_to_login(client):
    """An anonymous visitor is redirected to the login page."""
    response = client.get(DASHBOARD_URL)
    assert response.status_code == 302
    assert "/accounts/login/" in response.url
