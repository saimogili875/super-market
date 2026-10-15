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
    return render(request, "menu/admin/dashboard.html", context)


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
