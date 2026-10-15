"""Reusable RBAC primitives — role guard, object scoping, role check."""
import functools

from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404


def has_role(user, *roles):
    """Return True if the authenticated user's role is in the given set.

    Usage::

        if has_role(request.user, "ADMIN", "AGENT"):
            ...
    """
    return user.is_authenticated and user.role in roles


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

                login_url = getattr(settings, "LOGIN_URL", "/backoffice/login/")
                return redirect(f"{login_url}?next={request.path}")
            if not has_role(request.user, *roles):
                raise PermissionDenied
            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator


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
