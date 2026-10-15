"""Admin frontend views for the tables app — list, CRUD, and sessions."""
from decimal import Decimal

from django.contrib import messages
from django.db.models import Count, Prefetch, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from apps.core.permissions import role_required
from apps.orders.models import Order

from .forms import TableForm
from .models import Table, TableSession


@require_GET
@role_required("ADMIN")
def tables_management(request):
    """Admin frontend view for managing dining tables."""
    # Annotate each table with its count of currently OPEN tabs (closed_at IS NULL)
    # so the template can show an open-tab indicator without an extra query per row.
    tables = Table.objects.annotate(
        open_tabs=Count("sessions", filter=Q(sessions__closed_at__isnull=True)),
    ).order_by("number")
    return render(
        request,
        "tables/admin/dashboard.html",
        {"tables": tables},
    )


@require_http_methods(["GET", "POST"])
@role_required("ADMIN")
def table_create(request):
    """Create a new dining table (qr_token auto-generated)."""
    form = TableForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        table = form.save()
        messages.success(request, f"Table {table.number} created.")
        return redirect("tables_admin:management")
    return render(request, "tables/admin/table_form.html", {"form": form, "mode": "create"})


@require_http_methods(["GET", "POST"])
@role_required("ADMIN")
def table_edit(request, pk):
    """Edit an existing dining table."""
    table = get_object_or_404(Table, pk=pk)
    form = TableForm(request.POST or None, instance=table)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f"Table {table.number} updated.")
        return redirect("tables_admin:management")
    return render(
        request,
        "tables/admin/table_form.html",
        {"form": form, "mode": "edit", "table": table},
    )


@require_POST
@role_required("ADMIN")
def table_deactivate(request, pk):
    """Deactivate (soft-disable) a dining table."""
    table = get_object_or_404(Table, pk=pk)
    table.is_active = False
    table.save(update_fields=["is_active"])
    messages.success(request, f"Table {table.number} deactivated.")
    return redirect("tables_admin:management")


@require_GET
@role_required("ADMIN")
def sessions_list(request):
    """Read-only overview of open/closed tabs with their orders and totals."""
    orders_qs = Order.objects.prefetch_related("items").order_by("-created_at")
    sessions = (
        TableSession.objects
        .select_related("table")
        .prefetch_related(Prefetch("orders", queryset=orders_qs))
        .order_by("-opened_at")[:100]
    )
    rows = []
    for session in sessions:
        orders = list(session.orders.all())
        total = sum((o.total_amount for o in orders), Decimal("0"))
        rows.append({"session": session, "orders": orders, "total": total})
    return render(request, "tables/admin/sessions.html", {"rows": rows})
