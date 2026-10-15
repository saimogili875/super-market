"""Context processors for customer delivery pages."""

def delivery_cart(request):
    """Expose cart_count and delivery_customer across all customer delivery templates."""
    cart_raw = request.session.get("delv_cart", {})
    cart_count = sum(v for v in cart_raw.values() if isinstance(v, int) and v > 0)

    customer = getattr(request, "delivery_customer", None)
    if not customer:
        from apps.customer_auth.views import get_logged_in_customer
        customer = get_logged_in_customer(request)

    return {
        "cart_count": cart_count,
        "delivery_customer": customer,
    }
