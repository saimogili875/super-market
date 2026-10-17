"""Views for Supplier and Purchase Order procurement management."""
from datetime import date
from decimal import Decimal
from django.contrib import messages
from django.db import models, transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.audit.models import log_audit_event
from apps.core.permissions import staff_required
from apps.menu.models import MenuItem, StockMovement
from .models import PurchaseOrder, Supplier


@staff_required
def supplier_list(request):
    """Supplier directory, purchase order creation, and delivery tracking."""
    if request.method == "POST":
        action = request.POST.get("action")

        if action == "add_supplier":
            name = request.POST.get("name", "").strip()
            contact = request.POST.get("contact", "").strip()
            email = request.POST.get("email", "").strip()
            phone = request.POST.get("phone", "").strip()
            address = request.POST.get("address", "").strip()
            status = request.POST.get("status", "Active")

            if not name:
                messages.error(request, "Supplier name is required.")
            else:
                supplier = Supplier.objects.create(
                    name=name, contact=contact, email=email, phone=phone, address=address, status=status
                )
                log_audit_event(
                    request=request,
                    action="Supplier added",
                    category="Products",
                    record_id=f"SUP-{supplier.pk}",
                    change_summary=f"Added supplier '{name}'",
                )
                messages.success(request, f"Supplier '{name}' created successfully.")
            return redirect("suppliers:list")

        elif action == "create_po":
            supplier_id = request.POST.get("supplier_id")
            product_name = request.POST.get("product_name", "").strip()
            qty = int(request.POST.get("quantity") or 1)
            unit_cost = Decimal(request.POST.get("unit_cost") or "0.00")
            status = request.POST.get("status", "Draft")

            supplier = get_object_or_404(Supplier, pk=supplier_id)
            import uuid
            po_num = f"PO-{uuid.uuid4().hex[:4].upper()}"

            # Link to existing product if matched by name
            item = MenuItem.objects.filter(name__iexact=product_name).first()

            po = PurchaseOrder.objects.create(
                po_number=po_num,
                supplier=supplier,
                product_name=product_name,
                item=item,
                quantity=qty,
                unit_cost=unit_cost,
                total_cost=Decimal(qty) * unit_cost,
                status=status,
                expected_delivery=date.today() + timezone.timedelta(days=3),
            )
            log_audit_event(
                request=request,
                action="Purchase order created",
                category="Inventory",
                record_id=po.po_number,
                change_summary=f"Ordered {qty} of '{product_name}' at ₹{unit_cost}/unit from {supplier.name}",
            )
            messages.success(request, f"Purchase order {po.po_number} created.")
            return redirect("suppliers:list")

    # Search & filters
    q = request.GET.get("q", "").strip()
    status_filter = request.GET.get("status", "All")

    suppliers = Supplier.objects.all()
    if q:
        suppliers = suppliers.filter(models.Q(name__icontains=q) | models.Q(contact__icontains=q))
    if status_filter in ["Active", "Inactive"]:
        suppliers = suppliers.filter(status=status_filter)

    all_suppliers = Supplier.objects.filter(status="Active")
    all_products = MenuItem.objects.filter(is_available=True)[:50]
    recent_pos = PurchaseOrder.objects.select_related("supplier", "item").order_by("-created_at")[:15]

    return render(
        request,
        "admin/suppliers.html",
        {
            "suppliers": suppliers,
            "all_suppliers": all_suppliers,
            "all_products": all_products,
            "recent_pos": recent_pos,
            "q": q,
            "status_filter": status_filter,
            "active_nav": "suppliers",
        },
    )


@staff_required
@transaction.atomic
def receive_po(request, pk):
    """Mark PO as received, update stock quantity, and create stock movement record."""
    po = get_object_or_404(PurchaseOrder, pk=pk)
    if po.status != "Complete":
        po.status = "Complete"
        po.received_quantity = po.quantity
        po.received_at = timezone.now()
        po.save()

        # Update product stock if item is linked
        if po.item:
            old_qty = po.item.stock_quantity
            new_qty = old_qty + po.quantity
            po.item.stock_quantity = new_qty
            po.item.is_available = True
            po.item.save()

            StockMovement.objects.create(
                item=po.item,
                movement_type="RESTOCK",
                quantity=po.quantity,
                resulting_quantity=new_qty,
                cost_per_unit=po.unit_cost,
                notes=f"Goods received via {po.po_number}",
                created_by=request.user,
            )

        log_audit_event(
            request=request,
            action="PO delivery received",
            category="Inventory",
            record_id=po.po_number,
            change_summary=f"Received {po.quantity} items for {po.product_name}",
        )
        messages.success(request, f"PO {po.po_number} marked complete and stock updated.")
    return redirect("suppliers:list")
