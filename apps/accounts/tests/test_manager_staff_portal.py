"""Comprehensive functional, authorization, security, and button tests for the Store Manager & Staff Portal."""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse
from django.utils.timezone import now

from apps.accounts.models import (
    Role,
    StaffAttendance,
    StaffProfile,
    StaffShift,
    StaffTask,
    StockAdjustmentRequest,
    User,
)
from apps.customer_auth.models import Customer
from apps.menu.models import Category, MenuItem, StockMovement
from apps.notifications.models import AdminNotification
from apps.orders.models import Order, OrderEvent, OrderItem, OrderStatus
from apps.orders.services import assign_agent, create_order, transition
from apps.suppliers.models import Supplier


# ===========================================================================
# Fixtures
# ===========================================================================

@pytest.fixture
def store_manager(db):
    user = User.objects.create_user(
        username="manager_ravi",
        password="managerpass123",
        role=Role.MANAGER,
        first_name="Ravi",
        last_name="Kumar",
        email="ravi@supermarket.in",
        phone="+91 98765 11111",
    )
    StaffProfile.objects.create(
        user=user,
        employee_id="MGR-001",
        department="Store Management",
        responsibilities="Store operations oversight, inventory management, staff scheduling",
    )
    return user


@pytest.fixture
def store_staff_1(db, store_manager):
    user = User.objects.create_user(
        username="staff_priya",
        password="staffpass123",
        role=Role.STAFF,
        first_name="Priya",
        last_name="Sharma",
        email="priya@supermarket.in",
        phone="+91 98765 22222",
    )
    StaffProfile.objects.create(
        user=user,
        employee_id="STF-101",
        department="Order Fulfillment",
        assigned_by=store_manager,
        responsibilities="Order picking, packing, customer assistance",
    )
    return user


@pytest.fixture
def store_staff_2(db, store_manager):
    user = User.objects.create_user(
        username="staff_amit",
        password="staffpass123",
        role=Role.INVENTORY,
        first_name="Amit",
        last_name="Verma",
        email="amit@supermarket.in",
        phone="+91 98765 33333",
    )
    StaffProfile.objects.create(
        user=user,
        employee_id="STF-102",
        department="Inventory",
        assigned_by=store_manager,
        responsibilities="Stock receipt, shelf replenishment, discrepancy logging",
    )
    return user


@pytest.fixture
def customer_user(db):
    return User.objects.create_user(
        username="cust_vikram",
        password="custpass123",
        role=Role.CUSTOMER,
        email="vikram@example.com",
    )


@pytest.fixture
def delivery_agent(db):
    user = User.objects.create_user(
        username="agent_karan",
        password="agentpass123",
        role=Role.AGENT,
    )
    from apps.accounts.models import AgentProfile
    AgentProfile.objects.create(user=user, is_available=True)
    return user


@pytest.fixture
def category_groceries(db):
    return Category.objects.create(name="Groceries & Staples", sort_order=1, is_active=True)


@pytest.fixture
def category_dairy(db):
    return Category.objects.create(name="Dairy & Eggs", sort_order=2, is_active=True)


@pytest.fixture
def product_rice(category_groceries):
    return MenuItem.objects.create(
        name="Basmati Rice 5kg",
        sku="RC-BAS-5",
        category=category_groceries,
        price=Decimal("645.00"),
        unit="bag",
        stock_quantity=40,
        low_stock_threshold=15,
        track_stock=True,
        is_available=True,
    )


@pytest.fixture
def product_milk(category_dairy):
    return MenuItem.objects.create(
        name="Toned Milk 1L",
        sku="DA-MLK-1",
        category=category_dairy,
        price=Decimal("56.00"),
        unit="pack",
        stock_quantity=8,  # Below threshold
        low_stock_threshold=20,
        track_stock=True,
        is_available=True,
    )


@pytest.fixture
def morning_shift(db):
    return StaffShift.objects.create(
        name="Morning Shift (06:00 - 14:00)",
        start_time="06:00:00",
        end_time="14:00:00",
        is_active=True,
    )


@pytest.fixture
def sample_store_order(product_rice, product_milk, store_manager):
    order = create_order(
        order_type="DELV",
        items=[
            {"menu_item_id": product_rice.pk, "quantity": 1},
            {"menu_item_id": product_milk.pk, "quantity": 2},
        ],
        contact_name="Sunita Rao",
        contact_phone="9876543210",
        instructions="Handle eggs & milk carefully.",
    )
    return order


# ===========================================================================
# 1. Authentication & Role-Based Access Tests
# ===========================================================================

@pytest.mark.django_db
def test_manager_login_get_form(client):
    """GET /manager/login/ renders the store manager/staff login form."""
    resp = client.get(reverse("manager:login"))
    assert resp.status_code == 200
    html = resp.content.decode()
    assert "Store Manager & Staff Portal" in html
    assert 'name="username"' in html
    assert 'name="password"' in html
    assert "Sign in to Portal" in html


@pytest.mark.django_db
def test_manager_login_valid_credentials(client, store_manager):
    """Store Manager logs in via /manager/login/ and is redirected to /manager/ dashboard."""
    resp = client.post(
        reverse("manager:login"),
        {"username": "manager_ravi", "password": "managerpass123"},
    )
    assert resp.status_code == 302
    assert resp.url == reverse("manager:dashboard")

    # Follow redirect
    follow_resp = client.get(resp.url)
    assert follow_resp.status_code == 200
    assert "Store Manager Dashboard" in follow_resp.content.decode()


@pytest.mark.django_db
def test_staff_login_valid_credentials(client, store_staff_1):
    """Store Staff logs in via /manager/login/ and is redirected to /manager/staff-dashboard/."""
    resp = client.post(
        reverse("manager:login"),
        {"username": "staff_priya", "password": "staffpass123"},
    )
    assert resp.status_code == 302
    assert resp.url == reverse("manager:staff_dashboard")

    # Follow redirect
    follow_resp = client.get(resp.url)
    assert follow_resp.status_code == 200
    assert "Staff Operations Dashboard" in follow_resp.content.decode()


@pytest.mark.django_db
def test_manager_login_invalid_password(client, store_manager):
    """Invalid password returns error message and stays on login screen."""
    resp = client.post(
        reverse("manager:login"),
        {"username": "manager_ravi", "password": "wrongpassword"},
    )
    assert resp.status_code == 200
    assert "Invalid username or password" in resp.content.decode()


@pytest.mark.django_db
def test_customer_and_agent_cannot_login_to_manager_portal(client, customer_user, delivery_agent):
    """Customers and Delivery Agents are denied access to the Manager/Staff Portal."""
    # Attempt customer login
    resp_cust = client.post(
        reverse("manager:login"),
        {"username": "cust_vikram", "password": "custpass123"},
    )
    assert resp_cust.status_code == 200
    assert "Access denied: This portal is exclusively for SuperMarket Managers and Staff." in resp_cust.content.decode()

    # Attempt agent login
    resp_agent = client.post(
        reverse("manager:login"),
        {"username": "agent_karan", "password": "agentpass123"},
    )
    assert resp_agent.status_code == 200
    assert "Access denied" in resp_agent.content.decode()


@pytest.mark.django_db
def test_unauthenticated_manager_redirects(client):
    """Unauthenticated access to /manager/ routes redirects to login."""
    resp = client.get(reverse("manager:dashboard"))
    assert resp.status_code == 302
    assert "login" in resp.url


@pytest.mark.django_db
def test_staff_cannot_access_manager_dashboard(client, store_staff_1):
    """Regular staff member attempting to access /manager/ gets 403 Forbidden."""
    client.force_login(store_staff_1)
    resp = client.get(reverse("manager:dashboard"))
    assert resp.status_code == 403


@pytest.mark.django_db
def test_manager_logout(client, store_manager):
    """Logging out clears session and redirects to /manager/login/."""
    client.force_login(store_manager)
    resp = client.get(reverse("manager:logout"))
    assert resp.status_code == 302
    assert resp.url == reverse("manager:login")


# ===========================================================================
# 2. Dashboards Tests
# ===========================================================================

@pytest.mark.django_db
def test_manager_dashboard_metrics_and_sections(client, store_manager, sample_store_order, product_milk):
    """Manager dashboard displays live database KPIs, order queue, low stock, and staff roster."""
    client.force_login(store_manager)
    resp = client.get(reverse("manager:dashboard"))
    assert resp.status_code == 200
    html = resp.content.decode()

    assert "Store Manager Dashboard" in html
    assert f"#{sample_store_order.pk}" in html
    assert "Sunita Rao" in html
    assert "Toned Milk 1L" in html  # Low stock item
    assert "Inventory Health" in html
    assert "Order Queue" in html


@pytest.mark.django_db
def test_staff_dashboard_view(client, store_staff_1, sample_store_order, morning_shift):
    """Staff dashboard renders employee profile, shift info, and attendance button."""
    client.force_login(store_staff_1)
    
    # Associate morning shift
    store_staff_1.staff_profile.current_shift = morning_shift
    store_staff_1.staff_profile.save()

    resp = client.get(reverse("manager:staff_dashboard"))
    assert resp.status_code == 200
    html = resp.content.decode()

    assert "Staff Operations Dashboard" in html
    assert "Priya Sharma" in html
    assert "Order Fulfillment" in html
    assert "Morning Shift (06:00 - 14:00)" in html
    assert "Check In for Duty" in html


# ===========================================================================
# 3. Staff Management Tests (Manager Only)
# ===========================================================================

@pytest.mark.django_db
def test_staff_management_list_search_filter(client, store_manager, store_staff_1, store_staff_2):
    """Manager can list, search, and filter staff members."""
    client.force_login(store_manager)

    # All staff list
    resp = client.get(reverse("manager:staff"))
    assert resp.status_code == 200
    html = resp.content.decode()
    assert "Priya Sharma" in html
    assert "Amit Verma" in html

    # Filter by role
    resp_role = client.get(reverse("manager:staff") + "?role=INVENTORY")
    assert "Amit Verma" in resp_role.content.decode()
    assert "Priya Sharma" not in resp_role.content.decode()

    # Search by employee ID
    resp_search = client.get(reverse("manager:staff") + "?q=STF-101")
    assert "Priya Sharma" in resp_search.content.decode()


@pytest.mark.django_db
def test_manager_create_staff_account_success(client, store_manager, morning_shift):
    """Manager creates a new staff account with hashed password and profile metadata."""
    client.force_login(store_manager)

    resp = client.post(
        reverse("manager:staff_create"),
        {
            "username": "kavita_staff",
            "password": "securepass456",
            "first_name": "Kavita",
            "last_name": "Reddy",
            "role": "STAFF",
            "employee_id": "EMP-205",
            "department": "Checkout",
            "shift_id": morning_shift.pk,
            "phone": "+91 99999 88888",
            "responsibilities": "Billing, cashier duties, bag packing",
        },
    )
    assert resp.status_code == 302
    assert resp.url == reverse("manager:staff")

    # Verify database persistence
    new_user = User.objects.get(username="kavita_staff")
    assert new_user.first_name == "Kavita"
    assert new_user.role == Role.STAFF
    assert new_user.check_password("securepass456")  # Password hashed, NOT plaintext
    assert new_user.is_staff is False
    assert new_user.is_superuser is False

    profile = new_user.staff_profile
    assert profile.employee_id == "EMP-205"
    assert profile.department == "Checkout"
    assert profile.current_shift == morning_shift
    assert profile.assigned_by == store_manager


@pytest.mark.django_db
def test_manager_cannot_create_admin_or_superuser(client, store_manager):
    """Manager attempting to pass role='ADMIN' is sanitized to 'STAFF' (no privilege escalation)."""
    client.force_login(store_manager)

    client.post(
        reverse("manager:staff_create"),
        {
            "username": "fake_admin",
            "password": "hackerpassword",
            "first_name": "Evil",
            "last_name": "Admin",
            "role": "ADMIN",  # Unauthorized role escalation attempt
            "employee_id": "EMP-999",
        },
    )

    user = User.objects.get(username="fake_admin")
    assert user.role == Role.STAFF  # Coerced to regular STAFF
    assert user.is_superuser is False
    assert user.is_staff is False


@pytest.mark.django_db
def test_duplicate_staff_username_rejected(client, store_manager, store_staff_1):
    """Attempting to create a duplicate username is rejected with error feedback."""
    client.force_login(store_manager)

    resp = client.post(
        reverse("manager:staff_create"),
        {
            "username": "staff_priya",  # Existing username
            "password": "somepassword",
            "first_name": "Another",
            "role": "STAFF",
        },
    )
    assert resp.status_code == 302
    # Verify only one user exists
    assert User.objects.filter(username="staff_priya").count() == 1


@pytest.mark.django_db
def test_manager_edit_staff_permitted_fields(client, store_manager, store_staff_1):
    """Manager can update department, phone, and responsibilities for a staff member."""
    client.force_login(store_manager)

    resp = client.post(
        reverse("manager:staff_edit", args=[store_staff_1.pk]),
        {
            "first_name": "Priya",
            "last_name": "Verma",
            "email": "priya.updated@supermarket.in",
            "phone": "+91 91111 22222",
            "department": "Quality Assurance",
            "responsibilities": "Inspect fresh produce daily",
        },
    )
    assert resp.status_code == 302

    store_staff_1.refresh_from_db()
    assert store_staff_1.last_name == "Verma"
    assert store_staff_1.phone == "+91 91111 22222"
    assert store_staff_1.staff_profile.department == "Quality Assurance"


@pytest.mark.django_db
def test_manager_toggle_staff_active(client, store_manager, store_staff_1):
    """Manager can deactivate and re-activate staff accounts."""
    client.force_login(store_manager)

    # Deactivate
    client.post(reverse("manager:staff_toggle", args=[store_staff_1.pk]))
    store_staff_1.refresh_from_db()
    assert store_staff_1.is_active is False

    # Reactivate
    client.post(reverse("manager:staff_toggle", args=[store_staff_1.pk]))
    store_staff_1.refresh_from_db()
    assert store_staff_1.is_active is True


@pytest.mark.django_db
def test_staff_cannot_access_staff_management(client, store_staff_1):
    """Regular staff cannot access /manager/staff/ or create other staff members."""
    client.force_login(store_staff_1)
    resp_get = client.get(reverse("manager:staff"))
    assert resp_get.status_code == 403

    resp_post = client.post(reverse("manager:staff_create"), {"username": "illegal"})
    assert resp_post.status_code == 403


# ===========================================================================
# 4. Staff Task Management Tests
# ===========================================================================

@pytest.mark.django_db
def test_task_creation_and_assignment(client, store_manager, store_staff_1, sample_store_order):
    """Manager creates task and assigns to staff; staff receives alert notification."""
    client.force_login(store_manager)

    resp = client.post(
        reverse("manager:task_create"),
        {
            "title": "Pack order #100 items from dairy aisle",
            "description": "Double check expiry date on milk packs.",
            "assigned_to": store_staff_1.pk,
            "priority": "HIGH",
            "category": "ORDER_PREP",
            "due_date": (now() + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M"),
        },
    )
    assert resp.status_code == 302
    assert resp.url == reverse("manager:tasks")

    task = StaffTask.objects.get(title="Pack order #100 items from dairy aisle")
    assert task.assigned_to == store_staff_1
    assert task.created_by == store_manager
    assert task.priority == "HIGH"
    assert task.status == "PENDING"

    # Verify notification created for Priya
    notif = AdminNotification.objects.filter(recipient=store_staff_1).first()
    assert notif is not None
    assert "Pack order #100" in notif.title


@pytest.mark.django_db
def test_staff_update_task_progress_and_complete(client, store_staff_1, store_manager):
    """Staff member starts assigned task and marks it complete with notes."""
    task = StaffTask.objects.create(
        title="Restock Shelf B-4",
        assigned_to=store_staff_1,
        created_by=store_manager,
        priority="MEDIUM",
    )

    client.force_login(store_staff_1)

    # 1. Start task
    client.post(reverse("manager:task_update_status", args=[task.pk]), {"status": "IN_PROGRESS"})
    task.refresh_from_db()
    assert task.status == "IN_PROGRESS"

    # 2. Mark complete
    client.post(
        reverse("manager:task_update_status", args=[task.pk]),
        {"status": "COMPLETED", "completion_notes": "Added 20 packs of biscuits"},
    )
    task.refresh_from_db()
    assert task.status == "COMPLETED"
    assert task.completed_at is not None
    assert "20 packs" in task.completion_notes


@pytest.mark.django_db
def test_staff_cannot_update_another_staff_task(client, store_staff_1, store_staff_2, store_manager):
    """Staff A cannot modify or complete Staff B's task (IDOR protection)."""
    task_b = StaffTask.objects.create(
        title="Audit Frozen Section",
        assigned_to=store_staff_2,
        created_by=store_manager,
    )

    client.force_login(store_staff_1)
    resp = client.post(reverse("manager:task_update_status", args=[task_b.pk]), {"status": "COMPLETED"})
    assert resp.status_code == 404


# ===========================================================================
# 5. Shifts & Attendance Tests
# ===========================================================================

@pytest.mark.django_db
def test_manager_create_shift_schedule(client, store_manager):
    """Manager creates a work shift schedule."""
    client.force_login(store_manager)

    resp = client.post(
        reverse("manager:shift_create"),
        {
            "name": "Evening Shift (14:00 - 22:00)",
            "start_time": "14:00:00",
            "end_time": "22:00:00",
        },
    )
    assert resp.status_code == 302
    assert StaffShift.objects.filter(name="Evening Shift (14:00 - 22:00)").exists()


@pytest.mark.django_db
def test_staff_attendance_checkin_and_checkout(client, store_staff_1, morning_shift):
    """Staff records check-in and check-out with accurate server timestamps."""
    client.force_login(store_staff_1)
    store_staff_1.staff_profile.current_shift = morning_shift
    store_staff_1.staff_profile.save()

    # 1. Check in
    resp_in = client.post(reverse("manager:attendance_check"), {"action": "check_in"})
    assert resp_in.status_code == 302

    att = StaffAttendance.objects.get(staff=store_staff_1, date=now().date())
    assert att.check_in is not None
    assert att.check_out is None
    assert att.status == "PRESENT"
    assert att.shift == morning_shift

    # 2. Check out
    resp_out = client.post(reverse("manager:attendance_check"), {"action": "check_out"})
    assert resp_out.status_code == 302

    att.refresh_from_db()
    assert att.check_out is not None


# ===========================================================================
# 6. Orders Pipeline & Pick/Pack Checklist Tests
# ===========================================================================

@pytest.mark.django_db
def test_orders_pipeline_view_and_filtering(client, store_manager, sample_store_order):
    """Orders list filters orders by PLACED, APPROVED, READY, etc."""
    client.force_login(store_manager)

    resp = client.get(reverse("manager:orders") + "?status=PLACED")
    assert resp.status_code == 200
    assert f'id="btn-view-order-{sample_store_order.pk}"' in resp.content.decode()

    # Empty filter check
    resp_empty = client.get(reverse("manager:orders") + "?status=PAID")
    assert resp_empty.status_code == 200
    assert f'id="btn-view-order-{sample_store_order.pk}"' not in resp_empty.content.decode()


@pytest.mark.django_db
def test_order_item_pick_checklist(client, store_staff_1, sample_store_order):
    """Staff can toggle item picking checklist on an order."""
    client.force_login(store_staff_1)
    first_item = sample_store_order.items.first()
    assert first_item.is_picked is False

    # Toggle pick -> True
    resp_pick = client.post(reverse("manager:order_toggle_pick", args=[sample_store_order.pk, first_item.pk]))
    assert resp_pick.status_code == 302

    first_item.refresh_from_db()
    assert first_item.is_picked is True

    # Toggle unpick -> False
    client.post(reverse("manager:order_toggle_pick", args=[sample_store_order.pk, first_item.pk]))
    first_item.refresh_from_db()
    assert first_item.is_picked is False


@pytest.mark.django_db
def test_order_preparation_lifecycle_enforces_checklist(client, store_manager, sample_store_order):
    """Cannot mark order packed (READY) until all items are picked."""
    client.force_login(store_manager)

    # 1. Accept order: PLACED -> APPROVED
    client.post(reverse("manager:order_action", args=[sample_store_order.pk]), {"action": "accept"})
    sample_store_order.refresh_from_db()
    assert sample_store_order.status == OrderStatus.APPROVED

    # 2. Start preparing: APPROVED -> KITCHEN
    client.post(reverse("manager:order_action", args=[sample_store_order.pk]), {"action": "prepare"})
    sample_store_order.refresh_from_db()
    assert sample_store_order.status == OrderStatus.IN_KITCHEN

    # 3. Attempt packing without picking items -> blocked
    resp_blocked = client.post(reverse("manager:order_action", args=[sample_store_order.pk]), {"action": "pack"})
    sample_store_order.refresh_from_db()
    assert sample_store_order.status == OrderStatus.IN_KITCHEN  # Remains KITCHEN

    # 4. Pick all items
    sample_store_order.items.all().update(is_picked=True)

    # 5. Pack order: KITCHEN -> READY
    client.post(reverse("manager:order_action", args=[sample_store_order.pk]), {"action": "pack"})
    sample_store_order.refresh_from_db()
    assert sample_store_order.status == OrderStatus.READY


@pytest.mark.django_db
def test_order_cancellation_with_reason_restocks_inventory(client, store_manager, sample_store_order, product_rice):
    """Cancelling order via manager portal logs reason and restores tracked inventory."""
    product_rice.refresh_from_db()
    initial_stock = product_rice.stock_quantity

    client.force_login(store_manager)
    resp = client.post(
        reverse("manager:order_action", args=[sample_store_order.pk]),
        {"action": "cancel", "reason": "Store operational issue", "notes": "Freezer breakdown"},
    )
    assert resp.status_code == 302

    sample_store_order.refresh_from_db()
    assert sample_store_order.status == OrderStatus.CANCELLED
    assert sample_store_order.delivery_issue_reason == "Store operational issue"

    # Inventory restored
    product_rice.refresh_from_db()
    assert product_rice.stock_quantity == initial_stock + 1  # 1 unit restored


# ===========================================================================
# 7. Inventory Adjustments & Staff Discrepancy Requests
# ===========================================================================

@pytest.mark.django_db
def test_manager_direct_stock_adjustment(client, store_manager, product_rice):
    """Manager adjusts stock directly; persists stock and logs StockMovement."""
    initial_stock = product_rice.stock_quantity
    client.force_login(store_manager)

    resp = client.post(
        reverse("manager:inventory_adjust"),
        {
            "item_id": product_rice.pk,
            "movement_type": "Stock Received",
            "quantity": 10,
            "reason": "Weekly PO delivery",
            "ref": "GRN-2049",
        },
    )
    assert resp.status_code == 302

    product_rice.refresh_from_db()
    assert product_rice.stock_quantity == initial_stock + 10

    # StockMovement record created
    move = StockMovement.objects.filter(item=product_rice, created_by=store_manager).first()
    assert move is not None
    assert move.quantity == 10
    assert move.resulting_quantity == initial_stock + 10


@pytest.mark.django_db
def test_staff_stock_discrepancy_request_flow(client, store_staff_1, store_manager, product_rice):
    """Staff submits discrepancy request; Manager reviews and approves, updating stock."""
    initial_stock = product_rice.stock_quantity

    # 1. Staff submits damaged goods report
    client.force_login(store_staff_1)
    resp = client.post(
        reverse("manager:inventory_adjust"),
        {
            "item_id": product_rice.pk,
            "movement_type": "Damaged Goods",
            "quantity": 2,
            "reason": "Torn bag spilled during unloading",
        },
    )
    assert resp.status_code == 302
    assert resp.url == reverse("manager:stock_requests")

    # Stock not changed yet
    product_rice.refresh_from_db()
    assert product_rice.stock_quantity == initial_stock

    req = StockAdjustmentRequest.objects.get(item=product_rice, requested_by=store_staff_1)
    assert req.status == "PENDING"

    # 2. Manager approves request
    client.force_login(store_manager)
    resp_approve = client.post(reverse("manager:stock_request_action", args=[req.pk]), {"action": "approve"})
    assert resp_approve.status_code == 302

    # Stock now decremented
    product_rice.refresh_from_db()
    assert product_rice.stock_quantity == initial_stock - 2

    req.refresh_from_db()
    assert req.status == "APPROVED"
    assert req.reviewed_by == store_manager


# ===========================================================================
# 8. Products, Categories, Movements & Low Stock Tests
# ===========================================================================

@pytest.mark.django_db
def test_product_crud_by_manager(client, store_manager, category_groceries):
    """Manager can create, edit, and toggle active status of catalog products."""
    client.force_login(store_manager)

    # 1. Create product
    client.post(
        reverse("manager:product_add"),
        {
            "name": "Sunflower Oil 1L",
            "sku": "GR-OIL-01",
            "category_id": category_groceries.pk,
            "price": "165.00",
            "unit": "pack",
            "stock_quantity": "50",
            "low_stock_threshold": "10",
        },
    )
    product = MenuItem.objects.get(sku="GR-OIL-01")
    assert product.name == "Sunflower Oil 1L"
    assert product.price == Decimal("165.00")

    # 2. Toggle active
    client.post(reverse("manager:product_toggle", args=[product.pk]))
    product.refresh_from_db()
    assert product.is_available is False


@pytest.mark.django_db
def test_category_crud_by_manager(client, store_manager):
    """Manager can create, edit, and toggle categories."""
    client.force_login(store_manager)

    # Create
    client.post(reverse("manager:category_add"), {"name": "Snacks & Munchies"})
    cat = Category.objects.get(name="Snacks & Munchies")
    assert cat.is_active is True

    # Toggle
    client.post(reverse("manager:category_toggle", args=[cat.pk]))
    cat.refresh_from_db()
    assert cat.is_active is False


@pytest.mark.django_db
def test_reports_and_notifications_views(client, store_manager):
    """Reports view renders analytics and notifications view handles read actions."""
    client.force_login(store_manager)

    # Reports
    resp_rep = client.get(reverse("manager:reports"))
    assert resp_rep.status_code == 200
    assert "Store Operational Metrics" in resp_rep.content.decode()

    # Notifications
    notif = AdminNotification.objects.create(
        title="Restock Notice",
        message="Order arriving today",
        is_read=False,
    )
    resp_notif = client.get(reverse("manager:notifications"))
    assert resp_notif.status_code == 200
    assert "Restock Notice" in resp_notif.content.decode()

    # Mark all read
    client.post(reverse("manager:notifications"), {"action": "mark_all_read"})
    notif.refresh_from_db()
    assert notif.is_read is True


@pytest.mark.django_db
def test_settings_view_and_preferences(client, store_manager):
    """Manager can update notification preferences and view store configuration."""
    client.force_login(store_manager)

    resp = client.get(reverse("manager:settings"))
    assert resp.status_code == 200
    html = resp.content.decode()
    assert "SuperMarket – LB Nagar Hub" in html
    assert "Manager Profile" in html

    # Save preferences
    resp_pref = client.post(
        reverse("manager:settings"),
        {"action": "save_prefs", "pref_low_stock": "1", "pref_new_orders": "1"},
    )
    assert resp_pref.status_code == 302
    assert client.session.get("manager_notification_prefs") == {"low_stock": True, "new_orders": True}
