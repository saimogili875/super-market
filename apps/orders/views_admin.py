"""Admin-only endpoints for the orders app.

Thin views: they resolve objects, delegate to services.py, and hand back an
HTMX fragment. No business rules live here — assignment logic (role checks,
availability, audit event, broadcast) is all in services.assign_agent.
"""
from itertools import groupby

from django.db.models import Q
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET, require_POST

from apps.accounts.models import Role, User
from apps.core.permissions import role_required
from apps.tables.models import TableSession

from . import services, state
from .models import Order, OrderStatus

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TERMINAL = (OrderStatus.PAID, OrderStatus.CANCELLED)


def _action_buttons(order):
    """Return labelled targets the ADMIN may transition this order to."""
    if order.status in _TERMINAL:
        return []

    if order.order_type == "DELV" and order.agent_id is not None:
        # Once an agent is assigned, admin gets read-only view with emergency cancel only
        return [{"value": OrderStatus.CANCELLED, "label": "Emergency cancel"}]

    targets = state.allowed_targets("ADMIN", order.status)
    targets = [t for t in targets if t != OrderStatus.DISPATCHED]
    return [
        {"value": t, "label": OrderStatus(t).label}
        for t in targets
    ]


def _available_agents():
    """Return AGENT users whose profile is marked available."""
    return User.objects.filter(role=Role.AGENT, agent__is_available=True)


def _card_context(order):
    """Build the template context dict for a single order card."""
    return {
        "order": order,
        "targets": _action_buttons(order),
        "available_agents": _available_agents(),
    }


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@require_GET
@role_required("ADMIN")
def dashboard(request):
    """Admin operational dashboard — live view of active orders."""
    available_agents = _available_agents()

    active_delivery = (
        Order.objects
        .filter(order_type="DELV")
        .exclude(status__in=_TERMINAL)
        .select_related("table", "session", "agent", "customer")
        .prefetch_related("items")
        .order_by("-created_at")[:100]
    )
    delivery_orders = [
        {
            "order": order,
            "targets": _action_buttons(order),
            "available_agents": available_agents,
        }
        for order in active_delivery
    ]

    active_dine_session_ids = (
        Order.objects
        .filter(order_type="DINE", session__isnull=False)
        .exclude(status__in=_TERMINAL)
        .values_list("session_id", flat=True)
    )

    open_sessions = (
        TableSession.objects.filter(
            Q(closed_at__isnull=True) | Q(pk__in=active_dine_session_ids),
            table__is_active=True,
        )
        .select_related("table")
        .prefetch_related(
            "orders__items",
            "orders__table",
            "orders__session",
            "orders__agent",
            "orders__customer",
        )
        .order_by("table__number", "-opened_at")
    )

    dine_by_table = []
    for table, sessions in groupby(open_sessions, key=lambda s: s.table):
        session_list = []
        for s in sessions:
            active_orders = [o for o in s.orders.all() if o.status != OrderStatus.CANCELLED]
            order_cards = [
                {
                    "order": o,
                    "targets": _action_buttons(o),
                    "available_agents": available_agents,
                }
                for o in active_orders
            ]
            session_list.append({
                "session": s,
                "table": table,
                "orders": order_cards,
                "total": s.total,
                "bill_requested": getattr(s, "bill_requested", False),
            })
        dine_by_table.append({"table": table, "sessions": session_list})

    context = {
        "dine_by_table": dine_by_table,
        "delivery_cards": delivery_orders,
    }
    return render(request, "orders/admin/dashboard.html", context)


# ---------------------------------------------------------------------------
# Transition (thin: ≤ 15 lines)
# ---------------------------------------------------------------------------

@require_GET
@role_required("ADMIN")
def order_detail(request, pk):
    """Full detail view for one order: items, audit timeline, contact, maps link."""
    order = get_object_or_404(
        Order.objects
        .select_related("table", "session", "agent", "customer")
        .prefetch_related("items", "events__actor", "messages"),
        pk=pk,
    )
    # Build a human-readable audit timeline from the append-only OrderEvents.
    timeline = []
    for event in order.events.all():
        from_label = OrderStatus(event.from_status).label if event.from_status else "New"
        to_label = OrderStatus(event.to_status).label if event.to_status else "—"
        timeline.append({
            "from_label": from_label,
            "to_label": to_label,
            "actor": event.actor,
            "at": event.at,
            "is_assignment": event.from_status == event.to_status and event.from_status != "",
        })
    context = _card_context(order)
    context.update({"order": order, "timeline": timeline, "messages_list": order.messages.all()})
    return render(request, "orders/admin/detail.html", context)


@require_POST
@role_required("ADMIN")
def transition_order(request, pk):
    """Move an order to a new status via the state machine; return the card."""
    order = get_object_or_404(Order, pk=pk)
    to_status = request.POST.get("to_status", "")
    services.transition(order, to_status, request.user)
    return render(
        request, "orders/admin/partials/order_card.html", _card_context(order),
    )


# ---------------------------------------------------------------------------
# Card partial (GET — used by live-update JS to refresh a single card)
# ---------------------------------------------------------------------------

@require_GET
@role_required("ADMIN")
def order_card(request, pk):
    """Return the rendered card partial for one order (HTMX fragment)."""
    order = get_object_or_404(
        Order.objects.select_related("table", "session", "agent", "customer")
        .prefetch_related("items"),
        pk=pk,
    )
    return render(
        request, "orders/admin/partials/order_card.html", _card_context(order),
    )


# ---------------------------------------------------------------------------
# Assign (existing endpoint — unchanged business logic, updated context)
# ---------------------------------------------------------------------------

@require_POST
@role_required("ADMIN")
def assign_order(request, pk):
    """Assign a delivery order to an available agent; return the updated row."""
    order = get_object_or_404(
        Order.objects.select_related("customer", "table", "agent", "session"),
        pk=pk,
    )
    agent_id = request.POST.get("agent_id")
    if agent_id:
        agent = get_object_or_404(User, pk=agent_id, role=Role.AGENT)
        services.assign_agent(order, agent, request.user)
    return render(request, "orders/admin/partials/order_card.html", _card_context(order))
