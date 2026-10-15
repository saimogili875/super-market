"""Tests verifying that MenuItem save, update, toggle, and delete invalidate the menu cache."""
from decimal import Decimal
import pytest
from django.core.cache import cache

from apps.menu.models import Category, MenuItem
from apps.menu.services import MENU_CACHE_KEY, get_cached_menu, toggle_availability


@pytest.fixture
def menu_item():
    cat = Category.objects.create(name="Cache Test Category")
    return MenuItem.objects.create(
        category=cat,
        name="Cache Burger",
        price=Decimal("10.00"),
        is_available=True,
    )


@pytest.mark.django_db
def test_menu_item_save_invalidates_cache(menu_item):
    """Saving a MenuItem (e.g. updating price) clears MENU_CACHE_KEY."""
    get_cached_menu()
    assert cache.get(MENU_CACHE_KEY) is not None

    menu_item.price = Decimal("15.00")
    menu_item.save()

    assert cache.get(MENU_CACHE_KEY) is None


@pytest.mark.django_db
def test_menu_item_toggle_availability_invalidates_cache(menu_item):
    """toggle_availability() on a MenuItem clears MENU_CACHE_KEY."""
    get_cached_menu()
    assert cache.get(MENU_CACHE_KEY) is not None

    toggle_availability(menu_item)

    assert cache.get(MENU_CACHE_KEY) is None


@pytest.mark.django_db
def test_menu_item_delete_invalidates_cache(menu_item):
    """Deleting a MenuItem clears MENU_CACHE_KEY."""
    get_cached_menu()
    assert cache.get(MENU_CACHE_KEY) is not None

    menu_item.delete()

    assert cache.get(MENU_CACHE_KEY) is None
