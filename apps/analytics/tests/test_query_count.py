"""Proof the aggregation is DB-side: each metric runs in a bounded query count.

If these functions were summing rows in Python, they would need to SELECT the
orders first (extra queries / full row loads). A single query proves the math
happens in the database.
"""
import pytest

from apps.analytics.services import daily_summary, totals


@pytest.mark.django_db
def test_totals_runs_in_one_query(make_order, aware_dt, django_assert_num_queries):
    """totals() is a single aggregate() round-trip regardless of order volume."""
    day = aware_dt(2026, 6, 10)
    make_order(amount="10.00", when=day)
    make_order(amount="20.00", when=day)
    make_order(amount="30.00", when=day)

    with django_assert_num_queries(1):
        totals(day.date(), day.date())


@pytest.mark.django_db
def test_daily_summary_runs_in_one_query(make_order, aware_dt, django_assert_num_queries):
    """daily_summary() groups DB-side in a single query."""
    make_order(amount="10.00", when=aware_dt(2026, 6, 10))
    make_order(amount="20.00", when=aware_dt(2026, 6, 11))

    with django_assert_num_queries(1):
        daily_summary(aware_dt(2026, 6, 10).date(), aware_dt(2026, 6, 11).date())
