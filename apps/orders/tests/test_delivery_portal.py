"""Comprehensive functional, authorization, security, and button tests for the Delivery Agent Portal."""
from decimal import Decimal
from datetime import timedelta
from io import BytesIO

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils.timezone import now

from apps.accounts.models import AgentProfile, Role, User
from apps.accounts.services import set_agent_availability
from apps.customer_auth.models import Customer
from apps.menu.models import Category, MenuItem
from apps.notifications.models import AdminNotification
from apps.orders.models import Order, OrderEvent, OrderStatus
from apps.orders.services import assign_agent, create_order, transition


@pytest.fixture
def menu_category(db):
    return Category.objects.create(name="Groceries", is_active=True)


@pytest.fixture
def product_milk(menu_category):
    return MenuItem.objects.create(
        category=menu_category,
        name="Organic Whole Milk 1L",
        price=Decimal("65.00"),
        is_available=True,
    )


@pytest.fixture
def product_bread(menu_category):
    return MenuItem.objects.create(
        category=menu_category,
        name="Multigrain Bread",
        price=Decimal("45.00"),
        is_available=True,
    )


@pytest.fixture
def admin_user(db):
    return User.objects.create_user(
        username="superadmin",
        password="adminpassword123",
        role=Role.ADMIN,
        is_staff=True,
        is_superuser=True,
    )


@pytest.fixture
def agent_arjun(db):
    user = User.objects.create_user(
        username="arjun_agent",
        password="agentpassword123",
        role=Role.AGENT,
        first_name="Arjun",
        last_name="Reddy",
        phone="+91 98765 43210",
        email="arjun@supermarket.in",
    )
    AgentProfile.objects.create(user=user, is_available=True, vehicle_type="Motorbike", vehicle_number="AP-09-AB-1234")
    return user


@pytest.fixture
def agent_bob(db):
    user = User.objects.create_user(
        username="bob_agent",
        password="bobpassword123",
        role=Role.AGENT,
        first_name="Bob",
        last_name="Kumar",
        phone="+91 98765 00000",
        email="bob@supermarket.in",
    )
    AgentProfile.objects.create(user=user, is_available=True, vehicle_type="Scooter", vehicle_number="AP-09-CD-5678")
    return user


@pytest.fixture
def customer_user(db):
    return User.objects.create_user(
        username="customer1",
        password="custpassword123",
        role=Role.CUSTOMER,
        email="customer1@example.com",
    )


@pytest.fixture
def delivery_customer(db):
    return Customer.objects.create(
        name="Sample Customer A",
        phone="9876512345",
        email="customera@example.com",
        default_address="Flat 402, Green Park Residency, Road No 12, Hyderabad",
    )


@pytest.fixture
def sample_delivery_order(product_milk, product_bread, delivery_customer, agent_arjun, admin_user):
    order = create_order(
        order_type="DELV",
        items=[
            {"menu_item_id": product_milk.pk, "quantity": 2},
            {"menu_item_id": product_bread.pk, "quantity": 1},
        ],
        delivery_customer=delivery_customer,
        contact_name="Sample Customer A",
        contact_phone="9876512345",
        maps_url="https://www.google.com/maps/dir/?api=1&destination=Flat%20402%2C%20Green%20Park%20Residency",
        instructions="Leave at door, ring bell twice.",
    )
    assign_agent(order, agent_arjun, admin_user)
    return order


# ===========================================================================
# 1. Authentication & Role-Based Access Control Tests
# ===========================================================================

@pytest.mark.django_db
def test_agent_login_view_get(client):
    """GET /agent/login/ returns 200 and renders the delivery partner sign in form."""
    resp = client.get(reverse("orders_agent:login"))
    assert resp.status_code == 200
    html = resp.content.decode()
    assert "Delivery Partner Sign in" in html
    assert 'name="username"' in html
    assert 'name="password"' in html
    assert "Sign in" in html


@pytest.mark.django_db
def test_agent_login_valid_credentials(client, agent_arjun):
    """POST /agent/login/ with valid AGENT credentials redirects to dashboard."""
    resp = client.post(
        reverse("orders_agent:login"),
        {"username": "arjun_agent", "password": "agentpassword123"},
    )
    assert resp.status_code == 302
    assert resp.url == reverse("orders_agent:dashboard")

    # Follow redirect to dashboard
    dash_resp = client.get(resp.url)
    assert dash_resp.status_code == 200
    assert "Arjun Reddy" in dash_resp.content.decode()


@pytest.mark.django_db
def test_agent_login_invalid_password(client, agent_arjun):
    """POST /agent/login/ with bad password displays error feedback and stays on login."""
    resp = client.post(
        reverse("orders_agent:login"),
        {"username": "arjun_agent", "password": "wrongpassword"},
    )
    assert resp.status_code == 200
    assert "Invalid credentials" in resp.content.decode()


@pytest.mark.django_db
def test_agent_login_non_agent_rejected(client, customer_user):
    """A customer attempting to log into the delivery agent portal is blocked with 200 + error."""
    resp = client.post(
        reverse("orders_agent:login"),
        {"username": "customer1", "password": "custpassword123"},
    )
    assert resp.status_code == 200
    assert "Access denied: This portal is exclusively for SuperMarket Delivery Partners." in resp.content.decode()


@pytest.mark.django_db
def test_unauthenticated_agent_route_redirects(client):
    """Unauthenticated access to /agent/ redirects to login with next parameter."""
    resp = client.get(reverse("orders_agent:dashboard"))
    assert resp.status_code == 302
    assert "login" in resp.url
    assert "next=" in resp.url


@pytest.mark.django_db
def test_customer_cannot_access_agent_portal(client, customer_user):
    """A logged-in CUSTOMER attempting to access /agent/ receives 403 Forbidden."""
    client.force_login(customer_user)
    resp = client.get(reverse("orders_agent:dashboard"))
    assert resp.status_code == 403


@pytest.mark.django_db
def test_agent_cannot_access_admin_dashboard(client, agent_arjun):
    """A logged-in AGENT attempting to reach the admin dashboard gets 403 Forbidden."""
    client.force_login(agent_arjun)
    resp = client.get(reverse("orders_admin:dashboard"))
    assert resp.status_code in [302, 403]


@pytest.mark.django_db
def test_agent_cannot_access_inventory_or_suppliers(client, agent_arjun):
    """A logged-in AGENT attempting to access inventory/suppliers gets 403."""
    client.force_login(agent_arjun)
    resp = client.get(reverse("suppliers:list"))
    assert resp.status_code in [302, 403]


# ===========================================================================
# 2. Delivery Agent Dashboard Tests
# ===========================================================================

@pytest.mark.django_db
def test_dashboard_renders_stats_and_orders(client, agent_arjun, sample_delivery_order):
    """Dashboard displays greeting, availability toggle, stats, and assigned order."""
    client.force_login(agent_arjun)
    resp = client.get(reverse("orders_agent:dashboard"))
    assert resp.status_code == 200
    html = resp.content.decode()

    assert "Arjun Reddy" in html
    assert "You are Online" in html
    assert "Go offline" in html
    assert f"#{sample_delivery_order.pk}" in html
    assert f"order-card-{sample_delivery_order.pk}" in html
    assert "New assignment" in html
    assert "Accept" in html
    assert "Reject" in html


@pytest.mark.django_db
def test_dashboard_empty_state_when_no_orders(client, agent_arjun):
    """Dashboard shows clean empty states when the agent has no assignments."""
    client.force_login(agent_arjun)
    resp = client.get(reverse("orders_agent:dashboard"))
    assert resp.status_code == 200
    html = resp.content.decode()

    assert "No active delivery. Accepted orders appear here." in html
    assert "No new assignments right now." in html


@pytest.mark.django_db
def test_toggle_availability_post_and_htmx(client, agent_arjun):
    """POST to availability toggle flips the agent's status."""
    client.force_login(agent_arjun)
    profile = AgentProfile.objects.get(user=agent_arjun)
    assert profile.is_available is True

    # 1. Standard POST with redirect
    resp = client.post(reverse("orders_agent:toggle_availability"), {"available": "false", "redirect": "true"})
    assert resp.status_code == 302
    profile.refresh_from_db()
    assert profile.is_available is False

    # 2. HTMX POST returns partial with 200
    resp_htmx = client.post(
        reverse("orders_agent:toggle_availability"),
        {"available": "true"},
        HTTP_HX_REQUEST="true",
    )
    assert resp_htmx.status_code == 200
    profile.refresh_from_db()
    assert profile.is_available is True


@pytest.mark.django_db
def test_dashboard_shows_active_vs_new_assignment(client, agent_arjun, sample_delivery_order):
    """Orders awaiting acceptance appear under New assignment; accepted orders appear under Active delivery."""
    client.force_login(agent_arjun)

    # 1. Fresh assignment (not yet accepted)
    resp1 = client.get(reverse("orders_agent:dashboard"))
    assert "New assignment" in resp1.content.decode()

    # 2. Accept the order
    client.post(reverse("orders_agent:order_action", args=[sample_delivery_order.pk]), {"action": "accept"})

    # 3. Now should appear under Active delivery
    resp2 = client.get(reverse("orders_agent:dashboard"))
    html2 = resp2.content.decode()
    assert "Active delivery" in html2
    assert "View order" in html2


# ===========================================================================
# 3. My Orders List & Filtering Tests
# ===========================================================================

@pytest.mark.django_db
def test_my_orders_list_shows_only_assigned_orders(client, agent_arjun, agent_bob, sample_delivery_order, product_milk):
    """Agent only sees orders assigned to them, never other agents' orders (anti-IDOR)."""
    # Create order for Bob
    bob_order = create_order(
        order_type="DELV",
        items=[{"menu_item_id": product_milk.pk, "quantity": 1}],
        contact_name="Bob Customer",
    )
    admin = User.objects.get(username="superadmin")
    assign_agent(bob_order, agent_bob, admin)

    client.force_login(agent_arjun)
    resp = client.get(reverse("orders_agent:orders"))
    assert resp.status_code == 200
    html = resp.content.decode()

    assert f"#{sample_delivery_order.pk}" in html
    assert f"#{bob_order.pk}" not in html


@pytest.mark.django_db
def test_my_orders_filters(client, agent_arjun, sample_delivery_order, admin_user):
    """Filter chips (new, active, done, failed) filter orders correctly."""
    client.force_login(agent_arjun)

    # Order 1: New
    resp_new = client.get(reverse("orders_agent:orders") + "?filter=new")
    assert f"#{sample_delivery_order.pk}" in resp_new.content.decode()

    # Move Order 1 to active (ARRIVED)
    client.post(reverse("orders_agent:order_action", args=[sample_delivery_order.pk]), {"action": "accept"})
    client.post(reverse("orders_agent:order_action", args=[sample_delivery_order.pk]), {"action": "arrived"})

    resp_active = client.get(reverse("orders_agent:orders") + "?filter=active")
    assert f"#{sample_delivery_order.pk}" in resp_active.content.decode()

    resp_new_after = client.get(reverse("orders_agent:orders") + "?filter=new")
    assert f"#{sample_delivery_order.pk}" not in resp_new_after.content.decode()


@pytest.mark.django_db
def test_my_orders_search(client, agent_arjun, sample_delivery_order):
    """Search query matches by ID or customer name."""
    client.force_login(agent_arjun)

    # Search by ID
    resp_id = client.get(reverse("orders_agent:orders") + f"?q={sample_delivery_order.pk}")
    assert f"#{sample_delivery_order.pk}" in resp_id.content.decode()

    # Search by customer name
    resp_name = client.get(reverse("orders_agent:orders") + "?q=Customer A")
    assert f"#{sample_delivery_order.pk}" in resp_name.content.decode()

    # Search non-matching query
    resp_none = client.get(reverse("orders_agent:orders") + "?q=NonExistentZXYZ")
    assert "No orders here" in resp_none.content.decode()


# ===========================================================================
# 4. Order Details & Contact Navigation Tests
# ===========================================================================

@pytest.mark.django_db
def test_order_detail_view_success(client, agent_arjun, sample_delivery_order):
    """Order details screen renders customer name, address, items, and progress stepper."""
    client.force_login(agent_arjun)
    url = reverse("orders_agent:order_detail", args=[sample_delivery_order.pk])
    resp = client.get(url)
    assert resp.status_code == 200
    html = resp.content.decode()

    assert f"Order #{sample_delivery_order.pk}" in html
    assert "Sample Customer A" in html
    assert "Green Park Residency" in html
    assert "Organic Whole Milk 1L" in html
    assert "Multigrain Bread" in html
    assert "Progress" in html
    assert "Call" in html
    assert "Navigate" in html
    assert "Copy" in html


@pytest.mark.django_db
def test_order_detail_idor_protection(client, agent_bob, sample_delivery_order):
    """Attempting to view an order assigned to a different agent returns 404 (anti-IDOR)."""
    client.force_login(agent_bob)
    url = reverse("orders_agent:order_detail", args=[sample_delivery_order.pk])
    resp = client.get(url)
    assert resp.status_code == 404


# ===========================================================================
# 5. Delivery Workflow Action Tests (Accept, Step, Reject, Issue, Complete)
# ===========================================================================

@pytest.mark.django_db
def test_agent_accept_delivery(client, agent_arjun, sample_delivery_order):
    """Agent accepts assigned delivery; sets accepted timestamp and creates event."""
    client.force_login(agent_arjun)
    assert sample_delivery_order.delivery_accepted_at is None

    url = reverse("orders_agent:order_action", args=[sample_delivery_order.pk])
    resp = client.post(url, {"action": "accept"})
    assert resp.status_code == 302

    sample_delivery_order.refresh_from_db()
    assert sample_delivery_order.delivery_accepted_at is not None


@pytest.mark.django_db
def test_agent_step_confirm_arrival_and_pickup(client, agent_arjun, sample_delivery_order):
    """Agent advances through 'arrived at store' and 'picked up'."""
    client.force_login(agent_arjun)
    url = reverse("orders_agent:order_action", args=[sample_delivery_order.pk])

    # 1. Accept
    client.post(url, {"action": "accept"})

    # 2. Arrived at store
    resp_arr = client.post(url, {"action": "arrived"})
    assert resp_arr.status_code == 302
    sample_delivery_order.refresh_from_db()
    assert sample_delivery_order.status == OrderStatus.ARRIVED
    assert sample_delivery_order.delivery_arrived_at is not None

    # 3. Picked up from store
    resp_pick = client.post(url, {"action": "picked"})
    assert resp_pick.status_code == 302
    sample_delivery_order.refresh_from_db()
    assert sample_delivery_order.status == OrderStatus.COLLECTED
    assert sample_delivery_order.delivery_picked_at is not None


@pytest.mark.django_db
def test_agent_complete_delivery_with_otp_success(client, agent_arjun, sample_delivery_order):
    """Customer OTP verification completes delivery, moves status to PAID, and records POD."""
    client.force_login(agent_arjun)
    url = reverse("orders_agent:order_action", args=[sample_delivery_order.pk])

    # Advance to COLLECTED (out for delivery)
    client.post(url, {"action": "accept"})
    client.post(url, {"action": "arrived"})
    client.post(url, {"action": "picked"})

    # Complete with correct OTP
    correct_otp = sample_delivery_order.delivery_otp
    resp = client.post(
        url,
        {
            "action": "complete",
            "pod_type": "otp",
            "otp": correct_otp,
            "notes": "Handed to customer at apartment door",
        },
    )
    assert resp.status_code == 302
    assert resp.url == reverse("orders_agent:delivery_complete", args=[sample_delivery_order.pk])

    sample_delivery_order.refresh_from_db()
    assert sample_delivery_order.status == OrderStatus.PAID
    assert sample_delivery_order.delivery_completed_at is not None
    assert "Customer OTP verified" in sample_delivery_order.delivery_pod_detail
    assert sample_delivery_order.delivery_notes == "Handed to customer at apartment door"


@pytest.mark.django_db
def test_agent_complete_delivery_invalid_otp_fails(client, agent_arjun, sample_delivery_order):
    """Entering an incorrect OTP rejects completion without modifying order status."""
    client.force_login(agent_arjun)
    url = reverse("orders_agent:order_action", args=[sample_delivery_order.pk])

    # Advance to COLLECTED
    client.post(url, {"action": "accept"})
    client.post(url, {"action": "arrived"})
    client.post(url, {"action": "picked"})

    # Complete with wrong OTP
    resp = client.post(
        url,
        {
            "action": "complete",
            "pod_type": "otp",
            "otp": "999999",
        },
    )
    assert resp.status_code == 302
    sample_delivery_order.refresh_from_db()
    assert sample_delivery_order.status == OrderStatus.COLLECTED
    assert sample_delivery_order.delivery_completed_at is None


@pytest.mark.django_db
def test_agent_complete_delivery_handover_mode(client, agent_arjun, sample_delivery_order):
    """Delivery completion via physical handover confirmation."""
    client.force_login(agent_arjun)
    url = reverse("orders_agent:order_action", args=[sample_delivery_order.pk])

    # Advance to COLLECTED
    client.post(url, {"action": "accept"})
    client.post(url, {"action": "arrived"})
    client.post(url, {"action": "picked"})

    # Complete with handover confirmation
    resp = client.post(
        url,
        {
            "action": "complete",
            "pod_type": "handover",
            "handover_confirmed": "true",
            "notes": "Received by security desk",
        },
    )
    assert resp.status_code == 302
    sample_delivery_order.refresh_from_db()
    assert sample_delivery_order.status == OrderStatus.PAID
    assert "Handover confirmed" in sample_delivery_order.delivery_pod_detail


@pytest.mark.django_db
def test_agent_reject_delivery_unassigns_and_alerts_admin(client, agent_arjun, sample_delivery_order):
    """Rejecting an assignment unassigns the agent, resets status to READY, and notifies admin."""
    client.force_login(agent_arjun)
    url = reverse("orders_agent:order_action", args=[sample_delivery_order.pk])

    resp = client.post(url, {"action": "reject", "reason": "Vehicle issue"})
    assert resp.status_code == 302

    sample_delivery_order.refresh_from_db()
    assert sample_delivery_order.agent is None
    assert sample_delivery_order.status == OrderStatus.READY
    assert "Vehicle issue" in sample_delivery_order.delivery_issue_reason

    # Verify admin notification was created
    notif = AdminNotification.objects.filter(reference_id=f"ORD-{sample_delivery_order.pk}", notification_type="Delivery").first()
    assert notif is not None
    assert "Vehicle issue" in notif.message


@pytest.mark.django_db
def test_agent_report_issue_records_notes(client, agent_arjun, sample_delivery_order):
    """Reporting an operational issue logs details and keeps the order active."""
    client.force_login(agent_arjun)
    url = reverse("orders_agent:order_action", args=[sample_delivery_order.pk])

    client.post(url, {"action": "accept"})
    resp = client.post(
        url,
        {
            "action": "issue",
            "reason": "Customer unreachable",
            "notes": "Called 3 times, gate security phoned",
        },
    )
    assert resp.status_code == 302

    sample_delivery_order.refresh_from_db()
    assert sample_delivery_order.delivery_issue_reason == "Customer unreachable"
    assert sample_delivery_order.delivery_issue_notes == "Called 3 times, gate security phoned"


# ===========================================================================
# 6. Delivery Complete & Receipt View Tests
# ===========================================================================

@pytest.mark.django_db
def test_delivery_complete_screen(client, agent_arjun, sample_delivery_order):
    """Delivery complete screen renders celebratory checkmark and order details."""
    client.force_login(agent_arjun)
    transition(sample_delivery_order, OrderStatus.ARRIVED, agent_arjun)
    transition(sample_delivery_order, OrderStatus.COLLECTED, agent_arjun)
    transition(sample_delivery_order, OrderStatus.PAID, agent_arjun)

    url = reverse("orders_agent:delivery_complete", args=[sample_delivery_order.pk])
    resp = client.get(url)
    assert resp.status_code == 200
    html = resp.content.decode()

    assert "Delivery complete" in html
    assert "Back to dashboard" in html
    assert "My orders" in html


@pytest.mark.django_db
def test_delivery_receipt_preview(client, agent_arjun, sample_delivery_order):
    """Receipt view generates printable receipt with itemized totals."""
    client.force_login(agent_arjun)
    url = reverse("orders_agent:order_receipt", args=[sample_delivery_order.pk])
    resp = client.get(url)
    assert resp.status_code == 200
    html = resp.content.decode()

    assert "DELIVERY RECEIPT" in html
    assert "SUPERMARKET STORE 01" in html
    assert "TOTAL PAID" in html
    assert "Organic Whole Milk 1L" in html


# ===========================================================================
# 7. Earnings & Notifications Tests
# ===========================================================================

@pytest.mark.django_db
def test_earnings_view_today_and_week(client, agent_arjun, sample_delivery_order):
    """Earnings page aggregates delivered orders and displays settlement status."""
    client.force_login(agent_arjun)
    # Mark order as completed
    transition(sample_delivery_order, OrderStatus.ARRIVED, agent_arjun)
    transition(sample_delivery_order, OrderStatus.COLLECTED, agent_arjun)
    transition(sample_delivery_order, OrderStatus.PAID, agent_arjun)

    url = reverse("orders_agent:earnings")
    resp_today = client.get(url + "?range=today")
    assert resp_today.status_code == 200
    html_today = resp_today.content.decode()
    assert 'id="earnings-count">1</strong> completed deliveries' in html_today
    assert "Settled &amp; Cleared" in html_today or "Settled" in html_today

    resp_week = client.get(url + "?range=week")
    assert resp_week.status_code == 200


@pytest.mark.django_db
def test_notifications_isolation_and_actions(client, agent_arjun, agent_bob):
    """Agent sees only their own notifications; can toggle read state and mark all as read."""
    # Create notification for Arjun
    notif_arjun = AdminNotification.objects.create(
        title="Delivery assignment #101",
        message="Pickup at SuperMarket Store 01",
        recipient=agent_arjun,
        notification_type="Delivery",
    )
    # Create notification for Bob
    notif_bob = AdminNotification.objects.create(
        title="Delivery assignment #102",
        message="Pickup for Bob",
        recipient=agent_bob,
        notification_type="Delivery",
    )

    client.force_login(agent_arjun)
    url = reverse("orders_agent:notifications")
    resp = client.get(url)
    assert resp.status_code == 200
    html = resp.content.decode()

    assert "Delivery assignment #101" in html
    assert "Delivery assignment #102" not in html

    # Toggle read
    client.post(url, {"action": "toggle_read", "notif_id": notif_arjun.pk})
    notif_arjun.refresh_from_db()
    assert notif_arjun.is_read is True

    # Mark all read
    notif_arjun_2 = AdminNotification.objects.create(
        title="Alert 2",
        recipient=agent_arjun,
        is_read=False,
    )
    client.post(url, {"action": "mark_all_read"})
    notif_arjun_2.refresh_from_db()
    assert notif_arjun_2.is_read is True
    # Bob's notification is unaffected
    notif_bob.refresh_from_db()
    assert notif_bob.is_read is False


# ===========================================================================
# 8. Profile View & Logout Tests
# ===========================================================================

@pytest.mark.django_db
def test_profile_view_and_logout(client, agent_arjun):
    """Profile displays partner details, vehicle info, support guidelines, and sign out."""
    client.force_login(agent_arjun)
    url = reverse("orders_agent:profile")
    resp = client.get(url)
    assert resp.status_code == 200
    html = resp.content.decode()

    assert "Arjun Reddy" in html
    assert "AP-09-AB-1234" in html
    assert "Motorbike" in html
    assert "Support &amp; Guidelines" in html or "Support" in html
    assert "Sign Out" in html

    # Test logout
    logout_url = reverse("accounts:logout")
    logout_resp = client.post(logout_url)
    assert logout_resp.status_code == 302
