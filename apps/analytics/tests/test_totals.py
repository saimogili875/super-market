"""totals() returns correct orders/revenue/AOV and never divides by zero."""
import datetime
from decimal import Decimal

import pytest

from apps.analytics.services import totals


@pytest.mark.django_db
def test_totals_orders_revenue_and_aov(make_order, aware_dt):
    """AOV is revenue / orders, derived from the single aggregate."""
    day = aware_dt(2026, 6, 15)
    make_order(amount="30.00", when=day)
    make_order(amount="70.00", when=day)

    result = totals(day.date(), day.date())

    assert result["orders"] == 2
    assert result["revenue"] == Decimal("100.00")
    assert result["avg_order_value"] == Decimal("50.00")


@pytest.mark.django_db
def test_totals_empty_range_is_zero(db):
    """An empty range yields zeros — revenue 0.00 and AOV 0.00, no ZeroDivision."""
    result = totals(datetime.date(2026, 1, 1), datetime.date(2026, 1, 7))

    assert result["orders"] == 0
    assert result["revenue"] == Decimal("0.00")
    assert result["avg_order_value"] == Decimal("0.00")
