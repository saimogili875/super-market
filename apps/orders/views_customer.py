"""Views for customer delivery ordering and checkout.

Thin views orchestrating services.create_order() and build_maps_url().
Never computes pricing or mutates status directly.
"""
import re
from decimal import Decimal

from django.core import signing
from django.core.exceptions import ValidationError
from django.db.models import Prefetch, Q
from django.http import Http404, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from apps.core.ratelimits import checkout, messaging
from apps.customer_auth.decorators import customer_login_required
from apps.menu.models import Category as MenuCategory
from apps.menu.models import MenuItem
from apps.menu.services import get_cached_menu
from apps.orders import services
from apps.orders.models import Order, OrderStatus
from apps.orders.services import build_maps_url, create_order

# Salt for the per-order signed tracking cookie set at checkout. Must match
# the value used when the cookie is written in delivery_checkout().
_TRACKING_SALT = "delv_tracking"


def _get_delivery_cart(session_dict: dict) -> tuple[list[dict], Decimal, int]:
    """Parse session delivery cart into item dicts and computed total."""
    cart_raw = session_dict.get("delv_cart", {})
    if not cart_raw:
        return [], Decimal("0"), 0

    item_ids = [int(mid) for mid in cart_raw.keys()]
    menu_items = {
        mi.pk: mi
        for mi in MenuItem.objects.filter(pk__in=item_ids, is_available=True)
    }

    cart_items = []
    total = Decimal("0")
    count = 0
    for mid_str, qty in cart_raw.items():
        mid = int(mid_str)
        if mid in menu_items and qty > 0:
            mi = menu_items[mid]
            line_tot = mi.effective_price * qty
            cart_items.append(
                {
                    "item": mi,
                    "quantity": qty,
                    "line_total": line_tot,
                }
            )
            total += line_tot
            count += qty
    return cart_items, total, count


@require_GET
def delivery_menu(request):
    """Render the public delivery menu with server-side cart."""
    from apps.customer_auth.views import get_logged_in_customer

    customer = getattr(request, "delivery_customer", None) or get_logged_in_customer(request)
    if customer:
        request.delivery_customer = customer

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
    cart_items, cart_total, cart_count = _get_delivery_cart(request.session)

    context = {
        "categories": categories,
        "all_categories": all_categories,
        "has_results": has_results,
        "search": search,
        "category": category,
        "cart_items": cart_items,
        "cart_total": cart_total,
        "cart_count": cart_count,
        "delivery_customer": customer,
    }
    if request.headers.get("HX-Request"):
        return render(request, "orders/customer/partials/menu_results.html", context)
    return render(request, "orders/customer/menu.html", context)


@require_POST
def cart_add(request):
    """HTMX endpoint to add a menu item to the delivery session cart."""
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
            cart = request.session.get("delv_cart", {})
            current_qty = cart.get(str(menu_item_id), 0)
            if mi.track_stock and mi.stock_quantity < (current_qty + quantity):
                if mi.stock_quantity:
                    error = f"Only {mi.stock_quantity} left of '{mi.name}'."
                else:
                    error = f"'{mi.name}' is sold out."
            else:
                cart[str(menu_item_id)] = current_qty + quantity
                request.session["delv_cart"] = cart
                request.session.modified = True

    cart_items, cart_total, cart_count = _get_delivery_cart(request.session)
    context = {
        "cart_items": cart_items,
        "cart_total": cart_total,
        "cart_count": cart_count,
        "error": error,
    }
    response = render(request, "orders/customer/partials/cart_bar.html", context)
    if request.headers.get("HX-Request"):
        response["HX-Trigger"] = "cartUpdated"
    return response


@require_POST
def cart_update(request):
    """HTMX / Form endpoint to update or remove a menu item quantity in the delivery session cart."""
    menu_item_id = request.POST.get("menu_item_id")
    action = request.POST.get("action")
    
    try:
        raw_qty = request.POST.get("quantity")
        quantity = int(raw_qty) if raw_qty is not None and raw_qty != "" else None
    except (ValueError, TypeError):
        quantity = None

    error = None
    if menu_item_id:
        try:
            mid_int = int(menu_item_id)
        except (ValueError, TypeError):
            mid_int = None
            
        if mid_int is not None:
            cart = request.session.get("delv_cart", {})
            item_key = str(mid_int)
            current_qty = cart.get(item_key, 0)

            if action == "remove":
                new_qty = 0
            elif action == "decrement":
                new_qty = current_qty - (quantity if quantity is not None else 1)
            elif action == "increment":
                new_qty = current_qty + (quantity if quantity is not None else 1)
            elif quantity is not None:
                new_qty = quantity
            else:
                new_qty = current_qty

            if new_qty <= 0:
                if item_key in cart:
                    del cart[item_key]
                    request.session["delv_cart"] = cart
                    request.session.modified = True
            else:
                mi = MenuItem.objects.filter(pk=mid_int).first()
                if not mi or not mi.is_available:
                    error = f"'{mi.name if mi else menu_item_id}' is currently unavailable."
                elif not mi.is_orderable:
                    error = f"'{mi.name}' is sold out."
                elif mi.track_stock and mi.stock_quantity < new_qty:
                    if mi.stock_quantity:
                        error = f"Only {mi.stock_quantity} left of '{mi.name}'."
                    else:
                        error = f"'{mi.name}' is sold out."
                else:
                    cart[item_key] = new_qty
                    request.session["delv_cart"] = cart
                    request.session.modified = True

    cart_items, cart_total, cart_count = _get_delivery_cart(request.session)
    
    is_htmx = bool(request.headers.get("HX-Request"))
    target = request.headers.get("HX-Target")

    context = {
        "cart_items": cart_items,
        "cart_total": cart_total,
        "cart_count": cart_count,
        "error": error,
    }

    if is_htmx:
        if cart_count == 0 and target == "order-summary-container":
            response = redirect("orders_customer:menu")
            response["HX-Redirect"] = response.url
            return response
            
        if target == "order-summary-container":
            response = render(request, "orders/customer/partials/checkout_summary.html", context)
            response["HX-Trigger"] = "cartUpdated"
            return response

        response = render(request, "orders/customer/partials/cart_bar.html", context)
        response["HX-Trigger"] = "cartUpdated"
        return response

    referer = request.META.get("HTTP_REFERER", "")
    if "checkout" in referer:
        if cart_count == 0:
            return redirect("orders_customer:menu")
        return redirect("orders_customer:checkout")

    response = render(request, "orders/customer/partials/cart_bar.html", context)
    return response


@checkout
@require_http_methods(["GET", "POST"])
@customer_login_required
def delivery_checkout(request):
    """Render checkout form or process delivery order placement (COD)."""
    from apps.customer_auth.views import get_logged_in_customer

    cart_items, cart_total, cart_count = _get_delivery_cart(request.session)

    if not cart_items:
        return redirect("orders_customer:menu")

    delivery_customer = get_logged_in_customer(request)

    if request.method == "GET":
        form_data = {}
        if delivery_customer:
            form_data = {
                "contact_name": delivery_customer.name,
                "contact_phone": delivery_customer.phone,
                "address": delivery_customer.default_address,
            }
        context = {
            "cart_items": cart_items,
            "cart_total": cart_total,
            "cart_count": cart_count,
            "form_data": form_data,
            "delivery_customer": delivery_customer,
        }
        return render(request, "orders/customer/checkout.html", context)

    # POST checkout
    contact_name = request.POST.get("contact_name", "").strip()
    contact_phone = request.POST.get("contact_phone", "").strip()
    address = request.POST.get("address", "").strip()
    instructions = request.POST.get("instructions", "").strip()
    lat = request.POST.get("lat", "").strip()
    lng = request.POST.get("lng", "").strip()

    valid_lat = None
    valid_lng = None
    if lat and lng:
        try:
            f_lat = float(lat)
            f_lng = float(lng)
            if -90.0 <= f_lat <= 90.0 and -180.0 <= f_lng <= 180.0:
                valid_lat = lat
                valid_lng = lng
            else:
                lat = ""
                lng = ""
        except (ValueError, TypeError):
            lat = ""
            lng = ""
    else:
        lat = ""
        lng = ""

    errors = []
    if not contact_name:
        errors.append("Contact name is required.")
    if not contact_phone:
        errors.append("Contact phone number is required.")
    if not (valid_lat and valid_lng) and not address:
        errors.append("A delivery location is required (share your location or enter an address).")

    form_data = request.POST.copy()
    form_data["lat"] = lat
    form_data["lng"] = lng

    if errors:
        context = {
            "cart_items": cart_items,
            "cart_total": cart_total,
            "cart_count": cart_count,
            "errors": errors,
            "form_data": form_data,
            "delivery_customer": delivery_customer,
        }
        return render(request, "orders/customer/checkout.html", context, status=400)

    if valid_lat and valid_lng:
        maps_url = build_maps_url(lat=valid_lat, lng=valid_lng)
    else:
        maps_url = build_maps_url(address=address)
    items = [
        {"menu_item_id": entry["item"].pk, "quantity": entry["quantity"]}
        for entry in cart_items
    ]

    customer = request.user if request.user.is_authenticated else None

    try:
        order = create_order(
            order_type="DELV",
            items=items,
            customer=customer,
            delivery_customer=delivery_customer,
            contact_name=contact_name,
            contact_phone=contact_phone,
            maps_url=maps_url,
            instructions=instructions,
        )

        # Save customer default address and name for future pre-filling
        if delivery_customer:
            updated = False
            if contact_name and not delivery_customer.name:
                delivery_customer.name = contact_name
                updated = True
            if address and delivery_customer.default_address != address:
                delivery_customer.default_address = address
                updated = True
            if updated:
                delivery_customer.save()

    except ValidationError as exc:
        context = {
            "cart_items": cart_items,
            "cart_total": cart_total,
            "cart_count": cart_count,
            "errors": exc.messages if hasattr(exc, "messages") else [str(exc)],
            "form_data": form_data,
            "delivery_customer": delivery_customer,
        }
        return render(request, "orders/customer/checkout.html", context, status=400)

    # Clear delivery cart
    request.session["delv_cart"] = {}
    delv_orders = request.session.get("delv_orders", [])
    if order.pk not in delv_orders:
        delv_orders.append(order.pk)
    request.session["delv_orders"] = delv_orders
    request.session.modified = True

    response = render(request, "orders/customer/thank_you.html", {"order": order})
    response.set_signed_cookie(
        f"delv_token_{order.pk}", str(order.pk), salt=_TRACKING_SALT
    )
    return response


# ---------------------------------------------------------------------------
# Tracking + quick messaging (Task 6.5)
# ---------------------------------------------------------------------------

def _may_access_order(request, order: Order) -> bool:
    """Authorise viewing/messaging an order.

    A guest proves ownership with the signed ``delv_token_<pk>`` cookie set
    at checkout or via their session ``delv_orders``. Logged-in delivery
    customers qualify if their contact phone matches the order's phone.
    Logged-in staff and order owner also qualify.
    """
    try:
        token = request.get_signed_cookie(
            f"delv_token_{order.pk}", salt=_TRACKING_SALT
        )
        if token == str(order.pk):
            return True
    except (KeyError, signing.BadSignature):
        pass

    delv_orders = request.session.get("delv_orders", [])
    if order.pk in delv_orders:
        return True

    delivery_customer = getattr(request, "delivery_customer", None)
    if not delivery_customer:
        from apps.customer_auth.views import get_logged_in_customer
        delivery_customer = get_logged_in_customer(request)

    if delivery_customer:
        if order.delivery_customer_id and order.delivery_customer_id == delivery_customer.pk:
            return True
        if delivery_customer.phone:
            cust_phone = re.sub(r"[\s\-\(\)]", "", delivery_customer.phone.strip())
            ord_phone = re.sub(r"[\s\-\(\)]", "", (order.contact_phone or "").strip())
            if cust_phone and ord_phone:
                if cust_phone == ord_phone:
                    return True
                if len(cust_phone) >= 10 and len(ord_phone) >= 10 and cust_phone[-10:] == ord_phone[-10:]:
                    return True

    user = request.user
    if user and user.is_authenticated:
        if getattr(user, "role", None) == "ADMIN" or order.agent_id == user.pk or order.customer_id == user.pk:
            return True

    return False


CUSTOMER_STATUS_LABELS = {
    OrderStatus.PLACED: "Order Placed",
    OrderStatus.APPROVED: "Order Confirmed",
    OrderStatus.IN_KITCHEN: "Preparing Your Food",
    OrderStatus.READY: "Ready for Pickup",
    OrderStatus.DISPATCHED: "Out for Delivery",
    OrderStatus.ARRIVED: "Agent Has Arrived",
    OrderStatus.COLLECTED: "Delivered",
    OrderStatus.PAID: "Paid",
    OrderStatus.CANCELLED: "Order Cancelled",
}

TRACKING_STEPS = [
    (OrderStatus.PLACED, "Order Placed"),
    (OrderStatus.APPROVED, "Order Confirmed"),
    (OrderStatus.IN_KITCHEN, "Preparing Your Food"),
    (OrderStatus.READY, "Ready for Pickup"),
    (OrderStatus.DISPATCHED, "Out for Delivery"),
    (OrderStatus.ARRIVED, "Agent Has Arrived"),
    (OrderStatus.COLLECTED, "Delivered"),
]


@require_GET
@customer_login_required
def track_order(request, pk):
    """Customer live tracking page for a single delivery order."""
    order = get_object_or_404(
        Order.objects.select_related("customer", "table", "agent", "session"),
        pk=pk,
    )
    if not _may_access_order(request, order):
        raise Http404("No such order.")

    step_codes = [s[0] for s in TRACKING_STEPS]
    if order.status == OrderStatus.PAID:
        current_step_index = len(step_codes)
    elif order.status in step_codes:
        current_step_index = step_codes.index(order.status)
    else:
        current_step_index = 0

    context = {
        "order": order,
        "messages": order.messages.select_related("sender").all(),
        # Code -> human label map for the Alpine status ticker (safe JSON).
        "status_labels": CUSTOMER_STATUS_LABELS,
        "tracking_steps": TRACKING_STEPS,
        "current_step_index": current_step_index,
        "delivery_customer": getattr(request, "delivery_customer", None),
    }
    return render(request, "orders/customer/track.html", context)



@messaging
@require_POST
@customer_login_required
def post_order_message(request, pk):
    """Post a short chat message on an order; return the rendered bubble."""
    order = get_object_or_404(
        Order.objects.select_related("customer", "table", "agent", "session"),
        pk=pk,
    )
    if not _may_access_order(request, order):
        raise Http404("No such order.")

    body = request.POST.get("body", "").strip()
    if not body:
        return HttpResponseBadRequest("Message cannot be empty.")

    sender = request.user if request.user.is_authenticated else None
    message = services.post_message(order, sender, body)
    return render(request, "orders/customer/partials/message.html", {"message": message})


@require_GET
def delivery_cart_view(request):
    """Customer dedicated cart page showing session cart items, totals, and checkout button."""
    from apps.customer_auth.views import get_logged_in_customer

    customer = getattr(request, "delivery_customer", None) or get_logged_in_customer(request)
    if customer:
        request.delivery_customer = customer

    cart_items, cart_total, cart_count = _get_delivery_cart(request.session)

    context = {
        "cart_items": cart_items,
        "cart_total": cart_total,
        "cart_count": cart_count,
        "delivery_customer": customer,
    }
    return render(request, "orders/customer/cart.html", context)


@require_GET
def order_history(request):
    """Customer order history page listing past orders and live active order banner if present."""
    from apps.customer_auth.views import get_logged_in_customer

    customer = getattr(request, "delivery_customer", None) or get_logged_in_customer(request)
    if customer:
        request.delivery_customer = customer

    status_filter = request.GET.get("status", "all").lower()

    # Query customer's orders by contact_phone or session order IDs
    delv_order_ids = request.session.get("delv_orders", [])
    phone = customer.phone.strip() if (customer and customer.phone) else ""
    cleaned_phone = re.sub(r"[\s\-\(\)]", "", phone) if phone else ""

    query = Q()
    if customer:
        query |= Q(delivery_customer=customer)
    if cleaned_phone:
        query |= Q(contact_phone__iendswith=cleaned_phone[-10:]) if len(cleaned_phone) >= 10 else Q(contact_phone=phone)
    if delv_order_ids:
        query |= Q(pk__in=delv_order_ids)

    orders_qs = Order.objects.none()
    active_order = None
    if query:
        base_qs = Order.objects.filter(query).prefetch_related("items").order_by("-created_at").distinct()
        non_terminal_exclude = [OrderStatus.PAID, OrderStatus.CANCELLED]
        completed_statuses = [OrderStatus.PAID, OrderStatus.COLLECTED, OrderStatus.CANCELLED]
        if status_filter == "completed":
            orders_qs = base_qs.filter(status__in=completed_statuses)
            active_order = None
        elif status_filter in ("not_completed", "active"):
            orders_qs = base_qs.exclude(status__in=completed_statuses)
            active_order = base_qs.exclude(status__in=non_terminal_exclude).first()
        else:
            orders_qs = base_qs
            active_order = base_qs.exclude(status__in=non_terminal_exclude).first()

    cart_items, cart_total, cart_count = _get_delivery_cart(request.session)

    context = {
        "active_order": active_order,
        "orders": list(orders_qs),
        "status_filter": status_filter,
        "delivery_customer": customer,
        "cart_count": cart_count,
        "completed_statuses": [OrderStatus.PAID.value, OrderStatus.COLLECTED.value, OrderStatus.CANCELLED.value],
    }
    return render(request, "orders/customer/order_history.html", context)


@require_GET
def track_current(request):
    """Redirect to the customer's most recent active (non-terminal) order or show merged orders view."""
    from apps.customer_auth.views import get_logged_in_customer

    customer = getattr(request, "delivery_customer", None) or get_logged_in_customer(request)
    if customer:
        request.delivery_customer = customer

    delv_order_ids = request.session.get("delv_orders", [])

    query = Q()
    if delv_order_ids:
        query |= Q(pk__in=delv_order_ids)
    if customer:
        query |= Q(delivery_customer=customer)
        if customer.phone:
            cleaned_phone = re.sub(r"[\s\-\(\)]", "", customer.phone.strip())
            if cleaned_phone:
                if len(cleaned_phone) >= 10:
                    query |= Q(contact_phone__iendswith=cleaned_phone[-10:])
                else:
                    query |= Q(contact_phone=customer.phone.strip())

    active_order = None
    if query:
        non_terminal_exclude = [OrderStatus.PAID, OrderStatus.CANCELLED]
        active_order = (
            Order.objects.filter(query)
            .exclude(status__in=non_terminal_exclude)
            .order_by("-created_at")
            .first()
        )

    if active_order:
        return redirect("orders_customer:track", pk=active_order.pk)

    return order_history(request)


@require_GET
def customer_settings(request):
    """Customer settings page displaying account info and auth actions."""
    customer = getattr(request, "delivery_customer", None)
    if not customer:
        from apps.customer_auth.views import get_logged_in_customer
        customer = get_logged_in_customer(request)

    if customer:
        request.delivery_customer = customer

    context = {
        "delivery_customer": customer,
    }
    return render(request, "orders/customer/settings.html", context)


