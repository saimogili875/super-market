"""Django Admin configuration for the Menu app."""
from django.contrib import admin
from django.utils.html import format_html

from .models import Category, MenuItem
from apps.core.templatetags.currency import CURRENCY_SYMBOL


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    """Admin for menu categories."""

    list_display = ("name", "sort_order", "is_active")
    list_editable = ("sort_order", "is_active")
    search_fields = ("name",)


@admin.register(MenuItem)
class MenuItemAdmin(admin.ModelAdmin):
    """Admin for menu items."""

    list_display = (
        "name",
        "category",
        "price",
        "offer_percent",
        "get_effective_price",
        "is_available",
        "prep_minutes",
    )
    list_filter = ("category", "is_available")
    list_select_related = ("category",)
    list_per_page = 50
    list_editable = ("is_available",)
    search_fields = ("name",)
    autocomplete_fields = ("category",)

    @admin.display(description="Effective Price")
    def get_effective_price(self, obj: MenuItem):
        """Read-only computed price showing discount math."""
        if obj.offer_percent > 0:
            return format_html("<b>{}{}</b>", CURRENCY_SYMBOL, obj.effective_price)
        return f"{CURRENCY_SYMBOL}{obj.effective_price}"

    def save_model(self, request, obj, form, change):
        """Hook into save to compress images if they changed."""
        if change and "image" in form.changed_data:
            from .services import compress_image
            compress_image(obj.image)
        elif not change and obj.image:
            from .services import compress_image
            compress_image(obj.image)
        super().save_model(request, obj, form, change)
