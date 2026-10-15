"""Currency template filter — single-source formatting for all displayed money.

Usage in templates::

    {% load currency %}
    {{ amount|money }}          →  ₹1,250.00
    {{ amount|money_int }}      →  ₹1,250

The currency symbol is defined exactly once in CURRENCY_SYMBOL. To switch back
to dollars (or any other currency) change only that constant.
"""
from decimal import Decimal, InvalidOperation

from django import template

register = template.Library()

# ── Single-source currency symbol ──────────────────────────────────────────
CURRENCY_SYMBOL = "₹"


def _format_amount(value, decimal_places: int = 2) -> str:
    """Format *value* as currency with the project symbol.

    Returns ``₹1,234.56`` (or ``₹1,234`` when *decimal_places* is 0).
    Uses standard international comma grouping (thousands).
    """
    try:
        num = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return f"{CURRENCY_SYMBOL}{value}"

    if decimal_places > 0:
        fmt = f",.{decimal_places}f"
    else:
        fmt = ",.0f"

    return f"{CURRENCY_SYMBOL}{num:{fmt}}"


@register.filter(name="money")
def money(value):
    """Format a numeric value as currency with 2 decimal places.

    Example: ``{{ 1250|money }}`` → ``₹1,250.00``
    """
    return _format_amount(value, decimal_places=2)


@register.filter(name="money_int")
def money_int(value):
    """Format a numeric value as currency with no decimal places.

    Example: ``{{ 1250|money_int }}`` → ``₹1,250``
    """
    return _format_amount(value, decimal_places=0)


@register.filter(name="cart_qty")
def cart_qty(cart_items, item_id):
    """Return quantity of item_id in cart_items list or dict.

    Example: ``{{ cart_items|cart_qty:item.pk }}`` → ``2``
    """
    if not cart_items:
        return 0
    if isinstance(cart_items, dict):
        return cart_items.get(str(item_id), 0) or cart_items.get(int(item_id), 0)
    for entry in cart_items:
        item = entry.get("item")
        if item and getattr(item, "pk", None) == item_id:
            return entry.get("quantity", 0)
    return 0

