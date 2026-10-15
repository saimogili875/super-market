"""Test that an AGENT who logs in via /accounts/login/ can reach /agent/."""
import pytest
from django.test import Client
from django.urls import reverse

from apps.accounts.models import AgentProfile, Role, User


@pytest.mark.django_db
def test_agent_can_reach_dashboard():
    user = User.objects.create_user(
        username="testagent2", password="testpass123", role=Role.AGENT,
    )
    AgentProfile.objects.create(user=user)
    client = Client()

    # Login via the front-door login.
    resp = client.post(
        reverse("accounts:login"),
        {"username": "testagent2", "password": "testpass123"},
    )
    assert resp.status_code == 302

    # Now GET the agent dashboard — should be 200, not a redirect to admin login.
    resp = client.get(reverse("orders_agent:dashboard"))
    assert resp.status_code == 200
