"""Tests for User model role behaviour."""
import pytest

from apps.accounts.models import Role, User


@pytest.mark.django_db
class TestUserRoles:
    """Verify default role and convenience properties."""

    def test_default_role_is_customer(self):
        user = User.objects.create_user(username="cust1", password="testpass123")
        assert user.role == Role.CUSTOMER

    def test_is_admin_role(self):
        user = User(username="a", role=Role.ADMIN)
        assert user.is_admin_role is True
        assert user.is_agent is False
        assert user.is_customer is False

    def test_is_agent(self):
        user = User(username="b", role=Role.AGENT)
        assert user.is_agent is True
        assert user.is_admin_role is False
        assert user.is_customer is False

    def test_is_customer(self):
        user = User(username="c", role=Role.CUSTOMER)
        assert user.is_customer is True
        assert user.is_admin_role is False
        assert user.is_agent is False
