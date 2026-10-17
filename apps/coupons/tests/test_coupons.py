import pytest
from datetime import date, timedelta
from decimal import Decimal
from django.urls import reverse
from apps.accounts.models import Role, User
from apps.coupons.models import Coupon


@pytest.mark.django_db
def test_coupon_creation_and_discount(client):
    admin = User.objects.create_user(username="coupadmin", password="password123", role=Role.ADMIN)
    client.force_login(admin)

    # 1. Access coupon list
    resp = client.get(reverse("coupons:list"))
    assert resp.status_code == 200

    # 2. Create coupon via POST
    today = date.today()
    resp = client.post(
        reverse("coupons:list"),
        {
            "code": "FRESH20",
            "discount_type": "Percentage",
            "value": "20.00",
            "min_order": "500.00",
            "usage_limit": "50",
            "valid_from": (today - timedelta(days=1)).isoformat(),
            "valid_to": (today + timedelta(days=7)).isoformat(),
            "is_active": "on",
        },
    )
    assert resp.status_code == 302
    assert Coupon.objects.filter(code="FRESH20").exists()

    coupon = Coupon.objects.get(code="FRESH20")
    assert coupon.status == "Active"

    # 20% of 600 = 120.00
    valid, _ = coupon.is_valid_for(Decimal("600.00"))
    assert valid is True
    disc = coupon.calculate_discount(Decimal("600.00"))
    assert disc == Decimal("120.00")

    # Order below min_order (400 < 500)
    valid_low, _ = coupon.is_valid_for(Decimal("400.00"))
    assert valid_low is False
