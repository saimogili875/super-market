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
