"""Tests for stock tracking, availability, race-safe ordering, and restock on cancel."""
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from apps.accounts.models import Role, User
from apps.menu.models import Category, MenuItem
from apps.orders.models import OrderStatus
from apps.orders.services import add_item_to_order, create_order, transition


@pytest.fixture
def category(db):
    """A simple active menu category."""
    return Category.objects.create(name="Mains", is_active=True)


@pytest.fixture
def customer(db):
    """A customer user."""
    return User.objects.create_user(
        username="stock_cust", password="pw", role=Role.CUSTOMER
    )


@pytest.fixture
def admin_user(db):
    """An admin user."""
    return User.objects.create_user(
        username="stock_admin", password="pw", role=Role.ADMIN
    )


@pytest.mark.django_db
def test_is_orderable_property(category):
    """is_orderable combines admin availability and stock rules."""
    # Untracked, available -> True
    item1 = MenuItem.objects.create(
        category=category, name="Untracked Avail", price=Decimal("10"),
        is_available=True, track_stock=False
    )
    assert item1.is_orderable is True

    # Untracked, unavailable -> False
    item2 = MenuItem.objects.create(
        category=category, name="Untracked Unavail", price=Decimal("10"),
        is_available=False, track_stock=False
    )
    assert item2.is_orderable is False

    # Tracked, available, stock > 0 -> True
    item3 = MenuItem.objects.create(
        category=category, name="Tracked In Stock", price=Decimal("10"),
        is_available=True, track_stock=True, stock_quantity=5
    )
    assert item3.is_orderable is True

    # Tracked, available, stock == 0 -> False
    item4 = MenuItem.objects.create(
        category=category, name="Tracked Sold Out", price=Decimal("10"),
        is_available=True, track_stock=True, stock_quantity=0
    )
    assert item4.is_orderable is False

    # Tracked, unavailable, stock > 0 -> False
    item5 = MenuItem.objects.create(
        category=category, name="Tracked Disabled", price=Decimal("10"),
        is_available=False, track_stock=True, stock_quantity=5
    )
    assert item5.is_orderable is False


@pytest.mark.django_db
def test_order_unavailable_item_raises(category, customer):
    """Ordering an item with is_available=False raises ValidationError."""
    item = MenuItem.objects.create(
        category=category, name="Soup", price=Decimal("15"),
        is_available=False, track_stock=False
    )

    with pytest.raises(ValidationError, match="currently unavailable"):
        create_order(
            order_type="DELV",
            items=[{"menu_item_id": item.pk, "quantity": 1}],
            customer=customer,
        )


@pytest.mark.django_db
def test_order_exceeds_stock_raises_and_exact_succeeds(category, customer):
    """Ordering qty > stock raises ValidationError; qty == stock succeeds and sets stock to 0."""
    item = MenuItem.objects.create(
        category=category, name="Limited Special", price=Decimal("50"),
        is_available=True, track_stock=True, stock_quantity=2
    )

    # Ordering 3 when only 2 available -> raises ValidationError
    with pytest.raises(ValidationError, match="Only 2 left"):
        create_order(
            order_type="DELV",
            items=[{"menu_item_id": item.pk, "quantity": 3}],
            customer=customer,
        )

    # Ordering exactly 2 -> succeeds
    order = create_order(
        order_type="DELV",
        items=[{"menu_item_id": item.pk, "quantity": 2}],
        customer=customer,
    )
    assert order.items.count() == 1

    item.refresh_from_db()
    assert item.stock_quantity == 0
    assert item.is_orderable is False

    # Ordering again when stock is 0 -> raises ValidationError
    with pytest.raises(ValidationError, match="sold out"):
        create_order(
            order_type="DELV",
            items=[{"menu_item_id": item.pk, "quantity": 1}],
            customer=customer,
        )


@pytest.mark.django_db
def test_order_decrements_tracked_stock_leaves_untracked(category, customer):
    """Ordering a tracked item decrements stock; untracked item stock is unchanged."""
    tracked = MenuItem.objects.create(
        category=category, name="Tracked Burger", price=Decimal("20"),
        is_available=True, track_stock=True, stock_quantity=10
    )
    untracked = MenuItem.objects.create(
        category=category, name="Untracked Fries", price=Decimal("5"),
        is_available=True, track_stock=False, stock_quantity=0
    )

    create_order(
        order_type="DELV",
        items=[
            {"menu_item_id": tracked.pk, "quantity": 3},
            {"menu_item_id": untracked.pk, "quantity": 2},
        ],
        customer=customer,
    )

    tracked.refresh_from_db()
    untracked.refresh_from_db()

    assert tracked.stock_quantity == 7
    assert untracked.stock_quantity == 0

    # Test add_item_to_order also decrements tracked stock
    order = create_order(
        order_type="DELV",
        items=[{"menu_item_id": untracked.pk, "quantity": 1}],
        customer=customer,
    )
    add_item_to_order(order, tracked.pk, quantity=2)
    tracked.refresh_from_db()
    assert tracked.stock_quantity == 5


@pytest.mark.django_db
def test_cancelling_order_restocks_tracked_items(category, customer, admin_user):
    """Cancelling an order restocks tracked items back to their prior quantity."""
    tracked = MenuItem.objects.create(
        category=category, name="Tracked Pizza", price=Decimal("30"),
        is_available=True, track_stock=True, stock_quantity=10
    )
    untracked = MenuItem.objects.create(
        category=category, name="Untracked Soda", price=Decimal("3"),
        is_available=True, track_stock=False, stock_quantity=0
    )

    order = create_order(
        order_type="DELV",
        items=[
            {"menu_item_id": tracked.pk, "quantity": 4},
            {"menu_item_id": untracked.pk, "quantity": 2},
        ],
        customer=customer,
    )

    tracked.refresh_from_db()
    assert tracked.stock_quantity == 6

    # Transition to CANCELLED -> restocks tracked items
    transition(order, OrderStatus.CANCELLED, actor=admin_user)

    tracked.refresh_from_db()
    untracked.refresh_from_db()
    assert tracked.stock_quantity == 10
    assert untracked.stock_quantity == 0


@pytest.mark.django_db
def test_non_cancel_transitions_do_not_restock(category, customer, admin_user):
    """Transitioning to APPROVED, PREPARING, DELIVERED, etc. does not restock items."""
    tracked = MenuItem.objects.create(
        category=category, name="Tracked Taco", price=Decimal("10"),
        is_available=True, track_stock=True, stock_quantity=5
    )

    order = create_order(
        order_type="DELV",
        items=[{"menu_item_id": tracked.pk, "quantity": 2}],
        customer=customer,
    )

    tracked.refresh_from_db()
    assert tracked.stock_quantity == 3

    transition(order, OrderStatus.APPROVED, actor=admin_user)
    tracked.refresh_from_db()
    assert tracked.stock_quantity == 3

    transition(order, OrderStatus.IN_KITCHEN, actor=admin_user)
    tracked.refresh_from_db()
    assert tracked.stock_quantity == 3


@pytest.mark.django_db
def test_sequential_order_calls_for_last_unit(category, customer):
    """Two sequential create_order calls for the last unit: first succeeds, second is rejected."""
    item = MenuItem.objects.create(
        category=category, name="Last Cake Slice", price=Decimal("8"),
        is_available=True, track_stock=True, stock_quantity=1
    )

    # First call succeeds
    order1 = create_order(
        order_type="DELV",
        items=[{"menu_item_id": item.pk, "quantity": 1}],
        customer=customer,
    )
    assert order1 is not None

    item.refresh_from_db()
    assert item.stock_quantity == 0

    # Second call for the last unit is rejected
    with pytest.raises(ValidationError, match="sold out"):
        create_order(
            order_type="DELV",
            items=[{"menu_item_id": item.pk, "quantity": 1}],
            customer=customer,
        )

    # Assert final stock never negative
    item.refresh_from_db()
    assert item.stock_quantity == 0
    assert item.stock_quantity >= 0
