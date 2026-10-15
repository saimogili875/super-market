"""Smoke tests for the key HTTP routes across every role.

Regression guard against the admin-frontend breakage class (500s from wrong
reverse accessors, NoReverseMatch, missing templates) and against role-based
access control regressions. Uses Django's test Client and asserts real status
codes — no view internals are mocked.
"""
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.accounts.models import AgentProfile, Role, User
from apps.menu.models import Category, MenuItem
from apps.tables.models import Table


@pytest.fixture
def table(db):
    """An active dining table (its qr_token drives the guest dine-in URL)."""
    return Table.objects.create(number=1, is_active=True)


@pytest.fixture
def menu_item(db):
    """One available menu item so the admin/menu dashboards have rows to render."""
    cat = Category.objects.create(name="Drinks", is_active=True)
    return MenuItem.objects.create(
        category=cat, name="Lemonade", price=Decimal("5.00"), is_available=True,
    )


@pytest.fixture
def admin_user(db):
    """ADMIN business role AND Django staff/superuser (Django admin needs both)."""
    return User.objects.create_user(
        username="smoke_admin", password="pw", role=Role.ADMIN,
        is_staff=True, is_superuser=True,
    )


@pytest.fixture
def agent_user(db):
    """AGENT role with an availability profile."""
    user = User.objects.create_user(
        username="smoke_agent", password="pw", role=Role.AGENT,
    )
    AgentProfile.objects.create(user=user, is_available=True)
    return user


@pytest.fixture
def customer_user(db):
    """A logged-in CUSTOMER (used only for access-control assertions)."""
    return User.objects.create_user(
        username="smoke_cust", password="pw", role=Role.CUSTOMER,
    )


# ---------------------------------------------------------------------------
# Guest (unauthenticated) routes
# ---------------------------------------------------------------------------

def test_guest_routes_return_200(client, table, menu_item):
    """Public routes must be reachable without authentication."""
    for url in [
        reverse("healthz"),
        reverse("tables:menu", args=[table.qr_token]),
        reverse("accounts:login"),
        reverse("customer_auth:login"),
    ]:
        response = client.get(url)
        assert response.status_code == 200, f"{url} -> {response.status_code}"


def test_customer_menu_accessible_without_auth(client, db):
    """The public delivery menu is browsable without customer auth (returns 200)."""
    menu_url = reverse("orders_customer:menu")
    res = client.get(menu_url)
    assert res.status_code == 200



# ---------------------------------------------------------------------------
# Admin frontend + Django admin
# ---------------------------------------------------------------------------

def test_admin_routes_return_200(client, admin_user, table, menu_item):
    """Every admin page (the previously-broken set) must render for an ADMIN."""
    client.force_login(admin_user)
    for url in [
        reverse("orders_admin:dashboard"),
        reverse("menu:management"),
        reverse("tables_admin:management"),
        reverse("tables_admin:sessions"),
        reverse("accounts_admin:agents"),
        reverse("accounts_admin:users"),
        reverse("analytics:dashboard"),
        reverse("admin:index"),
    ]:
        response = client.get(url)
        assert response.status_code == 200, f"{url} -> {response.status_code}"


# ---------------------------------------------------------------------------
# Agent dashboard
# ---------------------------------------------------------------------------

def test_agent_dashboard_returns_200(client, agent_user):
    """The delivery-agent dashboard must render for an AGENT."""
    client.force_login(agent_user)
    response = client.get(reverse("orders_agent:dashboard"))
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# Access control — non-admins must NOT reach admin pages
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("role_fixture", ["agent_user", "customer_user"])
def test_non_admin_cannot_reach_admin_dashboard(client, request, role_fixture):
    """AGENT/CUSTOMER hitting an admin page get 403/redirect — never 200."""
    user = request.getfixturevalue(role_fixture)
    client.force_login(user)
    response = client.get(reverse("orders_admin:dashboard"))
    assert response.status_code in (302, 403), (
        f"{role_fixture} reached admin dashboard: {response.status_code}"
    )


def test_anonymous_redirected_from_admin_dashboard(client, db):
    """Anonymous users are redirected to login (not served the page)."""
    response = client.get(reverse("orders_admin:dashboard"))
    assert response.status_code == 302
    assert reverse("accounts:login") in response.url
