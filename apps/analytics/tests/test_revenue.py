"""Only PAID (settled) orders count as revenue; other statuses are excluded."""
from decimal import Decimal

import pytest

from apps.analytics.services import daily_summary, totals


@pytest.mark.django_db
def test_only_paid_orders_count(make_order, aware_dt):
    """En-route / in-progress orders never inflate revenue or order counts."""
    day = aware_dt(2026, 6, 10)
    make_order(status="PAID", amount="100.00", when=day)
    make_order(status="PAID", amount="50.00", when=day)
    # None of these are settled and must be ignored entirely:
    make_order(status="COLLECT", amount="999.00", when=day)  # cash still with driver
    make_order(status="DISPATCH", amount="999.00", when=day)
    make_order(status="PLACED", amount="999.00", when=day)

    result = totals(day.date(), day.date())
    assert result["orders"] == 2
    assert result["revenue"] == Decimal("150.00")


@pytest.mark.django_db
def test_daily_summary_excludes_non_settled(make_order, aware_dt):
    """daily_summary reflects only the settled orders for the day."""
    day = aware_dt(2026, 6, 10)
    make_order(status="PAID", amount="80.00", when=day)
    make_order(status="COLLECT", amount="999.00", when=day)

    rows = daily_summary(day.date(), day.date())
    assert len(rows) == 1
    assert rows[0]["order_count"] == 1
    assert rows[0]["revenue"] == Decimal("80.00")
