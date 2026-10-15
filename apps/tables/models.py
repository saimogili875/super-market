"""Table and TableSession domain models for QR dine-in ordering."""
import secrets
from decimal import Decimal

from django.db import models

from apps.core.models import TimeStampedModel


def gen_qr_token() -> str:
    """Named (not lambda) so migrations can serialise the default."""
    return secrets.token_urlsafe(16)[:32]


class Table(TimeStampedModel):
    """Represents a physical dining table in the restaurant.

    The QR encodes qr_token (opaque), NEVER the id/number — prevents a guest
    from guessing another table's URL (IDOR defense).
    """

    number = models.PositiveSmallIntegerField(unique=True)
    qr_token = models.CharField(
        max_length=32,
        unique=True,
        db_index=True,
        default=gen_qr_token,
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["number"]

    def __str__(self) -> str:
        return f"Table {self.number}"


class TableSession(TimeStampedModel):
    """Represents an active dining session or open 'tab' at a table for a guest.

    Multiple open sessions per table are allowed (one per guest/tab).
    """

    table = models.ForeignKey(
        Table,
        on_delete=models.PROTECT,
        related_name="sessions",
    )
    guest_name = models.CharField(max_length=60, blank=True)
    bill_requested = models.BooleanField(default=False)
    opened_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-opened_at"]

    @property
    def total(self) -> Decimal:
        """Sum of total_amount for all non-cancelled orders in this session."""
        from apps.orders.models import OrderStatus

        return sum(
            (o.total_amount for o in self.orders.all() if o.status != OrderStatus.CANCELLED),
            Decimal("0"),
        )

    def __str__(self) -> str:
        status = "Closed" if self.closed_at else "Open"
        guest_info = f" - {self.guest_name}" if self.guest_name else ""
        return f"Session #{self.pk} ({self.table}{guest_info} - {status})"
