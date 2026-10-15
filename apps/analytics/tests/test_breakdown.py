"""breakdown_by_type splits settled revenue and counts by DINE vs DELV."""
from decimal import Decimal

import pytest

from apps.analytics.services import breakdown_by_type


@pytest.mark.django_db
def test_breakdown_splits_dine_and_delv(make_order, aware_dt):
    """Each channel reports its own order count and revenue."""
    day = aware_dt(2026, 6, 20)
    make_order(order_type="DINE", amount="40.00", when=day)
    make_order(order_type="DINE", amount="60.00", when=day)
    make_order(order_type="DELV", amount="25.00", when=day)

    rows = breakdown_by_type(day.date(), day.date())
    by_type = {row["order_type"]: row for row in rows}

    assert by_type["DINE"]["order_count"] == 2
    assert by_type["DINE"]["revenue"] == Decimal("100.00")
    assert by_type["DELV"]["order_count"] == 1
    assert by_type["DELV"]["revenue"] == Decimal("25.00")
