"""Tests for availability toggle endpoint."""
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.accounts.models import Role, User
from apps.menu.models import Category, MenuItem


@pytest.fixture
def test_item():
    """Create a test menu item."""
    cat = Category.objects.create(name="Cat")
    return MenuItem.objects.create(
        category=cat, name="Item", price=Decimal("10"), is_available=True
    )


@pytest.mark.django_db
def test_toggle_endpoint_forbidden_for_agent(client, test_item):
    """AGENT users get 403 on toggle."""
    user = User.objects.create_user(username="agent", password="pw", role=Role.AGENT)
    client.force_login(user)
    
    url = reverse("menu:toggle_availability", kwargs={"pk": test_item.pk})
    resp = client.post(url)
    assert resp.status_code == 403


@pytest.mark.django_db
def test_toggle_endpoint_success_for_admin(client, test_item):
    """ADMIN users can toggle availability."""
    user = User.objects.create_user(username="admin", password="pw", role=Role.ADMIN)
    client.force_login(user)
    
    url = reverse("menu:toggle_availability", kwargs={"pk": test_item.pk})
    resp = client.post(url)
    assert resp.status_code == 200
    assert "Unavailable" in resp.content.decode()
    
    test_item.refresh_from_db()
    assert test_item.is_available is False
