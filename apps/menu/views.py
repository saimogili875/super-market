"""Thin endpoints for the menu app."""
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_POST

from apps.core.permissions import role_required

from . import services
from .models import MenuItem


@require_POST
@role_required("ADMIN")
def toggle_availability(request, pk):
    """Toggle the availability of a menu item."""
    item = get_object_or_404(MenuItem, pk=pk)
    updated_item = services.toggle_availability(item)
    # Return a fully functional HTMX button fragment
    from django.urls import reverse
    status = "Available" if updated_item.is_available else "Unavailable"
    btn_class = "btn-success" if updated_item.is_available else "btn-secondary"
    url = reverse("menu:toggle_availability", args=[updated_item.pk])
    html = (
        f'<button class="btn btn-sm {btn_class}" '
        f'hx-post="{url}" '
        f'hx-target="this" hx-swap="outerHTML">{status}</button>'
    )
    return HttpResponse(html)
