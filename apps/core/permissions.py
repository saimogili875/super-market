"""Reusable RBAC primitives — role guard, object scoping, role check."""
import functools

from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404


ADMIN_ROLES = ("ADMIN", "MANAGER")
STAFF_ROLES = ("ADMIN", "MANAGER", "INVENTORY", "CASHIER")


def has_role(user, *roles):
    """Return True if the authenticated user's role is in the given set or is superuser.

    Usage::

        if has_role(request.user, "ADMIN", "AGENT"):
            ...
    """
    if not (user and user.is_authenticated):
        return False
    if user.is_superuser:
        return True
    # If checking for "ADMIN", also accept "MANAGER" for general admin views
    effective_roles = set(roles)
    if "ADMIN" in effective_roles:
        effective_roles.add("MANAGER")
    return user.role in effective_roles


def role_required(*roles):
    """Decorator for function-based views.

    Anonymous users are redirected to the login page.
    Authenticated users with the wrong role get 403.

    Usage::

        @role_required("ADMIN")
        def dashboard(request):
            ...
    """

    def decorator(view_func):
        @functools.wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                from django.conf import settings
                from django.shortcuts import redirect

                login_url = getattr(settings, "LOGIN_URL", "/accounts/login/")
                return redirect(f"{login_url}?next={request.path}")
            if not has_role(request.user, *roles):
                raise PermissionDenied
            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator


admin_required = role_required(*ADMIN_ROLES)
super_admin_required = role_required("ADMIN")
manager_required = role_required("ADMIN", "MANAGER")
inventory_required = role_required("ADMIN", "MANAGER", "INVENTORY")
cashier_required = role_required("ADMIN", "MANAGER", "CASHIER")
staff_required = role_required(*STAFF_ROLES)


class RoleRequiredMixin:
    """CBV mixin — set ``allowed_roles`` on the view class.

    Usage::

        class AgentDashboard(RoleRequiredMixin, TemplateView):
            allowed_roles = ("AGENT",)
    """

    allowed_roles: tuple = ()

    def dispatch(self, request, *args, **kwargs):
        if not has_role(request.user, *self.allowed_roles):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)


def scoped_get(model, **filters):
    """Fetch ONE object with an ownership/tenancy filter to prevent IDOR.

    Callers MUST include a filter that ties the object to the requesting user.
    Never fetch by pk alone.

    Usage::

        profile = scoped_get(AgentProfile, user=request.user, pk=profile_id)

    Raises Http404 if no matching object exists (ownership mismatch or absent).
    """
    return get_object_or_404(model, **filters)
