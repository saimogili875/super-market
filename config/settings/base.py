"""Shared settings — reads all config from environment via django-environ."""
import os
from pathlib import Path

import environ

# ---------- paths ----------
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# ---------- environment ----------
env = environ.Env(
    DEBUG=(bool, False),
    ALLOWED_HOSTS=(list, []),
)
environ.Env.read_env(os.path.join(BASE_DIR, ".env"))

# ---------- security ----------
SECRET_KEY = env("SECRET_KEY")

DEBUG = env("DEBUG")

ALLOWED_HOSTS = env("ALLOWED_HOSTS")

AUTH_USER_MODEL = "accounts.User"

# ---------- apps ----------
INSTALLED_APPS = [
    "daphne",
    "channels",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # project apps
    "apps.accounts",
    "apps.analytics",
    "apps.audit",
    "apps.core",
    "apps.coupons",
    "apps.customer_auth",
    "apps.menu",
    "apps.notifications",
    "apps.orders",
    "apps.payments",
    "apps.realtime",
    "apps.swecha",
    "apps.suppliers",
    "apps.tables",
]

# ---------- middleware ----------
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "csp.middleware.CSPMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

# ---------- urls ----------
ROOT_URLCONF = "config.urls"

# ---------- templates ----------
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.orders.context_processors.delivery_cart",
                "apps.core.context_processors.brand_context",
                "apps.core.context_processors.admin_context",
            ],
        },
    },
]

# ---------- asgi / wsgi ----------
ASGI_APPLICATION = "config.asgi.application"
WSGI_APPLICATION = "config.wsgi.application"

# ---------- database ----------
DATABASES = {
    "default": env.db("DATABASE_URL"),
}
# avoids per-request connect overhead on the small VPS
DATABASES["default"]["CONN_MAX_AGE"] = 60
# connect_timeout is a PostgreSQL-only option; skip it on SQLite (dev).
if "postgresql" in DATABASES["default"].get("ENGINE", ""):
    DATABASES["default"]["OPTIONS"] = {"connect_timeout": 5}

# ---------- caches & channel layers ----------
REDIS_URL = env("REDIS_URL", default="redis://localhost:6379/0")

if "localhost" in REDIS_URL or "127.0.0.1" in REDIS_URL:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        }
    }
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels.layers.InMemoryChannelLayer",
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": REDIS_URL,
        },
    }
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels_redis.core.RedisChannelLayer",
            "CONFIG": {
                "hosts": [REDIS_URL],
            },
        },
    }

# ---------- password validation ----------
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ---------- i18n ----------
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# ---------- static files ----------
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        # serves compressed static assets from the app process without a separate CDN, low overhead.
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

# ---------- media (user uploads, e.g. menu item images) ----------
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# ---------- auth redirects ----------
LOGIN_URL = "/accounts/login/"
LOGIN_REDIRECT_URL = "/accounts/login/"   # RoleLoginView.get_success_url overrides per role
LOGOUT_REDIRECT_URL = "/accounts/login/"

# ---------- CSP ----------
# django-csp >= 4 uses CONTENT_SECURITY_POLICY dictionary
CONTENT_SECURITY_POLICY = {
    "DIRECTIVES": {
        "default-src": ["'self'"],
        # HTMX and Alpine loaded from unpkg
        "script-src": ["'self'", "'unsafe-inline'", "https://unpkg.com"],
        # Templates use inline styles and Google Fonts
        "style-src": ["'self'", "'unsafe-inline'", "https://fonts.googleapis.com"],
        # Local + data uris + blob + external images
        "img-src": ["'self'", "data:", "blob:", "https:"],
        # WebSocket status feed
        "connect-src": ["'self'", "ws:", "wss:"],
        "font-src": ["'self'", "https://fonts.gstatic.com", "data:"],
        "media-src": ["'self'", "data:", "blob:"],
        "frame-ancestors": ["'none'"],
        "base-uri": ["'self'"],
        "form-action": ["'self'"],
    }
}

# ---------- email ----------
EMAIL_BACKEND = env("EMAIL_BACKEND", default="django.core.mail.backends.smtp.EmailBackend")
EMAIL_HOST = env("EMAIL_HOST", default="smtp.gmail.com")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)
EMAIL_USE_SSL = env.bool("EMAIL_USE_SSL", default=False)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
DEFAULT_FROM_EMAIL = (
    env("DEFAULT_FROM_EMAIL", default="") or EMAIL_HOST_USER or "support@freshmart.com"
)
EMAIL_TIMEOUT = env.int("EMAIL_TIMEOUT", default=10)
RESEND_API_KEY = env("RESEND_API_KEY", default="")

# ---------- brand settings ----------
BRAND_NAME = env("BRAND_NAME", default="FreshMart")
BRAND_SHORT = env("BRAND_SHORT", default="FM")
BRAND_TAGLINE = env("BRAND_TAGLINE", default="Fresh groceries, delivered fast")
BRAND_PHONE = env("BRAND_PHONE", default="6281238410")
BRAND_PHONE_INTL = env("BRAND_PHONE_INTL", default="916281238410")
BRAND_EMAIL = env("BRAND_EMAIL", default="support@freshmart.com")
BRAND_LOCATION = env("BRAND_LOCATION", default="Hyderabad")


# ---------- AI Assistant (SWECHA) ----------
GROQ_API_KEY = env("GROQ_API_KEY", default="")
GROQ_MODEL = env("GROQ_MODEL", default="llama-3.3-70b-versatile")

# ---------- default primary key ----------
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------- test runner ----------
TEST_RUNNER = "config.test_runner.PytestTestRunner"

