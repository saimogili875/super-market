"""Agent-facing delivery views (login required, role=AGENT).

Thin views: every query is scoped to ``request.user`` (anti-IDOR) and every
status change is delegated to ``services.transition`` (which enforces the
state machine in ``state.py``). Availability flips go through
``accounts.services.set_agent_availability``. No business rules live here.
"""
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET, require_POST

from apps.accounts.services import set_agent_availability
from apps.core.permissions import role_required

from . import services, state
from .models import Order, OrderStatus


def _next_actions(order: Order) -> list[dict]:
    """Labelled status choices this agent may pick next (for action buttons).

    Turns the bare status codes from ``state.allowed_targets`` into
    {"value", "label"} dicts so the template can render human-readable
    buttons without embedding workflow knowledge.
    """
    targets = []
    for target in state.allowed_targets("AGENT", order.status):
        label = "Paid" if target == OrderStatus.PAID else OrderStatus(target).label
        targets.append({"value": target, "label": label})
    return targets


def _is_available(user) -> bool:
    """True if the agent currently has an available AgentProfile."""
    profile = getattr(user, "agent", None)
    return bool(profile and profile.is_available)


@require_GET
@role_required("AGENT")
def dashboard(request):
    """List the delivery orders assigned to the signed-in agent."""
    orders = (
        Order.objects.filter(agent=request.user)
        .select_related("customer", "table", "session")
        .order_by("-created_at")[:50]
    )
    cards = [{"order": order, "targets": _next_actions(order)} for order in orders]
    context = {"cards": cards, "is_available": _is_available(request.user)}
    return render(request, "agent/dashboard.html", context)


@require_POST
@role_required("AGENT")
def update_status(request, pk):
    """Advance ONE of this agent's orders along the delivery arc."""
    order = get_object_or_404(Order, pk=pk, agent=request.user)
    services.transition(order, request.POST.get("to_status", ""), request.user)
    context = {"order": order, "targets": _next_actions(order)}
    return render(request, "agent/partials/order_card.html", context)


@require_POST
@role_required("AGENT")
def toggle_availability(request):
    """Flip the agent between Available and Busy for order routing."""
    desired = request.POST.get("available") == "true"
    profile = set_agent_availability(request.user, desired)
    return render(
        request,
        "agent/partials/availability_toggle.html",
        {"is_available": profile.is_available},
    )
