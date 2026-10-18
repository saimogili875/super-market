"""Store Manager & Staff Portal backend views.

Provides complete functionality for:
- Store Manager Dashboard & Operations
- Staff Operations Dashboard & Task Assignment
- Pick & Pack Order Preparation Workflows
- Inventory Stock Adjustments & Staff Discrepancy Requests
- Product Catalog & Category Management
- Shift Scheduling & Daily Attendance Check-in/out
- Operational Notifications & Analytics Reports
"""
from datetime import date, timedelta
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import F, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.timezone import now
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from apps.accounts.models import (
    Role,
    StaffAttendance,
    StaffProfile,
    StaffShift,
    StaffTask,
    StockAdjustmentRequest,
    User,
)
from apps.audit.models import log_audit_event
from apps.core.permissions import role_required
from apps.menu.models import Category, MenuItem, StockMovement
from apps.notifications.models import AdminNotification
from apps.orders.models import Order, OrderEvent, OrderItem, OrderStatus
from apps.orders.services import transition
from apps.suppliers.models import Supplier


# ===========================================================================
# 1. Authentication Views
# ===========================================================================

@require_http_methods(["GET", "POST"])
def manager_login(request):
    """Dedicated login view for Store Managers and Store Staff."""
    if request.user.is_authenticated:
        if request.user.role in {Role.ADMIN, Role.MANAGER} or request.user.is_superuser:
            return redirect("manager:dashboard")
        elif request.user.role in {Role.STAFF, Role.INVENTORY, Role.CASHIER}:
            return redirect("manager:staff_dashboard")

    next_url = request.GET.get("next") or request.POST.get("next") or ""

    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")

        user = authenticate(request, username=username, password=password)
        if user is None:
            # Check by employee ID fallback
            profile = StaffProfile.objects.filter(employee_id__iexact=username).select_related("user").first()
            if profile and profile.user.is_active:
                user = authenticate(request, username=profile.user.username, password=password)

        if user is not None:
            if not user.is_active:
                messages.error(request, "Your staff account has been deactivated. Please contact store management.")
                return render(request, "manager/login.html", {"next": next_url})

            allowed_roles = {Role.ADMIN, Role.MANAGER, Role.STAFF, Role.INVENTORY, Role.CASHIER}
            if user.role not in allowed_roles and not user.is_superuser:
                messages.error(request, "Access denied: This portal is exclusively for SuperMarket Managers and Staff.")
                return render(request, "manager/login.html", {"next": next_url})

            auth_login(request, user)
            messages.success(request, f"Welcome back, {user.first_name or user.username}!")

            if next_url and next_url.startswith("/"):
                return redirect(next_url)

            if user.role in {Role.ADMIN, Role.MANAGER} or user.is_superuser:
                return redirect("manager:dashboard")
            return redirect("manager:staff_dashboard")

        messages.error(request, "Invalid username or password. Please try again.")

    return render(request, "manager/login.html", {"next": next_url})


@require_GET
def manager_logout(request):
    """Log out manager/staff and redirect to portal sign in."""
    auth_logout(request)
    messages.success(request, "You have been logged out of the Store Manager portal.")
    return redirect("manager:login")


# ===========================================================================
# 2. Dashboards (Manager & Staff)
# ===========================================================================

@require_GET
@role_required("MANAGER", "ADMIN")
def manager_dashboard(request):
    """Primary operational dashboard for Store Managers."""
    today = now().date()

    # Real database queries for KPIs
    new_orders = Order.objects.filter(status=OrderStatus.PLACED).count()
    preparing = Order.objects.filter(status__in=[OrderStatus.APPROVED, OrderStatus.IN_KITCHEN]).count()
    ready = Order.objects.filter(status=OrderStatus.READY).count()
    
    tracked_items = MenuItem.objects.filter(track_stock=True)
    low_stock = tracked_items.filter(stock_quantity__gt=0, stock_quantity__lte=F("low_stock_threshold")).count()
    out_of_stock = tracked_items.filter(stock_quantity__lte=0).count()
    active_products = MenuItem.objects.filter(is_available=True).count()
    active_staff = StaffAttendance.objects.filter(date=today, status="PRESENT", check_out__isnull=True).count()

    kpis = {
        "new_orders": new_orders,
        "preparing": preparing,
        "ready": ready,
        "low_stock": low_stock,
        "out_of_stock": out_of_stock,
        "active_products": active_products,
        "active_staff": active_staff,
    }

    # Order Queue (recent active orders)
    recent_orders = (
        Order.objects.filter(status__in=[OrderStatus.PLACED, OrderStatus.APPROVED, OrderStatus.IN_KITCHEN, OrderStatus.READY])
        .select_related("agent")
        .prefetch_related("items")
        .order_by("-created_at")[:5]
    )

    # Low Stock Items
    low_stock_items = [
        p for p in MenuItem.objects.filter(track_stock=True).select_related("category").order_by("stock_quantity")[:10]
        if p.is_low_stock or p.is_out_of_stock
    ][:5]

    # Inventory Health Counts & Percentages
    in_stock_cnt = tracked_items.filter(stock_quantity__gt=F("low_stock_threshold")).count()
    total_tracked = max(1, in_stock_cnt + low_stock + out_of_stock)
    
    inventory_counts = {
        "in_stock": in_stock_cnt,
        "low_stock": low_stock,
        "out_of_stock": out_of_stock,
    }
    inventory_pct = {
        "in_stock": round(in_stock_cnt / total_tracked * 100),
        "low_stock": round(low_stock / total_tracked * 100),
        "out_of_stock": round(out_of_stock / total_tracked * 100),
    }

    # Recent Store Activity
    recent_activity = []
    for m in StockMovement.objects.select_related("item", "created_by").order_by("-created_at")[:4]:
        delta_str = f"+{m.quantity}" if m.quantity > 0 else f"{m.quantity}"
        recent_activity.append({
            "text": f"Stock {m.movement_type}: {m.item.name} ({delta_str})",
            "timestamp": m.created_at,
            "user": m.created_by.get_full_name() if m.created_by else "System",
        })

    # Staff on duty today
    staff_on_duty = (
        StaffAttendance.objects.filter(date=today, status="PRESENT", check_out__isnull=True)
        .select_related("staff", "shift")
        .order_by("-check_in")[:5]
    )

    # Pending store tasks
    pending_tasks = (
        StaffTask.objects.filter(status__in=["PENDING", "IN_PROGRESS"])
        .select_related("assigned_to")
        .order_by("due_date", "-created_at")[:5]
    )

    context = {
        "kpis": kpis,
        "recent_orders": recent_orders,
        "low_stock_items": low_stock_items,
        "inventory_counts": inventory_counts,
        "inventory_pct": inventory_pct,
        "recent_activity": recent_activity,
        "staff_on_duty": staff_on_duty,
        "pending_tasks": pending_tasks,
        "active_nav": "dashboard",
        "new_orders_badge": new_orders or None,
        "low_stock_badge": low_stock or None,
        "pending_requests_badge": StockAdjustmentRequest.objects.filter(status="PENDING").count() or None,
        "unread_notifs_count": AdminNotification.objects.filter(Q(recipient=request.user) | Q(recipient__isnull=True), is_read=False).count(),
    }
    return render(request, "manager/dashboard.html", context)


@require_GET
@role_required("STAFF", "INVENTORY", "CASHIER", "MANAGER", "ADMIN")
def staff_dashboard(request):
    """Personalized operational dashboard for store staff members."""
    user = request.user
    today = now().date()

    profile, _ = StaffProfile.objects.get_or_create(user=user)
    today_attendance = StaffAttendance.objects.filter(staff=user, date=today).first()

    my_tasks = StaffTask.objects.filter(assigned_to=user).order_by("status", "due_date")[:8]
    prep_orders = Order.objects.filter(status__in=[OrderStatus.APPROVED, OrderStatus.IN_KITCHEN]).order_by("created_at")[:6]
    my_requests = StockAdjustmentRequest.objects.filter(requested_by=user).order_by("-created_at")[:5]

    context = {
        "profile": profile,
        "today_attendance": today_attendance,
        "my_tasks": my_tasks,
        "prep_orders": prep_orders,
        "my_requests": my_requests,
        "active_nav": "staff_dashboard",
        "unread_notifs_count": AdminNotification.objects.filter(recipient=user, is_read=False).count(),
    }
    return render(request, "manager/staff_dashboard.html", context)


# ===========================================================================
# 3. Orders Pipeline & Pick/Pack Checklist
# ===========================================================================

@require_GET
@role_required("STAFF", "INVENTORY", "CASHIER", "MANAGER", "ADMIN")
def orders_list(request):
    """Orders pipeline view with status filter chips and search."""
    status_filter = request.GET.get("status", "").strip().upper()
    q = request.GET.get("q", "").strip()

    orders_qs = Order.objects.select_related("agent", "customer", "delivery_customer").prefetch_related("items").order_by("-created_at")

    if status_filter:
        orders_qs = orders_qs.filter(status=status_filter)

    if q:
        clean_q = q.replace("#", "")
        if clean_q.isdigit():
            orders_qs = orders_qs.filter(Q(pk=int(clean_q)) | Q(contact_name__icontains=q))
        else:
            orders_qs = orders_qs.filter(Q(contact_name__icontains=q) | Q(contact_phone__icontains=q))

    # Counts for status chips
    counts = {
        st: Order.objects.filter(status=st).count()
        for st in [
            OrderStatus.PLACED,
            OrderStatus.APPROVED,
            OrderStatus.IN_KITCHEN,
            OrderStatus.READY,
            OrderStatus.DISPATCHED,
            OrderStatus.PAID,
            OrderStatus.CANCELLED,
        ]
    }

    context = {
        "orders": orders_qs[:50],
        "current_status": status_filter,
        "q": q,
        "counts": counts,
        "active_nav": "orders",
        "new_orders_badge": counts.get(OrderStatus.PLACED) or None,
    }
    return render(request, "manager/orders.html", context)


@require_GET
@role_required("STAFF", "INVENTORY", "CASHIER", "MANAGER", "ADMIN")
def order_detail(request, pk):
    """Order detail view with interactive pick & pack checklist and transition controls."""
    order = get_object_or_404(
        Order.objects.select_related("agent", "customer", "delivery_customer").prefetch_related("items__menu_item", "events__actor"),
        pk=pk,
    )

    all_picked = order.items.count() > 0 and not order.items.filter(is_picked=False).exists()
    has_insufficient_stock = any(
        it.menu_item.track_stock and it.menu_item.stock_quantity < it.quantity
        for it in order.items.all()
    )

    # Next status action mappings
    next_action = None
    action_hint = ""

    if order.status == OrderStatus.PLACED:
        next_action = {"value": "accept", "label": "Accept Order", "disabled": False}
        action_hint = "Review items before accepting order."
    elif order.status == OrderStatus.APPROVED:
        next_action = {"value": "prepare", "label": "Start Preparing", "disabled": False}
        action_hint = "Begin gathering items from store shelves."
    elif order.status == OrderStatus.IN_KITCHEN:
        disabled = not all_picked or has_insufficient_stock
        next_action = {"value": "pack", "label": "Mark Order as Packed", "disabled": disabled}
        if not all_picked:
            action_hint = "Pick and verify all items below to enable packing."
        elif has_insufficient_stock:
            action_hint = "Warning: Some items have insufficient stock."
    elif order.status == OrderStatus.READY:
        next_action = {"value": "handover", "label": "Mark Handed Over to Delivery Agent", "disabled": False}
        action_hint = "Hand order package to assigned courier."

    can_cancel = order.status in [OrderStatus.PLACED, OrderStatus.APPROVED, OrderStatus.IN_KITCHEN]

    context = {
        "order": order,
        "all_picked": all_picked,
        "has_insufficient_stock": has_insufficient_stock,
        "next_action": next_action,
        "action_hint": action_hint,
        "can_cancel": can_cancel,
        "active_nav": "orders",
    }
    return render(request, "manager/order_detail.html", context)


@require_POST
@role_required("STAFF", "INVENTORY", "CASHIER", "MANAGER", "ADMIN")
def order_toggle_pick(request, order_pk, item_pk):
    """Toggle the is_picked checklist status for an order item."""
    order = get_object_or_404(Order, pk=order_pk)
    item = get_object_or_404(OrderItem, pk=item_pk, order=order)

    item.is_picked = not item.is_picked
    item.save(update_fields=["is_picked"])

    status_str = "picked" if item.is_picked else "unpicked"
    messages.success(request, f"Marked '{item.name_snap}' as {status_str}.")
    return redirect("manager:order_detail", pk=order_pk)


@require_POST
@role_required("STAFF", "INVENTORY", "CASHIER", "MANAGER", "ADMIN")
def order_action(request, pk):
    """Execute order transition actions from the manager/staff portal."""
    order = get_object_or_404(Order.objects.prefetch_related("items__menu_item"), pk=pk)
    action = request.POST.get("action")

    try:
        if action == "accept":
            transition(order, OrderStatus.APPROVED, request.user)
            messages.success(request, f"Order #{order.pk} accepted.")
        elif action == "prepare":
            transition(order, OrderStatus.IN_KITCHEN, request.user)
            messages.success(request, f"Order #{order.pk} preparation started.")
        elif action == "pack":
            # Verify all items picked
            if order.items.filter(is_picked=False).exists():
                raise ValidationError("All items must be checked off before packing.")
            transition(order, OrderStatus.READY, request.user)
            messages.success(request, f"Order #{order.pk} packed and ready for courier pickup.")
        elif action == "handover":
            transition(order, OrderStatus.DISPATCHED, request.user)
            messages.success(request, f"Order #{order.pk} handed over to delivery partner.")
        elif action == "cancel":
            reason = request.POST.get("reason", "Cancelled by store staff")
            notes = request.POST.get("notes", "").strip()
            full_notes = f"{reason} — {notes}" if notes else reason

            order.delivery_issue_reason = reason
            order.delivery_issue_notes = full_notes
            order.save(update_fields=["delivery_issue_reason", "delivery_issue_notes"])

            transition(order, OrderStatus.CANCELLED, request.user)
            messages.success(request, f"Order #{order.pk} has been cancelled.")
    except (ValidationError, PermissionDenied) as e:
        messages.error(request, str(e))

    return redirect("manager:order_detail", pk=pk)


# ===========================================================================
# 4. Inventory, Stock Adjustments & Staff Discrepancy Requests
# ===========================================================================

@require_GET
@role_required("STAFF", "INVENTORY", "CASHIER", "MANAGER", "ADMIN")
def inventory_list(request):
    """Inventory overview with search, category filtering, and sorting."""
    q = request.GET.get("q", "").strip()
    category_id = request.GET.get("category", "").strip()
    status_filter = request.GET.get("status", "").strip().lower()
    sort = request.GET.get("sort", "name").strip()

    items_qs = MenuItem.objects.select_related("category").all()

    if q:
        items_qs = items_qs.filter(Q(name__icontains=q) | Q(sku__icontains=q))

    if category_id:
        items_qs = items_qs.filter(category_id=category_id)

    if status_filter == "ok":
        items_qs = items_qs.filter(track_stock=True, stock_quantity__gt=F("low_stock_threshold"))
    elif status_filter == "low":
        items_qs = items_qs.filter(track_stock=True, stock_quantity__gt=0, stock_quantity__lte=F("low_stock_threshold"))
    elif status_filter == "out":
        items_qs = items_qs.filter(track_stock=True, stock_quantity__lte=0)

    if sort == "stock":
        items_qs = items_qs.order_by("stock_quantity")
    else:
        items_qs = items_qs.order_by("name")

    categories = Category.objects.filter(is_active=True).order_by("name")
    all_products = MenuItem.objects.all().order_by("name")

    context = {
        "products": items_qs[:100],
        "categories": categories,
        "all_products": all_products,
        "q": q,
        "selected_cat": category_id,
        "selected_status": status_filter,
        "sort": sort,
        "active_nav": "inventory",
    }
    return render(request, "manager/inventory.html", context)


@require_POST
@role_required("STAFF", "INVENTORY", "CASHIER", "MANAGER", "ADMIN")
def inventory_adjust(request):
    """Perform direct stock adjustment (Managers) or submit discrepancy request (Staff)."""
    user = request.user
    item_id = request.POST.get("item_id")
    movement_type = request.POST.get("movement_type", "Stock Received")
    qty_raw = request.POST.get("quantity", "0").strip()
    reason = request.POST.get("reason", "").strip()
    ref = request.POST.get("ref", "").strip()
    notes = request.POST.get("notes", "").strip()

    item = get_object_or_404(MenuItem, pk=item_id)

    try:
        qty = int(qty_raw)
        if qty < 0:
            raise ValueError()
    except ValueError:
        messages.error(request, "Please enter a valid non-negative quantity.")
        return redirect("manager:inventory")

    # Store Managers & Admins execute directly
    if user.role in {Role.MANAGER, Role.ADMIN} or user.is_superuser:
        old_stock = item.stock_quantity
        is_decrease = movement_type in ["Manual Decrease", "Damaged Goods", "Expired Goods"]

        if movement_type == "Stock Correction":
            new_stock = qty
            delta = new_stock - old_stock
        elif is_decrease:
            if qty > old_stock:
                messages.error(request, f"Cannot remove {qty} units. Current stock is only {old_stock}.")
                return redirect("manager:inventory")
            new_stock = old_stock - qty
            delta = -qty
        else:
            new_stock = old_stock + qty
            delta = qty

        with transaction.atomic():
            item.stock_quantity = new_stock
            item.track_stock = True
            item.is_available = new_stock > 0
            item.save(update_fields=["stock_quantity", "track_stock", "is_available"])

            # Map to StockMovement type enum
            m_type_map = {
                "Stock Received": "RESTOCK",
                "Manual Increase": "RESTOCK",
                "Manual Decrease": "WASTE",
                "Damaged Goods": "WASTE",
                "Expired Goods": "WASTE",
                "Stock Correction": "CORRECTION",
            }

            StockMovement.objects.create(
                item=item,
                movement_type=m_type_map.get(movement_type, "CORRECTION"),
                quantity=delta,
                resulting_quantity=new_stock,
                cost_per_unit=item.cost_price,
                notes=f"{reason} {notes}".strip(),
                created_by=user,
            )

            log_audit_event(
                request=request,
                action="Stock Adjusted",
                category="Inventory",
                record_id=item.sku or f"PRD-{item.pk}",
                change_summary=f"{item.name}: {old_stock} -> {new_stock} ({delta:+d}) [{movement_type}]",
            )

        messages.success(request, f"Updated stock for '{item.name}' from {old_stock} to {new_stock} {item.unit}.")
        return redirect("manager:inventory")

    # Regular staff submit request for approval
    req_type_map = {
        "Stock Received": "RESTOCK",
        "Manual Increase": "RESTOCK",
        "Manual Decrease": "CORRECTION",
        "Damaged Goods": "DAMAGED",
        "Expired Goods": "EXPIRED",
        "Stock Correction": "CORRECTION",
    }
    StockAdjustmentRequest.objects.create(
        item=item,
        request_type=req_type_map.get(movement_type, "CORRECTION"),
        quantity=qty,
        reason=reason,
        notes=notes,
        requested_by=user,
    )
    # Notify managers
    AdminNotification.objects.create(
        title=f"Stock request: {item.name}",
        message=f"Staff member {user.get_full_name() or user.username} reported {movement_type} of {qty} units.",
        notification_type="Inventory",
    )
    messages.success(request, f"Stock discrepancy request for '{item.name}' submitted for Manager approval.")
    return redirect("manager:stock_requests")


@require_GET
@role_required("STAFF", "INVENTORY", "CASHIER", "MANAGER", "ADMIN")
def stock_requests_list(request):
    """View pending and completed staff stock discrepancy/adjustment requests."""
    user = request.user
    if user.role in {Role.MANAGER, Role.ADMIN} or user.is_superuser:
        requests_qs = StockAdjustmentRequest.objects.select_related("item", "requested_by", "reviewed_by").all()
    else:
        requests_qs = StockAdjustmentRequest.objects.filter(requested_by=user).select_related("item", "requested_by", "reviewed_by")

    context = {
        "requests": requests_qs[:50],
        "active_nav": "stock_requests",
    }
    return render(request, "manager/stock_requests.html", context)


@require_POST
@role_required("MANAGER", "ADMIN")
def stock_request_action(request, pk):
    """Approve or reject a staff stock adjustment request."""
    req = get_object_or_404(StockAdjustmentRequest.objects.select_related("item"), pk=pk)
    action = request.POST.get("action")

    if req.status != "PENDING":
        messages.warning(request, "This request has already been processed.")
        return redirect("manager:stock_requests")

    if action == "approve":
        item = req.item
        old_stock = item.stock_quantity
        qty = req.quantity
        delta = -qty if req.request_type in ["DAMAGED", "EXPIRED", "MISSING"] else qty
        new_stock = max(0, old_stock + delta)

        with transaction.atomic():
            item.stock_quantity = new_stock
            item.save(update_fields=["stock_quantity"])

            StockMovement.objects.create(
                item=item,
                movement_type="WASTE" if delta < 0 else "CORRECTION",
                quantity=delta,
                resulting_quantity=new_stock,
                cost_per_unit=item.cost_price,
                notes=f"Approved staff request #{req.pk}: {req.reason}",
                created_by=request.user,
            )

            req.status = "APPROVED"
            req.reviewed_by = request.user
            req.reviewed_at = now()
            req.save(update_fields=["status", "reviewed_by", "reviewed_at"])

        messages.success(request, f"Approved request #{req.pk} for '{item.name}'. Stock adjusted to {new_stock}.")
    elif action == "reject":
        req.status = "REJECTED"
        req.reviewed_by = request.user
        req.reviewed_at = now()
        req.review_notes = request.POST.get("review_notes", "Declined by store manager")
        req.save(update_fields=["status", "reviewed_by", "reviewed_at", "review_notes"])
        messages.success(request, f"Request #{req.pk} has been rejected.")

    return redirect("manager:stock_requests")


# ===========================================================================
# 5. Products & Categories Management
# ===========================================================================

@require_GET
@role_required("MANAGER", "ADMIN")
def products_list(request):
    """Product catalog management view."""
    q = request.GET.get("q", "").strip()
    category_id = request.GET.get("category", "").strip()

    products_qs = MenuItem.objects.select_related("category").all().order_by("name")

    if q:
        products_qs = products_qs.filter(Q(name__icontains=q) | Q(sku__icontains=q))
    if category_id:
        products_qs = products_qs.filter(category_id=category_id)

    categories = Category.objects.filter(is_active=True).order_by("name")

    context = {
        "products": products_qs[:100],
        "categories": categories,
        "q": q,
        "selected_cat": category_id,
        "active_nav": "products",
    }
    return render(request, "manager/products.html", context)


@require_POST
@role_required("MANAGER", "ADMIN")
def product_add(request):
    """Add a new product to the catalog."""
    name = request.POST.get("name", "").strip()
    sku = request.POST.get("sku", "").strip()
    category_id = request.POST.get("category_id")
    price_raw = request.POST.get("price", "0").strip()
    unit = request.POST.get("unit", "pack").strip()
    stock_raw = request.POST.get("stock_quantity", "0").strip()
    thr_raw = request.POST.get("low_stock_threshold", "10").strip()

    if not name or not sku:
        messages.error(request, "Product name and SKU are required.")
        return redirect("manager:products")

    if MenuItem.objects.filter(sku__iexact=sku).exists():
        messages.error(request, f"A product with SKU '{sku}' already exists.")
        return redirect("manager:products")

    try:
        price = Decimal(price_raw)
        stock = max(0, int(stock_raw))
        thr = max(0, int(thr_raw))
    except (ValueError, TypeError):
        messages.error(request, "Please enter valid numeric values for price and stock.")
        return redirect("manager:products")

    category = get_object_or_404(Category, pk=category_id)

    with transaction.atomic():
        item = MenuItem.objects.create(
            name=name,
            sku=sku,
            category=category,
            price=price,
            unit=unit,
            stock_quantity=stock,
            low_stock_threshold=thr,
            track_stock=True,
            is_available=True,
        )

        log_audit_event(
            request=request,
            action="Product Added",
            category="Catalog",
            record_id=sku,
            change_summary=f"Created product '{name}' (₹{price})",
        )

    messages.success(request, f"Product '{name}' added successfully.")
    return redirect("manager:products")


@require_POST
@role_required("MANAGER", "ADMIN")
def product_edit(request, pk):
    """Edit an existing product."""
    item = get_object_or_404(MenuItem, pk=pk)

    name = request.POST.get("name", "").strip()
    sku = request.POST.get("sku", "").strip()
    category_id = request.POST.get("category_id")
    price_raw = request.POST.get("price", "0").strip()
    unit = request.POST.get("unit", "pack").strip()
    stock_raw = request.POST.get("stock_quantity", "0").strip()
    thr_raw = request.POST.get("low_stock_threshold", "10").strip()

    if not name or not sku:
        messages.error(request, "Product name and SKU are required.")
        return redirect("manager:products")

    if MenuItem.objects.filter(sku__iexact=sku).exclude(pk=item.pk).exists():
        messages.error(request, f"Another product already uses SKU '{sku}'.")
        return redirect("manager:products")

    try:
        price = Decimal(price_raw)
        stock = max(0, int(stock_raw))
        thr = max(0, int(thr_raw))
    except (ValueError, TypeError):
        messages.error(request, "Invalid numeric values.")
        return redirect("manager:products")

    category = get_object_or_404(Category, pk=category_id)

    item.name = name
    item.sku = sku
    item.category = category
    item.price = price
    item.unit = unit
    item.stock_quantity = stock
    item.low_stock_threshold = thr
    item.save()

    messages.success(request, f"Product '{name}' updated.")
    return redirect("manager:products")


@require_POST
@role_required("MANAGER", "ADMIN")
def product_toggle(request, pk):
    """Toggle product is_available status."""
    item = get_object_or_404(MenuItem, pk=pk)
    item.is_available = not item.is_available
    item.save(update_fields=["is_available"])

    state_str = "activated" if item.is_available else "deactivated"
    messages.success(request, f"Product '{item.name}' {state_str}.")
    return redirect("manager:products")


@require_GET
@role_required("MANAGER", "ADMIN")
def categories_list(request):
    """Category list view with counts."""
    cats = Category.objects.prefetch_related("items").order_by("name")
    return render(request, "manager/categories.html", {"categories": cats, "active_nav": "categories"})


@require_POST
@role_required("MANAGER", "ADMIN")
def category_add(request):
    """Create a new category."""
    name = request.POST.get("name", "").strip()
    if not name:
        messages.error(request, "Category name is required.")
        return redirect("manager:categories")

    if Category.objects.filter(name__iexact=name).exists():
        messages.error(request, f"Category '{name}' already exists.")
        return redirect("manager:categories")

    Category.objects.create(name=name, is_active=True)
    messages.success(request, f"Category '{name}' created.")
    return redirect("manager:categories")


@require_POST
@role_required("MANAGER", "ADMIN")
def category_edit(request, pk):
    """Edit an existing category."""
    cat = get_object_or_404(Category, pk=pk)
    name = request.POST.get("name", "").strip()
    if not name:
        messages.error(request, "Name cannot be empty.")
        return redirect("manager:categories")

    if Category.objects.filter(name__iexact=name).exclude(pk=cat.pk).exists():
        messages.error(request, f"Another category is already named '{name}'.")
        return redirect("manager:categories")

    cat.name = name
    cat.save(update_fields=["name"])
    messages.success(request, f"Category updated to '{name}'.")
    return redirect("manager:categories")


@require_POST
@role_required("MANAGER", "ADMIN")
def category_toggle(request, pk):
    """Toggle category active state."""
    cat = get_object_or_404(Category, pk=pk)
    cat.is_active = not cat.is_active
    cat.save(update_fields=["is_active"])
    messages.success(request, f"Category '{cat.name}' is now {'active' if cat.is_active else 'inactive'}.")
    return redirect("manager:categories")


# ===========================================================================
# 6. Stock Movements, Low Stock Alerts & Suppliers
# ===========================================================================

@require_GET
@role_required("STAFF", "INVENTORY", "CASHIER", "MANAGER", "ADMIN")
def movements_list(request):
    """View stock movements log."""
    prod_id = request.GET.get("product", "").strip()
    m_type = request.GET.get("type", "").strip()

    moves_qs = StockMovement.objects.select_related("item", "created_by").order_by("-created_at")

    if prod_id:
        moves_qs = moves_qs.filter(item_id=prod_id)
    if m_type == "in":
        moves_qs = moves_qs.filter(quantity__gt=0)
    elif m_type == "out":
        moves_qs = moves_qs.filter(quantity__lt=0)

    all_products = MenuItem.objects.all().order_by("name")

    context = {
        "movements": moves_qs[:60],
        "all_products": all_products,
        "selected_prod": prod_id,
        "selected_type": m_type,
        "active_nav": "movements",
    }
    return render(request, "manager/movements.html", context)


@require_GET
@role_required("STAFF", "INVENTORY", "CASHIER", "MANAGER", "ADMIN")
def low_stock_list(request):
    """Low stock alerts with urgency filters."""
    urgency = request.GET.get("urgency", "").strip()
    category_id = request.GET.get("category", "").strip()

    items = MenuItem.objects.filter(track_stock=True).select_related("category")
    if category_id:
        items = items.filter(category_id=category_id)

    low_items = []
    reviewed_set = set(request.session.get("reviewed_low_stock_ids", []))

    for p in items:
        if urgency == "out" and p.stock_quantity <= 0:
            pass
        elif urgency == "low" and 0 < p.stock_quantity <= p.low_stock_threshold:
            pass
        elif urgency == "near" and p.low_stock_threshold < p.stock_quantity <= (p.low_stock_threshold * 1.3):
            pass
        elif not urgency and (p.stock_quantity <= p.low_stock_threshold or p.stock_quantity <= (p.low_stock_threshold * 1.3)):
            pass
        else:
            continue

        p.suggested_reorder = max(p.low_stock_threshold * 2 - p.stock_quantity, 0)
        p.is_reviewed = p.pk in reviewed_set
        low_items.append(p)

    categories = Category.objects.filter(is_active=True).order_by("name")

    context = {
        "low_items": low_items,
        "categories": categories,
        "selected_urgency": urgency,
        "selected_cat": category_id,
        "active_nav": "low",
    }
    return render(request, "manager/low_stock.html", context)


@require_POST
@role_required("STAFF", "INVENTORY", "CASHIER", "MANAGER", "ADMIN")
def low_stock_review(request, pk):
    """Mark a low-stock alert as reviewed in session."""
    reviewed_ids = request.session.get("reviewed_low_stock_ids", [])
    if pk not in reviewed_ids:
        reviewed_ids.append(pk)
        request.session["reviewed_low_stock_ids"] = reviewed_ids
    messages.success(request, "Product marked as reviewed.")
    return redirect("manager:low_stock")


@require_GET
@role_required("STAFF", "INVENTORY", "CASHIER", "MANAGER", "ADMIN")
def suppliers_list(request):
    """Vendor directory list view."""
    sups = Supplier.objects.all().order_by("name")
    return render(request, "manager/suppliers.html", {"suppliers": sups, "active_nav": "suppliers"})


# ===========================================================================
# 7. Staff Management (Manager Only)
# ===========================================================================

@require_GET
@role_required("MANAGER", "ADMIN")
def staff_list(request):
    """View and filter store staff members."""
    q = request.GET.get("q", "").strip()
    role_filter = request.GET.get("role", "").strip()
    status_filter = request.GET.get("status", "").strip()

    staff_roles = [Role.STAFF, Role.INVENTORY, Role.CASHIER]
    staff_qs = User.objects.filter(role__in=staff_roles).select_related("staff_profile__current_shift").order_by("first_name", "username")

    if role_filter:
        staff_qs = staff_qs.filter(role=role_filter)
    if status_filter == "active":
        staff_qs = staff_qs.filter(is_active=True)
    elif status_filter == "inactive":
        staff_qs = staff_qs.filter(is_active=False)

    if q:
        staff_qs = staff_qs.filter(
            Q(username__icontains=q)
            | Q(first_name__icontains=q)
            | Q(last_name__icontains=q)
            | Q(staff_profile__employee_id__icontains=q)
        )

    shifts = StaffShift.objects.filter(is_active=True).order_by("start_time")

    context = {
        "staff_members": staff_qs,
        "shifts": shifts,
        "q": q,
        "selected_role": role_filter,
        "selected_status": status_filter,
        "active_nav": "staff",
    }
    return render(request, "manager/staff.html", context)


@require_POST
@role_required("MANAGER", "ADMIN")
def staff_create(request):
    """Create a new staff member account."""
    username = request.POST.get("username", "").strip()
    password = request.POST.get("password", "")
    first_name = request.POST.get("first_name", "").strip()
    last_name = request.POST.get("last_name", "").strip()
    role = request.POST.get("role", "STAFF").strip()
    employee_id = request.POST.get("employee_id", "").strip() or None
    department = request.POST.get("department", "Store Operations").strip()
    shift_id = request.POST.get("shift_id")
    phone = request.POST.get("phone", "").strip()
    responsibilities = request.POST.get("responsibilities", "").strip()

    # Prevent privilege escalation
    if role not in [Role.STAFF, Role.INVENTORY, Role.CASHIER]:
        role = Role.STAFF

    if not username or not password:
        messages.error(request, "Username and password are required.")
        return redirect("manager:staff")

    if User.objects.filter(username__iexact=username).exists():
        messages.error(request, f"Username '{username}' is already taken.")
        return redirect("manager:staff")

    if employee_id and StaffProfile.objects.filter(employee_id__iexact=employee_id).exists():
        messages.error(request, f"Employee ID '{employee_id}' is already assigned.")
        return redirect("manager:staff")

    with transaction.atomic():
        user = User.objects.create_user(
            username=username,
            password=password,
            first_name=first_name,
            last_name=last_name,
            role=role,
            phone=phone,
            is_staff=False,
            is_superuser=False,
        )

        shift = StaffShift.objects.filter(pk=shift_id).first() if shift_id else None

        StaffProfile.objects.create(
            user=user,
            employee_id=employee_id,
            department=department,
            assigned_by=request.user,
            responsibilities=responsibilities,
            current_shift=shift,
        )

        log_audit_event(
            request=request,
            action="Staff Created",
            category="Staff",
            record_id=username,
            change_summary=f"Created staff user '{username}' with role {role}",
        )

    messages.success(request, f"Staff member '{user.get_full_name() or username}' created successfully.")
    return redirect("manager:staff")


@require_POST
@role_required("MANAGER", "ADMIN")
def staff_edit(request, pk):
    """Edit permitted staff member details."""
    user = get_object_or_404(User.objects.filter(role__in=[Role.STAFF, Role.INVENTORY, Role.CASHIER]), pk=pk)
    profile, _ = StaffProfile.objects.get_or_create(user=user)

    user.first_name = request.POST.get("first_name", "").strip()
    user.last_name = request.POST.get("last_name", "").strip()
    user.email = request.POST.get("email", "").strip()
    user.phone = request.POST.get("phone", "").strip()
    user.save(update_fields=["first_name", "last_name", "email", "phone"])

    profile.department = request.POST.get("department", "Store Operations").strip()
    profile.responsibilities = request.POST.get("responsibilities", "").strip()
    shift_id = request.POST.get("shift_id")
    profile.current_shift = StaffShift.objects.filter(pk=shift_id).first() if shift_id else None
    profile.save()

    messages.success(request, f"Staff details for '{user.username}' updated.")
    return redirect("manager:staff")


@require_POST
@role_required("MANAGER", "ADMIN")
def staff_toggle(request, pk):
    """Activate or deactivate a staff member."""
    user = get_object_or_404(User.objects.filter(role__in=[Role.STAFF, Role.INVENTORY, Role.CASHIER]), pk=pk)
    if user.pk == request.user.pk:
        messages.error(request, "You cannot deactivate your own account.")
        return redirect("manager:staff")

    user.is_active = not user.is_active
    user.save(update_fields=["is_active"])

    status_str = "activated" if user.is_active else "deactivated"
    messages.success(request, f"Staff member '{user.username}' {status_str}.")
    return redirect("manager:staff")


# ===========================================================================
# 8. Staff Task Management
# ===========================================================================

@require_GET
@role_required("STAFF", "INVENTORY", "CASHIER", "MANAGER", "ADMIN")
def tasks_list(request):
    """View operational tasks with status filters."""
    user = request.user
    status_filter = request.GET.get("status", "").strip().upper()

    if user.role in {Role.MANAGER, Role.ADMIN} or user.is_superuser:
        tasks_qs = StaffTask.objects.select_related("assigned_to", "created_by").all().order_by("-created_at")
    else:
        tasks_qs = StaffTask.objects.filter(assigned_to=user).select_related("assigned_to", "created_by").order_by("-created_at")

    if status_filter:
        tasks_qs = tasks_qs.filter(status=status_filter)

    staff_options = User.objects.filter(role__in=[Role.STAFF, Role.INVENTORY, Role.CASHIER], is_active=True).order_by("first_name")

    context = {
        "tasks": tasks_qs[:60],
        "selected_status": status_filter,
        "staff_options": staff_options,
        "active_nav": "tasks",
    }
    return render(request, "manager/tasks.html", context)


@require_POST
@role_required("MANAGER", "ADMIN")
def task_create(request):
    """Assign a new operational task to a staff member."""
    title = request.POST.get("title", "").strip()
    description = request.POST.get("description", "").strip()
    assigned_to_id = request.POST.get("assigned_to")
    priority = request.POST.get("priority", "MEDIUM").strip().upper()
    category = request.POST.get("category", "GENERAL").strip().upper()
    due_date_raw = request.POST.get("due_date", "").strip()
    due_date = None
    if due_date_raw:
        from django.utils.dateparse import parse_datetime
        from django.utils.timezone import is_naive, make_aware
        parsed_dt = parse_datetime(due_date_raw)
        if parsed_dt:
            due_date = make_aware(parsed_dt) if is_naive(parsed_dt) else parsed_dt

    assigned_to = get_object_or_404(User, pk=assigned_to_id)

    task = StaffTask.objects.create(
        title=title,
        description=description,
        assigned_to=assigned_to,
        created_by=request.user,
        priority=priority,
        category=category,
        due_date=due_date,
    )

    # Notify staff member
    AdminNotification.objects.create(
        recipient=assigned_to,
        title=f"New Task: {title}",
        message=f"You have been assigned a new task by {request.user.get_full_name() or request.user.username}.",
        notification_type="Task",
    )

    messages.success(request, f"Task '{title}' assigned to {assigned_to.get_full_name() or assigned_to.username}.")
    return redirect("manager:tasks")


@require_POST
@role_required("STAFF", "INVENTORY", "CASHIER", "MANAGER", "ADMIN")
def task_update_status(request, pk):
    """Update task progress or mark complete."""
    user = request.user
    if user.role in {Role.MANAGER, Role.ADMIN} or user.is_superuser:
        task = get_object_or_404(StaffTask, pk=pk)
    else:
        task = get_object_or_404(StaffTask, pk=pk, assigned_to=user)

    new_status = request.POST.get("status", "COMPLETED").strip().upper()
    notes = request.POST.get("completion_notes", "").strip()

    task.status = new_status
    if new_status == "COMPLETED":
        task.completed_at = now()
        if notes:
            task.completion_notes = notes
    task.save()

    messages.success(request, f"Task '{task.title}' updated to {task.get_status_display()}.")
    if user.role in {Role.MANAGER, Role.ADMIN} or user.is_superuser:
        return redirect("manager:tasks")
    return redirect("manager:staff_dashboard")


@require_POST
@role_required("MANAGER", "ADMIN")
def task_cancel(request, pk):
    """Cancel a staff task."""
    task = get_object_or_404(StaffTask, pk=pk)
    task.status = "CANCELLED"
    task.save(update_fields=["status"])
    messages.success(request, f"Task '{task.title}' cancelled.")
    return redirect("manager:tasks")


# ===========================================================================
# 9. Shifts & Attendance
# ===========================================================================

@require_GET
@role_required("STAFF", "INVENTORY", "CASHIER", "MANAGER", "ADMIN")
def attendance_view(request):
    """View shifts, today's attendance roster, and log."""
    user = request.user
    today = now().date()

    shifts = StaffShift.objects.prefetch_related("assigned_staff").filter(is_active=True).order_by("start_time")
    attendance_today = StaffAttendance.objects.filter(date=today).select_related("staff", "shift")
    on_duty_count = attendance_today.filter(status="PRESENT", check_out__isnull=True).count()

    if user.role in {Role.MANAGER, Role.ADMIN} or user.is_superuser:
        records = StaffAttendance.objects.select_related("staff", "shift").order_by("-date", "-check_in")[:50]
    else:
        records = StaffAttendance.objects.filter(staff=user).select_related("staff", "shift").order_by("-date", "-check_in")[:30]

    my_attendance = StaffAttendance.objects.filter(staff=user, date=today).first()

    context = {
        "shifts": shifts,
        "today": today,
        "attendance_today": attendance_today,
        "on_duty_count": on_duty_count,
        "attendance_records": records,
        "my_attendance": my_attendance,
        "active_nav": "attendance",
    }
    return render(request, "manager/attendance.html", context)


@require_POST
@role_required("STAFF", "INVENTORY", "CASHIER", "MANAGER", "ADMIN")
def attendance_check(request):
    """Log staff check-in or check-out with atomic timestamp."""
    user = request.user
    today = now().date()
    action = request.POST.get("action")
    redirect_target = request.POST.get("redirect", "attendance")

    profile = StaffProfile.objects.filter(user=user).first()
    shift = profile.current_shift if profile else None

    if action == "check_in":
        att, created = StaffAttendance.objects.get_or_create(
            staff=user,
            date=today,
            defaults={
                "check_in": now(),
                "status": "PRESENT",
                "shift": shift,
            },
        )
        if not created and not att.check_in:
            att.check_in = now()
            att.status = "PRESENT"
            att.save(update_fields=["check_in", "status"])
        messages.success(request, f"Checked in for duty at {now().strftime('%H:%M')}.")
    elif action == "check_out":
        att = StaffAttendance.objects.filter(staff=user, date=today).first()
        if att and not att.check_out:
            att.check_out = now()
            att.save(update_fields=["check_out"])
            messages.success(request, f"Shift check-out recorded at {now().strftime('%H:%M')}. Good job today!")
        else:
            messages.warning(request, "No active check-in record found for today.")

    if redirect_target == "staff_dashboard":
        return redirect("manager:staff_dashboard")
    return redirect("manager:attendance")


@require_POST
@role_required("MANAGER", "ADMIN")
def shift_create(request):
    """Define a new store work shift schedule."""
    name = request.POST.get("name", "").strip()
    start_time = request.POST.get("start_time")
    end_time = request.POST.get("end_time")

    if not name or not start_time or not end_time:
        messages.error(request, "Shift name, start time, and end time are required.")
        return redirect("manager:attendance")

    StaffShift.objects.create(name=name, start_time=start_time, end_time=end_time, is_active=True)
    messages.success(request, f"Shift schedule '{name}' created.")
    return redirect("manager:attendance")


# ===========================================================================
# 10. Reports, Notifications & Settings
# ===========================================================================

@require_GET
@role_required("STAFF", "INVENTORY", "CASHIER", "MANAGER", "ADMIN")
def reports_view(request):
    """Store operational reports and visual analytics."""
    all_items = MenuItem.objects.select_related("category").all()

    total_val = sum((it.price * it.stock_quantity) for it in all_items if it.track_stock)
    tracked_count = all_items.filter(track_stock=True).count()
    available_count = all_items.filter(is_available=True).count()
    avail_pct = round((available_count / max(1, all_items.count())) * 100)

    low_cnt = all_items.filter(track_stock=True, stock_quantity__gt=0, stock_quantity__lte=F("low_stock_threshold")).count()
    out_cnt = all_items.filter(track_stock=True, stock_quantity__lte=0).count()
    moves_cnt = StockMovement.objects.count()

    # Category distribution calculation
    category_distributions = []
    cat_units_total = 0
    for cat in Category.objects.prefetch_related("items").all():
        u = sum(i.stock_quantity for i in cat.items.all() if i.track_stock)
        cat_units_total += u
        category_distributions.append({"name": cat.name, "units": u, "pct": 0})

    max_u = max(1, max([c["units"] for c in category_distributions], default=1))
    for c in category_distributions:
        c["pct"] = round((c["units"] / max_u) * 100)

    # Order status pipeline distribution
    total_orders = max(1, Order.objects.count())
    status_distributions = []
    for st, label in OrderStatus.choices:
        cnt = Order.objects.filter(status=st).count()
        status_distributions.append({
            "status": st,
            "label": label,
            "count": cnt,
            "pct": round((cnt / total_orders) * 100),
        })

    context = {
        "total_valuation": total_val,
        "active_availability_pct": avail_pct,
        "low_stock_count": low_cnt,
        "out_of_stock_count": out_cnt,
        "movements_count": moves_cnt,
        "category_distributions": category_distributions,
        "status_distributions": status_distributions,
        "active_nav": "reports",
    }
    return render(request, "manager/reports.html", context)


@require_http_methods(["GET", "POST"])
@role_required("STAFF", "INVENTORY", "CASHIER", "MANAGER", "ADMIN")
def notifications_view(request):
    """Store operational alerts and messaging."""
    user = request.user

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "mark_all_read":
            AdminNotification.objects.filter(Q(recipient=user) | Q(recipient__isnull=True), is_read=False).update(is_read=True)
            messages.success(request, "All store notifications marked as read.")
        elif action == "toggle_read":
            notif_id = request.POST.get("notif_id")
            notif = get_object_or_404(AdminNotification, pk=notif_id)
            notif.is_read = not notif.is_read
            notif.save(update_fields=["is_read"])
        return redirect("manager:notifications")

    notifs = AdminNotification.objects.filter(Q(recipient=user) | Q(recipient__isnull=True)).order_by("-created_at")[:50]
    return render(request, "manager/notifications.html", {"notifications": notifs, "active_nav": "notifications"})


@require_http_methods(["GET", "POST"])
@role_required("MANAGER", "ADMIN")
def settings_view(request):
    """Manager profile, store info, notification toggles, and prototype reset."""
    prefs = request.session.get("manager_notification_prefs", {"low_stock": True, "new_orders": True})

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "save_prefs":
            prefs["low_stock"] = bool(request.POST.get("pref_low_stock"))
            prefs["new_orders"] = bool(request.POST.get("pref_new_orders"))
            request.session["manager_notification_prefs"] = prefs
            messages.success(request, "Notification preferences saved.")
        elif action == "reset_demo":
            request.session.pop("manager_notification_prefs", None)
            request.session.pop("reviewed_low_stock_ids", None)
            messages.success(request, "Demo session preferences reset.")
        return redirect("manager:settings")

    context = {
        "prefs": prefs,
        "active_nav": "settings",
    }
    return render(request, "manager/settings.html", context)
