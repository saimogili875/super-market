"""User, Role, AgentProfile, and LoginAttempt models for identity & RBAC."""
from datetime import timedelta

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.timezone import now

from apps.core.models import TimeStampedModel


class Role(models.TextChoices):
    """Platform roles — stored on the User.role column."""

    ADMIN = "ADMIN", "Admin"
    AGENT = "AGENT", "Delivery Agent"
    CUSTOMER = "CUST", "Customer"


class User(AbstractUser):
    """Custom user with a business role and optional phone number."""

    role = models.CharField(
        max_length=5,
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
        """True when the user holds the ADMIN business role."""
        return self.role == Role.ADMIN

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

