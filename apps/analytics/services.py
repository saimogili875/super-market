"""Financial analytics — all revenue/volume aggregation, computed DB-side.

Every metric here is a thin wrapper over a single ORM ``aggregate()`` /
``annotate()`` call, so PostgreSQL (or SQLite in tests) does the summing. We
NEVER pull Order rows into Python to add them up — that is the low-memory / RAM
rule for this module: math stays in the database, only small result rows come
back.

A human tuning a metric edits ONE documented function here; views and templates
hold no arithmetic. The single most important knob — what counts as revenue —
is the ``SETTLED_STATUSES`` constant right below.
"""
import datetime
from decimal import Decimal

from django.db.models import Count, DateField, DecimalField, Sum, Value
from django.db.models.functions import Coalesce, TruncDate, TruncWeek
from django.utils import timezone

from apps.orders.models import Order

# ---------------------------------------------------------------------------
# WHAT COUNTS AS REVENUE — the single tunable definition.
#
# Cash is only "real" once it has been cleared and the order reaches its
# terminal PAID state. COLLECT is en-route cash the driver is still physically
# holding; PAID is the settled, cleared state that actually belongs to the
# business. To redefine revenue, edit this ONE tuple — nothing else changes.
# ---------------------------------------------------------------------------
SETTLED_STATUSES = ("PAID",)

# Money output type for Coalesced sums (keeps an empty range at Decimal 0.00
# rather than NULL, and pins the column type so the ORM never guesses).
_MONEY = DecimalField(max_digits=12, decimal_places=2)
_ZERO = Decimal("0.00")


def _start_of_day(day: datetime.date) -> datetime.datetime:
    """Timezone-aware midnight at the start of *day* (active timezone)."""
    return timezone.make_aware(datetime.datetime.combine(day, datetime.time.min))


def _settled_orders(start_date: datetime.date, end_date: datetime.date):
    """Base queryset: settled orders whose settlement time is in [start, end].

    Filters ``status__in=SETTLED_STATUSES`` and a half-open datetime window
    ``[start 00:00, (end + 1 day) 00:00)`` so the entire end day is included.
    Using a plain datetime range (not a ``__date`` cast) lets PostgreSQL scan
    the ``Index(fields=["status", "updated_at"])`` added to Order for exactly
    this page — settlement time is the order's last update.

    Every metric builds on this one queryset so the revenue definition stays
    consistent across the whole dashboard.
    """
    start_dt = _start_of_day(start_date)
    end_dt = _start_of_day(end_date + datetime.timedelta(days=1))
    return Order.objects.filter(
        status__in=SETTLED_STATUSES,
        updated_at__gte=start_dt,
        updated_at__lt=end_dt,
    )


def daily_summary(start_date: datetime.date, end_date: datetime.date) -> list[dict]:
    """Per-day order count and revenue for settled orders in [start, end].

    Groups PAID orders by the calendar day they settled (``TruncDate`` on
    ``updated_at``) and returns one small row per day, ordered chronologically::

        [{"day": date, "order_count": int, "revenue": Decimal}, ...]

    Grouping and summing happen entirely in the database via
    ``values().annotate()``; no Order rows are materialised in Python.
    """
    rows = (
        _settled_orders(start_date, end_date)
        .annotate(day=TruncDate("updated_at"))
        .values("day")
        .annotate(order_count=Count("id"), revenue=Sum("total_amount"))
        .order_by("day")
    )
    return list(rows)


def weekly_summary(start_date: datetime.date, end_date: datetime.date) -> list[dict]:
    """Per-week order count and revenue for settled orders in [start, end].

    Identical to :func:`daily_summary` but buckets by ISO week
    (``TruncWeek``, Monday-anchored). Returns::

        [{"week": date, "order_count": int, "revenue": Decimal}, ...]

    ordered chronologically. All aggregation is DB-side.
    """
    rows = (
        # output_field=DateField keeps the week key a plain date (like the daily
        # key), rather than TruncWeek's default midnight datetime.
        _settled_orders(start_date, end_date)
        .annotate(week=TruncWeek("updated_at", output_field=DateField()))
        .values("week")
        .annotate(order_count=Count("id"), revenue=Sum("total_amount"))
        .order_by("week")
    )
    return list(rows)


def totals(start_date: datetime.date, end_date: datetime.date) -> dict:
    """Headline KPIs for the range, in a SINGLE aggregate() round-trip.

    Returns ``{"orders": int, "revenue": Decimal, "avg_order_value": Decimal}``.

    Order count and revenue are computed DB-side in one query; the average
    order value is derived in Python from those two scalars — guarding against
    division by zero on an empty range (no orders -> AOV 0.00, revenue 0.00).
    No rows are loaded to compute the sums.
    """
    agg = _settled_orders(start_date, end_date).aggregate(
        orders=Count("id"),
        revenue=Coalesce(Sum("total_amount"), Value(_ZERO), output_field=_MONEY),
    )
    orders = agg["orders"] or 0
    revenue = agg["revenue"] or _ZERO
    avg_order_value = (revenue / orders) if orders else _ZERO
    return {
        "orders": orders,
        "revenue": revenue,
        "avg_order_value": avg_order_value.quantize(Decimal("0.01")),
    }


def breakdown_by_type(start_date: datetime.date, end_date: datetime.date) -> list[dict]:
    """Revenue and order count split by channel (DINE vs DELV).

    One grouped query (``values("order_type").annotate(...)``). Returns::

        [{"order_type": "DELV", "order_count": int, "revenue": Decimal}, ...]

    ordered by ``order_type`` for stable display. Aggregation is DB-side.
    """
    rows = (
        _settled_orders(start_date, end_date)
        .values("order_type")
        .annotate(order_count=Count("id"), revenue=Sum("total_amount"))
        .order_by("order_type")
    )
    return list(rows)
