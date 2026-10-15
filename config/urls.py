"""Root URL configuration — admin (env-configurable path), apps, and healthz."""
import environ
from django.contrib import admin
from django.urls import include, path

from apps.core.ratelimits import admin_login
from apps.core.views import contact, healthz, home

env = environ.Env()

# Admin lives at a non-default, env-driven path to shrink automated attack surface.
_admin_path = env("ADMIN_URL", default="admin/")

# Wrap admin login to protect against brute-force (avoids editing Django internals)
admin.site.login = admin_login(admin.site.login)

urlpatterns = [
    # Admin-scoped app endpoints must precede admin.site.urls so they resolve first.
    path(f"{_admin_path}menu/", include("apps.menu.urls")),
    path(f"{_admin_path}orders/", include("apps.orders.urls_admin")),
    path(f"{_admin_path}accounts/", include("apps.analytics.urls")),
    path(f"{_admin_path}agents/", include("apps.accounts.urls_admin")),
    path(f"{_admin_path}tables/", include("apps.tables.urls_admin")),
    path(_admin_path, admin.site.urls),
    # Customer delivery authentication & flow.
    path("order/auth/", include("apps.customer_auth.urls")),
    path("order/", include("apps.orders.urls_customer")),
    # Agent delivery dashboard (login required, role=AGENT).
    path("agent/", include("apps.orders.urls_agent")),
    # Authentication (login/logout for all roles).
    path("accounts/", include("apps.accounts.urls")),
    # Public landing page — must precede the tables include so "/" resolves here
    # while dine-in "t/<token>/" routes still match below.
    path("", home, name="home"),
    path("contact/", contact, name="contact"),
    # Dine-in flow (QR scan resolves by opaque token).
    path("", include("apps.tables.urls")),
    # Liveness probe.
    path("healthz", healthz, name="healthz"),
]

from django.conf import settings
from django.conf.urls.static import static

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATICFILES_DIRS[0])
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)


