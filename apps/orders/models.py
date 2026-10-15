"""Order models — Order, OrderItem, OrderEvent, and related enums.

This module holds the data layer only. All behaviour (creating orders,
transitioning status, computing totals) lives in services.py. The state
machine rules live in state.py. Models are intentionally "dumb".
"""
from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

from apps.core.models import TimeStampedModel

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class OrderType(models.TextChoices):
    """Whether this order is dine-in or delivery."""

    DINE_IN = "DINE", "Dine-in"
    DELIVERY = "DELV", "Delivery"


class OrderStatus(models.TextChoices):
    """Every status an order can pass through.

    The allowed transitions between these are defined in state.py.
    """

    PLACED = "PLACED", "Placed"
    APPROVED = "APPROVED", "Approved"
    IN_KITCHEN = "KITCHEN", "In kitchen"
    READY = "READY", "Ready"
    DISPATCHED = "DISPATCH", "Dispatched"
    ARRIVED = "ARRIVED", "Driver arrived"
    COLLECTED = "COLLECT", "Amount collected"
    PAID = "PAID", "Paid / cleared"
    CANCELLED = "CANCEL", "Cancelled"


# ---------------------------------------------------------------------------
# Order
# ---------------------------------------------------------------------------

class Order(TimeStampedModel):
    """A single customer order (dine-in or delivery).

    The ``status`` field must ONLY be changed via ``services.transition()``,
    which enforces the state machine in ``state.py`` and writes an audit
    event. Never flip ``order.status`` directly.
    """

    order_type = models.CharField(
        max_length=4,
        choices=OrderType.choices,
        db_index=True,
    )
    status = models.CharField(
        max_length=8,
        choices=OrderStatus.choices,
        default=OrderStatus.PLACED,
        db_index=True,
    )

    table = models.ForeignKey(
        "tables.Table",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="orders",
    )
    session = models.ForeignKey(
        "tables.TableSession",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="orders",
    )

    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="orders",
    )
    delivery_customer = models.ForeignKey(
        "customer_auth.Customer",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="orders",
    )
    agent = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="deliveries",
    )

    contact_name = models.CharField(max_length=80, blank=True)
    contact_phone = models.CharField(max_length=20, blank=True)
    maps_url = models.URLField(
        max_length=300,
        blank=True,
        help_text="Built at checkout in Sprint 6.",
    )
    instructions = models.CharField(max_length=280, blank=True)

    total_amount = models.DecimalField(
        max_digits=9,
        decimal_places=2,
        default=Decimal("0"),
    )

    class Meta:
        indexes = [
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["agent", "status"]),
            # Settlement-time analytics filter/group on (status, updated_at):
            # the accounts page scans settled (PAID) orders by their last-update
            # time, so this index turns that into a plain range scan.
            models.Index(fields=["status", "updated_at"]),
        ]
        constraints = [
            models.CheckConstraint(
                name="order_channel_shape",
                condition=(
                    models.Q(
                        order_type="DINE",
                        table__isnull=False,
                    )
                    | models.Q(
                        order_type="DELV",
                        table__isnull=True,
                    )
                ),
            ),
        ]

    def __str__(self) -> str:
        return f"Order #{self.pk} ({self.order_type} · {self.status})"


# ---------------------------------------------------------------------------
# OrderItem
# ---------------------------------------------------------------------------

class OrderItem(models.Model):
    """A line item on an order — snapshots menu data at order time.

    ``name_snap`` and ``unit_price`` are frozen copies of the menu item's
    name and effective_price at the moment the order was placed. This
    ensures historical orders stay correct even if the menu changes later
    (e.g. a price increase or item rename won't retroactively alter past
    orders).
    """

    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="items",
    )
    menu_item = models.ForeignKey(
        "menu.MenuItem",
        on_delete=models.PROTECT,
    )

    # Snapshots — frozen at order time
    name_snap = models.CharField(max_length=120)
    unit_price = models.DecimalField(max_digits=8, decimal_places=2)

    quantity = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1)],
    )

    @property
    def line_total(self) -> Decimal:
        """Unit price × quantity for this line item."""
        return self.unit_price * self.quantity

    def __str__(self) -> str:
        return f"{self.quantity}× {self.name_snap}"


# ---------------------------------------------------------------------------
# OrderEvent (append-only audit trail)
# ---------------------------------------------------------------------------

class OrderEvent(models.Model):
    """Append-only audit log entry for order status changes.

    Every call to ``services.transition()`` appends one row here. The
    initial order creation also writes a row (from_status="" -> "PLACED").
    This tamper-evident history powers analytics timing (e.g. how long
    orders spend in the kitchen) and lets support staff reconstruct
    what happened to any order.
    """

    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="events",
    )
    from_status = models.CharField(max_length=8, blank=True)
    to_status = models.CharField(max_length=8)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
    )
    at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-at"]

    def __str__(self) -> str:
        return f"Order #{self.order_id}: {self.from_status or 'new'} -> {self.to_status}"


# ---------------------------------------------------------------------------
# Message (quick customer <-> agent/admin chat, scoped to an order)
# ---------------------------------------------------------------------------

class Message(models.Model):
    """A short chat message tied to one order.

    Body is length-capped plain text and auto-escaped when rendered in
    templates (XSS defense). Messages are delivered live via the order.<id>
    channel group. Customers and the assigned agent/admin exchange quick
    notes here ("running late", "leave at door", etc.).
    """

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="messages")
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL
    )
    body = models.CharField(max_length=300)
    at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["at"]

    def __str__(self) -> str:
        return f"Message #{self.pk} on Order #{self.order_id}"
