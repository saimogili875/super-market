"""Tests for menu item pricing logic."""
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from apps.menu.models import Category, MenuItem


@pytest.mark.django_db
def test_effective_price_no_discount():
    """effective_price equals price when offer_percent is 0."""
    category = Category.objects.create(name="Mains")
    item = MenuItem(category=category, name="Burger", price=Decimal("15.00"), offer_percent=0)
    assert item.effective_price == Decimal("15.00")


@pytest.mark.django_db
def test_effective_price_with_discount():
    """effective_price applies discount and quantizes to 2 decimals."""
    category = Category.objects.create(name="Mains")
    item = MenuItem(category=category, name="Pizza", price=Decimal("100.00"), offer_percent=20)
    assert item.effective_price == Decimal("80.00")


@pytest.mark.django_db
def test_offer_percent_validation():
    """offer_percent > 100 fails full_clean validation."""
    category = Category.objects.create(name="Mains")
    item = MenuItem(category=category, name="Freebie", price=Decimal("10.00"), offer_percent=101)
    with pytest.raises(ValidationError):
        item.full_clean()


@pytest.mark.django_db
def test_price_validation():
    """price <= 0 fails full_clean validation."""
    category = Category.objects.create(name="Mains")
    item = MenuItem(category=category, name="Zero", price=Decimal("0.00"), offer_percent=0)
    with pytest.raises(ValidationError):
        item.full_clean()
