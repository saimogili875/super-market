"""Admin financial-analytics dashboard — a thin view over services.py.

The view does NO aggregation: it resolves an optional ?start=&end= date range
(defaulting to the last 7 days), calls the analytics services, attaches a
presentation-only bar width to each day row, and renders. All revenue/volume
math lives in apps/analytics/services.py.
"""
import datetime
from decimal import Decimal

from django.shortcuts import render
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_GET

from apps.core.permissions import role_required

from . import services


def _parse_date(raw: str | None, default: datetime.date) -> datetime.date:
    """Parse a YYYY-MM-DD query param, falling back to *default* on any error."""
    if raw:
        parsed = parse_date(raw)
        if parsed:
            return parsed
    return default


def _add_bar_widths(daily: list[dict]) -> list[dict]:
    """Attach a 0-100 ``bar_pct`` (share of peak revenue) to each day row.

    Pure presentation over the already-aggregated daily list (a handful of
    rows) so the template can draw bars without arithmetic — this is NOT
    order-level aggregation and touches no Order rows.
    """
    peak = max((row["revenue"] for row in daily), default=Decimal("0"))
    for row in daily:
        row["bar_pct"] = float(row["revenue"] / peak * 100) if peak else 0
    return daily


@require_GET
@role_required("ADMIN")
def dashboard(request):
    """Render the financial analytics dashboard for the selected date range."""
    today = timezone.localdate()
    start = _parse_date(request.GET.get("start"), today - datetime.timedelta(days=6))
    end = _parse_date(request.GET.get("end"), today)
    context = {
        "start": start,
        "end": end,
        "totals": services.totals(start, end),
        "daily": _add_bar_widths(services.daily_summary(start, end)),
        "breakdown": services.breakdown_by_type(start, end),
    }
    return render(request, "analytics/dashboard.html", context)
