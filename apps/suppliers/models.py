"""Supplier profiles and Purchase Order management models."""
from decimal import Decimal
from django.db import models
from apps.core.models import TimeStampedModel


class Supplier(TimeStampedModel):
    """Supermarket vendor / supplier directory."""

    name = models.CharField(max_length=120, unique=True, db_index=True)
    contact = models.CharField(max_length=120, blank=True, help_text="Contact person or representative")
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=30, blank=True)
    address = models.TextField(blank=True)
    status = models.CharField(
        max_length=20,
        default="Active",
        choices=[("Active", "Active"), ("Inactive", "Inactive")],
        db_index=True,
    )

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def open_pos_count(self):
        return self.purchase_orders.filter(status__in=["Draft", "Submitted", "Partial"]).count()

    @property
    def last_delivery_date(self):
        last_po = self.purchase_orders.filter(status="Complete").order_by("-received_at").first()
        return last_po.received_at if last_po else None


class PurchaseOrder(TimeStampedModel):
    """Procurement purchase order sent to supplier for supermarket restocking."""

    po_number = models.CharField(max_length=40, unique=True, db_index=True)
    supplier = models.ForeignKey(Supplier, on_delete=models.CASCADE, related_name="purchase_orders")
    product_name = models.CharField(max_length=150)
    item = models.ForeignKey(
        "menu.MenuItem",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="purchase_orders",
        help_text="Associated catalog item if already existing in menu",
    )
    quantity = models.PositiveIntegerField(default=1)
    unit_cost = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    total_cost = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    status = models.CharField(
        max_length=20,
        default="Draft",
        choices=[
            ("Draft", "Draft"),
            ("Submitted", "Submitted"),
            ("Partial", "Partial"),
            ("Complete", "Complete"),
            ("Cancelled", "Cancelled"),
        ],
        db_index=True,
    )
    received_quantity = models.PositiveIntegerField(default=0)
    expected_delivery = models.DateField(null=True, blank=True)
    received_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.po_number} — {self.supplier.name} ({self.status})"

    def save(self, *args, **kwargs):
        if not self.total_cost or self.total_cost == Decimal("0.00"):
            self.total_cost = (Decimal(self.quantity) * self.unit_cost).quantize(Decimal("0.01"))
        super().save(*args, **kwargs)
