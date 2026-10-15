"""Tests for RBAC primitives — role_required decorator and scoped_get."""
import pytest
from django.http import JsonResponse
from django.test import RequestFactory

from apps.accounts.models import AgentProfile, Role, User
from apps.core.permissions import role_required, scoped_get


# --- dummy view for decorator testing ---
@role_required("ADMIN")
def admin_only_view(request):
    """Stub view that only ADMINs may access."""
    return JsonResponse({"ok": True})


@pytest.mark.django_db
class TestRoleRequired:
    """role_required decorator returns 403 for wrong role, 200 for correct."""

    def setup_method(self):
        self.factory = RequestFactory()

    def test_admin_gets_200(self):
        user = User.objects.create_user(username="adm", password="pass", role=Role.ADMIN)
        request = self.factory.get("/fake/")
        request.user = user
        response = admin_only_view(request)
        assert response.status_code == 200

    def test_agent_gets_403(self):
        user = User.objects.create_user(username="agt", password="pass", role=Role.AGENT)
        request = self.factory.get("/fake/")
        request.user = user
        with pytest.raises(Exception) as exc_info:
            admin_only_view(request)
        assert "403" in str(exc_info.value) or exc_info.type.__name__ == "PermissionDenied"

    def test_anonymous_gets_redirect(self):
        from django.contrib.auth.models import AnonymousUser

        request = self.factory.get("/fake/")
        request.user = AnonymousUser()
        response = admin_only_view(request)
        assert response.status_code == 302


@pytest.mark.django_db
class TestScopedGet:
    """scoped_get returns 404 when ownership filter doesn't match (IDOR)."""

    def test_owner_can_fetch_own_profile(self):
        user = User.objects.create_user(username="agt1", password="pass", role=Role.AGENT)
        profile = AgentProfile.objects.create(user=user)
        result = scoped_get(AgentProfile, user=user, pk=profile.pk)
        assert result == profile

    def test_idor_returns_404(self):
        """Agent A cannot fetch agent B's profile via scoped_get."""
        agent_a = User.objects.create_user(username="a", password="pass", role=Role.AGENT)
        agent_b = User.objects.create_user(username="b", password="pass", role=Role.AGENT)
        profile_b = AgentProfile.objects.create(user=agent_b)

        from django.http import Http404

        with pytest.raises(Http404):
            scoped_get(AgentProfile, user=agent_a, pk=profile_b.pk)
