"""Views for digital dining table ordering and session management.

Thin views orchestrating services.create_order(), transition(), and
session lifecycle. Never computes pricing or mutates status directly.
"""
from decimal import Decimal

from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Prefetch, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST

from apps.core.permissions import role_required
from apps.core.ratelimits import dine_in_order
from apps.menu.models import Category as MenuCategory
from apps.menu.models import MenuItem
from apps.menu.services import get_cached_menu
from apps.orders.models import OrderStatus
from apps.orders.services import create_order, transition
from apps.realtime.broadcast import broadcast

from .models import Table, TableSession
from .services import (
    close_session,
    resolve_active_session,
    resolve_session,
    set_session_cookie,
    start_tab,
)


def _get_cart_data(session_id: int, session_dict: dict) -> tuple[list[dict], Decimal, int]:
    """Helper to parse session cart into item dicts and computed total."""
    cart_raw = session_dict.get(f"cart_{session_id}", {})
    if not cart_raw:
        return [], Decimal("0"), 0

    items = []
    total = Decimal("0")
    count = 0
    menu_items = MenuItem.objects.filter(pk__in=cart_raw.keys(), is_available=True)
    menu_map = {str(item.pk): item for item in menu_items}

    for mid, qty in cart_raw.items():
        if mid in menu_map and qty > 0:
            item = menu_map[mid]
            line_total = item.effective_price * qty
            total += line_total
            count += qty
            items.append({
                "item": item,
                "quantity": qty,
                "line_total": line_total,
            })

    return items, total, count


@require_GET
def table_menu(request, qr_token: str):
    """Render the digital menu for a dining table."""
    table = get_object_or_404(Table, qr_token=qr_token, is_active=True)
    session = resolve_active_session(request, table)
    if session is None:
        return render(request, "tables/start_tab.html", {"table": table})
    request.session["table_token"] = qr_token

    all_categories = get_cached_menu()
    search = request.GET.get("search", "").strip()
    category = request.GET.get("category", "all")

    if search or (category and category != "all"):
        item_qs = MenuItem.objects.filter(is_available=True).order_by("name")
        if search:
            item_qs = item_qs.filter(Q(name__icontains=search) | Q(description__icontains=search))
        if category and category != "all":
            item_qs = item_qs.filter(category__name=category)
        categories = MenuCategory.objects.filter(is_active=True).prefetch_related(
            Prefetch("items", queryset=item_qs)
        ).order_by("sort_order", "name")
    else:
        categories = all_categories

    has_results = any(len(cat.items.all()) > 0 for cat in categories)
    cart_items, cart_total, cart_count = _get_cart_data(session.pk, request.session)

    context = {
        "table": table,
        "session": session,
        "categories": categories,
        "all_categories": all_categories,
        "has_results": has_results,
        "search": search,
        "category": category,
        "cart_items": cart_items,
        "cart_total": cart_total,
        "cart_count": cart_count,
    }
    if request.headers.get("HX-Request"):
        response = render(request, "tables/partials/menu_results.html", context)
    else:
        response = render(request, "tables/menu.html", context)
    set_session_cookie(response, table, session)
    return response


@require_POST
def cart_add(request, qr_token: str):
    """HTMX endpoint to add a menu item to the active session cart."""
    table = get_object_or_404(Table, qr_token=qr_token, is_active=True)
    session = resolve_active_session(request, table)
    if session is None:
        return HttpResponse("No active tab found.", status=404)

    menu_item_id = request.POST.get("menu_item_id")
    try:
        quantity = int(request.POST.get("quantity", 1))
    except (ValueError, TypeError):
        quantity = 1

    error = None
    if menu_item_id and quantity > 0:
        mi = MenuItem.objects.filter(pk=menu_item_id).first()
        if not mi or not mi.is_available:
            error = f"'{mi.name if mi else menu_item_id}' is currently unavailable."
        elif not mi.is_orderable:
            error = f"'{mi.name}' is sold out."
        else:
            cart_key = f"cart_{session.pk}"
            cart = request.session.get(cart_key, {})
            current_qty = cart.get(str(menu_item_id), 0)
            if mi.track_stock and mi.stock_quantity < (current_qty + quantity):
                if mi.stock_quantity:
                    error = f"Only {mi.stock_quantity} left of '{mi.name}'."
                else:
                    error = f"'{mi.name}' is sold out."
            else:
                cart[str(menu_item_id)] = current_qty + quantity
                request.session[cart_key] = cart
                request.session.modified = True

    cart_items, cart_total, cart_count = _get_cart_data(session.pk, request.session)
    context = {
        "table": table,
        "session": session,
        "cart_items": cart_items,
        "cart_total": cart_total,
        "cart_count": cart_count,
        "error": error,
    }
    return render(request, "tables/partials/cart_bar.html", context)


@dine_in_order
@require_POST
def place_order(request, qr_token: str):
    """Place initial or iterative order from cart for this table session."""
    table = get_object_or_404(Table, qr_token=qr_token, is_active=True)
    session = resolve_active_session(request, table)
    if session is None:
        return HttpResponse("No active tab found.", status=404)

    cart_key = f"cart_{session.pk}"
    cart_raw = request.session.get(cart_key, {})
    if not cart_raw:
        return HttpResponse("Cart is empty", status=400)

    items = [
        {"menu_item_id": int(mid), "quantity": qty}
        for mid, qty in cart_raw.items()
        if qty > 0
    ]

    try:
        create_order(
            order_type="DINE",
            table=table,
            session=session,
            items=items,
        )
    except ValidationError as exc:
        error_msg = exc.messages[0] if hasattr(exc, "messages") and exc.messages else str(exc)
        return HttpResponse(
            f'<div class="card mt-4" style="background-color: var(--color-danger-light); '
            f'border-color: var(--color-danger); color: var(--color-danger-dark);">'
            f'<div class="card-body">'
            f'<h3 class="text-lg text-bold mb-2">Order Could Not Be Placed</h3>'
            f'<p class="mb-4">{error_msg}</p>'
            f'<a href="?category=all" class="btn btn-primary">Back to Menu</a>'
            f'</div></div>'
        )

    request.session[cart_key] = {}
    request.session.modified = True

    orders = (
        session.orders.exclude(status=OrderStatus.CANCELLED)
        .prefetch_related("items")
        .order_by("-created_at")
    )
    tab_total = session.total

    context = {
        "table": table,
        "session": session,
        "orders": orders,
        "tab_total": tab_total,
        "bill_requested": (
            session.bill_requested
            or request.session.get(f"bill_req_{session.pk}", False)
        ),
    }
    return render(request, "tables/partials/running_tab.html", context)


@dine_in_order
@require_POST
def add_items(request, qr_token: str):
    """Iterative ordering endpoint: delegates to place_order."""
    return place_order(request, qr_token)


@require_POST
def request_bill(request, qr_token: str):
    """Request the bill for the active table session."""
    table = get_object_or_404(Table, qr_token=qr_token, is_active=True)
    session = resolve_active_session(request, table)
    if session is None:
        return HttpResponse("No active tab found.", status=404)

    session.bill_requested = True
    session.save(update_fields=["bill_requested", "updated_at"])
    request.session[f"bill_req_{session.pk}"] = True
    request.session.modified = True

    broadcast(
        "admin.dashboard",
        "table.bill_request",
        {
            "table_id": table.pk,
            "table_number": table.number,
            "session_id": session.pk,
        },
    )

    orders = (
        session.orders.exclude(status=OrderStatus.CANCELLED)
        .prefetch_related("items")
        .order_by("-created_at")
    )
    tab_total = session.total
    context = {
        "table": table,
        "session": session,
        "orders": orders,
        "tab_total": tab_total,
        "bill_requested": True,
    }
    return render(request, "tables/partials/running_tab.html", context)


@require_GET
def table_status(request, qr_token: str):
    """Live tab status view for a dining table."""
    table = get_object_or_404(Table, qr_token=qr_token, is_active=True)
    session = resolve_active_session(request, table)

    if session is None or session.closed_at is not None:
        return render(request, "tables/thank_you.html", {"table": table})

    orders = (
        session.orders.exclude(status=OrderStatus.CANCELLED)
        .prefetch_related("items")
        .order_by("-created_at")
    )
    tab_total = session.total

    context = {
        "table": table,
        "session": session,
        "orders": orders,
        "tab_total": tab_total,
        "bill_requested": (
            session.bill_requested
            or request.session.get(f"bill_req_{session.pk}", False)
        ),
    }
    return render(request, "tables/status.html", context)


@require_POST
def start_tab_view(request, qr_token: str):
    """Handle starting a new dining tab for a guest."""
    table = get_object_or_404(Table, qr_token=qr_token, is_active=True)
    guest_name = request.POST.get("guest_name", "").strip()
    session = start_tab(table, guest_name=guest_name)
    response = redirect("tables:menu", qr_token=qr_token)
    set_session_cookie(response, table, session)
    return response


@require_GET
def receipt_view(request, qr_token: str):
    """Render the itemized receipt for a guest's session (open or closed)."""
    table = get_object_or_404(Table, qr_token=qr_token, is_active=True)
    session = resolve_session(request, table)
    if session is None:
        return HttpResponse("No valid session found for receipt.", status=404)

    orders = (
        session.orders.exclude(status=OrderStatus.CANCELLED)
        .prefetch_related("items")
        .order_by("created_at")
    )
    context = {
        "table": table,
        "session": session,
        "orders": orders,
        "tab_total": session.total,
    }
    return render(request, "tables/receipt.html", context)


@role_required("ADMIN")
@require_POST
def clear_bill(request, session_id: int):
    """Admin endpoint to clear cash for a table tab and close the session."""
    session = get_object_or_404(TableSession, pk=session_id)

    try:
        with transaction.atomic():
            for order in session.orders.exclude(status=OrderStatus.CANCELLED):
                if order.status != OrderStatus.PAID:
                    transition(order, OrderStatus.PAID, request.user)

            close_session(session)
            if session.bill_requested:
                session.bill_requested = False
                session.save(update_fields=["bill_requested", "updated_at"])
    except (PermissionDenied, ValidationError) as exc:
        msg = f"Cannot clear bill: {exc}"
        messages.error(request, msg)
        if request.headers.get("HX-Request"):
            from apps.orders.views_admin import _action_buttons, _available_agents
            available_agents = _available_agents()
            active_orders = [o for o in session.orders.all() if o.status != OrderStatus.CANCELLED]
            order_cards = [
                {
                    "order": o,
                    "targets": _action_buttons(o),
                    "available_agents": available_agents,
                }
                for o in active_orders
            ]
            return render(
                request,
                "orders/admin/partials/tab_card.html",
                {
                    "session": session,
                    "table": session.table,
                    "orders": order_cards,
                    "total": session.total,
                    "bill_requested": session.bill_requested,
                    "error": msg,
                },
                status=400,
            )
        return redirect("orders_admin:dashboard")

    broadcast(
        f"table.{session.table.qr_token}",
        "table.paid",
        {"table_id": session.table.pk, "session_id": session.pk},
    )

    if request.headers.get("HX-Request"):
        return render(
            request,
            "orders/admin/partials/tab_card.html",
            {
                "session": session,
                "table": session.table,
                "orders": [],
                "total": session.total,
                "bill_requested": False,
                "cleared": True,
            },
        )
    return redirect("orders_admin:dashboard")
