"""Django Admin for orders — read-mostly, for visibility.

Status changes must go through services.transition(), which enforces the
state machine. The admin is intentionally read-heavy: status is read-only
in the detail view so nobody bypasses the workflow by accident.
"""
from django.contrib import admin

from .models import Order, OrderEvent, OrderItem


class OrderItemInline(admin.TabularInline):
    """Read-only inline showing line items on an order."""

    model = OrderItem
    extra = 0
    readonly_fields = (
        "menu_item",
        "name_snap",
        "unit_price",
        "quantity",
    )

    def has_add_permission(self, request, obj=None):
        """Prevent adding items via admin — use services.add_item_to_order."""
        return False

    def has_delete_permission(self, request, obj=None):
        """Prevent deleting items via admin."""
        return False


class OrderEventInline(admin.TabularInline):
    """Read-only inline showing the audit trail for an order."""

    model = OrderEvent
    extra = 0
    readonly_fields = ("from_status", "to_status", "actor", "at")

    def has_add_permission(self, request, obj=None):
        """Events are append-only via services.transition()."""
        return False

    def has_delete_permission(self, request, obj=None):
        """Events must never be deleted — they are the audit trail."""
        return False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    """Admin for orders — read-mostly.

    Status is read-only here. To change an order's status, use
    services.transition() (via the dashboard in Sprint 4). This
    prevents anyone from bypassing the state machine.
    """

    list_display = (
        "id",
        "order_type",
        "status",
        "table",
        "session",
        "total_amount",
        "created_at",
    )
    list_filter = ("status", "order_type")
    list_select_related = ("table", "session", "customer", "agent")
    list_per_page = 50
    date_hierarchy = "created_at"
    # Status is read-only: changes must go through services.transition()
    readonly_fields = ("status", "total_amount", "created_at", "updated_at")
    inlines = [OrderItemInline, OrderEventInline]
