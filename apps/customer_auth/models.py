from django.conf import settings
from django.db import models


class Customer(models.Model):
    """Lightweight customer account for the delivery flow.

    Decoupled from Django's staff/admin User model (apps.accounts).
    Stores delivery contact details and address preferences across visits.
    """
    phone = models.CharField(max_length=20, db_index=True)
    email = models.EmailField(db_index=True)
    name = models.CharField(max_length=100, blank=True, default="")
    default_address = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    last_login_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["phone", "email"], name="unique_customer_phone_email")
        ]

    def __str__(self):
        return f"Customer {self.email} ({self.phone})"


class CustomerAddress(models.Model):
    """Customer saved delivery address."""

    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name="addresses")
    title = models.CharField(max_length=50, default="Home", help_text="e.g. Home, Office, Other")
    recipient_name = models.CharField(max_length=100, blank=True, default="")
    phone = models.CharField(max_length=20, blank=True, default="")
    address = models.TextField()
    city = models.CharField(max_length=80, default="Hyderabad")
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-is_default", "-created_at"]

    def __str__(self):
        return f"[{self.title}] {self.address[:30]}"


class WishlistItem(models.Model):
    """Product saved to customer's wishlist."""

    customer = models.ForeignKey(Customer, null=True, blank=True, on_delete=models.CASCADE, related_name="wishlist_items")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE, related_name="user_wishlist_items")
    item = models.ForeignKey("menu.MenuItem", on_delete=models.CASCADE, related_name="wishlisted_by")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Wishlist: {self.item.name}"

