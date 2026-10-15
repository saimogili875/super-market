"""Feature tests for the bespoke Agents/Users admin dashboard."""
import pytest
from django.urls import reverse

from apps.accounts.models import AgentProfile, Role, User


@pytest.fixture
def admin_user(db):
    return User.objects.create_user(
        username="agent_admin", password="pw", role=Role.ADMIN,
        is_staff=True, is_superuser=True,
    )


@pytest.fixture
def customer_user(db):
    return User.objects.create_user(username="cust1", password="pw", role=Role.CUSTOMER)


@pytest.mark.django_db
def test_admin_can_create_agent_with_hashed_password_and_profile(client, admin_user):
    """Creating an agent via the dashboard hashes the password + provisions a profile."""
    client.force_login(admin_user)
    resp = client.post(
        reverse("accounts_admin:agent_create"),
        {
            "username": "courier9",
            "phone": "555-0101",
            "password1": "Str0ng!Passw0rd",
            "password2": "Str0ng!Passw0rd",
        },
    )
    assert resp.status_code == 302
    agent = User.objects.get(username="courier9")
    assert agent.role == Role.AGENT
    # Password must be hashed — never stored raw.
    assert agent.password != "Str0ng!Passw0rd"
    assert agent.check_password("Str0ng!Passw0rd")
    assert AgentProfile.objects.filter(user=agent).exists()


@pytest.mark.django_db
def test_toggle_and_deactivate_agent(client, admin_user):
    """Availability toggle flips the flag; deactivate disables the account."""
    client.force_login(admin_user)
    agent = User.objects.create_user(username="courier2", password="pw", role=Role.AGENT)
    AgentProfile.objects.create(user=agent, is_available=False)

    resp = client.post(reverse("accounts_admin:agent_toggle", args=[agent.pk]))
    assert resp.status_code == 200
    assert AgentProfile.objects.get(user=agent).is_available is True

    resp = client.post(reverse("accounts_admin:agent_deactivate", args=[agent.pk]))
    assert resp.status_code == 200
    agent.refresh_from_db()
    assert agent.is_active is False
    assert AgentProfile.objects.get(user=agent).is_available is False


@pytest.mark.django_db
def test_users_overview_never_exposes_password_hash(client, admin_user):
    """The users overview must not render any password material."""
    client.force_login(admin_user)
    resp = client.get(reverse("accounts_admin:users"))
    assert resp.status_code == 200
    assert admin_user.password.encode() not in resp.content
    assert b"pbkdf2_" not in resp.content


@pytest.mark.django_db
def test_non_admin_cannot_reach_agents_page(client, customer_user):
    """A CUSTOMER hitting the agents page is denied (403), never 200."""
    client.force_login(customer_user)
    resp = client.get(reverse("accounts_admin:agents"))
    assert resp.status_code in (302, 403)
