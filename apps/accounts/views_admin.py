"""Admin-dashboard views for users & delivery-agent management.

All views are role_required("ADMIN"). Business rules are reused from
accounts.services (availability) and Django's UserCreationForm (hashed
passwords). Password hashes are NEVER placed in any context.
"""
from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST

from apps.core.permissions import role_required

from .forms import AgentCreationForm
from .models import AgentProfile, Role, User
from .services import set_agent_availability


def _agents_qs():
    """Delivery agents with their availability profile (avoids N+1)."""
    return (
        User.objects.filter(role=Role.AGENT)
        .select_related("agent")
        .order_by("-is_active", "username")
    )


@require_GET
@role_required("ADMIN")
def agents(request):
    """List delivery agents + the create-agent form."""
    return render(
        request,
        "accounts/admin/agents.html",
        {"agents": _agents_qs(), "form": AgentCreationForm()},
    )


@require_POST
@role_required("ADMIN")
def agent_create(request):
    """Create a delivery-agent account (hashed password) + AgentProfile."""
    form = AgentCreationForm(request.POST)
    if form.is_valid():
        with transaction.atomic():
            user = form.save()
            AgentProfile.objects.get_or_create(user=user)
        messages.success(request, f"Agent '{user.username}' created.")
        return redirect("accounts_admin:agents")

    # Re-render the page with validation errors (no redirect so errors show).
    messages.error(request, "Could not create agent — please fix the errors below.")
    return render(
        request,
        "accounts/admin/agents.html",
        {"agents": _agents_qs(), "form": form},
        status=400,
    )


@require_POST
@role_required("ADMIN")
def agent_toggle_availability(request, pk):
    """Flip an agent's availability; return the updated row (HTMX)."""
    agent = get_object_or_404(User, pk=pk, role=Role.AGENT)
    profile = set_agent_availability(agent, not _is_available(agent))
    agent.refresh_from_db()
    return render(
        request,
        "accounts/admin/partials/agent_row.html",
        {"agent": agent, "profile": profile},
    )


@require_POST
@role_required("ADMIN")
def agent_deactivate(request, pk):
    """Deactivate an agent account (also marks them unavailable)."""
    agent = get_object_or_404(User, pk=pk, role=Role.AGENT)
    with transaction.atomic():
        agent.is_active = False
        agent.save(update_fields=["is_active"])
        set_agent_availability(agent, False)
    agent.refresh_from_db()
    return render(
        request,
        "accounts/admin/partials/agent_row.html",
        {"agent": agent, "profile": getattr(agent, "agent", None)},
    )


@require_GET
@role_required("ADMIN")
def users(request):
    """Read-only overview of all users grouped by role (no password hashes)."""
    by_role = []
    for value, label in Role.choices:
        members = (
            User.objects.filter(role=value)
            .only("id", "username", "email", "phone", "role", "is_active", "is_staff")
            .order_by("username")
        )
        by_role.append({"label": label, "value": value, "users": members})
    return render(request, "accounts/admin/users.html", {"by_role": by_role})


def _is_available(agent) -> bool:
    """True if the agent currently has an available AgentProfile."""
    profile = getattr(agent, "agent", None)
    return bool(profile and profile.is_available)
