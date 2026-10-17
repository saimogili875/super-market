"""Admin frontend views for the menu app — list + full CRUD.

Thin views: forms do validation, services do side effects (image compression,
cache invalidation via the model save hooks). All views are role_required("ADMIN").
"""
from django.contrib import messages
from django.db.models import Prefetch, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_http_methods

from apps.core.permissions import role_required

from .forms import CategoryForm, MenuItemForm
from .models import Category, MenuItem
from .services import compress_image


@require_GET
@role_required("ADMIN")
def menu_management(request):
    """Admin frontend view for managing menu items (list + search/filter)."""
    q = request.GET.get("q", "").strip()
    category = request.GET.get("category", "")

    item_qs = MenuItem.objects.all().order_by("name")
    if q:
        item_qs = item_qs.filter(Q(name__icontains=q) | Q(description__icontains=q))
    if category and category != "all":
        item_qs = item_qs.filter(category_id=category)

    categories = Category.objects.prefetch_related(
        Prefetch("items", queryset=item_qs)
    ).order_by("sort_order", "name")
    all_categories = Category.objects.all().order_by("sort_order", "name")
    has_results = any(len(cat.items.all()) > 0 for cat in categories)

    context = {
        "categories": categories,
        "all_categories": all_categories,
        "has_results": has_results,
        "q": q,
        "category": category,
    }
    if request.headers.get("HX-Request"):
        return render(request, "menu/admin/partials/results.html", context)
    return render(request, "admin/products.html", context)


# ---------------------------------------------------------------------------
# Category CRUD
# ---------------------------------------------------------------------------

@require_http_methods(["GET", "POST"])
@role_required("ADMIN")
def category_create(request):
    """Create a new menu category."""
    form = CategoryForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        category = form.save()
        messages.success(request, f"Category '{category.name}' created.")
        return redirect("menu:management")
    return render(
        request,
        "menu/admin/category_form.html",
        {"form": form, "mode": "create"},
    )


@require_http_methods(["GET", "POST"])
@role_required("ADMIN")
def category_edit(request, pk):
    """Edit an existing menu category."""
    category = get_object_or_404(Category, pk=pk)
    form = CategoryForm(request.POST or None, instance=category)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f"Category '{category.name}' updated.")
        return redirect("menu:management")
    return render(
        request,
        "menu/admin/category_form.html",
        {"form": form, "mode": "edit", "category": category},
    )


# ---------------------------------------------------------------------------
# Menu-item CRUD
# ---------------------------------------------------------------------------

@require_http_methods(["GET", "POST"])
@role_required("ADMIN")
def item_create(request):
    """Create a new menu item (compresses any uploaded image)."""
    form = MenuItemForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        item = form.save(commit=False)
        if item.image:
            compress_image(item.image)
        item.save()
        messages.success(request, f"Item '{item.name}' created.")
        return redirect("menu:management")
    return render(request, "menu/admin/item_form.html", {"form": form, "mode": "create"})


@require_http_methods(["GET", "POST"])
@role_required("ADMIN")
def item_edit(request, pk):
    """Edit an existing menu item (re-compresses a newly uploaded image)."""
    item = get_object_or_404(MenuItem, pk=pk)
    form = MenuItemForm(request.POST or None, request.FILES or None, instance=item)
    if request.method == "POST" and form.is_valid():
        item = form.save(commit=False)
        if "image" in form.changed_data and item.image:
            compress_image(item.image)
        item.save()
        messages.success(request, f"Item '{item.name}' updated.")
        return redirect("menu:management")
    return render(
        request,
        "menu/admin/item_form.html",
        {"form": form, "mode": "edit", "item": item},
    )


@require_http_methods(["POST"])
@role_required("ADMIN")
def item_delete(request, pk):
    """Delete a menu item."""
    item = get_object_or_404(MenuItem, pk=pk)
    name = item.name
    item.delete()
    messages.success(request, f"Item '{name}' deleted.")
    return redirect("menu:management")


# ---------------------------------------------------------------------------
# Supermarket Executive Dashboard & Modules
# ---------------------------------------------------------------------------

@require_GET
@role_required("ADMIN")
def supermarket_dashboard(request):
    """Executive KPI view showing live supermarket metrics and action tables."""
    from datetime import date, timedelta
    from decimal import Decimal
    from django.db.models import Sum
    from apps.customer_auth.models import Customer
    from apps.orders.models import Order
    from apps.payments.models import PaymentTransaction
    from apps.suppliers.models import PurchaseOrder

    today = date.today()
    total_products = MenuItem.objects.count()
    active_products = MenuItem.objects.filter(is_available=True).count()
    
    # Inventory metrics
    low_stock_items = [item for item in MenuItem.objects.filter(track_stock=True) if item.is_low_stock]
    out_of_stock_items = [item for item in MenuItem.objects.filter(track_stock=True) if item.is_out_of_stock]
    near_expiry_items = [item for item in MenuItem.objects.filter(expiry_date__isnull=False) if item.is_near_expiry or item.is_expired]

    # Customers & Sales
    total_customers = Customer.objects.count()
    
    today_orders = Order.objects.filter(created_at__date=today)
    today_orders_count = today_orders.count()
    
    today_sales_agg = today_orders.filter(status__in=["PAID", "READY", "COLLECT"]).aggregate(total=Sum("total_amount"))
    today_sales = today_sales_agg["total"] or Decimal("0.00")

    # Recent transactions
    recent_transactions = PaymentTransaction.objects.all().order_by("-created_at")[:6]
    
    # Open Purchase Orders
    open_pos = PurchaseOrder.objects.filter(status__in=["Draft", "Submitted", "Partial"]).select_related("supplier")[:5]

    context = {
        "total_products": total_products,
        "active_products": active_products,
        "low_stock_count": len(low_stock_items),
        "out_of_stock_count": len(out_of_stock_items),
        "near_expiry_count": len(near_expiry_items),
        "total_customers": total_customers,
        "today_orders_count": today_orders_count,
        "today_sales": today_sales,
        "low_stock_items": low_stock_items[:8],
        "near_expiry_items": near_expiry_items[:8],
        "recent_transactions": recent_transactions,
        "open_pos": open_pos,
        "active_nav": "dashboard",
    }
    return render(request, "admin/dashboard.html", context)


@require_http_methods(["GET", "POST"])
@role_required("ADMIN")
def inventory_management(request):
    """Inventory tracking, low stock alerts, near-expiry items, and stock corrections."""
    from datetime import date, timedelta
    from apps.audit.models import log_audit_event
    from .models import StockMovement

    today = date.today()

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "stock_adjust":
            item_id = request.POST.get("item_id")
            movement_type = request.POST.get("movement_type", "CORRECTION")
            qty_change_raw = request.POST.get("quantity", "0").strip()
            notes = request.POST.get("notes", "").strip()

            item = get_object_or_404(MenuItem, pk=item_id)
            try:
                qty_change = int(qty_change_raw)
            except ValueError:
                messages.error(request, "Invalid quantity adjustment value.")
                return redirect("menu:inventory")

            old_qty = item.stock_quantity
            new_qty = max(0, old_qty + qty_change)
            item.stock_quantity = new_qty
            item.track_stock = True
            item.is_available = new_qty > 0
            item.save()

            StockMovement.objects.create(
                item=item,
                movement_type=movement_type,
                quantity=qty_change,
                resulting_quantity=new_qty,
                cost_per_unit=item.cost_price,
                notes=notes or f"Manual adjustment from {old_qty} to {new_qty}",
                created_by=request.user,
            )

            log_audit_event(
                request=request,
                action="Stock adjusted",
                category="Inventory",
                record_id=item.sku or f"PRD-{item.pk}",
                change_summary=f"Changed {old_qty} to {new_qty} ({qty_change:+d}) [{movement_type}]",
            )
            messages.success(request, f"Stock for '{item.name}' updated to {new_qty} {item.unit}.")
            return redirect("menu:inventory")

    # Filtered inventory queries
    low_stock_items = [i for i in MenuItem.objects.filter(track_stock=True).select_related("category") if i.is_low_stock or i.is_out_of_stock]
    near_expiry_items = [i for i in MenuItem.objects.filter(expiry_date__isnull=False).select_related("category") if i.is_near_expiry or i.is_expired]
    recent_movements = StockMovement.objects.select_related("item", "created_by").order_by("-created_at")[:25]
    all_products = MenuItem.objects.all().order_by("name")

    return render(
        request,
        "admin/inventory.html",
        {
            "low_stock_items": low_stock_items,
            "near_expiry_items": near_expiry_items,
            "recent_movements": recent_movements,
            "all_products": all_products,
            "active_nav": "inventory",
        },
    )


@require_http_methods(["GET", "POST"])
@role_required("ADMIN")
def import_export_view(request):
    """CSV Import preview and data exporters for Products, Orders, Customers, and Logs."""
    import csv
    import io
    from datetime import date
    from decimal import Decimal
    from django.http import HttpResponse
    from apps.audit.models import AuditLog, log_audit_event
    from apps.customer_auth.models import Customer
    from apps.orders.models import Order

    preview_rows = []
    file_uploaded = False

    if request.method == "POST":
        action = request.POST.get("action")

        if action == "upload_preview":
            csv_file = request.FILES.get("file")
            if not csv_file or not csv_file.name.endswith(".csv"):
                messages.error(request, "Please upload a valid .csv file.")
            else:
                try:
                    decoded = csv_file.read().decode("utf-8", errors="replace")
                    reader = csv.DictReader(io.StringIO(decoded))
                    for idx, row in enumerate(reader, start=1):
                        p_name = row.get("product_name") or row.get("Product") or row.get("name") or ""
                        p_price = row.get("price") or row.get("Price") or ""
                        p_sku = row.get("sku") or row.get("SKU") or f"SKU-IMP-{idx:03d}"
                        
                        # Validation checks
                        if not p_name:
                            res_status = "er"
                            res_label = "Name required"
                        elif not p_price:
                            res_status = "er"
                            res_label = "Price required"
                        elif MenuItem.objects.filter(sku=p_sku).exists():
                            res_status = "wn"
                            res_label = "Duplicate SKU"
                        else:
                            res_status = "ok"
                            res_label = "Valid"

                        preview_rows.append({
                            "row": idx,
                            "name": p_name,
                            "price": p_price,
                            "sku": p_sku,
                            "status": res_status,
                            "label": res_label,
                        })
                    file_uploaded = True
                    request.session["csv_import_data"] = [r for r in preview_rows if r["status"] == "ok"]
                except Exception as e:
                    messages.error(request, f"Error parsing CSV: {e}")

        elif action == "commit_import":
            valid_rows = request.session.get("csv_import_data", [])
            default_cat = Category.objects.first()
            imported_count = 0

            for r in valid_rows:
                try:
                    price_val = Decimal(r["price"])
                    item, created = MenuItem.objects.update_or_create(
                        sku=r["sku"],
                        defaults={
                            "name": r["name"],
                            "price": price_val,
                            "category": default_cat,
                            "is_available": True,
                        },
                    )
                    imported_count += 1
                except Exception:
                    continue

            log_audit_event(
                request=request,
                action="Products imported",
                category="Products",
                change_summary=f"Imported {imported_count} products via CSV upload",
            )
            messages.success(request, f"Successfully imported {imported_count} products into the catalog.")
            request.session.pop("csv_import_data", None)
            return redirect("menu:management")

    # Export functionality via GET
    export_dataset = request.GET.get("dataset")
    if export_dataset:
        today_str = date.today().isoformat()
        response = HttpResponse(content_type="text/csv")

        if export_dataset == "products":
            response["Content-Disposition"] = f'attachment; filename="supermarket_products_{today_str}.csv"'
            writer = csv.writer(response)
            writer.writerow(["SKU", "Name", "Category", "Price", "Cost Price", "Stock", "Unit", "Expiry Date", "Available"])
            for item in MenuItem.objects.select_related("category").all():
                writer.writerow([item.sku, item.name, item.category.name, item.price, item.cost_price or 0, item.stock_quantity, item.unit, item.expiry_date or "", item.is_available])
            
            log_audit_event(request=request, action="CSV Export", category="Products", change_summary="Exported products CSV")
            return response

        elif export_dataset == "orders":
            response["Content-Disposition"] = f'attachment; filename="supermarket_orders_{today_str}.csv"'
            writer = csv.writer(response)
            writer.writerow(["Order ID", "Customer", "Phone", "Type", "Status", "Total Amount", "Date"])
            for ord in Order.objects.all().order_by("-created_at")[:500]:
                writer.writerow([ord.pk, ord.contact_name or "Walk-in", ord.contact_phone, ord.order_type, ord.status, ord.total_amount, ord.created_at.strftime("%Y-%m-%d %H:%M")])
            
            log_audit_event(request=request, action="CSV Export", category="Orders", change_summary="Exported orders CSV")
            return response

        elif export_dataset == "customers":
            response["Content-Disposition"] = f'attachment; filename="supermarket_customers_{today_str}.csv"'
            writer = csv.writer(response)
            writer.writerow(["Phone", "Email", "Name", "Default Address", "Registered Date"])
            for cust in Customer.objects.all():
                writer.writerow([cust.phone, cust.email, cust.name, cust.default_address, cust.created_at.strftime("%Y-%m-%d")])
            
            log_audit_event(request=request, action="CSV Export", category="Security", change_summary="Exported customers CSV")
            return response

    return render(
        request,
        "admin/import_export.html",
        {
            "preview_rows": preview_rows,
            "file_uploaded": file_uploaded,
            "active_nav": "import_export",
        },
    )

