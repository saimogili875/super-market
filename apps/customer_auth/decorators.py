import functools
from urllib.parse import quote

from django.http import HttpResponse
from django.shortcuts import redirect
from django.urls import reverse

from apps.customer_auth.views import get_logged_in_customer


def customer_login_required(view_func):
    """Decorator ensuring the request has a valid, authenticated Customer session.

    Redirects unauthenticated visitors to /login/?next=<current_path>.
    For HTMX/AJAX requests, returns 401 and sets HX-Redirect header.
    Redirects other logged-in roles (Agent, Manager, Admin) to their designated dashboards.
    """
    @functools.wraps(view_func)
    def wrapper(request, *args, **kwargs):
        user = getattr(request, "user", None)
        if user and user.is_authenticated:
            role = getattr(user, "role", None)
            if role == "AGENT":
                return redirect("orders_agent:dashboard")
            elif role in ("MGR", "STAFF", "INVENTORY", "CASHIER"):
                return redirect("manager:dashboard")
            elif role == "ADMIN":
                return redirect("orders_admin:dashboard")

        # No logged-in customer; proceed as guest (no redirect)
        customer = get_logged_in_customer(request)
        if customer:
            request.delivery_customer = customer
        return view_func(request, *args, **kwargs)

    return wrapper
