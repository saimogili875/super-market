"""Payment transactions and refunds tracking model."""
from decimal import Decimal
from django.db import models
from apps.core.models import TimeStampedModel


class PaymentTransaction(TimeStampedModel):
    """Payment record linked to orders with verified status and refund auditing."""

    txn_id = models.CharField(max_length=40, unique=True, db_index=True)
    order = models.ForeignKey(
        "orders.Order",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="payments",
    )
    order_ref = models.CharField(max_length=50, blank=True, help_text="e.g. ORD-1029")
    customer_name = models.CharField(max_length=120, blank=True)
    method = models.CharField(
        max_length=30,
        default="UPI",
        choices=[
            ("UPI", "UPI"),
            ("Card", "Debit / Credit Card"),
            ("Cash", "Cash on Counter / Delivery"),
            ("NetBanking", "Net Banking"),
            ("Wallet", "Digital Wallet"),
        ],
        db_index=True,
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(
        max_length=20,
        default="Paid",
        choices=[
            ("Paid", "Paid"),
            ("Pending", "Pending"),
            ("Failed", "Failed"),
            ("Refunded", "Refunded"),
        ],
        db_index=True,
    )
    refund_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    refund_reason = models.CharField(max_length=150, blank=True)
    refunded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.txn_id} — {self.amount} ({self.status})"
