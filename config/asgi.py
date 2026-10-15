"""ASGI entrypoint routing HTTP to Django and WebSockets to Channels.

The database and HTTP views are the source of truth. WebSockets carry
status-change notifications only, so the "websocket" branch is a thin,
origin-checked, authenticated router into the realtime consumers.
"""
import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

# Initialize Django's app registry before importing anything that touches models.
django_asgi_app = get_asgi_application()

from channels.auth import AuthMiddlewareStack  # noqa: E402
from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402
from channels.security.websocket import AllowedHostsOriginValidator  # noqa: E402

from apps.realtime.routing import websocket_urlpatterns  # noqa: E402

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        # Origin-checked (CSRF-analog for sockets) + session-authenticated.
        "websocket": AllowedHostsOriginValidator(
            AuthMiddlewareStack(URLRouter(websocket_urlpatterns))
        ),
    }
)
