"""Context processor injecting brand configuration into all template contexts."""
from django.conf import settings


def brand_context(request):
    """Expose brand settings to templates globally."""
    return {
        "BRAND_NAME": getattr(settings, "BRAND_NAME", "FreshMart"),
        "BRAND_SHORT": getattr(settings, "BRAND_SHORT", "FM"),
        "BRAND_TAGLINE": getattr(settings, "BRAND_TAGLINE", "Fresh groceries, delivered fast"),
        "BRAND_PHONE": getattr(settings, "BRAND_PHONE", "6281238410"),
        "BRAND_PHONE_INTL": getattr(settings, "BRAND_PHONE_INTL", "916281238410"),
        "BRAND_EMAIL": getattr(settings, "BRAND_EMAIL", "support@freshmart.com"),
        "BRAND_LOCATION": getattr(settings, "BRAND_LOCATION", "Hyderabad"),
    }


def admin_context(request):
    """Expose admin notification & alert counts to admin templates."""
    if not (request.user.is_authenticated and getattr(request.user, "is_admin_role", False)):
        return {}
    try:
        from apps.notifications.models import AdminNotification
        return {
            "unread_notifs_count": AdminNotification.objects.filter(is_read=False).count(),
        }
    except Exception:
        return {"unread_notifs_count": 0}

