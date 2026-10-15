import pytest
from django.core import mail
from django.core.cache import cache
from django.urls import reverse

from apps.customer_auth.models import Customer
from apps.customer_auth import services


@pytest.fixture(autouse=True)
def clear_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.mark.django_db
def test_customer_model():
    cust = Customer.objects.create(
        phone="9876543210",
        email="customer@example.com",
        name="John Doe",
        default_address="123 Main St",
    )
    assert str(cust) == "Customer customer@example.com (9876543210)"
    assert cust.pk is not None


def test_otp_generation_and_hashing():
    otp1 = services.generate_otp()
    assert len(otp1) == 6
    assert otp1.isdigit()

    hash1 = services.hash_otp(otp1)
    hash2 = services.hash_otp(otp1)
    assert hash1 == hash2
    assert hash1 != otp1


def test_redis_otp_storage_and_verification():
    phone = "9876543210"
    email = "test@example.com"
    otp = "123456"

    # Store OTP
    services.store_otp_in_redis(phone, email, otp)

    # Wrong OTP fails
    is_valid, is_locked = services.verify_otp_in_redis(phone, email, "654321")
    assert not is_valid
    assert not is_locked

    # Correct OTP succeeds
    is_valid, is_locked = services.verify_otp_in_redis(phone, email, otp)
    assert is_valid
    assert not is_locked

    # Single-use: Second verification fails because OTP was deleted
    is_valid, is_locked = services.verify_otp_in_redis(phone, email, otp)
    assert not is_valid
    assert not is_locked


def test_otp_verification_lockout():
    """5 failed OTP verification attempts lock out and invalidate the OTP key."""
    phone = "9876543210"
    email = "lockout@example.com"
    otp = "123456"

    services.store_otp_in_redis(phone, email, otp)

    # 4 wrong attempts
    for _ in range(4):
        is_valid, is_locked = services.verify_otp_in_redis(phone, email, "000000")
        assert not is_valid
        assert not is_locked

    # 5th wrong attempt triggers lockout
    is_valid, is_locked = services.verify_otp_in_redis(phone, email, "000000")
    assert not is_valid
    assert is_locked

    # Subsequent attempt (even with correct code) is rejected because code was invalidated
    is_valid, is_locked = services.verify_otp_in_redis(phone, email, otp)
    assert not is_valid
    assert is_locked


def test_otp_rate_limiting():
    phone = "9876543210"
    email = "rate@example.com"

    for _ in range(3):
        is_allowed, _ = services.check_rate_limit(phone, email)
        assert is_allowed
        services.increment_rate_limit(phone, email)

    # 4th request exceeds rate limit
    is_allowed, remaining = services.check_rate_limit(phone, email)
    assert not is_allowed
    assert remaining == 0


@pytest.mark.django_db
def test_case_1_new_email_existing_customer_login_fails(client):
    """Case 1: New email -> 'Existing Customer Login' -> shows 'account not found' error, does NOT send OTP or create account."""
    login_url = reverse("customer_auth:login")
    mail.outbox.clear()

    res = client.post(login_url, {"action": "login", "email": "notfound@example.com"})
    assert res.status_code == 200
    content = res.content.decode("utf-8")
    assert "No account found with this email" in content
    assert len(mail.outbox) == 0
    assert not Customer.objects.filter(email="notfound@example.com").exists()


def wait_for_mail():
    import time
    for _ in range(30):
        if len(mail.outbox) > 0:
            return
        time.sleep(0.05)


@pytest.mark.django_db
def test_case_2_new_email_create_account_succeeds(client):
    """Case 2: New email -> 'New Customer — Create Account' -> OTP sends, verify creates account correctly."""
    signup_url = reverse("customer_auth:signup")
    mail.outbox.clear()

    post_data = {"action": "signup", "phone": "9876543210", "email": "newuser@example.com"}
    res = client.post(signup_url, post_data)
    assert res.status_code == 302
    assert res.url == reverse("customer_auth:verify_otp")

    wait_for_mail()
    # OTP email sent
    assert len(mail.outbox) == 1

    # Customer record NOT created before OTP verification
    assert not Customer.objects.filter(email="newuser@example.com").exists()

    # Extract OTP code from mail body
    mail_body = mail.outbox[0].body
    import re
    otp_code = re.search(r"(\d{6})", mail_body).group(1)

    # Verify OTP -> Customer created
    verify_url = reverse("customer_auth:verify_otp")
    res = client.post(verify_url, {"otp": otp_code})
    assert res.status_code == 302

    customer = Customer.objects.get(email="newuser@example.com")
    assert customer.phone == "9876543210"
    assert client.session.get("customer_id") == customer.pk


@pytest.mark.django_db
def test_case_3_existing_email_create_account_fails(client):
    """Case 3: Existing/verified email -> 'New Customer — Create Account' -> shows 'account already exists' error, does NOT create duplicate."""
    Customer.objects.create(phone="9876543210", email="existing@example.com", name="Bob")
    mail.outbox.clear()

    signup_url = reverse("customer_auth:signup")
    post_data = {"action": "signup", "phone": "9876543210", "email": "existing@example.com"}
    res = client.post(signup_url, post_data)
    assert res.status_code == 200
    assert "An account already exists with this email" in res.content.decode("utf-8")
    assert len(mail.outbox) == 0
    assert Customer.objects.filter(email="existing@example.com").count() == 1


@pytest.mark.django_db
def test_case_4_existing_email_existing_customer_login_succeeds(client):
    """Case 4: Existing/verified email -> 'Existing Customer — Login' -> OTP sends and logs them in correctly, no duplicate created."""
    existing_customer = Customer.objects.create(phone="5551234567", email="returning@example.com", name="Alice")
    mail.outbox.clear()

    login_url = reverse("customer_auth:login")
    res = client.post(login_url, {"action": "login", "email": "returning@example.com"})
    assert res.status_code == 302
    assert res.url == reverse("customer_auth:verify_otp")

    wait_for_mail()
    # OTP email sent
    assert len(mail.outbox) == 1

    # Extract OTP code from mail body
    mail_body = mail.outbox[0].body
    import re
    otp_code = re.search(r"(\d{6})", mail_body).group(1)

    # Verify OTP -> logged in as returning customer
    verify_url = reverse("customer_auth:verify_otp")
    res = client.post(verify_url, {"otp": otp_code})
    assert res.status_code == 302
    assert Customer.objects.filter(email="returning@example.com").count() == 1
    assert client.session.get("customer_id") == existing_customer.pk


@pytest.mark.django_db
def test_checkout_prefill_and_address_update(client):
    from decimal import Decimal
    from apps.menu.models import Category, MenuItem

    # Create category & menu item
    cat = Category.objects.create(name="Drinks", is_active=True)
    item = MenuItem.objects.create(category=cat, name="Coffee", price=Decimal("100"), is_available=True)

    # Create Customer
    customer = Customer.objects.create(
        phone="9876543210",
        email="prefill@example.com",
        name="Pre-filled Name",
        default_address="123 Saved Street",
    )

    # Add item to session cart & set logged in customer session
    session = client.session
    session["delv_cart"] = {str(item.pk): 2}
    session["customer_id"] = customer.pk
    session.save()

    # GET checkout page — verify form pre-filling
    checkout_url = reverse("orders_customer:checkout")
    res = client.get(checkout_url)
    assert res.status_code == 200
    assert res.context["form_data"]["contact_name"] == "Pre-filled Name"
    assert res.context["form_data"]["contact_phone"] == "9876543210"
    assert res.context["form_data"]["address"] == "123 Saved Street"

    # POST checkout with updated address
    post_data = {
        "contact_name": "Pre-filled Name",
        "contact_phone": "9876543210",
        "address": "456 New Delivery Address",
        "instructions": "Leave at front door",
    }
    res = client.post(checkout_url, post_data)
    assert res.status_code == 200

    # Refresh Customer and check updated default_address
    customer.refresh_from_db()
    assert customer.default_address == "456 New Delivery Address"


@pytest.mark.django_db
def test_unauthenticated_delivery_flow_redirects_to_login(client):
    from decimal import Decimal
    from apps.menu.models import Category, MenuItem

    cat = Category.objects.create(name="Food", is_active=True)
    item = MenuItem.objects.create(category=cat, name="Burger", price=Decimal("250"), is_available=True)

    # Unauthenticated GET menu renders public menu without login
    menu_url = reverse("orders_customer:menu")
    res = client.get(menu_url)
    assert res.status_code == 200

    # Add item to cart without logging in
    session = client.session
    session["delv_cart"] = {str(item.pk): 1}
    session.save()

    # Unauthenticated GET checkout redirects to login
    checkout_url = reverse("orders_customer:checkout")
    res = client.get(checkout_url)
    assert res.status_code == 302
    assert res.url == reverse("customer_auth:login")


@pytest.mark.django_db
def test_session_expiry_is_7_days(client):
    login_url = reverse("customer_auth:login")
    client.post(login_url, {"phone": "9876543210", "email": "expiry@example.com"})

    mail_body = mail.outbox[0].body
    import re
    otp_code = re.search(r"(\d{6})", mail_body).group(1)

    verify_url = reverse("customer_auth:verify_otp")
    client.post(verify_url, {"otp": otp_code})

    # Session expiry should be 7 days (604,800 seconds)
    expiry = client.session.get_expiry_age()
    assert expiry == 7 * 24 * 3600


