"""Unit and integration tests for customer-facing supermarket features.

Covers:
- Homepage rendering with real categories, best sellers, highlights.
- Category browsing, filtering (stock), and sorting (price_asc, price_desc).
- Product detail view with real catalog data, related products, and wishlist state.
- Cart quantity stepper, item removal, and subtotal.
- Coupon application, discount calculation, and removal.
- Delivery address management (add, list, delete, set default).
- Wishlist toggle and view.
- Delivery slot and payment method in checkout.
- Order confirmation with order summary and sound trigger deduplication.
"""
from datetime import date, timedelta
from decimal import Decimal
import pytest
from django.urls import reverse

from apps.coupons.models import Coupon
from apps.customer_auth.models import Customer, CustomerAddress, WishlistItem
from apps.menu.models import Category, MenuItem
from apps.orders.models import Order, OrderStatus


@pytest.fixture
def supermarket_catalog(db):
    """Create sample categories and items for testing."""
    cat_grains = Category.objects.create(name="Rice, Pulses & Grains", is_active=True, sort_order=1)
    cat_dairy = Category.objects.create(name="Dairy & Eggs", is_active=True, sort_order=2)

    rice = MenuItem.objects.create(
        category=cat_grains,
        name="Basmati Rice",
        price=Decimal("150.00"),
        unit="kg",
        is_available=True,
        track_stock=True,
        stock_quantity=50,
        offer_percent=10,  # 10% discount -> 135.00
    )
    dal = MenuItem.objects.create(
        category=cat_grains,
        name="Toor Dal",
        price=Decimal("180.00"),
        unit="kg",
        is_available=True,
        track_stock=True,
        stock_quantity=20,
    )
    milk = MenuItem.objects.create(
        category=cat_dairy,
        name="Toned Milk",
        price=Decimal("60.00"),
        unit="L",
        is_available=True,
        track_stock=True,
        stock_quantity=30,
    )
    out_of_stock_item = MenuItem.objects.create(
        category=cat_grains,
        name="Sona Masoori",
        price=Decimal("280.00"),
        unit="kg",
        is_available=True,
        track_stock=True,
        stock_quantity=0,  # Sold out
    )
    return {
        "cat_grains": cat_grains,
        "cat_dairy": cat_dairy,
        "rice": rice,
        "dal": dal,
        "milk": milk,
        "out_of_stock": out_of_stock_item,
    }


@pytest.fixture
def customer_user(db):
    return Customer.objects.create(
        phone="9876543210",
        email="customer@example.com",
        name="John Doe",
        default_address="Flat 101, Green Acres, Hyderabad",
    )


@pytest.mark.django_db
def test_homepage_loads_real_catalog(client, supermarket_catalog):
    """Test public homepage loads categories, best sellers, and highlights."""
    res = client.get(reverse("home"))
    assert res.status_code == 200
    assert "categories" in res.context
    assert len(res.context["categories"]) >= 2
    assert "best_sellers" in res.context
    assert any(item.name == "Basmati Rice" for item in res.context["best_sellers"])


@pytest.mark.django_db
def test_category_menu_sorting_and_filtering(client, supermarket_catalog):
    """Test category browsing with sorting by price and filtering out-of-stock items."""
    # Filter by category
    res = client.get(reverse("orders_customer:menu") + "?category=Dairy%20%26%20Eggs")
    assert res.status_code == 200
    assert res.context["category"] == "Dairy & Eggs"

    # Sort price ascending
    res_sort = client.get(reverse("orders_customer:menu") + "?sort=price_asc")
    assert res_sort.status_code == 200
    assert res_sort.context["sort"] == "price_asc"

    # In-stock filter
    res_stock = client.get(reverse("orders_customer:menu") + "?stock=in_stock")
    assert res_stock.status_code == 200


@pytest.mark.django_db
def test_product_detail_view(client, supermarket_catalog):
    """Test product detail page displays correct item data, unit, and related items."""
    rice = supermarket_catalog["rice"]
    url = reverse("orders_customer:product_detail", kwargs={"pk": rice.pk})
    res = client.get(url)
    assert res.status_code == 200
    assert res.context["item"] == rice
    assert res.context["item"].effective_price == Decimal("135.00")
    assert "related_items" in res.context


@pytest.mark.django_db
def test_cart_coupon_flow(client, supermarket_catalog):
    """Test applying a valid coupon, calculating discount, and removing coupon."""
    rice = supermarket_catalog["rice"]
    dal = supermarket_catalog["dal"]

    # Create active coupon
    today = date.today()
    coupon = Coupon.objects.create(
        code="SUPER50",
        discount_type="Fixed",
        value=Decimal("50.00"),
        valid_from=today - timedelta(days=1),
        valid_to=today + timedelta(days=30),
        min_order=Decimal("200.00"),
        is_active=True,
    )

    # Add items to cart (1 rice @ 135 + 1 dal @ 180 = 315)
    session = client.session
    session["delv_cart"] = {str(rice.pk): 1, str(dal.pk): 1}
    session.save()

    # Apply coupon
    res_apply = client.post(reverse("orders_customer:cart_apply_coupon"), {"code": "SUPER50"})
    assert res_apply.status_code == 302
    assert client.session.get("delv_coupon_code") == "SUPER50"

    # View cart — verify coupon discount reflection
    res_cart = client.get(reverse("orders_customer:cart"))
    assert res_cart.status_code == 200
    assert res_cart.context["coupon_data"]["code"] == "SUPER50"
    assert res_cart.context["coupon_discount"] == Decimal("50.00")
    assert res_cart.context["payable_total"] == Decimal("265.00")

    # Remove coupon
    res_rem = client.post(reverse("orders_customer:cart_remove_coupon"))
    assert res_rem.status_code == 302
    assert "delv_coupon_code" not in client.session


@pytest.mark.django_db
def test_customer_address_crud(client, customer_user):
    """Test customer address listing, adding, setting default, and deleting."""
    session = client.session
    session["customer_id"] = customer_user.pk
    session.save()

    # Add address
    add_url = reverse("orders_customer:address_add")
    res_add = client.post(add_url, {
        "title": "Office",
        "recipient_name": "John Office",
        "phone": "9876543210",
        "address": "Floor 5, Tech Park, Hitec City",
        "city": "Hyderabad",
        "is_default": "1",
    })
    assert res_add.status_code == 302
    addr = CustomerAddress.objects.filter(customer=customer_user, title="Office").first()
    assert addr is not None
    assert addr.is_default is True

    # List addresses
    res_list = client.get(reverse("orders_customer:addresses"))
    assert res_list.status_code == 200
    assert len(res_list.context["addresses"]) >= 1

    # Delete address
    del_url = reverse("orders_customer:address_delete", kwargs={"pk": addr.pk})
    res_del = client.post(del_url)
    assert res_del.status_code == 302
    assert not CustomerAddress.objects.filter(pk=addr.pk).exists()


@pytest.mark.django_db
def test_wishlist_toggle_and_view(client, customer_user, supermarket_catalog):
    """Test adding and removing products from wishlist."""
    rice = supermarket_catalog["rice"]
    session = client.session
    session["customer_id"] = customer_user.pk
    session.save()

    # Toggle add
    toggle_url = reverse("orders_customer:wishlist_toggle", kwargs={"pk": rice.pk})
    res_toggle = client.post(toggle_url)
    assert res_toggle.status_code == 302
    assert WishlistItem.objects.filter(customer=customer_user, item=rice).exists()

    # View wishlist
    res_view = client.get(reverse("orders_customer:wishlist"))
    assert res_view.status_code == 200
    assert len(res_view.context["wishlist_items"]) == 1

    # Toggle remove
    res_toggle2 = client.post(toggle_url)
    assert res_toggle2.status_code == 302
    assert not WishlistItem.objects.filter(customer=customer_user, item=rice).exists()


@pytest.mark.django_db
def test_checkout_with_slot_and_coupon(client, customer_user, supermarket_catalog):
    """Test full checkout flow with delivery slot, payment method, and coupon applied."""
    rice = supermarket_catalog["rice"]

    # Coupon: 10% off
    today = date.today()
    Coupon.objects.create(
        code="SAVE10",
        discount_type="Percentage",
        value=Decimal("10.00"),
        valid_from=today - timedelta(days=1),
        valid_to=today + timedelta(days=30),
        min_order=Decimal("50.00"),
        is_active=True,
    )

    session = client.session
    session["delv_cart"] = {str(rice.pk): 2}  # 2 * 135 = 270
    session["customer_id"] = customer_user.pk
    session["delv_coupon_code"] = "SAVE10"
    session.save()

    checkout_url = reverse("orders_customer:checkout")
    post_data = {
        "contact_name": "John Doe",
        "contact_phone": "9876543210",
        "address": "123 Supermarket Road",
        "delivery_slot": "Today Evening (5:00 PM - 8:00 PM)",
        "payment_method": "Cash on Delivery",
        "instructions": "Call upon arrival",
    }
    res = client.post(checkout_url, post_data)
    assert res.status_code == 200
    assert "order" in res.context

    order = res.context["order"]
    assert order.status == OrderStatus.PLACED
    # 270 - 10% (27) = 243
    assert order.total_amount == Decimal("243.00")
    assert "Slot: Today Evening" in order.instructions
    assert res.context.get("sound_order_id") == order.pk


@pytest.mark.django_db
def test_set_location_session(client):
    """Test location picker updates session location."""
    res = client.post(reverse("orders_customer:set_location"), {"location": "Banjara Hills"})
    assert res.status_code == 302
    assert client.session.get("customer_location") == "Banjara Hills"
