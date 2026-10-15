"""Test that bad credentials re-render the login page with an error."""
import pytest
from django.test import Client
from django.urls import reverse

from apps.accounts.models import Role, User


@pytest.mark.django_db
def test_wrong_password_shows_error():
    User.objects.create_user(
        username="testagent3", password="correctpass", role=Role.AGENT,
    )
    client = Client()
    resp = client.post(
        reverse("accounts:login"),
        {"username": "testagent3", "password": "wrongpass"},
    )
    # Should re-render the form, not redirect — status 200.
    assert resp.status_code == 200
    assert b"Incorrect username or password" in resp.content
