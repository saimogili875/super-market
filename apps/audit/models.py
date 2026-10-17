"""AuditLog model and helper function for administrative logging."""
from django.conf import settings
from django.db import models


class AuditLog(models.Model):
    """Read-only log of sensitive administrator activities."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_logs",
    )
    user_display = models.CharField(max_length=100, blank=True)
    action = models.CharField(max_length=60, db_index=True)
    category = models.CharField(
        max_length=30,
        default="Logins",
        choices=[
            ("Logins", "Logins"),
            ("Products", "Products"),
            ("Inventory", "Inventory"),
            ("Order status", "Order status"),
            ("Payments", "Payments"),
            ("Security", "Security"),
            ("System", "System"),
        ],
        db_index=True,
    )
    record_id = models.CharField(max_length=60, blank=True, help_text="e.g. PRD-101 or ORD-205")
    change_summary = models.CharField(max_length=255, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    status = models.CharField(
        max_length=20,
        default="Success",
        choices=[("Success", "Success"), ("Failed", "Failed")],
        db_index=True,
    )
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-timestamp"]

    def __str__(self):
        return f"{self.timestamp:%Y-%m-%d %H:%M} [{self.category}] {self.action} by {self.user_display}"


def log_audit_event(request=None, action="", category="System", record_id="", change_summary="", status="Success", user=None):
    """Helper to record audit log events safely without failing the calling transaction."""
    try:
        ip = None
        user_obj = user
        if request:
            if not user_obj and hasattr(request, "user") and request.user.is_authenticated:
                user_obj = request.user
            ip = request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip() or request.META.get("REMOTE_ADDR")

        user_name = user_obj.username if user_obj else (request.POST.get("username", "Unknown") if request else "System")

        return AuditLog.objects.create(
            user=user_obj if (user_obj and user_obj.is_authenticated) else None,
            user_display=user_name,
            action=action,
            category=category,
            record_id=record_id,
            change_summary=change_summary,
            ip_address=ip if ip else None,
            status=status,
        )
    except Exception:
        # Never break primary business logic if audit logging encounters an issue
        return None
