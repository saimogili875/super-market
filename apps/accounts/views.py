"""Login and logout views with role-aware redirect and progressive lockout."""
from django.contrib.auth import authenticate, login as auth_login
from django.contrib.auth import views as auth_views
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme

from apps.core.ratelimits import login as login_ratelimit

from .models import LoginAttempt, Role, User


def _get_client_ip(request):
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "127.0.0.1")


class RoleLoginView(auth_views.LoginView):
    """Login view with iPhone-style progressive lockout and role-based redirect.

    Lockout enforcement (per username + IP pair):
        Attempts 1-2 → no lockout
        Attempt 3    → 1 minute
        Attempt 4    → 5 minutes
        Attempt 5    → 15 minutes
        Attempt 6    → 60 minutes
        Attempt 7+   → 24 hours (requires admin unlock)

    Admin-role users are exempt from lockout entirely.
    """

    template_name = "accounts/login.html"
    redirect_authenticated_user = True

    def get_success_url(self):
        # Honour ?next= if it's safe.
        redirect_to = self.request.POST.get(
            self.redirect_field_name,
            self.request.GET.get(self.redirect_field_name, ""),
        )
        if redirect_to and url_has_allowed_host_and_scheme(
            url=redirect_to,
            allowed_hosts={self.request.get_host()},
            require_https=self.request.is_secure(),
        ):
            return redirect_to

        user = self.request.user
        if user.role == "ADMIN":
            return reverse("orders_admin:dashboard")
        if user.role == "AGENT":
            return reverse("orders_agent:dashboard")
        # CUSTOMER or anything else → delivery menu
        return reverse("orders_customer:menu")

    def _is_admin_user(self, username):
        """Check if the given username belongs to an ADMIN-role user."""
        try:
            return User.objects.only("role").get(username=username).role == Role.ADMIN
        except User.DoesNotExist:
            return False

    def post(self, request, *args, **kwargs):
        """Override POST to enforce progressive lockout before authentication."""
        form = self.get_form()
        username = request.POST.get("username", "").strip()
        client_ip = _get_client_ip(request)

        # Admin-role users are exempt from lockout.
        if username and not self._is_admin_user(username):
            tracker, _ = LoginAttempt.objects.get_or_create(
                username=username, ip_address=client_ip
            )

            # If currently locked out, reject immediately (even correct passwords).
            if tracker.is_locked:
                if tracker.requires_admin_unlock:
                    lockout_msg = (
                        "Account locked due to too many failed attempts. "
                        "Please contact an administrator to unlock your account."
                    )
                else:
                    remaining = tracker.remaining_lockout_display
                    lockout_msg = (
                        f"Too many failed attempts. Try again in {remaining}."
                    )
                return self.render_to_response(
                    self.get_context_data(form=form, lockout_message=lockout_msg)
                )

        # Attempt authentication via the standard form validation.
        if form.is_valid():
            # Successful login — reset lockout tracker for this IP.
            user = form.get_user()
            if user.role != Role.ADMIN:
                LoginAttempt.objects.filter(
                    username=user.username, ip_address=client_ip
                ).update(failed_attempts=0, locked_until=None)
            auth_login(request, user)
            return self.form_valid(form)

        # Authentication failed — record the failure.
        if username and not self._is_admin_user(username):
            tracker, _ = LoginAttempt.objects.get_or_create(
                username=username, ip_address=client_ip
            )
            tracker.record_failure()

            # If this failure just triggered a lockout, show lockout message
            # instead of the generic credential error.
            if tracker.is_locked:
                if tracker.requires_admin_unlock:
                    lockout_msg = (
                        "Account locked due to too many failed attempts. "
                        "Please contact an administrator to unlock your account."
                    )
                else:
                    remaining = tracker.remaining_lockout_display
                    lockout_msg = (
                        f"Too many failed attempts. Try again in {remaining}."
                    )
                return self.render_to_response(
                    self.get_context_data(form=form, lockout_message=lockout_msg)
                )

        return self.form_invalid(form)

    def form_valid(self, form):
        """Skip the parent's auth_login — we already called it in post()."""
        from django.http import HttpResponseRedirect

        return HttpResponseRedirect(self.get_success_url())

    @classmethod
    def as_view(cls, **initkwargs):
        view = super().as_view(**initkwargs)
        # Apply rate-limiting to the login view (POST only, 5/min per IP).
        return login_ratelimit(view)
