"""Tests for customer delivery ordering views."""
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.menu.models import Category, MenuItem
from apps.orders.models import Order, OrderStatus


@pytest.fixture
def category(db):
    """A simple active menu category."""
    return Category.objects.create(name="Mains", is_active=True)


@pytest.fixture
def burger(category):
    """A menu item with a 20% discount: price=100, effective=80."""
    return MenuItem.objects.create(
        category=category,
        name="Burger",
        price=Decimal("100.00"),
        offer_percent=20,
        is_available=True,
    )


@pytest.fixture
def customer_client(client, db):
    from apps.customer_auth.models import Customer
    cust = Customer.objects.create(phone="9876543210", email="test@example.com", name="Test Customer")
    session = client.session
    session["customer_id"] = cust.pk
    session.save()
    return client


@pytest.mark.django_db
def test_delivery_menu_view(customer_client, burger):
    """GET /order/menu/ renders the public delivery menu."""
    url = reverse("orders_customer:menu")
    response = customer_client.get(url)
    assert response.status_code == 200
    assert burger.name in response.content.decode("utf-8")


@pytest.mark.django_db
def test_delivery_menu_view_logged_out(client, burger):
    """GET /order/menu/ renders the public delivery menu for unauthenticated guests (no login required)."""
    url = reverse("orders_customer:menu")
    response = client.get(url)
    assert response.status_code == 200
    assert burger.name in response.content.decode("utf-8")


@pytest.mark.django_db
def test_cart_add_view_logged_out(client, burger):
    """POST /order/cart/add adds item to session cart for unauthenticated guests."""
    url = reverse("orders_customer:cart_add")
    response = client.post(url, {"menu_item_id": burger.pk, "quantity": 1})
    assert response.status_code == 200
    assert "1 item" in response.content.decode("utf-8")
    assert client.session["delv_cart"][str(burger.pk)] == 1



@pytest.mark.django_db
def test_cart_add_view(customer_client, burger):
    """POST /order/cart/add adds item to session cart and renders fragment."""
    url = reverse("orders_customer:cart_add")
    response = customer_client.post(url, {"menu_item_id": burger.pk, "quantity": 2})
    assert response.status_code == 200
    assert "2 items" in response.content.decode("utf-8")
    assert customer_client.session["delv_cart"][str(burger.pk)] == 2


@pytest.mark.django_db
def test_cart_update_decrement(customer_client, burger):
    """POST /order/cart/update with action='decrement' decreases item quantity."""
    session = customer_client.session
    session["delv_cart"] = {str(burger.pk): 2}
    session.save()

    url = reverse("orders_customer:cart_update")
    response = customer_client.post(url, {"menu_item_id": burger.pk, "action": "decrement"})
    assert response.status_code == 200
    assert customer_client.session["delv_cart"][str(burger.pk)] == 1
    assert "1 item" in response.content.decode("utf-8")


@pytest.mark.django_db
def test_cart_update_remove_item_to_zero(customer_client, burger):
    """POST /order/cart/update with action='remove' removes key from session cart."""
    session = customer_client.session
    session["delv_cart"] = {str(burger.pk): 2}
    session.save()

    url = reverse("orders_customer:cart_update")
    response = customer_client.post(url, {"menu_item_id": burger.pk, "action": "remove"})
    assert response.status_code == 200
    assert str(burger.pk) not in customer_client.session.get("delv_cart", {})
    assert response.content.decode("utf-8").strip() == ""


@pytest.mark.django_db
def test_cart_update_decrement_last_item_clears_cart(customer_client, burger):
    """POST /order/cart/update decrementing quantity of 1 removes item and empties cart."""
    session = customer_client.session
    session["delv_cart"] = {str(burger.pk): 1}
    session.save()

    url = reverse("orders_customer:cart_update")
    response = customer_client.post(url, {"menu_item_id": burger.pk, "action": "decrement"})
    assert response.status_code == 200
    assert str(burger.pk) not in customer_client.session.get("delv_cart", {})


@pytest.mark.django_db
def test_cart_update_explicit_quantity(customer_client, burger):
    """POST /order/cart/update with explicit quantity updates quantity in cart."""
    session = customer_client.session
    session["delv_cart"] = {str(burger.pk): 1}
    session.save()

    url = reverse("orders_customer:cart_update")
    response = customer_client.post(url, {"menu_item_id": burger.pk, "quantity": 4})
    assert response.status_code == 200
    assert customer_client.session["delv_cart"][str(burger.pk)] == 4


@pytest.mark.django_db
def test_cart_update_checkout_target_empty_redirects(customer_client, burger):
    """POST /order/cart/update from checkout targeting order summary redirects when cart becomes empty."""
    session = customer_client.session
    session["delv_cart"] = {str(burger.pk): 1}
    session.save()

    url = reverse("orders_customer:cart_update")
    response = customer_client.post(
        url,
        {"menu_item_id": burger.pk, "action": "remove"},
        HTTP_HX_REQUEST="true",
        HTTP_HX_TARGET="order-summary-container",
    )
    assert response.status_code == 302
    assert response["HX-Redirect"] == reverse("orders_customer:menu")



@pytest.mark.django_db
def test_checkout_get_redirects_when_empty(customer_client):
    """GET /order/checkout/ redirects to menu if cart is empty."""
    url = reverse("orders_customer:checkout")
    response = customer_client.get(url)
    assert response.status_code == 302
    assert response.url == reverse("orders_customer:menu")


@pytest.mark.django_db
def test_checkout_post_creates_order(customer_client, burger):
    """POST /order/checkout/ creates a COD delivery order and stores signed cookie."""
    session = customer_client.session
    session["delv_cart"] = {str(burger.pk): 1}
    session.save()

    url = reverse("orders_customer:checkout")
    payload = {
        "contact_name": "Alice Guest",
        "contact_phone": "555-0199",
        "address": "742 Evergreen Terrace",
        "instructions": "Leave on porch",
    }
    response = customer_client.post(url, payload)
    assert response.status_code == 200
    assert "Order Placed Successfully" in response.content.decode("utf-8")

    order = Order.objects.get(contact_name="Alice Guest")
    assert order.order_type == "DELV"
    assert order.total_amount == Decimal("80.00")
    assert order.maps_url == "https://www.google.com/maps/dir/?api=1&destination=742%20Evergreen%20Terrace"
    assert f"delv_token_{order.pk}" in response.cookies


@pytest.mark.django_db
def test_checkout_post_with_valid_lat_lng_creates_order(customer_client, burger):
    """checkout POST with valid lat/lng creates a DELV order with a coords-based maps_url."""
    session = customer_client.session
    session["delv_cart"] = {str(burger.pk): 1}
    session.save()

    url = reverse("orders_customer:checkout")
    payload = {
        "contact_name": "Bob GPS",
        "contact_phone": "555-0200",
        "lat": "17.4065",
        "lng": "78.4772",
        "address": "",
    }
    response = customer_client.post(url, payload)
    assert response.status_code == 200

    order = Order.objects.get(contact_name="Bob GPS")
    assert order.order_type == "DELV"
    assert order.maps_url == "https://www.google.com/maps/dir/?api=1&destination=17.4065,78.4772"


@pytest.mark.django_db
def test_checkout_post_missing_location_is_rejected(customer_client, burger):
    """checkout POST with NEITHER lat/lng NOR address is REJECTED (no order created)."""
    session = customer_client.session
    session["delv_cart"] = {str(burger.pk): 1}
    session.save()

    url = reverse("orders_customer:checkout")
    payload = {
        "contact_name": "No Location",
        "contact_phone": "555-0300",
        "address": "",
        "lat": "",
        "lng": "",
    }
    response = customer_client.post(url, payload)
    assert response.status_code == 400
    content = response.content.decode("utf-8")
    assert "A delivery location is required" in content
    assert Order.objects.filter(contact_name="No Location").count() == 0


@pytest.mark.django_db
def test_checkout_post_invalid_lat_lng_ignored_and_rejected_if_no_address(customer_client, burger):
    """invalid lat/lng (out of range/junk) is ignored; if no address either -> rejected."""
    session = customer_client.session
    session["delv_cart"] = {str(burger.pk): 1}
    session.save()

    url = reverse("orders_customer:checkout")
    payload = {
        "contact_name": "Junk Coords",
        "contact_phone": "555-0400",
        "lat": "999.9",
        "lng": "invalid_lng",
        "address": "",
    }
    response = customer_client.post(url, payload)
    assert response.status_code == 400
    content = response.content.decode("utf-8")
    assert "A delivery location is required" in content
    assert Order.objects.filter(contact_name="Junk Coords").count() == 0


@pytest.mark.django_db
def test_order_history_logged_out_renders_prompt(client):
    """Logged-out users hitting /order/my-orders/ directly receive status 200 with sign-in prompt."""
    url = reverse("orders_customer:my_orders")
    response = client.get(url)
    assert response.status_code == 200
    assert "Sign in to view your order history" in response.content.decode("utf-8")


@pytest.mark.django_db
def test_order_history_empty_state(customer_client):
    """Logged-in customer with zero orders -> empty state displays correctly."""
    url = reverse("orders_customer:my_orders")
    response = customer_client.get(url)
    assert response.status_code == 200
    content = response.content.decode("utf-8")
    assert "No orders yet — browse the menu to place your first order!" in content


@pytest.mark.django_db
def test_order_history_filters_all_completed_not_completed(customer_client, burger):
    """Logged-in customer with orders in different statuses -> All, Completed, and Not Completed filters return correct items."""
    from apps.orders.models import OrderItem, OrderStatus
    # Order 1: Completed / Paid
    order1 = Order.objects.create(
        order_type="DELV",
        status=OrderStatus.PAID,
        contact_name="Test Customer",
        contact_phone="9876543210",
        total_amount=Decimal("250.00"),
    )
    OrderItem.objects.create(
        order=order1,
        menu_item=burger,
        name_snap="Organic Apples",
        unit_price=Decimal("250.00"),
        quantity=1,
    )

    # Order 2: Not Completed / In Kitchen
    order2 = Order.objects.create(
        order_type="DELV",
        status=OrderStatus.IN_KITCHEN,
        contact_name="Test Customer",
        contact_phone="9876543210",
        total_amount=Decimal("180.00"),
    )
    OrderItem.objects.create(
        order=order2,
        menu_item=burger,
        name_snap="Paneer Butter Masala",
        unit_price=Decimal("180.00"),
        quantity=1,
    )

    url = reverse("orders_customer:my_orders")

    # Filter: All
    res_all = customer_client.get(f"{url}?status=all")
    assert res_all.status_code == 200
    content_all = res_all.content.decode("utf-8")
    assert f"Order #{order1.pk}" in content_all
    assert f"Order #{order2.pk}" in content_all

    # Filter: Completed
    res_completed = customer_client.get(f"{url}?status=completed")
    assert res_completed.status_code == 200
    content_completed = res_completed.content.decode("utf-8")
    assert f"Order #{order1.pk}" in content_completed
    assert f"Order #{order2.pk}" not in content_completed

    # Filter: Not Completed
    res_not_completed = customer_client.get(f"{url}?status=not_completed")
    assert res_not_completed.status_code == 200
    content_not_completed = res_not_completed.content.decode("utf-8")
    assert f"Order #{order1.pk}" not in content_not_completed
    assert f"Order #{order2.pk}" in content_not_completed


@pytest.mark.django_db
def test_order_history_phone_substring_isolation(client, burger):
    """Customer with phone 9876543210 should NOT match order for 987654321099."""
    from apps.customer_auth.models import Customer
    cust = Customer.objects.create(phone="9876543210", email="sub@example.com", name="Sub Customer")
    session = client.session
    session["customer_id"] = cust.pk
    session.save()

    # Order 1: exact match for customer's phone
    order_exact = Order.objects.create(
        order_type="DELV",
        status=OrderStatus.PLACED,
        contact_name="Exact Match",
        contact_phone="9876543210",
        total_amount=Decimal("10.00"),
    )

    # Order 2: phone containing customer's phone as prefix/substring, but different full number
    order_longer = Order.objects.create(
        order_type="DELV",
        status=OrderStatus.PLACED,
        contact_name="Longer Phone",
        contact_phone="987654321099",
        total_amount=Decimal("10.00"),
    )

    url = reverse("orders_customer:my_orders")
    res = client.get(url)
    assert res.status_code == 200
    content = res.content.decode("utf-8")

    assert f"Order #{order_exact.pk}" in content
    assert f"Order #{order_longer.pk}" not in content


@pytest.mark.django_db
def test_delivery_checkout_links_delivery_customer(customer_client, burger):
    """Placing a delivery order while logged in as a Customer sets order.delivery_customer."""
    from apps.customer_auth.models import Customer
    cust = Customer.objects.get(pk=customer_client.session["customer_id"])

    # Add item to cart
    cart_url = reverse("orders_customer:cart_add")
    customer_client.post(cart_url, {"menu_item_id": burger.pk, "quantity": 1})

    # Perform checkout
    checkout_url = reverse("orders_customer:checkout")
    res = customer_client.post(
        checkout_url,
        {
            "contact_name": "Test Customer",
            "contact_phone": "9876543210",
            "address": "123 Test Street",
        },
    )
    assert res.status_code == 200
    order = Order.objects.latest("id")
    assert order.delivery_customer == cust
    assert f"delv_token_{order.pk}" in res.cookies



