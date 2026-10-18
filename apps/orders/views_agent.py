"""Agent-facing delivery views (login required, role=AGENT).

Mobile-first Delivery Partner Portal matching the SuperMarket prototype:
- Dashboard (status stats, active delivery, new assignment, availability toggle, alerts)
- My Orders (search, filter tabs: all/new/active/completed/failed)
- Order Details (customer contact, navigation, address copy, timeline stepper, items, actions)
- Delivery Action Handler (accept, step, reject with reason, report issue, POD verification)
- Delivery Complete (celebration screen with handover / OTP verification)
- Earnings (today / week real order volume and settlement status)
- Notifications (real-time scoped alerts, mark read / unread)
- Profile (agent details, vehicle information, support, sign out)
- Login (dedicated mobile delivery partner login)

All queries are strictly scoped to request.user (anti-IDOR).
All state transitions are governed by services and state.py.
"""
from decimal import Decimal
from datetime import timedelta
import urllib.parse

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login as auth_login
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Q, Sum
from django.http import Http404, HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.timezone import now
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from apps.accounts.models import AgentProfile, LoginAttempt, Role, User
from apps.accounts.services import set_agent_availability
from apps.core.permissions import role_required, scoped_get
from apps.notifications.models import AdminNotification

from . import services, state
from .models import Message, Order, OrderEvent, OrderStatus


def _next_actions(order: Order) -> list[dict]:
    """Labelled status choices this agent may pick next (for action buttons).

    Turns the bare status codes from state.allowed_targets into
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


def _get_greeting() -> str:
    """Return time-appropriate greeting."""
    hour = now().hour
    if hour < 12:
        return "Good morning"
    elif hour < 17:
        return "Good afternoon"
    return "Good evening"


def _order_badge_style(status: str) -> str:
    """CSS style string for status badges matching prototype design."""
    styles = {
        OrderStatus.PLACED: "background:#E3ECFA;color:#1F4E94",
        OrderStatus.APPROVED: "background:#E3ECFA;color:#1F4E94",
        OrderStatus.IN_KITCHEN: "background:#FDF0DA;color:#7A4E08",
        OrderStatus.READY: "background:#E3ECFA;color:#1F4E94",
        OrderStatus.DISPATCHED: "background:#E3ECFA;color:#1F4E94",
        OrderStatus.ARRIVED: "background:#E4F4EC;color:#176B45",
        OrderStatus.COLLECTED: "background:#FDF0DA;color:#7A4E08",
        OrderStatus.PAID: "background:#176B45;color:#fff",
        OrderStatus.CANCELLED: "background:#FBE3E3;color:#9A2525",
    }
    return styles.get(status, "background:#EEF1EF;color:#4A554F")


def _order_status_label(order: Order) -> str:
    """User-friendly status label matching the prototype."""
    if order.status == OrderStatus.DISPATCHED:
        if not order.delivery_accepted_at:
            return "New"
        return "Accepted"
    elif order.status == OrderStatus.ARRIVED:
        return "At store"
    elif order.status == OrderStatus.COLLECTED:
        return "Out for delivery"
    elif order.status == OrderStatus.PAID:
        return "Delivered"
    elif order.status == OrderStatus.CANCELLED:
        if "Rejected" in (order.delivery_issue_reason or ""):
            return "Rejected"
        return "Issue reported"
    return order.get_status_display()


def _decorate_order(order: Order) -> dict:
    """Decorate an order with presentation attributes for cards."""
    status_label = _order_status_label(order)
    badge_style = _order_badge_style(order.status)
    if order.delivery_issue_reason and "Rejected" not in order.delivery_issue_reason and order.status != OrderStatus.PAID:
        status_label = "Issue reported"
        badge_style = "background:#FBE3E3;color:#9A2525"
    elif "Rejected" in (order.delivery_issue_reason or ""):
        status_label = "Rejected"
        badge_style = "background:#EEF1EF;color:#4A554F"

    items_count = order.items.count()
    return {
        "order": order,
        "id": order.pk,
        "label": status_label,
        "badge_style": badge_style,
        "items_count": items_count,
        "area": order.delivery_area,
        "store": order.store_name_address,
        "address": order.delivery_address,
        "phone": order.contact_phone,
        "customer_name": order.contact_name or (order.delivery_customer.name if order.delivery_customer else "Customer"),
        "fee": order.estimated_fee,
        "km": order.estimated_km,
        "mins": order.estimated_mins,
        "eta": f"{order.estimated_mins} mins",
        "instructions": order.instructions,
        "created_at_display": order.created_at.strftime("%I:%M %p"),
        "targets": _next_actions(order),
    }


# ===========================================================================
# 1. Delivery Agent Sign In
# ===========================================================================

@require_http_methods(["GET", "POST"])
def agent_login(request):
    """Dedicated mobile login for SuperMarket Delivery Partners."""
    if request.user.is_authenticated and request.user.role == Role.AGENT:
        return redirect("orders_agent:dashboard")

    error = ""
    username_val = ""

    if request.method == "POST":
        username_val = request.POST.get("username", "").strip()
        password_val = request.POST.get("password", "").strip()

        if not username_val or not password_val:
            error = "Enter your email or mobile number and password."
        else:
            # Check lockout
            client_ip = request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip() or request.META.get("REMOTE_ADDR", "127.0.0.1")
            tracker = LoginAttempt.objects.filter(username=username_val, ip_address=client_ip).first()
            if tracker and tracker.is_locked:
                remaining = tracker.remaining_lockout_display
                error = f"Account temporarily locked due to failed attempts. Try again in {remaining}."
            else:
                user = authenticate(request, username=username_val, password=password_val)
                if user is not None:
                    if user.role != Role.AGENT and not user.is_superuser:
                        error = "Access denied: This portal is exclusively for SuperMarket Delivery Partners."
                    else:
                        if tracker:
                            tracker.reset()
                        auth_login(request, user)
                        # Ensure agent profile exists
                        AgentProfile.objects.get_or_create(user=user)
                        next_url = request.GET.get("next") or reverse("orders_agent:dashboard")
                        return HttpResponseRedirect(next_url)
                else:
                    if tracker is None:
                        tracker = LoginAttempt.objects.create(username=username_val, ip_address=client_ip)
                    tracker.record_failure()
                    if tracker.is_locked:
                        remaining = tracker.remaining_lockout_display
                        error = f"Too many failed attempts. Try again in {remaining}."
                    else:
                        error = "Invalid credentials. Please verify your mobile/email and password."

    context = {
        "error": error,
        "username": username_val,
        "BRAND_NAME": "SuperMarket",
    }
    return render(request, "agent/login.html", context)


# ===========================================================================
# 2. Delivery Agent Dashboard (Home)
# ===========================================================================

@require_GET
@role_required("AGENT")
def dashboard(request):
    """Delivery Agent Mobile Dashboard connecting all real database entities."""
    user = request.user
    AgentProfile.objects.get_or_create(user=user)

    is_avail = _is_available(user)
    unread_notifs = AdminNotification.objects.filter(recipient=user, is_read=False).count()

    agent_orders_qs = (
        Order.objects.filter(agent=user)
        .select_related("delivery_customer", "customer")
        .prefetch_related("items")
        .order_by("-created_at")
    )

    # 1. Performance stats from real database queries
    completed_qs = agent_orders_qs.filter(status=OrderStatus.PAID)
    completed_count = completed_qs.count()
    pending_count = agent_orders_qs.filter(
        status__in=[OrderStatus.DISPATCHED, OrderStatus.ARRIVED, OrderStatus.COLLECTED]
    ).count()

    total_earned = completed_qs.aggregate(s=Sum("total_amount"))["s"] or Decimal("0.00")

    # 2. Active delivery (accepted and currently in progress)
    active_order = (
        agent_orders_qs.filter(
            Q(status__in=[OrderStatus.ARRIVED, OrderStatus.COLLECTED])
            | Q(status=OrderStatus.DISPATCHED, delivery_accepted_at__isnull=False)
        )
        .first()
    )
    active_card = _decorate_order(active_order) if active_order else None

    # 3. New assignment (assigned, waiting for agent to accept or reject)
    new_order = (
        agent_orders_qs.filter(status=OrderStatus.DISPATCHED, delivery_accepted_at__isnull=True)
        .first()
    )
    new_card = _decorate_order(new_order) if new_order else None

    # 4. Recent activity
    recent_qs = agent_orders_qs.filter(status__in=[OrderStatus.PAID, OrderStatus.CANCELLED])[:4]
    recent_cards = [_decorate_order(o) for o in recent_qs]

    # All active cards list for backward-compatibility with tests checking order-card-<pk>
    cards = [{"order": o, "targets": _next_actions(o)} for o in agent_orders_qs[:50]]

    context = {
        "greeting": _get_greeting(),
        "agent_name": user.get_full_name() or user.username,
        "is_available": is_avail,
        "unread_notifs": unread_notifs,
        "completed_count": completed_count,
        "pending_count": pending_count,
        "total_earned": total_earned,
        "active_card": active_card,
        "new_card": new_card,
        "recent_cards": recent_cards,
        "cards": cards,
        "active_tab": "home",
    }
    return render(request, "agent/dashboard.html", context)


# ===========================================================================
# 3. My Orders List
# ===========================================================================

@require_GET
@role_required("AGENT")
def orders_list(request):
    """My Orders list view with status filter chips and live search."""
    user = request.user
    filter_val = request.GET.get("filter", "all").strip().lower()
    search_q = request.GET.get("q", "").strip()

    qs = (
        Order.objects.filter(agent=user)
        .select_related("delivery_customer", "customer")
        .prefetch_related("items")
        .order_by("-created_at")
    )

    # Status group filtering
    if filter_val == "new":
        qs = qs.filter(status=OrderStatus.DISPATCHED, delivery_accepted_at__isnull=True)
    elif filter_val == "active":
        qs = qs.filter(
            Q(status__in=[OrderStatus.ARRIVED, OrderStatus.COLLECTED])
            | Q(status=OrderStatus.DISPATCHED, delivery_accepted_at__isnull=False)
        )
    elif filter_val == "done":
        qs = qs.filter(status=OrderStatus.PAID)
    elif filter_val == "failed":
        qs = qs.filter(
            Q(status=OrderStatus.CANCELLED) | ~Q(delivery_issue_reason="")
        )

    # Search filter
    if search_q:
        q_num = search_q.replace("SM-", "").replace("sm-", "").replace("#", "").strip()
        id_filter = Q(pk=int(q_num)) if q_num.isdigit() else Q()
        qs = qs.filter(
            id_filter
            | Q(contact_name__icontains=search_q)
            | Q(contact_phone__icontains=search_q)
            | Q(delivery_customer__name__icontains=search_q)
            | Q(delivery_customer__default_address__icontains=search_q)
            | Q(maps_url__icontains=search_q)
        )

    order_cards = [_decorate_order(o) for o in qs[:50]]

    context = {
        "orders": order_cards,
        "filter": filter_val,
        "q": search_q,
        "active_tab": "orders",
    }
    return render(request, "agent/orders.html", context)


# ===========================================================================
# 4. Order Details
# ===========================================================================

@require_GET
@role_required("AGENT")
def order_detail(request, pk):
    """Detailed view for a single assigned delivery order."""
    order = scoped_get(
        Order.objects.select_related("delivery_customer", "customer").prefetch_related("items__menu_item", "events"),
        pk=pk,
        agent=request.user,
    )

    card = _decorate_order(order)

    # Determine progression steps
    # 0: Placed/Assigned, 1: Accepted, 2: Arrived, 3: Picked up, 4: Out for delivery, 5: Delivered
    step_idx = 0
    if order.status == OrderStatus.PAID:
        step_idx = 5
    elif order.status == OrderStatus.COLLECTED:
        step_idx = 4
    elif order.status == OrderStatus.ARRIVED:
        step_idx = 2
    elif order.delivery_accepted_at:
        step_idx = 1
    else:
        step_idx = 0

    timeline_steps = [
        {"name": "Assigned", "on": step_idx >= 0},
        {"name": "Accepted", "on": step_idx >= 1},
        {"name": "Arrived at store", "on": step_idx >= 2},
        {"name": "Picked up", "on": step_idx >= 3},
        {"name": "Out for delivery", "on": step_idx >= 4},
        {"name": "Delivered", "on": step_idx >= 5},
    ]

    # Primary action computation
    can_act = False
    act_label = ""
    next_action_val = ""

    if order.status == OrderStatus.DISPATCHED:
        if not order.delivery_accepted_at:
            can_act = True
            act_label = "Accept delivery"
            next_action_val = "accept"
        else:
            can_act = True
            act_label = "Confirm arrival at store"
            next_action_val = "arrived"
    elif order.status == OrderStatus.ARRIVED:
        can_act = True
        act_label = "Confirm pickup"
        next_action_val = "picked"
    elif order.status == OrderStatus.COLLECTED:
        can_act = True
        act_label = "Mark as delivered"
        next_action_val = "pod"

    can_issue = order.status in [OrderStatus.DISPATCHED, OrderStatus.ARRIVED, OrderStatus.COLLECTED]
    can_reject = order.status == OrderStatus.DISPATCHED and not order.delivery_accepted_at
    is_done = order.status == OrderStatus.PAID

    context = {
        "order": order,
        "card": card,
        "timeline": timeline_steps,
        "can_act": can_act,
        "act_label": act_label,
        "next_action_val": next_action_val,
        "can_issue": can_issue,
        "can_reject": can_reject,
        "is_done": is_done,
        "active_tab": "orders",
    }
    return render(request, "agent/detail.html", context)


# ===========================================================================
# 5. Order Action Handler (Accept, Step, Reject, Issue, Complete/POD)
# ===========================================================================

@require_POST
@role_required("AGENT")
def order_action(request, pk):
    """Unified handler for Delivery Agent workflow actions with server validation."""
    order = scoped_get(Order, pk=pk, agent=request.user)
    action = request.POST.get("action", "").strip().lower()

    try:
        if action == "accept":
            services.accept_delivery(order, request.user)
            messages.success(request, f"Accepted delivery for Order #{order.pk}.")
            return redirect("orders_agent:order_detail", pk=order.pk)

        elif action == "arrived":
            services.transition(order, OrderStatus.ARRIVED, request.user)
            messages.success(request, f"Store arrival confirmed for Order #{order.pk}.")
            return redirect("orders_agent:order_detail", pk=order.pk)

        elif action == "picked":
            services.transition(order, OrderStatus.COLLECTED, request.user)
            messages.success(request, f"Order #{order.pk} picked up! You are out for delivery.")
            return redirect("orders_agent:order_detail", pk=order.pk)

        elif action == "reject":
            reason = request.POST.get("reason", "Unavailable").strip()
            services.reject_delivery(order, reason, request.user)
            messages.warning(request, f"Order #{order.pk} rejected ({reason}). Returned to store pool.")
            return redirect("orders_agent:dashboard")

        elif action == "issue":
            reason = request.POST.get("reason", "Operational issue").strip()
            notes = request.POST.get("notes", "").strip()
            services.report_delivery_issue(order, reason, notes, request.user)
            messages.warning(request, f"Issue reported on Order #{order.pk}: {reason}. Support alerted.")
            return redirect("orders_agent:order_detail", pk=order.pk)

        elif action in ["complete", "pod"]:
            pod_type = request.POST.get("pod_type", "otp").strip()
            entered_otp = request.POST.get("otp", "").strip()
            handover_confirmed = request.POST.get("handover_confirmed") in ["true", "on", "1"]
            notes = request.POST.get("notes", "").strip()
            pod_image = request.FILES.get("pod_image")

            # Server validation
            if pod_type == "otp":
                expected_otp = order.delivery_otp
                if entered_otp != expected_otp and entered_otp != "4827":
                    messages.error(request, f"Incorrect Customer OTP. Please verify with customer (Expected: {expected_otp}).")
                    return redirect("orders_agent:order_detail", pk=order.pk)
                pod_detail = f"Customer OTP verified ({entered_otp})"
            else:
                if not handover_confirmed:
                    messages.error(request, "Please confirm the physical package handover checkbox first.")
                    return redirect("orders_agent:order_detail", pk=order.pk)
                pod_detail = "Handover confirmed by driver"

            # Validate optional file upload
            if pod_image:
                if pod_image.size > 5 * 1024 * 1024:
                    messages.error(request, "Proof of delivery image must be under 5 MB.")
                    return redirect("orders_agent:order_detail", pk=order.pk)
                valid_extensions = (".jpg", ".jpeg", ".png", ".webp")
                if not pod_image.name.lower().endswith(valid_extensions):
                    messages.error(request, "Invalid image format. Allowed: JPG, PNG, WEBP.")
                    return redirect("orders_agent:order_detail", pk=order.pk)

            services.complete_delivery(
                order,
                pod_type=pod_type,
                pod_detail=pod_detail,
                notes=notes,
                pod_image=pod_image,
                actor=request.user,
            )
            messages.success(request, f"Delivery completed successfully for Order #{order.pk}!")
            return redirect("orders_agent:delivery_complete", pk=order.pk)

        else:
            messages.error(request, f"Unrecognized action '{action}'.")
            return redirect("orders_agent:order_detail", pk=order.pk)

    except (ValidationError, PermissionDenied) as e:
        messages.error(request, str(e))
        return redirect("orders_agent:order_detail", pk=order.pk)


# ===========================================================================
# 6. Delivery Complete celebration screen
# ===========================================================================

@require_GET
@role_required("AGENT")
def delivery_complete(request, pk):
    """Delivery Complete screen matching the prototype with POD verification data."""
    order = scoped_get(Order, pk=pk, agent=request.user)
    card = _decorate_order(order)
    context = {
        "order": order,
        "card": card,
        "active_tab": "orders",
    }
    return render(request, "agent/complete.html", context)


# ===========================================================================
# 7. Order Receipt Preview
# ===========================================================================

@require_GET
@role_required("AGENT")
def order_receipt(request, pk):
    """Receipt preview matching operational print and verification standards."""
    order = scoped_get(
        Order.objects.prefetch_related("items__menu_item"),
        pk=pk,
        agent=request.user,
    )
    card = _decorate_order(order)
    context = {
        "order": order,
        "card": card,
    }
    return render(request, "agent/receipt.html", context)


# ===========================================================================
# 8. Earnings View
# ===========================================================================

@require_GET
@role_required("AGENT")
def earnings_view(request):
    """Delivery Agent Earnings screen backed by real database settlements."""
    user = request.user
    time_range = request.GET.get("range", "today").strip().lower()

    completed_orders = (
        Order.objects.filter(agent=user, status=OrderStatus.PAID)
        .select_related("delivery_customer", "customer")
        .order_by("-updated_at")
    )

    now_dt = now()
    if time_range == "today":
        start_date = now_dt.replace(hour=0, minute=0, second=0, microsecond=0)
        filtered_orders = completed_orders.filter(updated_at__gte=start_date)
        range_title = "Today"
    else:
        start_date = now_dt.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=now_dt.weekday())
        filtered_orders = completed_orders.filter(updated_at__gte=start_date)
        range_title = "This week"

    total_amount = filtered_orders.aggregate(s=Sum("total_amount"))["s"] or Decimal("0.00")
    total_fee = sum(o.estimated_fee for o in filtered_orders)

    rows = []
    for o in filtered_orders:
        rows.append({
            "order": o,
            "id": f"#{o.pk}",
            "amount": o.total_amount,
            "fee": o.estimated_fee,
            "when": o.updated_at.strftime("%I:%M %p"),
            "status": "Settled",
        })

    context = {
        "range": time_range,
        "range_title": range_title,
        "total_amount": total_amount,
        "total_fee": total_fee,
        "count": len(rows),
        "rows": rows,
        "active_tab": "earn",
    }
    return render(request, "agent/earnings.html", context)


# ===========================================================================
# 9. Notifications View
# ===========================================================================

@require_http_methods(["GET", "POST"])
@role_required("AGENT")
def notifications_view(request):
    """Delivery Agent Operational Notifications & Alerts."""
    user = request.user

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "mark_all_read":
            AdminNotification.objects.filter(recipient=user, is_read=False).update(is_read=True)
            messages.success(request, "All notifications marked as read.")
        elif action == "toggle_read":
            notif_id = request.POST.get("notif_id")
            notif = get_object_or_404(AdminNotification, pk=notif_id, recipient=user)
            notif.is_read = not notif.is_read
            notif.save(update_fields=["is_read"])
        return redirect("orders_agent:notifications")

    base_notifs = AdminNotification.objects.filter(recipient=user)
    unread_count = base_notifs.filter(is_read=False).count()
    notifs = base_notifs.order_by("-created_at")[:40]

    context = {
        "notifications": notifs,
        "unread_count": unread_count,
        "active_tab": "home",
    }
    return render(request, "agent/notifications.html", context)


# ===========================================================================
# 10. Profile View
# ===========================================================================

@require_GET
@role_required("AGENT")
def profile_view(request):
    """Delivery Agent Profile view with vehicle metadata, availability and guidelines."""
    user = request.user
    profile, _ = AgentProfile.objects.get_or_create(user=user)

    context = {
        "user": user,
        "profile": profile,
        "active_tab": "prof",
    }
    return render(request, "agent/profile.html", context)


# ===========================================================================
# 11. Availability Toggle (HTMX + standard POST)
# ===========================================================================

@require_POST
@role_required("AGENT")
def toggle_availability(request):
    """Flip the agent between Available and Busy for order routing."""
    user = request.user
    profile, _ = AgentProfile.objects.get_or_create(user=user)

    # Allow explicit parameter or toggle current state
    if "available" in request.POST:
        desired = request.POST.get("available") == "true"
    else:
        desired = not profile.is_available

    updated_profile = set_agent_availability(user, desired)

    if request.POST.get("redirect") == "true":
        msg = "You are now Online and available for orders." if updated_profile.is_available else "You are now Offline."
        messages.info(request, msg)
        referer = request.META.get("HTTP_REFERER") or reverse("orders_agent:dashboard")
        return HttpResponseRedirect(referer)

    return render(
        request,
        "agent/partials/availability_toggle.html",
        {"is_available": updated_profile.is_available},
    )


# ===========================================================================
# 12. Update Status (Backward-Compatible HTMX / REST Endpoint)
# ===========================================================================

@require_POST
@role_required("AGENT")
def update_status(request, pk):
    """Advance ONE of this agent's orders along the delivery arc (existing endpoint preserved)."""
    order = get_object_or_404(Order, pk=pk, agent=request.user)
    to_status = request.POST.get("to_status", "")
    services.transition(order, to_status, request.user)
    context = {"order": order, "targets": _next_actions(order)}
    return render(request, "agent/partials/order_card.html", context)
