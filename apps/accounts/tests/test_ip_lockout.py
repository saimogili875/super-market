"""Tests verifying that login lockout is scoped to (username, ip_address) pair."""
import pytest
from django.urls import reverse

from apps.accounts.models import LoginAttempt, User


@pytest.fixture
def agent_user():
    user = User.objects.create_user(username="testagent", password="correct_password", role="AGENT")
    return user


@pytest.mark.django_db
def test_ip_scoped_login_lockout(client, agent_user):
    """Failed login attempts from IP A do not lock out login attempts for the same user from IP B."""
    login_url = reverse("accounts:login")

    # Fail login 7 times from IP_A (192.168.1.100)
    for _ in range(7):
        client.post(
            login_url,
            {"username": "testagent", "password": "wrong_password"},
            REMOTE_ADDR="192.168.1.100",
        )

    # Assert IP_A is locked out
    res_a = client.post(
        login_url,
        {"username": "testagent", "password": "wrong_password"},
        REMOTE_ADDR="192.168.1.100",
    )
    assert b"Account locked" in res_a.content or b"Too many failed attempts" in res_a.content

    # Assert IP_B (192.168.1.200) can still attempt and log in with correct password
    res_b = client.post(
        login_url,
        {"username": "testagent", "password": "correct_password"},
        REMOTE_ADDR="192.168.1.200",
    )
    assert res_b.status_code == 302
    assert res_b.url == reverse("orders_agent:dashboard")


@pytest.mark.django_db
def test_ip_scoped_escalating_schedule(client, agent_user):
    """Failure counts escalate lockout duration per (username, ip_address)."""
    login_url = reverse("accounts:login")
    ip = "10.0.0.1"

    # 3 failures -> tier 3 (1 min lockout)
    for _ in range(3):
        client.post(login_url, {"username": "testagent", "password": "wrong"}, REMOTE_ADDR=ip)

    tracker = LoginAttempt.objects.get(username="testagent", ip_address=ip)
    assert tracker.failed_attempts == 3
    assert tracker.is_locked
    assert tracker.get_lockout_duration().total_seconds() == 60


@pytest.mark.django_db
def test_admin_exempt_from_lockout(client):
    """Admin users are exempt from login lockout regardless of failed attempts."""
    admin = User.objects.create_user(username="adminuser", password="adminpassword", role="ADMIN")
    login_url = reverse("accounts:login")
    ip = "192.168.1.50"

    for _ in range(10):
        client.post(login_url, {"username": "adminuser", "password": "wrongpassword"}, REMOTE_ADDR=ip)

    # Admin attempt with correct password should still succeed
    res = client.post(login_url, {"username": "adminuser", "password": "adminpassword"}, REMOTE_ADDR=ip)
    assert res.status_code == 302
    assert res.url == reverse("orders_admin:dashboard")

