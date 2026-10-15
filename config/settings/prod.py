"""Production settings — security headers ON, DEBUG=False."""
from .base import *  # noqa: F401, F403

DEBUG = False

ALLOWED_HOSTS = env("ALLOWED_HOSTS")  # noqa: F405 — imported via base.*
DATABASES["default"]["CONN_MAX_AGE"] = env.int("CONN_MAX_AGE", default=60)  # noqa: F405

# ---------- media & static files storage (prod) ----------
# Static files served via WhiteNoise; media uploads persisted to S3/R2 cloud object storage.
STORAGES = {
    "default": {
        "BACKEND": "storages.backends.s3.S3Storage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedStaticFilesStorage",
    },
}

# S3 / Cloudflare R2 / Object Storage Configuration
AWS_STORAGE_BUCKET_NAME = env("AWS_STORAGE_BUCKET_NAME", default="")  # noqa: F405
AWS_S3_REGION_NAME = env("AWS_S3_REGION_NAME", default="auto")  # noqa: F405
AWS_S3_ENDPOINT_URL = env("AWS_S3_ENDPOINT_URL", default="")  # noqa: F405
AWS_ACCESS_KEY_ID = env("AWS_ACCESS_KEY_ID", default="")  # noqa: F405
AWS_SECRET_ACCESS_KEY = env("AWS_SECRET_ACCESS_KEY", default="")  # noqa: F405
AWS_S3_CUSTOM_DOMAIN = env("AWS_S3_CUSTOM_DOMAIN", default="")  # noqa: F405
AWS_QUERYSTRING_AUTH = env.bool("AWS_QUERYSTRING_AUTH", default=False)  # noqa: F405
AWS_S3_OBJECT_PARAMETERS = {
    "CacheControl": "max-age=86400",
}

# ---------- template caching (RAM/CPU lever, prod only) ----------
# Templates never change at runtime in prod, so parse each one ONCE and reuse
# the compiled form for the process's life. The cached loader wraps the normal
# filesystem + app-directory loaders; APP_DIRS must be False when loaders are
# set explicitly. Dev keeps auto-reloading loaders (base.py APP_DIRS=True).
TEMPLATES[0]["APP_DIRS"] = False  # noqa: F405 — imported via base.*
TEMPLATES[0]["OPTIONS"]["loaders"] = [  # noqa: F405
    (
        "django.template.loaders.cached.Loader",
        [
            "django.template.loaders.filesystem.Loader",
            "django.template.loaders.app_directories.Loader",
        ],
    ),
]

# ---------- security ----------
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 31_536_000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SECURE_REFERRER_POLICY = "same-origin"
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

