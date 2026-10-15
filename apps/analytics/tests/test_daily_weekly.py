"""daily_summary groups by calendar day; weekly_summary buckets by ISO week."""
import datetime
from decimal import Decimal

import pytest

from apps.analytics.services import daily_summary, weekly_summary


@pytest.mark.django_db
def test_daily_summary_groups_by_day(make_order, aware_dt):
    """A 3-day fixture yields one row per day with hand-checked sums."""
    d1 = aware_dt(2026, 6, 1)
    d2 = aware_dt(2026, 6, 2)
    d3 = aware_dt(2026, 6, 3)
    make_order(amount="10.00", when=d1)
    make_order(amount="20.00", when=d1)
    make_order(amount="30.00", when=d2)
    make_order(amount="40.00", when=d3)

    rows = daily_summary(d1.date(), d3.date())

    assert [r["day"] for r in rows] == [d1.date(), d2.date(), d3.date()]
    assert [r["order_count"] for r in rows] == [2, 1, 1]
    assert [r["revenue"] for r in rows] == [
        Decimal("30.00"),
        Decimal("30.00"),
        Decimal("40.00"),
    ]


@pytest.mark.django_db
def test_weekly_summary_buckets_by_week(make_order, aware_dt):
    """Same-week days collapse into one Monday-anchored bucket; next week is its own."""
    # 2026-06-01 is a Monday, 2026-06-03 same week, 2026-06-08 the next Monday.
    make_order(amount="10.00", when=aware_dt(2026, 6, 1))
    make_order(amount="15.00", when=aware_dt(2026, 6, 3))
    make_order(amount="50.00", when=aware_dt(2026, 6, 8))

    rows = weekly_summary(datetime.date(2026, 6, 1), datetime.date(2026, 6, 8))

    assert len(rows) == 2
    assert rows[0]["week"] == datetime.date(2026, 6, 1)
    assert rows[0]["order_count"] == 2
    assert rows[0]["revenue"] == Decimal("25.00")
    assert rows[1]["week"] == datetime.date(2026, 6, 8)
    assert rows[1]["order_count"] == 1
    assert rows[1]["revenue"] == Decimal("50.00")
