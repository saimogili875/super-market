"""Tests for FreshMart DMart-style supermarket storefront and srinri.in-style login flow."""
import pytest
from decimal import Decimal
from django.urls import reverse

from apps.accounts.models import Role, User, AgentProfile, StaffProfile
from apps.coupons.models import Coupon
from apps.customer_auth.models import Customer, CustomerAddress
from apps.menu.models import Category, MenuItem


@pytest.fixture
def freshmart_catalog(db):
    """Fixture providing FreshMart supermarket categories, products, and coupons."""
    cat_fruits = Category.objects.create(name="Fruits and Vegetables", tag="Fresh Daily Harvest", sort_order=1)
    cat_staples = Category.objects.create(name="Rice, Pulses and Grains", tag="Daily Pantry Staples", sort_order=2)
    cat_dairy = Category.objects.create(name="Dairy and Eggs", tag="Farm Fresh Dairy", sort_order=3)
    cat_house = Category.objects.create(name="Household Essentials", tag="Cleaning & Paper", sort_order=4)

    # Products with MRP (price) and discount offer_percent
    p1 = MenuItem.objects.create(
        name="Fresh Red Onions (Nashik Grade-A)",
        category=cat_fruits,
        price=Decimal("40.00"),  # MRP
        offer_percent=25,        # 25% off -> 30.00
        stock_quantity=100,
        unit="kg",
        sku="SKU-TEST-001",
        is_available=True,
    )
    p2 = MenuItem.objects.create(
        name="Royal Aged Basmati Rice (5kg Bag)",
        category=cat_staples,
        price=Decimal("599.00"), # MRP
        offer_percent=30,        # 30% off -> 419.30
        stock_quantity=80,
        unit="pack",
        sku="SKU-TEST-002",
        is_available=True,
    )
    p3 = MenuItem.objects.create(
        name="Pasteurized Full Cream Fresh Milk (1L)",
        category=cat_dairy,
        price=Decimal("70.00"),
        offer_percent=10,
        stock_quantity=60,
        unit="L",
        sku="SKU-TEST-003",
        is_available=True,
    )
    p4 = MenuItem.objects.create(
        name="Citrus Disinfectant Surface Cleaner (1L)",
        category=cat_house,
        price=Decimal("180.00"),
        offer_percent=30,
        stock_quantity=50,
        unit="L",
        sku="SKU-TEST-004",
        is_available=True,
    )

    from datetime import date, timedelta
    today = date.today()
    Coupon.objects.create(
        code="FRESH20",
        discount_type="Percentage",
        value=Decimal("20.00"),
        valid_from=today - timedelta(days=1),
        valid_to=today + timedelta(days=30),
        min_order=Decimal("499.00"),
        is_active=True,
    )

    return {
        "cat_fruits": cat_fruits,
        "cat_staples": cat_staples,
        "p1": p1,
        "p2": p2,
        "p3": p3,
        "p4": p4,
    }


@pytest.fixture
def freshmart_users(db):
    """Fixture providing demo accounts for all 4 roles."""
    admin = User.objects.create_superuser("admin", "admin@freshmart.com", "Admin1234!", role=Role.ADMIN)
    
    manager = User.objects.create_user("manager_ravi", "ravi@freshmart.com", "Pass1234!", role=Role.MANAGER, phone="9845012345")
    StaffProfile.objects.create(user=manager, department="Store Operations", employee_id="MGR-001")

    agent = User.objects.create_user("agent_kiran", "kiran@freshmart.com", "Pass1234!", role=Role.AGENT, phone="9876500001")
    AgentProfile.objects.create(user=agent, is_available=True, vehicle_number="TS 09 FM 4589")

    customer = User.objects.create_user("customer_sneha", "sneha@example.com", "Pass1234!", role=Role.CUSTOMER, phone="9876543210")
    cust_auth = Customer.objects.create(phone="9876543210", email="sneha@example.com", name="Sneha Sharma")
    CustomerAddress.objects.create(
        customer=cust_auth,
        title="Home",
        recipient_name="Sneha Sharma",
        phone="9876543210",
        address="Flat 402, Green Meadows, Jubilee Hills",
        city="Hyderabad",
        is_default=True,
    )

    return {
        "admin": admin,
        "manager": manager,
        "agent": agent,
        "customer": customer,
        "cust_auth": cust_auth,
    }


# =========================================================================
# 1. PUBLIC HOME PAGE TESTS (DMart-Style Layout)
# =========================================================================

@pytest.mark.django_db
def test_home_page_minimal_marketing_and_no_products(client, freshmart_catalog):
    """Home page must render clean minimal marketing page with zero products/prices/categories."""
    resp = client.get(reverse("home"))
    assert resp.status_code == 200
    html = resp.content.decode()

    # 1. Brand identity and tagline
    assert "FreshMart" in html
    assert "Fresh food. Everyday low prices." in html

    # 2. Header with dark-mode toggle and prominent Login button
    assert "themeToggleBtn" in html
    assert 'href="/login/"' in html

    # 3. Hero CTA buttons
    assert "Sign In to Shop" in html
    assert "Create Account" in html
    assert "/customer/auth/signup/" in html

    # 4. 3 Value points
    assert "Fresh" in html
    assert "Fast Delivery" in html or "Fast delivery" in html
    assert "Fair Prices" in html or "Fair prices" in html

    # 5. Support footer
    assert "support@freshmart.com" in html
    assert "+91 1800 266 2255" in html or "1800 266 2255" in html

    # 6. ZERO products, prices, categories, or cart exposed to logged-out visitors
    assert "dmart-card" not in html
    assert "add-to-cart" not in html
    assert "SKU-" not in html
    assert "Fresh Red Onions" not in html
    assert "Basmati Rice" not in html


# =========================================================================
# 1b. ROLE ISOLATION & ACCESS CONTROL TESTS (Step 1 & Step 6)
# =========================================================================

@pytest.mark.django_db
def test_unauthenticated_catalog_redirects_to_login(client):
    """Logged-out visitor requesting catalog routes must be redirected to /login/?next=..."""
    for path in ["/order/menu/", "/order/cart/", "/order/wishlist/"]:
        resp = client.get(path)
        assert resp.status_code == 302
        assert "/login/" in resp.url
        assert f"next={path}" in resp.url


@pytest.mark.django_db
def test_unauthenticated_htmx_catalog_returns_401_hx_redirect(client):
    """Logged-out HTMX request returns 401 with HX-Redirect header."""
    resp = client.get("/order/menu/", HTTP_HX_REQUEST="true")
    assert resp.status_code == 401
    assert "HX-Redirect" in resp.headers
    assert "/login/?next=/order/menu/" in resp.headers["HX-Redirect"]


@pytest.mark.django_db
def test_logged_in_customer_home_redirects_to_catalog(client, freshmart_users):
    """Authenticated customer hitting / is redirected straight to /order/menu/."""
    client.force_login(freshmart_users["customer"])
    resp = client.get("/")
    assert resp.status_code == 302
    assert resp.url == "/order/menu/"


@pytest.mark.django_db
def test_agent_visiting_catalog_redirects_to_agent_portal(client, freshmart_users):
    """Delivery agent visiting /order/menu/ is redirected to their /agent/ portal."""
    client.force_login(freshmart_users["agent"])
    resp = client.get("/order/menu/")
    assert resp.status_code == 302
    assert resp.url == "/agent/"


@pytest.mark.django_db
def test_customer_accessing_agent_portal_forbidden(client, freshmart_users):
    """Customer cannot access delivery agent portal routes."""
    client.force_login(freshmart_users["customer"])
    resp = client.get("/agent/")
    # Delivery agent decorator redirects non-agents or returns 403
    assert resp.status_code in (302, 403)
    if resp.status_code == 302:
        assert "/agent/" not in resp.url


@pytest.mark.django_db
def test_seed_demo_command_runs_idempotently(db):
    """python manage.py seed_demo executes without error."""
    from django.core.management import call_command
    call_command("seed_demo", skip_images=True)
    # Run second time to ensure idempotency
    call_command("seed_demo", skip_images=True)


# =========================================================================
# 2. DEDICATED FULL-PAGE LOGIN FLOW (srinri.in/login/ Match)
# =========================================================================

@pytest.mark.django_db
def test_login_page_split_layout_and_fields(client):
    """The /login/ page must be a separate full page matching srinri.in's layout."""
    # Test both /login/ and /accounts/login/
    for url in ["/login/", reverse("accounts:login")]:
        resp = client.get(url)
        assert resp.status_code == 200
        html = resp.content.decode()

        # Split layout panels
        assert "brand-hero-panel" in html
        assert "login-form-panel" in html

        # Left panel content
        assert "FreshMart" in html
        assert "Fresh food." in html
        assert "Everyday low prices." in html
        assert "Verified Products" in html or "5,000+" in html

        # Right panel login card
        assert "Welcome back" in html
        assert "Sign in to continue to your dashboard" in html
        assert "Username / Phone" in html
        assert "id_username" in html
        assert "id_password" in html
        assert "Security Check" in html
        assert "id_captcha" in html
        assert "btnRefreshCaptcha" in html
        assert "Try another captcha" in html
        assert "Remember me" in html
        assert "Forgot password?" in html
        assert "Sign In" in html

        # Crucial notice and support text
        assert "Please type your credentials manually. Autofill is not allowed." in html
        assert "NEED HELP" in html
        assert "New customer? <a" in html


@pytest.mark.django_db
def test_login_captcha_verification(client, freshmart_users):
    """Login requires valid security captcha verification."""
    # 1. GET sets captcha in session
    resp = client.get("/login/")
    assert resp.status_code == 200
    captcha_code = client.session.get("security_captcha")
    assert captcha_code is not None
    assert len(captcha_code) == 5

    # 2. POST with wrong captcha fails
    resp_wrong = client.post("/login/", {
        "username": "customer_sneha",
        "password": "Pass1234!",
        "captcha": "WRONG",
    })
    assert resp_wrong.status_code == 200
    assert "Incorrect security check code" in resp_wrong.content.decode()

    # 3. POST with correct captcha succeeds
    valid_captcha = client.session.get("security_captcha")
    resp_valid = client.post("/login/", {
        "username": "customer_sneha",
        "password": "Pass1234!",
        "captcha": valid_captcha,
    })
    assert resp_valid.status_code == 302
    assert resp_valid.url == "/order/menu/"


@pytest.mark.django_db
def test_login_phone_number_authentication(client, freshmart_users):
    """Users can sign in using their 10-digit mobile number."""
    client.get("/login/")
    captcha_code = client.session.get("security_captcha")

    resp = client.post("/login/", {
        "username": "9876543210",  # Sneha's phone number
        "password": "Pass1234!",
        "captcha": captcha_code,
    })
    assert resp.status_code == 302
    assert resp.url == "/order/menu/"


# =========================================================================
# 3. ROLE-BASED POST-LOGIN REDIRECT MATRIX
# =========================================================================

@pytest.mark.django_db
@pytest.mark.parametrize("username,password,expected_url_substring", [
    ("customer_sneha", "Pass1234!", "/order/menu/"),
    ("agent_kiran", "Pass1234!", "/agent/"),
    ("manager_ravi", "Pass1234!", "/manager/"),
    ("admin", "Admin1234!", "/orders/dashboard/"),
])
def test_login_role_redirect_matrix(client, freshmart_users, username, password, expected_url_substring):
    """Each role must be redirected to its specific operational dashboard."""
    client.get("/login/")
    captcha_code = client.session.get("security_captcha")

    resp = client.post("/login/", {
        "username": username,
        "password": password,
        "captcha": captcha_code,
    })
    assert resp.status_code == 302
    assert expected_url_substring in resp.url


@pytest.mark.django_db
def test_authenticated_user_visiting_login_redirects(client, freshmart_users):
    """Logged in users visiting /login/ are redirected to their dashboard."""
    client.force_login(freshmart_users["customer"])
    resp = client.get("/login/")
    assert resp.status_code == 302
    assert resp.url == "/order/menu/"


# =========================================================================
# 4. CUSTOMER SHOPPING & CART FLOW
# =========================================================================

@pytest.mark.django_db
def test_customer_cart_and_coupon_flow(client, freshmart_catalog, freshmart_users):
    """Verify customer can add items, apply FRESH20 coupon, and view cart."""
    client.force_login(freshmart_users["customer"])
    p2 = freshmart_catalog["p2"]  # Basmati Rice MRP 599 -> discounted to ~419.30

    # 1. Add item to cart
    resp_add = client.post(reverse("orders_customer:cart_add"), {
        "menu_item_id": p2.pk,
        "quantity": 2,
    })
    assert resp_add.status_code == 200

    # 2. View cart
    resp_cart = client.get(reverse("orders_customer:cart"))
    assert resp_cart.status_code == 200
    assert p2.name in resp_cart.content.decode()

    # 3. Apply coupon FRESH20
    resp_coupon = client.post(reverse("orders_customer:cart_apply_coupon"), {
        "code": "FRESH20",
    })
    assert resp_coupon.status_code == 302

    # Verify coupon discount is applied
    resp_cart_after = client.get(reverse("orders_customer:cart"))
    assert "FRESH20" in resp_cart_after.content.decode()


@pytest.mark.django_db
def test_customer_checkout_renders_address(client, freshmart_catalog, freshmart_users):
    """Authenticated customer checkout displays delivery address and slots."""
    client.force_login(freshmart_users["customer"])
    p1 = freshmart_catalog["p1"]
    client.post(reverse("orders_customer:cart_add"), {"menu_item_id": p1.pk, "quantity": 1})

    resp = client.get(reverse("orders_customer:checkout"))
    assert resp.status_code == 200
    html = resp.content.decode()
    assert "Jubilee Hills" in html
    assert "Payment Method" in html or "Cash on Delivery" in html
