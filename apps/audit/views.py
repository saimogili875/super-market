"""Views for read-only audit log records and log exporting."""
import csv
from datetime import date
from django.contrib import messages
from django.db import models
from django.http import HttpResponse
from django.shortcuts import render

from apps.core.permissions import staff_required
from .models import AuditLog


@staff_required
def audit_list(request):
    """Browse administrative audit logs and export security logs."""
    q = request.GET.get("q", "").strip()
    category = request.GET.get("category", "All")
    from_date = request.GET.get("from_date", "").strip()
    to_date = request.GET.get("to_date", "").strip()
    export_csv = request.GET.get("export") == "csv"

    logs = AuditLog.objects.all()

    if q:
        logs = logs.filter(
            models.Q(user_display__icontains=q)
            | models.Q(record_id__icontains=q)
            | models.Q(action__icontains=q)
            | models.Q(change_summary__icontains=q)
        )
    if category != "All":
        logs = logs.filter(category=category)
    if from_date:
        try:
            logs = logs.filter(timestamp__date__gte=date.fromisoformat(from_date))
        except ValueError:
            pass
    if to_date:
        try:
            logs = logs.filter(timestamp__date__lte=date.fromisoformat(to_date))
        except ValueError:
            pass

    if export_csv:
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = f'attachment; filename="supermarket_audit_log_{date.today().isoformat()}.csv"'
        writer = csv.writer(response)
        writer.writerow(["Timestamp", "User", "Action", "Category", "Record ID", "Change Summary", "IP Address", "Status"])
        for entry in logs[:1000]:
            writer.writerow([
                entry.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                entry.user_display,
                entry.action,
                entry.category,
                entry.record_id,
                entry.change_summary,
                entry.ip_address or "-",
                entry.status,
            ])
        return response

    return render(
        request,
        "admin/audit_logs.html",
        {
            "logs": logs[:100],
            "total_count": logs.count(),
            "q": q,
            "category": category,
            "from_date": from_date,
            "to_date": to_date,
            "active_nav": "audit",
        },
    )
