"""Tests for admin-driven agent account creation."""
import pytest

from apps.accounts.models import AgentProfile, Role, User


@pytest.mark.django_db
class TestAgentCreation:
    """Creating an AGENT user provisions exactly one AgentProfile with a hashed password."""

    def test_agent_profile_created_with_hashed_password(self):
        raw_password = "S3cure!Agent#99"
        user = User.objects.create_user(
            username="delivery1",
            password=raw_password,
            role=Role.AGENT,
        )
        # Simulate what UserAdmin.save_model does
        AgentProfile.objects.get_or_create(user=user)

        assert AgentProfile.objects.filter(user=user).count() == 1
        assert user.check_password(raw_password) is True
        assert user.password != raw_password  # stored hash, not plaintext

    def test_get_or_create_is_idempotent(self):
        """Re-saving an existing AGENT must not raise IntegrityError."""
        user = User.objects.create_user(
            username="delivery2",
            password="pass",
            role=Role.AGENT,
        )
        AgentProfile.objects.get_or_create(user=user)
        AgentProfile.objects.get_or_create(user=user)  # second call — must not crash

        assert AgentProfile.objects.filter(user=user).count() == 1
