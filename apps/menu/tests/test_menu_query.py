"""Tests for menu queries."""
from decimal import Decimal

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.menu.models import Category, MenuItem
from apps.menu.services import available_menu


@pytest.mark.django_db
def test_available_menu_query():
    """available_menu excludes inactive categories/items and bounds queries."""
    cat1 = Category.objects.create(name="Active Cat", is_active=True, sort_order=1)
    cat2 = Category.objects.create(name="Inactive Cat", is_active=False, sort_order=2)

    MenuItem.objects.create(category=cat1, name="Item 1", price=Decimal("10"), is_available=True)
    MenuItem.objects.create(category=cat1, name="Item 2", price=Decimal("10"), is_available=False)
    MenuItem.objects.create(category=cat2, name="Item 3", price=Decimal("10"), is_available=True)

    with CaptureQueriesContext(connection) as ctx:
        menu = list(available_menu())
        assert len(menu) == 1
        
        # Access prefected items
        items = list(menu[0].items.all())
        assert len(items) == 1
        assert items[0].name == "Item 1"

    # 1 query for categories + 1 query for items = 2 queries max
    assert len(ctx.captured_queries) == 2
