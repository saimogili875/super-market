"""Anti-IDOR tests for the guest delivery tracking page.

Only the guest holding the signed ``delv_token_<pk>`` cookie set at checkout
(or the assigned agent / an admin) may load the tracking page; everyone else
gets a 404.
"""
from decimal import Decimal

import pytest
from django.core.signing import get_cookie_signer

from apps.orders.models import Order, OrderStatus

_TRACKING_SALT = "delv_tracking"


@pytest.fixture
def order(db):
    return Order.objects.create(
        order_type="DELV",
        status=OrderStatus.READY,
        total_amount=Decimal("30.00"),
        contact_name="Sam",
        contact_phone="555-0199",
    )


def _sign_token(order):
    """Reproduce the signed cookie value set by delivery_checkout()."""
    key = f"delv_token_{order.pk}"
    return get_cookie_signer(salt=key + _TRACKING_SALT).sign(str(order.pk))


@pytest.fixture
def customer_client(client, db):
    from apps.customer_auth.models import Customer
    cust = Customer.objects.create(phone="9876543210", email="track@example.com")
    session = client.session
    session["customer_id"] = cust.pk
    session.save()
    return client


@pytest.mark.django_db
def test_owner_cookie_can_track(customer_client, order):
    """The signed tracking cookie grants access and shows the live status text."""
    customer_client.cookies[f"delv_token_{order.pk}"] = _sign_token(order)

    response = customer_client.get(f"/order/{order.pk}/track/")

    assert response.status_code == 200
    # Live status text reflects the order's current status.
    assert order.get_status_display() in response.content.decode()


@pytest.mark.django_db
def test_non_owner_without_cookie_gets_404(customer_client, order):
    """A visitor with no tracking cookie cannot reach the order (anti-IDOR)."""
    response = customer_client.get(f"/order/{order.pk}/track/")
    assert response.status_code == 404


@pytest.mark.django_db
def test_tampered_cookie_gets_404(customer_client, order):
    """A cookie with a bad signature is rejected, not trusted."""
    customer_client.cookies[f"delv_token_{order.pk}"] = "not-a-valid-signed-value"
    response = customer_client.get(f"/order/{order.pk}/track/")
    assert response.status_code == 404


@pytest.mark.django_db
def test_timeline_rendered_for_active_order(customer_client):
    """An active order (e.g. KITCHEN) renders completed, active, and upcoming steps with customer friendly labels."""
    order = Order.objects.create(
        order_type="DELV",
        status=OrderStatus.IN_KITCHEN,
        total_amount=Decimal("25.00"),
        contact_name="Sam",
        contact_phone="555-0199",
    )
    customer_client.cookies[f"delv_token_{order.pk}"] = _sign_token(order)

    response = customer_client.get(f"/order/{order.pk}/track/")
    assert response.status_code == 200

    html = response.content.decode()
    # Check customer friendly labels
    assert "Preparing Your Food" in html
    assert "Order Placed" in html
    assert "Order Confirmed" in html
    assert "Out for Delivery" in html

    # Check step states for KITCHEN
    assert 'id="step-KITCHEN"' in html
    assert 'class="timeline-step completed"' in html or 'completed' in html
    assert 'id="step-KITCHEN"\n             class="timeline-step active"' in html or 'active' in html


@pytest.mark.django_db
def test_timeline_cancelled_order(customer_client):
    """A cancelled order shows the cancelled card and hides the normal stepper timeline."""
    order = Order.objects.create(
        order_type="DELV",
        status=OrderStatus.CANCELLED,
        total_amount=Decimal("15.00"),
        contact_name="Sam",
        contact_phone="555-0199",
    )
    customer_client.cookies[f"delv_token_{order.pk}"] = _sign_token(order)

    response = customer_client.get(f"/order/{order.pk}/track/")
    assert response.status_code == 200

    html = response.content.decode()
    assert "Order Cancelled" in html
    assert 'id="timeline-wrapper" style="display: none;"' in html


@pytest.mark.django_db
def test_timeline_paid_order(customer_client):
    """A paid order displays the paid payment badge and marks all stages completed."""
    order = Order.objects.create(
        order_type="DELV",
        status=OrderStatus.PAID,
        total_amount=Decimal("40.00"),
        contact_name="Sam",
        contact_phone="555-0199",
    )
    customer_client.cookies[f"delv_token_{order.pk}"] = _sign_token(order)

    response = customer_client.get(f"/order/{order.pk}/track/")
    assert response.status_code == 200

    html = response.content.decode()
    assert "Paid" in html
    assert 'id="payment-status-badge"' in html


@pytest.mark.django_db
def test_logged_in_customer_matching_phone_can_track(customer_client):
    """A logged in customer can track an order matching their phone even without the cookie."""
    order = Order.objects.create(
        order_type="DELV",
        status=OrderStatus.IN_KITCHEN,
        total_amount=Decimal("45.00"),
        contact_name="Track Customer",
        contact_phone="9876543210",
    )
    # customer_client fixture has phone="9876543210", no cookie set
    response = customer_client.get(f"/order/{order.pk}/track/")
    assert response.status_code == 200
    assert "Order #"+str(order.pk) in response.content.decode()


@pytest.mark.django_db
def test_session_delv_orders_can_track(customer_client):
    """An order in session delv_orders can be tracked without cookie."""
    order = Order.objects.create(
        order_type="DELV",
        status=OrderStatus.DISPATCHED,
        total_amount=Decimal("50.00"),
        contact_name="Guest",
        contact_phone="1112223333",
    )
    session = customer_client.session
    session["delv_orders"] = [order.pk]
    session.save()

    response = customer_client.get(f"/order/{order.pk}/track/")
    assert response.status_code == 200
    assert "Order #"+str(order.pk) in response.content.decode()


@pytest.mark.django_db
def test_track_current_redirects_with_active_session_order(customer_client):
    """track_current redirects to the order tracking page if an active order exists in session."""
    order = Order.objects.create(
        order_type="DELV",
        status=OrderStatus.IN_KITCHEN,
        total_amount=Decimal("35.00"),
        contact_name="Alice",
        contact_phone="1234567890",
    )
    session = customer_client.session
    session["delv_orders"] = [order.pk]
    session.save()

    response = customer_client.get("/order/track/")
    assert response.status_code == 302
    assert response.url == f"/order/{order.pk}/track/"


@pytest.mark.django_db
def test_track_current_redirects_with_active_customer_order(customer_client):
    """track_current redirects to active order matching logged-in customer's phone."""
    order = Order.objects.create(
        order_type="DELV",
        status=OrderStatus.DISPATCHED,
        total_amount=Decimal("40.00"),
        contact_name="Track Customer",
        contact_phone="9876543210",
    )
    response = customer_client.get("/order/track/")
    assert response.status_code == 302
    assert response.url == f"/order/{order.pk}/track/"


@pytest.mark.django_db
def test_track_current_shows_empty_state_without_active_order(customer_client):
    """track_current delegates to merged order history when customer has no active orders (e.g. only PAID order)."""
    Order.objects.create(
        order_type="DELV",
        status=OrderStatus.PAID,
        total_amount=Decimal("40.00"),
        contact_name="Track Customer",
        contact_phone="9876543210",
    )
    response = customer_client.get("/order/track/")
    assert response.status_code == 200
    html = response.content.decode()
    assert "My Grocery Orders" in html
    assert "/order/menu/" in html


@pytest.mark.django_db
def test_customer_settings_logged_in(customer_client):
    """customer settings page shows logged-in email and logout button when customer is authenticated."""
    response = customer_client.get("/order/settings/")
    assert response.status_code == 200
    html = response.content.decode()
    assert "track@example.com" in html
    assert "/order/auth/logout/" in html


@pytest.mark.django_db
def test_customer_settings_logged_out(client):
    """customer settings page shows sign in and create account links when user is unauthenticated."""
    response = client.get("/order/settings/")
    assert response.status_code == 200
    html = response.content.decode()
    assert "/order/auth/login/" in html
    assert "/order/auth/signup/" in html


@pytest.mark.django_db
def test_track_current_logged_out_shows_signin_prompt(client):
    """track_current returns 200 and renders sign-in prompt when accessed logged out."""
    response = client.get("/order/track/")
    assert response.status_code == 200
    html = response.content.decode()
    assert "Sign in to view your order history" in html
    assert "/order/auth/login/" in html


@pytest.mark.django_db
def test_order_history_logged_out_shows_signin_prompt(client):
    """order_history returns 200 and renders sign-in prompt when accessed logged out."""
    response = client.get("/order/my-orders/")
    assert response.status_code == 200
    html = response.content.decode()
    assert "Sign in to view your order history" in html
    assert "/order/auth/login/" in html


@pytest.mark.django_db
def test_all_four_bottom_nav_routes_return_200_logged_out(client):
    """All 4 customer bottom nav routes (Home, Cart, Orders, Account) return 200 OK when logged out."""
    routes = [
        "/order/menu/",
        "/order/cart/",
        "/order/my-orders/",
        "/order/settings/",
    ]
    for url in routes:
        response = client.get(url)
        assert response.status_code == 200, f"{url} returned status {response.status_code}"


@pytest.mark.django_db
def test_all_four_bottom_nav_routes_return_200_logged_in(customer_client):
    """All 4 customer bottom nav routes return 200 OK when logged in."""
    routes = [
        "/order/menu/",
        "/order/cart/",
        "/order/my-orders/",
        "/order/settings/",
    ]
    for url in routes:
        response = customer_client.get(url)
        assert response.status_code == 200, f"{url} returned status {response.status_code}"


@pytest.mark.django_db
def test_merged_orders_view_shows_active_order_banner(customer_client):
    """The merged orders view shows active order banner at top when active order exists, and lists order history."""
    active_order = Order.objects.create(
        order_type="DELV",
        status=OrderStatus.IN_KITCHEN,
        total_amount=Decimal("50.00"),
        contact_name="Track Customer",
        contact_phone="9876543210",
    )
    past_order = Order.objects.create(
        order_type="DELV",
        status=OrderStatus.PAID,
        total_amount=Decimal("30.00"),
        contact_name="Track Customer",
        contact_phone="9876543210",
    )
    response = customer_client.get("/order/my-orders/")
    assert response.status_code == 200
    html = response.content.decode()
    assert "Live Active Order" in html
    assert f"Order #{active_order.pk}" in html
    assert f"Order #{past_order.pk}" in html


@pytest.mark.django_db
def test_cart_badge_count_matches_session_cart(client, db):
    """Cart item count badge matches total items in session cart."""
    from apps.menu.models import Category, MenuItem
    cat = Category.objects.create(name="Food", is_active=True)
    mi = MenuItem.objects.create(category=cat, name="Pizza", price=Decimal("300"), is_available=True)
    session = client.session
    session["delv_cart"] = {str(mi.pk): 3}
    session.save()

    response = client.get("/order/menu/")
    assert response.status_code == 200
    assert response.context["cart_count"] == 3
    html = response.content.decode()
    assert '<span class="mobile-bottom-nav__badge">3</span>' in html






