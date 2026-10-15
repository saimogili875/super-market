import functools
from django.shortcuts import redirect
from apps.customer_auth.views import get_logged_in_customer


def customer_login_required(view_func):
    """Decorator ensuring the request has a valid, non-expired Customer session.

    Redirects unauthenticated visitors to customer_auth:login.
    Supports HTMX requests by setting HX-Redirect header.
    """
    @functools.wraps(view_func)
    def wrapper(request, *args, **kwargs):
        customer = get_logged_in_customer(request)
        if not customer:
            if request.headers.get("HX-Request"):
                response = redirect("customer_auth:login")
                response["HX-Redirect"] = response.url
                return response
            return redirect("customer_auth:login")
        request.delivery_customer = customer
        return view_func(request, *args, **kwargs)

    return wrapper
