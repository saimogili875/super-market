"""Views for promotional discounts and coupon vouchers."""
from datetime import date
from decimal import Decimal
from django.contrib import messages
from django.shortcuts import redirect, render

from apps.audit.models import log_audit_event
from apps.core.permissions import staff_required
from .models import Coupon


@staff_required
def coupon_list(request):
    """List promotional coupons and handle creation."""
    if request.method == "POST":
        code = request.POST.get("code", "").strip().upper()
        dtype = request.POST.get("discount_type", "Percentage")
        val_raw = request.POST.get("value", "0").strip()
        v_from_raw = request.POST.get("valid_from", "").strip()
        v_to_raw = request.POST.get("valid_to", "").strip()
        limit_raw = request.POST.get("usage_limit", "100").strip()
        min_ord_raw = request.POST.get("min_order", "0").strip()
        is_active = request.POST.get("is_active") == "on"

        if not code:
            messages.error(request, "Coupon code is required.")
            return redirect("coupons:list")

        try:
            val = Decimal(val_raw)
            v_from = date.fromisoformat(v_from_raw)
            v_to = date.fromisoformat(v_to_raw)
            ulim = int(limit_raw)
            min_ord = Decimal(min_ord_raw)
        except Exception as e:
            messages.error(request, f"Invalid coupon input: {e}")
            return redirect("coupons:list")

        if v_from > v_to:
            messages.error(request, "Valid-from date cannot be after valid-to date.")
            return redirect("coupons:list")

        coupon, created = Coupon.objects.update_or_create(
            code=code,
            defaults={
                "discount_type": dtype,
                "value": val,
                "valid_from": v_from,
                "valid_to": v_to,
                "usage_limit": ulim,
                "min_order": min_ord,
                "is_active": is_active,
            },
        )
        log_audit_event(
            request=request,
            action="Coupon saved",
            category="Security",
            record_id=coupon.code,
            change_summary=f"Saved coupon {coupon.code} ({coupon.discount_display})",
        )
        messages.success(request, f"Coupon '{coupon.code}' saved successfully.")
        return redirect("coupons:list")

    coupons = Coupon.objects.all()

    return render(
        request,
        "admin/coupons.html",
        {
            "coupons": coupons,
            "today": date.today(),
            "active_nav": "coupons",
        },
    )
