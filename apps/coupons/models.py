"""Coupons and promotional discounts models."""
from datetime import date
from decimal import Decimal
from django.db import models
from apps.core.models import TimeStampedModel


class Coupon(TimeStampedModel):
    """Discount vouchers with usage limits, date ranges, and min order thresholds."""

    code = models.CharField(max_length=30, unique=True, db_index=True)
    discount_type = models.CharField(
        max_length=20,
        default="Percentage",
        choices=[("Percentage", "Percentage (%)"), ("Fixed", "Fixed Amount (₹)")],
    )
    value = models.DecimalField(max_digits=10, decimal_places=2)
    valid_from = models.DateField()
    valid_to = models.DateField()
    usage_limit = models.PositiveIntegerField(default=100)
    times_used = models.PositiveIntegerField(default=0)
    min_order = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.code} — {self.discount_display}"

    def save(self, *args, **kwargs):
        self.code = self.code.strip().upper()
        super().save(*args, **kwargs)

    @property
    def discount_display(self):
        if self.discount_type == "Percentage":
            return f"{int(self.value) if self.value == int(self.value) else self.value}% off"
        return f"₹{self.value} off"

    @property
    def status(self):
        today = date.today()
        if not self.is_active:
            return "Inactive"
        if today < self.valid_from:
            return "Scheduled"
        if today > self.valid_to or self.times_used >= self.usage_limit:
            return "Expired"
        return "Active"

    def is_valid_for(self, order_amount: Decimal):
        if self.status != "Active":
            return False, f"Coupon is {self.status.lower()}."
        if order_amount < self.min_order:
            return False, f"Minimum order amount of ₹{self.min_order} required."
        return True, "Valid"

    def calculate_discount(self, order_amount: Decimal) -> Decimal:
        if self.discount_type == "Percentage":
            discount = (order_amount * (self.value / Decimal("100"))).quantize(Decimal("0.01"))
        else:
            discount = min(self.value, order_amount).quantize(Decimal("0.01"))
        return discount
