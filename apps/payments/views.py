"""Views for payments, transaction auditing, and refund issuance."""
from datetime import date
from decimal import Decimal
from django.contrib import messages
from django.db import models, transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.audit.models import log_audit_event
from apps.core.permissions import staff_required
from .models import PaymentTransaction


@staff_required
def payment_list(request):
    """Transactions ledger with status filters and refund verification."""
    if request.method == "POST":
        action = request.POST.get("action")

        if action == "issue_refund":
            txn_id = request.POST.get("txn_id")
            refund_amount_raw = request.POST.get("refund_amount", "").strip()
            reason = request.POST.get("reason", "Customer request").strip()

            txn = get_object_or_404(PaymentTransaction, txn_id=txn_id)

            try:
                refund_amount = Decimal(refund_amount_raw)
            except Exception:
                messages.error(request, "Invalid refund amount.")
                return redirect("payments:list")

            if refund_amount <= Decimal("0.00"):
                messages.error(request, "Refund amount must be greater than zero.")
            elif refund_amount > txn.amount:
                messages.error(request, f"Refund cannot exceed transaction amount (₹{txn.amount}).")
            else:
                with transaction.atomic():
                    txn.status = "Refunded"
                    txn.refund_amount = refund_amount
                    txn.refund_reason = reason
                    txn.refunded_at = timezone.now()
                    txn.save()

                    log_audit_event(
                        request=request,
                        action="Refund issued",
                        category="Payments",
                        record_id=txn.txn_id,
                        change_summary=f"Refunded ₹{refund_amount} on {txn.txn_id} (Reason: {reason})",
                    )
                    messages.success(request, f"Refund of ₹{refund_amount} processed for {txn.txn_id}.")

            return redirect("payments:list")

    # Filters
    q = request.GET.get("q", "").strip()
    status_filter = request.GET.get("status", "All")
    from_date = request.GET.get("from_date", "").strip()
    to_date = request.GET.get("to_date", "").strip()

    txns = PaymentTransaction.objects.all()
    if q:
        txns = txns.filter(
            models.Q(txn_id__icontains=q)
            | models.Q(order_ref__icontains=q)
            | models.Q(customer_name__icontains=q)
        )
    if status_filter in ["Paid", "Pending", "Failed", "Refunded"]:
        txns = txns.filter(status=status_filter)
    if from_date:
        try:
            txns = txns.filter(created_at__date__gte=date.fromisoformat(from_date))
        except ValueError:
            pass
    if to_date:
        try:
            txns = txns.filter(created_at__date__lte=date.fromisoformat(to_date))
        except ValueError:
            pass

    return render(
        request,
        "admin/payments.html",
        {
            "transactions": txns,
            "q": q,
            "status_filter": status_filter,
            "from_date": from_date,
            "to_date": to_date,
            "active_nav": "payments",
        },
    )
