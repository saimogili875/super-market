"""User, Role, AgentProfile, and LoginAttempt models for identity & RBAC."""
from datetime import timedelta

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.timezone import now

from apps.core.models import TimeStampedModel


class Role(models.TextChoices):
    """Platform roles — stored on the User.role column."""

    ADMIN = "ADMIN", "Super Admin"
    MANAGER = "MANAGER", "Store Manager"
    STAFF = "STAFF", "Store Staff"
    INVENTORY = "INVENTORY", "Inventory Staff"
    CASHIER = "CASHIER", "Cashier"
    AGENT = "AGENT", "Delivery Agent"
    CUSTOMER = "CUST", "Customer"


class User(AbstractUser):
    """Custom user with a business role and optional phone number."""

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.CUSTOMER,
        db_index=True,
    )
    phone = models.CharField(max_length=20, blank=True)

    class Meta:
        indexes = [models.Index(fields=["role"])]

    def save(self, *args, **kwargs):
        if self.is_superuser and self.role == Role.CUSTOMER:
            self.role = Role.ADMIN
        super().save(*args, **kwargs)

    # --- convenience properties (business role, NOT Django admin flags) ---

    @property
    def is_admin_role(self):
        """True when the user holds an administrative/staff business role."""
        return self.role in {Role.ADMIN, Role.MANAGER, Role.STAFF, Role.INVENTORY, Role.CASHIER}

    @property
    def is_super_admin(self):
        return self.role == Role.ADMIN or self.is_superuser

    @property
    def is_manager(self):
        return self.role in {Role.ADMIN, Role.MANAGER} or self.is_superuser

    @property
    def is_store_manager(self):
        return self.role in {Role.ADMIN, Role.MANAGER} or self.is_superuser

    @property
    def is_staff_member(self):
        return self.role in {Role.ADMIN, Role.MANAGER, Role.STAFF, Role.INVENTORY, Role.CASHIER} or self.is_superuser

    @property
    def is_inventory_staff(self):
        return self.role in {Role.ADMIN, Role.MANAGER, Role.INVENTORY, Role.STAFF} or self.is_superuser

    @property
    def is_cashier(self):
        return self.role in {Role.ADMIN, Role.MANAGER, Role.CASHIER, Role.STAFF} or self.is_superuser

    @property
    def is_agent(self):
        """True when the user holds the AGENT (Delivery Agent) role."""
        return self.role == Role.AGENT

    @property
    def is_customer(self):
        """True when the user holds the CUSTOMER role."""
        return self.role == Role.CUSTOMER


class AgentProfile(TimeStampedModel):
    """Delivery-agent metadata — kept tiny; queried often for availability."""

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="agent")
    is_available = models.BooleanField(default=False, db_index=True)
    vehicle_type = models.CharField(max_length=50, blank=True, default="Motorbike")
    vehicle_number = models.CharField(max_length=50, blank=True, default="")

    def __str__(self):
        return f"AgentProfile({self.user.username})"


class LoginAttempt(models.Model):
    """Tracks cumulative failed login attempts per username for progressive lockout.

    Lockout schedule (iPhone-style escalation):
        Attempts 1-2 → no lockout
        Attempt 3    → 1 minute
        Attempt 4    → 5 minutes
        Attempt 5    → 15 minutes
        Attempt 6    → 60 minutes
        Attempt 7+   → 24 hours (requires manual admin unlock)
    """

    username = models.CharField(max_length=150, db_index=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True, db_index=True)
    failed_attempts = models.PositiveIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Login Attempt Tracker"
        verbose_name_plural = "Login Attempt Trackers"
        constraints = [
            models.UniqueConstraint(
                fields=["username", "ip_address"],
                name="unique_username_ip_lockout",
            )
        ]

    # Escalating lockout durations keyed by attempt number.
    LOCKOUT_SCHEDULE = {
        3: timedelta(minutes=1),
        4: timedelta(minutes=5),
        5: timedelta(minutes=15),
        6: timedelta(hours=1),
    }
    MAX_TIER_DURATION = timedelta(hours=24)  # attempt 7+

    def __str__(self):
        status = "LOCKED" if self.is_locked else "ok"
        return f"LoginAttempt({self.username}, fails={self.failed_attempts}, {status})"

    def get_lockout_duration(self):
        """Return the lockout timedelta for the current failed_attempts count, or None."""
        if self.failed_attempts < 3:
            return None
        if self.failed_attempts >= 7:
            return self.MAX_TIER_DURATION
        return self.LOCKOUT_SCHEDULE.get(self.failed_attempts)

    @property
    def is_locked(self):
        """True if currently in a lockout window."""
        return self.locked_until is not None and now() < self.locked_until

    @property
    def remaining_lockout_seconds(self):
        """Seconds remaining in the lockout window, or 0 if not locked."""
        if not self.is_locked:
            return 0
        return max(0, int((self.locked_until - now()).total_seconds()))

    @property
    def remaining_lockout_display(self):
        """Human-readable remaining lockout time, e.g. '5 minutes' or '23 hours, 45 minutes'."""
        total = self.remaining_lockout_seconds
        if total <= 0:
            return ""
        hours, remainder = divmod(total, 3600)
        minutes = remainder // 60
        if hours and minutes:
            h_label = "hour" if hours == 1 else "hours"
            m_label = "minute" if minutes == 1 else "minutes"
            return f"{hours} {h_label}, {minutes} {m_label}"
        if hours:
            h_label = "hour" if hours == 1 else "hours"
            return f"{hours} {h_label}"
        if minutes:
            m_label = "minute" if minutes == 1 else "minutes"
            return f"{minutes} {m_label}"
        return "less than a minute"

    @property
    def requires_admin_unlock(self):
        """True when at tier 7+ (24hr lockout requiring manual intervention)."""
        return self.failed_attempts >= 7

    def record_failure(self):
        """Increment the failure counter, compute the new lockout expiry, and save."""
        self.failed_attempts += 1
        duration = self.get_lockout_duration()
        if duration is not None:
            self.locked_until = now() + duration
        self.save(update_fields=["failed_attempts", "locked_until"])

    def reset(self):
        """Clear attempts and lockout — called on successful login."""
        self.failed_attempts = 0
        self.locked_until = None
        self.save(update_fields=["failed_attempts", "locked_until"])


# ===========================================================================
# Store Manager & Staff Operations Models
# ===========================================================================

class StaffShift(TimeStampedModel):
    """Store operational work shifts (e.g. Morning, Evening, Night)."""

    name = models.CharField(max_length=60, unique=True)
    start_time = models.TimeField()
    end_time = models.TimeField()
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["start_time", "name"]

    def __str__(self):
        return f"{self.name} ({self.start_time.strftime('%H:%M')} - {self.end_time.strftime('%H:%M')})"


class StaffProfile(TimeStampedModel):
    """Metadata for store staff members managed by Store Managers."""

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="staff_profile")
    employee_id = models.CharField(max_length=30, blank=True, unique=True, null=True)
    department = models.CharField(max_length=50, blank=True, default="Store Operations")
    assigned_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="managed_staff")
    responsibilities = models.TextField(blank=True, default="Order preparation, stock inspection, shelf replenishment")
    current_shift = models.ForeignKey(StaffShift, on_delete=models.SET_NULL, null=True, blank=True, related_name="assigned_staff")
    emergency_contact = models.CharField(max_length=50, blank=True)

    class Meta:
        ordering = ["user__first_name", "user__username"]

    def __str__(self):
        return f"StaffProfile({self.user.username} · {self.department})"


class StaffAttendance(TimeStampedModel):
    """Shift attendance log with check-in, check-out, and manager verification."""

    STATUS_CHOICES = [
        ("PRESENT", "Present"),
        ("ABSENT", "Absent"),
        ("LATE", "Late"),
        ("LEAVE", "On Leave"),
    ]

    staff = models.ForeignKey(User, on_delete=models.CASCADE, related_name="attendance_records")
    shift = models.ForeignKey(StaffShift, on_delete=models.SET_NULL, null=True, blank=True, related_name="attendances")
    date = models.DateField(db_index=True)
    check_in = models.DateTimeField(null=True, blank=True)
    check_out = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="PRESENT")
    notes = models.TextField(blank=True)
    verified_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="verified_attendances")

    class Meta:
        ordering = ["-date", "-check_in"]
        constraints = [
            models.UniqueConstraint(fields=["staff", "date"], name="unique_staff_daily_attendance")
        ]

    def __str__(self):
        return f"{self.staff.username} - {self.date} ({self.status})"


class StaffTask(TimeStampedModel):
    """Operational assignments distributed to staff by managers."""

    PRIORITY_CHOICES = [
        ("LOW", "Low"),
        ("MEDIUM", "Medium"),
        ("HIGH", "High"),
        ("URGENT", "Urgent"),
    ]

    STATUS_CHOICES = [
        ("PENDING", "Pending"),
        ("IN_PROGRESS", "In Progress"),
        ("COMPLETED", "Completed"),
        ("CANCELLED", "Cancelled"),
    ]

    CATEGORY_CHOICES = [
        ("ORDER_PREP", "Order Preparation"),
        ("INVENTORY", "Stock & Shelf Replenishment"),
        ("VERIFICATION", "Stock Verification"),
        ("CUSTOMER", "Customer Service"),
        ("MAINTENANCE", "Store Maintenance"),
        ("OTHER", "General Task"),
    ]

    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default="MEDIUM")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="PENDING")
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES, default="ORDER_PREP")
    assigned_to = models.ForeignKey(User, on_delete=models.CASCADE, related_name="assigned_tasks")
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="created_tasks")
    related_order = models.ForeignKey("orders.Order", on_delete=models.SET_NULL, null=True, blank=True, related_name="staff_tasks")
    related_item = models.ForeignKey("menu.MenuItem", on_delete=models.SET_NULL, null=True, blank=True, related_name="staff_tasks")
    due_date = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    completion_notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title} -> {self.assigned_to.username} [{self.status}]"


class StockAdjustmentRequest(TimeStampedModel):
    """Stock discrepancy or adjustment requests initiated by staff for Manager approval."""

    TYPE_CHOICES = [
        ("DAMAGED", "Damaged Goods"),
        ("EXPIRED", "Expired Goods"),
        ("MISSING", "Missing / Shrinkage"),
        ("CORRECTION", "Stock Correction"),
        ("RESTOCK", "Restock Request"),
    ]

    STATUS_CHOICES = [
        ("PENDING", "Pending Approval"),
        ("APPROVED", "Approved"),
        ("REJECTED", "Rejected"),
    ]

    item = models.ForeignKey("menu.MenuItem", on_delete=models.CASCADE, related_name="adjustment_requests")
    request_type = models.CharField(max_length=30, choices=TYPE_CHOICES)
    quantity = models.IntegerField(help_text="Positive for addition, negative for reduction, or exact correction count")
    reason = models.CharField(max_length=255)
    notes = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="PENDING")
    requested_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name="stock_requests")
    reviewed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="reviewed_stock_requests")
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.item.name} ({self.request_type}) by {self.requested_by.username} [{self.status}]"


