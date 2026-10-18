"""Views for customer delivery ordering and checkout.

Thin views orchestrating services.create_order() and build_maps_url().
Never computes pricing or mutates status directly.
"""
import re
from decimal import Decimal

from django.contrib import messages
from django.core import signing
from django.core.exceptions import ValidationError
from django.db.models import F, Prefetch, Q
from django.http import Http404, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from apps.core.ratelimits import checkout, messaging
from apps.customer_auth.decorators import customer_login_required
from apps.customer_auth.models import CustomerAddress, WishlistItem
from apps.menu.models import Category as MenuCategory
from apps.menu.models import MenuItem
from apps.menu.services import get_cached_menu
from apps.orders import services
from apps.orders.models import Order, OrderStatus
from apps.orders.services import build_maps_url, create_order

# Salt for the per-order signed tracking cookie set at checkout. Must match
# the value used when the cookie is written in delivery_checkout().
_TRACKING_SALT = "delv_tracking"


def _get_cart_coupon_summary(session_dict: dict, subtotal: Decimal) -> tuple[dict | None, Decimal, Decimal]:
    """Validate and compute coupon discount for delivery cart."""
    code = session_dict.get("delv_coupon_code", "")
    if not code:
        return None, Decimal("0.00"), subtotal

    from apps.coupons.models import Coupon
    coupon = Coupon.objects.filter(code__iexact=str(code).strip(), is_active=True).first()
    if not coupon:
        session_dict.pop("delv_coupon_code", None)
        return None, Decimal("0.00"), subtotal

    valid, msg = coupon.is_valid_for(subtotal)
    if not valid:
        return {"code": coupon.code, "error": msg, "valid": False}, Decimal("0.00"), subtotal

    discount = coupon.calculate_discount(subtotal)
    payable = max(Decimal("0.00"), subtotal - discount)
    return {
        "code": coupon.code,
        "discount": discount,
        "display": coupon.discount_display,
        "valid": True,
    }, discount, payable


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
    sort = request.GET.get("sort", "relevance")
    stock_filter = request.GET.get("stock", "")

    order_fields = ["name"]
    if sort == "price_asc":
        order_fields = ["price", "name"]
    elif sort == "price_desc":
        order_fields = ["-price", "name"]

    item_qs = MenuItem.objects.all().order_by(*order_fields)
    if stock_filter == "in_stock":
        item_qs = item_qs.filter(is_available=True).exclude(track_stock=True, stock_quantity__lte=0)

    if search:
        item_qs = item_qs.filter(Q(name__icontains=search) | Q(description__icontains=search) | Q(sku__icontains=search))
    if category and category != "all":
        item_qs = item_qs.filter(category__name=category)

    if search or (category and category != "all") or sort != "relevance" or stock_filter:
        categories = MenuCategory.objects.filter(is_active=True).prefetch_related(
            Prefetch("items", queryset=item_qs)
        ).order_by("sort_order", "name")
    else:
        categories = all_categories

    has_results = any(len(cat.items.all()) > 0 for cat in categories)
    total_products_count = sum(len(cat.items.all()) for cat in categories)
    cart_items, cart_total, cart_count = _get_delivery_cart(request.session)
    cart_map = {str(entry["item"].pk): entry["quantity"] for entry in cart_items}

    context = {
        "categories": categories,
        "all_categories": all_categories,
        "has_results": has_results,
        "total_products_count": total_products_count,
        "search": search,
        "category": category,
        "sort": sort,
        "stock_filter": stock_filter,
        "cart_items": cart_items,
        "cart_total": cart_total,
        "cart_count": cart_count,
        "cart_map": cart_map,
        "delivery_customer": customer,
        "active_nav": "categories",
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
    elif request.POST.get("next"):
        return redirect(request.POST.get("next"))
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
    """Render checkout form or process delivery order placement."""
    from apps.customer_auth.views import get_logged_in_customer

    cart_items, cart_total, cart_count = _get_delivery_cart(request.session)

    if not cart_items:
        return redirect("orders_customer:menu")

    delivery_customer = get_logged_in_customer(request)
    coupon_data, coupon_discount, payable_total = _get_cart_coupon_summary(request.session, cart_total)

    saved_addresses = []
    if delivery_customer:
        saved_addresses = list(CustomerAddress.objects.filter(customer=delivery_customer))

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
            "coupon_data": coupon_data,
            "coupon_discount": coupon_discount,
            "payable_total": payable_total,
            "saved_addresses": saved_addresses,
            "form_data": form_data,
            "delivery_customer": delivery_customer,
        }
        return render(request, "orders/customer/checkout.html", context)

    # POST checkout
    address_id = request.POST.get("address_id", "").strip()
    contact_name = request.POST.get("contact_name", "").strip()
    contact_phone = request.POST.get("contact_phone", "").strip()
    address = request.POST.get("address", "").strip()
    instructions = request.POST.get("instructions", "").strip()
    delivery_slot = request.POST.get("delivery_slot", "Standard Delivery (30-45 mins)").strip()
    payment_method = request.POST.get("payment_method", "Cash on Delivery").strip()
    save_address = request.POST.get("save_address")
    address_title = request.POST.get("address_title", "Home").strip()
    lat = request.POST.get("lat", "").strip()
    lng = request.POST.get("lng", "").strip()

    # Pre-fill from selected saved address if provided
    if address_id and delivery_customer:
        chosen_addr = CustomerAddress.objects.filter(pk=address_id, customer=delivery_customer).first()
        if chosen_addr:
            address = chosen_addr.address
            if not contact_name and chosen_addr.recipient_name:
                contact_name = chosen_addr.recipient_name
            if not contact_phone and chosen_addr.phone:
                contact_phone = chosen_addr.phone

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
        errors.append("A delivery location is required (select a saved address or enter an address).")

    form_data = request.POST.copy()
    form_data["lat"] = lat
    form_data["lng"] = lng

    if errors:
        context = {
            "cart_items": cart_items,
            "cart_total": cart_total,
            "cart_count": cart_count,
            "coupon_data": coupon_data,
            "coupon_discount": coupon_discount,
            "payable_total": payable_total,
            "saved_addresses": saved_addresses,
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

    # Format combined instructions with slot, payment method and coupon info
    notes_parts = []
    if delivery_slot:
        notes_parts.append(f"Slot: {delivery_slot}")
    if payment_method:
        notes_parts.append(f"Payment: {payment_method}")
    if coupon_data and coupon_data.get("valid"):
        notes_parts.append(f"Coupon: {coupon_data['code']} (-₹{coupon_discount:.2f})")
    if instructions:
        notes_parts.append(instructions)
    combined_instructions = " | ".join(notes_parts)

    try:
        order = create_order(
            order_type="DELV",
            items=items,
            customer=customer,
            delivery_customer=delivery_customer,
            contact_name=contact_name,
            contact_phone=contact_phone,
            maps_url=maps_url,
            instructions=combined_instructions,
        )

        # Apply coupon discount to authoritative order total
        if coupon_data and coupon_data.get("valid"):
            from apps.coupons.models import Coupon
            Coupon.objects.filter(code=coupon_data["code"]).update(times_used=F("times_used") + 1)
            order.total_amount = payable_total
            order.save(update_fields=["total_amount"])

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

            if address and save_address:
                CustomerAddress.objects.create(
                    customer=delivery_customer,
                    title=address_title or "Home",
                    recipient_name=contact_name,
                    phone=contact_phone,
                    address=address,
                    city=request.session.get("customer_location", "Hyderabad"),
                    is_default=(len(saved_addresses) == 0),
                )

    except ValidationError as exc:
        context = {
            "cart_items": cart_items,
            "cart_total": cart_total,
            "cart_count": cart_count,
            "coupon_data": coupon_data,
            "coupon_discount": coupon_discount,
            "payable_total": payable_total,
            "saved_addresses": saved_addresses,
            "errors": exc.messages if hasattr(exc, "messages") else [str(exc)],
            "form_data": form_data,
            "delivery_customer": delivery_customer,
        }
        return render(request, "orders/customer/checkout.html", context, status=400)

    # Clear delivery cart and coupon
    request.session["delv_cart"] = {}
    request.session.pop("delv_coupon_code", None)
    delv_orders = request.session.get("delv_orders", [])
    if order.pk not in delv_orders:
        delv_orders.append(order.pk)
    request.session["delv_orders"] = delv_orders
    request.session.modified = True

    response = render(request, "orders/customer/thank_you.html", {"order": order, "sound_order_id": order.pk})
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
    coupon_data, coupon_discount, payable_total = _get_cart_coupon_summary(request.session, cart_total)

    # Delivering to location or address
    current_location = request.session.get("customer_location", "Hyderabad")
    delivering_to = customer.default_address if (customer and customer.default_address) else current_location

    context = {
        "cart_items": cart_items,
        "cart_total": cart_total,
        "cart_count": cart_count,
        "coupon_data": coupon_data,
        "coupon_discount": coupon_discount,
        "payable_total": payable_total,
        "delivering_to": delivering_to,
        "delivery_customer": customer,
    }
    return render(request, "orders/customer/cart.html", context)


@require_POST
def cart_apply_coupon(request):
    """Apply coupon code to delivery cart session."""
    code = request.POST.get("code", "").strip().upper()
    cart_items, cart_total, cart_count = _get_delivery_cart(request.session)

    if not code:
        messages.error(request, "Please enter a coupon code.")
        return redirect("orders_customer:cart")

    from apps.coupons.models import Coupon
    coupon = Coupon.objects.filter(code__iexact=code, is_active=True).first()
    if not coupon:
        messages.error(request, f"Coupon '{code}' is invalid or does not exist.")
        request.session.pop("delv_coupon_code", None)
        request.session.modified = True
    else:
        valid, msg = coupon.is_valid_for(cart_total)
        if not valid:
            messages.error(request, msg)
            request.session.pop("delv_coupon_code", None)
            request.session.modified = True
        else:
            request.session["delv_coupon_code"] = coupon.code
            request.session.modified = True
            messages.success(request, f"Coupon '{coupon.code}' applied: {coupon.discount_display}!")

    referer = request.META.get("HTTP_REFERER", "")
    if "checkout" in referer:
        return redirect("orders_customer:checkout")
    return redirect("orders_customer:cart")


@require_POST
def cart_remove_coupon(request):
    """Remove active coupon from delivery cart."""
    request.session.pop("delv_coupon_code", None)
    request.session.modified = True
    messages.info(request, "Coupon removed.")
    referer = request.META.get("HTTP_REFERER", "")
    if "checkout" in referer:
        return redirect("orders_customer:checkout")
    return redirect("orders_customer:cart")


@require_GET
def product_detail(request, pk):
    """Individual product detail page."""
    item = get_object_or_404(MenuItem.objects.select_related("category"), pk=pk)
    related_items = MenuItem.objects.filter(
        category=item.category, is_available=True
    ).exclude(pk=item.pk)[:4]

    cart = request.session.get("delv_cart", {})
    cart_qty = cart.get(str(item.pk), 0)

    from apps.customer_auth.views import get_logged_in_customer
    customer = getattr(request, "delivery_customer", None) or get_logged_in_customer(request)

    is_wishlisted = False
    if customer:
        is_wishlisted = WishlistItem.objects.filter(customer=customer, item=item).exists()
    elif request.user.is_authenticated:
        is_wishlisted = WishlistItem.objects.filter(user=request.user, item=item).exists()

    cart_items, cart_total, cart_count = _get_delivery_cart(request.session)

    context = {
        "item": item,
        "related_items": related_items,
        "cart_qty": cart_qty,
        "is_wishlisted": is_wishlisted,
        "cart_count": cart_count,
        "cart_total": cart_total,
        "delivery_customer": customer,
    }
    return render(request, "orders/customer/product_detail.html", context)


@require_GET
def wishlist_view(request):
    """Customer saved wishlist page."""
    from apps.customer_auth.views import get_logged_in_customer
    customer = getattr(request, "delivery_customer", None) or get_logged_in_customer(request)
    
    wishlist_items = []
    if customer:
        wishlist_items = list(WishlistItem.objects.filter(customer=customer).select_related("item", "item__category"))
    elif request.user.is_authenticated:
        wishlist_items = list(WishlistItem.objects.filter(user=request.user).select_related("item", "item__category"))

    cart_items, cart_total, cart_count = _get_delivery_cart(request.session)

    context = {
        "wishlist_items": wishlist_items,
        "cart_count": cart_count,
        "cart_total": cart_total,
        "delivery_customer": customer,
    }
    return render(request, "orders/customer/wishlist.html", context)


@require_http_methods(["GET", "POST"])
def wishlist_toggle(request, pk):
    """Add or remove an item from the customer's wishlist."""
    item = get_object_or_404(MenuItem, pk=pk)
    from apps.customer_auth.views import get_logged_in_customer
    customer = getattr(request, "delivery_customer", None) or get_logged_in_customer(request)

    if not customer and not request.user.is_authenticated:
        # Prompt login
        if request.headers.get("HX-Request"):
            return JsonResponse({"status": "error", "message": "Login required"}, status=401)
        return redirect("customer_auth:login")

    filter_kwargs = {"item": item}
    if customer:
        filter_kwargs["customer"] = customer
    else:
        filter_kwargs["user"] = request.user

    existing = WishlistItem.objects.filter(**filter_kwargs).first()
    if existing:
        existing.delete()
        is_wishlisted = False
        messages.info(request, f"Removed {item.name} from wishlist.")
    else:
        WishlistItem.objects.create(**filter_kwargs)
        is_wishlisted = True
        messages.success(request, f"Added {item.name} to wishlist!")

    if request.headers.get("HX-Request"):
        return JsonResponse({"status": "ok", "is_wishlisted": is_wishlisted})

    referer = request.META.get("HTTP_REFERER", "")
    if referer:
        return redirect(referer)
    return redirect("orders_customer:wishlist")


@require_GET
def customer_addresses(request):
    """Customer saved addresses management page."""
    from apps.customer_auth.views import get_logged_in_customer
    customer = getattr(request, "delivery_customer", None) or get_logged_in_customer(request)
    if not customer:
        return redirect("customer_auth:login")

    addresses = list(CustomerAddress.objects.filter(customer=customer))
    cart_items, cart_total, cart_count = _get_delivery_cart(request.session)

    context = {
        "addresses": addresses,
        "cart_count": cart_count,
        "delivery_customer": customer,
    }
    return render(request, "orders/customer/addresses.html", context)


@require_POST
def address_add(request):
    """Add a new delivery address for the customer."""
    from apps.customer_auth.views import get_logged_in_customer
    customer = getattr(request, "delivery_customer", None) or get_logged_in_customer(request)
    if not customer:
        return redirect("customer_auth:login")

    title = request.POST.get("title", "Home").strip()
    recipient_name = request.POST.get("recipient_name", customer.name or "").strip()
    phone = request.POST.get("phone", customer.phone or "").strip()
    address = request.POST.get("address", "").strip()
    city = request.POST.get("city", "Hyderabad").strip()
    is_default = bool(request.POST.get("is_default"))

    if not address:
        messages.error(request, "Address cannot be empty.")
        return redirect("orders_customer:addresses")

    if is_default:
        CustomerAddress.objects.filter(customer=customer).update(is_default=False)

    CustomerAddress.objects.create(
        customer=customer,
        title=title or "Home",
        recipient_name=recipient_name,
        phone=phone,
        address=address,
        city=city,
        is_default=is_default or (CustomerAddress.objects.filter(customer=customer).count() == 0),
    )
    messages.success(request, "Address saved successfully.")
    
    referer = request.META.get("HTTP_REFERER", "")
    if "checkout" in referer:
        return redirect("orders_customer:checkout")
    return redirect("orders_customer:addresses")


@require_POST
def address_delete(request, pk):
    """Delete a customer saved delivery address."""
    from apps.customer_auth.views import get_logged_in_customer
    customer = getattr(request, "delivery_customer", None) or get_logged_in_customer(request)
    if not customer:
        return redirect("customer_auth:login")

    addr = get_object_or_404(CustomerAddress, pk=pk, customer=customer)
    addr.delete()
    messages.info(request, "Address removed.")
    return redirect("orders_customer:addresses")


@require_POST
def address_set_default(request, pk):
    """Set an address as customer default."""
    from apps.customer_auth.views import get_logged_in_customer
    customer = getattr(request, "delivery_customer", None) or get_logged_in_customer(request)
    if not customer:
        return redirect("customer_auth:login")

    addr = get_object_or_404(CustomerAddress, pk=pk, customer=customer)
    CustomerAddress.objects.filter(customer=customer).update(is_default=False)
    addr.is_default = True
    addr.save(update_fields=["is_default"])
    if customer:
        customer.default_address = addr.address
        customer.save(update_fields=["default_address"])
    messages.success(request, f"Set '{addr.title}' as default address.")
    return redirect("orders_customer:addresses")


@require_POST
def set_location(request):
    """Set customer active delivery location in session."""
    location = request.POST.get("location", "Hyderabad").strip()
    allowed_locations = ["Hyderabad", "Banjara Hills", "Jubilee Hills", "Hitec City", "Gachibowli", "Madhapur", "Kondapur", "Secunderabad"]
    if location in allowed_locations or len(location) <= 60:
        request.session["customer_location"] = location
        request.session.modified = True
    
    referer = request.META.get("HTTP_REFERER", "")
    if referer:
        return redirect(referer)
    return redirect("orders_customer:menu")



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


