"""Development settings — DEBUG=True, permissive hosts, console email.

Overrides Redis-backed CACHES and CHANNEL_LAYERS with in-memory backends
so the app runs without Docker / Redis in local development.
"""
from .base import *  # noqa: F401, F403

DEBUG = True

ALLOWED_HOSTS = ["*"]

# ---------- email ----------
EMAIL_BACKEND = env("EMAIL_BACKEND", default="django.core.mail.backends.smtp.EmailBackend")

# ---------- caches (no Redis needed in dev) ----------
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    },
}

# ---------- channel layers (no Redis needed in dev) ----------
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels.layers.InMemoryChannelLayer",
    },
}

# ---------- rate limiting ----------
# Disable in dev so views never 500 on missing Redis.
RATELIMIT_ENABLE = False

