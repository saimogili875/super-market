"""ModelForms for admin-dashboard menu management (server-side validation).

Thin forms over the existing models — price stays Decimal, offer_percent is
bounded 0-100 by the model validators, and image compression is applied by the
view via menu.services.compress_image. Widgets get the design-system classes.
"""
from django import forms

from .models import Category, MenuItem


def _style(fields, css="form-input"):
    """Apply a design-system class to each bound widget."""
    for field in fields.values():
        widget = field.widget
        if isinstance(widget, forms.CheckboxInput):
            continue
        base = widget.attrs.get("class", "")
        widget.attrs["class"] = (base + " " + css).strip()


class CategoryForm(forms.ModelForm):
    """Create/edit a menu category."""

    class Meta:
        model = Category
        fields = ("name", "tag", "image", "sort_order", "is_active")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _style(self.fields)


class MenuItemForm(forms.ModelForm):
    """Create/edit a menu item (with optional image upload)."""

    class Meta:
        model = MenuItem
        fields = (
            "category",
            "name",
            "sku",
            "barcode",
            "unit",
            "price",
            "cost_price",
            "offer_percent",
            "prep_minutes",
            "track_stock",
            "stock_quantity",
            "low_stock_threshold",
            "expiry_date",
            "supplier",
            "description",
            "image",
            "is_available",
        )
        widgets = {
            "description": forms.Textarea(attrs={"rows": 2}),
            "expiry_date": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _style(self.fields)
        self.fields["stock_quantity"].required = False
        self.fields["track_stock"].required = False
        self.fields["sku"].required = False
        self.fields["barcode"].required = False
        self.fields["unit"].required = False
        self.fields["cost_price"].required = False
        self.fields["low_stock_threshold"].required = False
        self.fields["expiry_date"].required = False
        self.fields["supplier"].required = False
        self.fields["prep_minutes"].required = False

    def clean_stock_quantity(self):
        return self.cleaned_data.get("stock_quantity") or 0

    def clean_low_stock_threshold(self):
        return self.cleaned_data.get("low_stock_threshold") or 5
