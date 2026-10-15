"""Django Admin registration for User, AgentProfile, and LoginAttempt."""
from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.db import transaction

from .models import AgentProfile, LoginAttempt, Role, User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """Custom UserAdmin — surfaces role and phone, auto-provisions AgentProfile."""

    list_display = ("username", "email", "role", "phone", "is_staff", "is_active")
    list_filter = ("role", "is_staff", "is_active")

    # Inject role & phone into the default fieldsets
    fieldsets = BaseUserAdmin.fieldsets + (
        ("Platform", {"fields": ("role", "phone")}),
    )
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ("Platform", {"fields": ("role", "phone")}),
    )

    def save_model(self, request, obj, form, change):
        """Create/ensure an AgentProfile when saving a user with role=AGENT."""
        with transaction.atomic():
            super().save_model(request, obj, form, change)
            if obj.role == Role.AGENT:
                AgentProfile.objects.get_or_create(user=obj)


@admin.register(AgentProfile)
class AgentProfileAdmin(admin.ModelAdmin):
    """Read-friendly admin for delivery-agent profiles."""

    list_display = ("user", "is_available", "updated_at")
    list_filter = ("is_available",)
    readonly_fields = ("created_at", "updated_at")


@admin.register(LoginAttempt)
class LoginAttemptAdmin(admin.ModelAdmin):
    """Admin for login-attempt trackers with bulk unlock action."""

    list_display = ("username", "failed_attempts", "locked_until", "lock_status")
    list_filter = ("failed_attempts",)
    search_fields = ("username",)
    readonly_fields = ("username", "failed_attempts", "locked_until")
    actions = ("unlock_accounts",)

    @admin.display(description="Status", ordering="locked_until")
    def lock_status(self, obj):
        """Show human-readable lock status in the list view."""
        if obj.requires_admin_unlock and obj.is_locked:
            return "🔒 LOCKED (admin unlock required)"
        if obj.is_locked:
            return f"🔒 Locked ({obj.remaining_lockout_display})"
        return "✅ OK"

    @admin.action(description="Unlock selected accounts (reset failed attempts)")
    def unlock_accounts(self, request, queryset):
        """Bulk-reset failed_attempts and locked_until for selected trackers."""
        count = queryset.update(failed_attempts=0, locked_until=None)
        self.message_user(
            request,
            f"Successfully unlocked {count} account(s).",
            messages.SUCCESS,
        )

