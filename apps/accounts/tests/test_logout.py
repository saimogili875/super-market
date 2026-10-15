"""Test that POST /accounts/logout/ ends the session."""
import pytest
from django.test import Client
from django.urls import reverse

from apps.accounts.models import AgentProfile, Role, User


@pytest.mark.django_db
def test_logout_ends_session():
    user = User.objects.create_user(
        username="testagent4", password="testpass123", role=Role.AGENT,
    )
    AgentProfile.objects.create(user=user)
    client = Client()

    # Login first.
    client.post(
        reverse("accounts:login"),
        {"username": "testagent4", "password": "testpass123"},
    )
    # Confirm agent can reach dashboard.
    resp = client.get(reverse("orders_agent:dashboard"))
    assert resp.status_code == 200

    # Logout via POST.
    resp = client.post(reverse("accounts:logout"))
    assert resp.status_code == 302  # redirect to login page

    # Agent dashboard should now redirect to login.
    resp = client.get(reverse("orders_agent:dashboard"))
    assert resp.status_code == 302
    assert "/accounts/login/" in resp.url
