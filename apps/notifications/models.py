from django.conf import settings
from django.db import models


class AdminNotification(models.Model):
    """Operational alerts (low stock, near-expiry, new order, PO receipt, agent alerts)."""

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="notifications",
        help_text="Target user if scoped (e.g. delivery agent), or null for all administrative staff.",
    )

    notification_type = models.CharField(
        max_length=30,
        default="System",
        choices=[
            ("Low stock", "Low stock"),
            ("Expiry", "Expiry"),
            ("Order", "Order"),
            ("Delivery", "Delivery"),
            ("System", "System"),
        ],
        db_index=True,
    )
    title = models.CharField(max_length=150)
    message = models.TextField(blank=True)
    reference_id = models.CharField(max_length=50, blank=True, help_text="e.g. PRD-102 or ORD-501")
    severity = models.CharField(
        max_length=20,
        default="wn",
        choices=[
            ("ok", "Success"),
            ("wn", "Warning"),
            ("er", "Danger"),
            ("mu", "Muted"),
            ("gd", "Order Gold"),
        ],
    )
    is_read = models.BooleanField(default=False, db_index=True)
    is_resolved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"[{self.notification_type}] {self.title}"
