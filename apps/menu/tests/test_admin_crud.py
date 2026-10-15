"""Feature tests for the bespoke Menu admin dashboard CRUD."""
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.accounts.models import Role, User
from apps.menu.models import Category, MenuItem


@pytest.fixture
def admin_user(db):
    return User.objects.create_user(
        username="menu_admin", password="pw", role=Role.ADMIN,
        is_staff=True, is_superuser=True,
    )


@pytest.fixture
def category(db):
    return Category.objects.create(name="Starters", is_active=True)


@pytest.mark.django_db
def test_category_create_persists(client, admin_user):
    client.force_login(admin_user)
    resp = client.post(
        reverse("menu:category_create"),
        {"name": "Desserts", "sort_order": 3, "is_active": "on"},
    )
    assert resp.status_code == 302
    assert Category.objects.filter(name="Desserts").exists()


@pytest.mark.django_db
def test_item_create_edit_toggle_delete(client, admin_user, category):
    client.force_login(admin_user)

    # Create — price is Decimal, offer bounded.
    resp = client.post(
        reverse("menu:item_create"),
        {
            "category": category.pk, "name": "Soup", "description": "warm",
            "price": "6.50", "prep_minutes": 8, "offer_percent": 10, "is_available": "on",
        },
    )
    assert resp.status_code == 302
    item = MenuItem.objects.get(name="Soup")
    assert item.price == Decimal("6.50")
    assert item.effective_price == Decimal("5.85")

    # Edit — rename + change price.
    resp = client.post(
        reverse("menu:item_edit", args=[item.pk]),
        {
            "category": category.pk, "name": "Tomato Soup", "description": "warm",
            "price": "7.00", "prep_minutes": 8, "offer_percent": 0, "is_available": "on",
        },
    )
    assert resp.status_code == 302
    item.refresh_from_db()
    assert item.name == "Tomato Soup"
    assert item.price == Decimal("7.00")

    # Toggle availability (reuses the existing endpoint).
    resp = client.post(reverse("menu:toggle_availability", args=[item.pk]))
    assert resp.status_code == 200
    item.refresh_from_db()
    assert item.is_available is False

    # Delete.
    resp = client.post(reverse("menu:item_delete", args=[item.pk]))
    assert resp.status_code == 302
    assert not MenuItem.objects.filter(pk=item.pk).exists()


@pytest.mark.django_db
def test_offer_percent_out_of_range_rejected(client, admin_user, category):
    """Server-side validation: offer_percent > 100 is rejected (form invalid)."""
    client.force_login(admin_user)
    resp = client.post(
        reverse("menu:item_create"),
        {
            "category": category.pk, "name": "Bad", "description": "",
            "price": "5.00", "prep_minutes": 5, "offer_percent": 150, "is_available": "on",
        },
    )
    assert resp.status_code == 200  # re-rendered form with errors, not a redirect
    assert not MenuItem.objects.filter(name="Bad").exists()
