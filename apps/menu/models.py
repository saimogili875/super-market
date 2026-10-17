"""Menu app models — Categories and Menu Items."""
from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.core.models import TimeStampedModel


class Category(TimeStampedModel):
    """Menu category (e.g., Starters, Mains)."""

    name = models.CharField(max_length=60, unique=True)
    tag = models.CharField(max_length=100, blank=True, help_text="Category tag/subtitle e.g. Aromatic & Flavorful")
    image = models.ImageField(upload_to="categories/", blank=True)
    sort_order = models.PositiveSmallIntegerField(default=0, db_index=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["sort_order", "name"]

    def __str__(self) -> str:
        return self.name

    @property
    def total_items_count(self) -> int:
        items_list = getattr(self, "_prefetched_objects_cache", {}).get("items")
        if items_list is not None:
            return len(items_list)
        return self.items.count()

    @property
    def available_items_count(self) -> int:
        items_list = getattr(self, "_prefetched_objects_cache", {}).get("items")
        if items_list is not None:
            return sum(1 for item in items_list if item.is_available)
        return self.items.filter(is_available=True).count()

    @property
    def unavailable_items_count(self) -> int:
        items_list = getattr(self, "_prefetched_objects_cache", {}).get("items")
        if items_list is not None:
            return sum(1 for item in items_list if not item.is_available)
        return self.items.filter(is_available=False).count()

    @property
    def header_image_url(self) -> str:
        if self.image:
            return self.image.url
        items_list = getattr(self, "_prefetched_objects_cache", {}).get("items")
        if items_list is not None:
            for item in items_list:
                if item.image:
                    return item.image.url
        else:
            item_with_img = self.items.filter(image__isnull=False).exclude(image="").first()
            if item_with_img and item_with_img.image:
                return item_with_img.image.url
        
        return "/static/images/exterior.jpeg"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        from .services import invalidate_menu_cache
        invalidate_menu_cache()

    def delete(self, *args, **kwargs):
        super().delete(*args, **kwargs)
        from .services import invalidate_menu_cache
        invalidate_menu_cache()


class MenuItem(TimeStampedModel):
    """Individual menu item linked to a category."""

    category = models.ForeignKey(
        Category, on_delete=models.PROTECT, related_name="items"
    )
    name = models.CharField(max_length=120)
    description = models.CharField(max_length=280, blank=True)
    price = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    prep_minutes = models.PositiveSmallIntegerField(default=15)
    is_available = models.BooleanField(default=True, db_index=True)
    track_stock = models.BooleanField(default=False)
    stock_quantity = models.PositiveIntegerField(default=0)
    low_stock_threshold = models.PositiveIntegerField(default=5)
    cost_price = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text="Purchase cost per unit for profit and valuation metrics",
    )
    sku = models.CharField(max_length=64, blank=True, null=True, unique=True, db_index=True)
    barcode = models.CharField(max_length=64, blank=True, db_index=True)
    unit = models.CharField(
        max_length=20,
        default="pcs",
        choices=[
            ("pcs", "Pieces (pcs)"),
            ("kg", "Kilograms (kg)"),
            ("g", "Grams (g)"),
            ("L", "Litres (L)"),
            ("ml", "Millilitres (ml)"),
            ("pack", "Pack"),
        ],
    )
    expiry_date = models.DateField(null=True, blank=True, db_index=True)
    supplier = models.ForeignKey(
        "suppliers.Supplier",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="products",
    )
    offer_percent = models.PositiveSmallIntegerField(
        default=0, validators=[MaxValueValidator(100)]
    )
    image = models.ImageField(upload_to="items/", blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["category", "is_available"]),
            models.Index(fields=["sku"]),
            models.Index(fields=["barcode"]),
            models.Index(fields=["expiry_date"]),
        ]

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        if not self.sku:
            import uuid
            self.sku = f"PRD-{uuid.uuid4().hex[:6].upper()}"
        super().save(*args, **kwargs)
        from .services import invalidate_menu_cache
        invalidate_menu_cache()

    def delete(self, *args, **kwargs):
        super().delete(*args, **kwargs)
        from .services import invalidate_menu_cache
        invalidate_menu_cache()

    @property
    def is_low_stock(self) -> bool:
        return self.track_stock and 0 < self.stock_quantity <= self.low_stock_threshold

    @property
    def is_out_of_stock(self) -> bool:
        return self.track_stock and self.stock_quantity <= 0

    @property
    def is_near_expiry(self) -> bool:
        if not self.expiry_date:
            return False
        from datetime import date, timedelta
        today = date.today()
        return today <= self.expiry_date <= today + timedelta(days=7)

    @property
    def is_expired(self) -> bool:
        if not self.expiry_date:
            return False
        from datetime import date
        return self.expiry_date < date.today()

    @property
    def effective_price(self) -> Decimal:
        """The single source of pricing truth.
        
        Calculates the discounted price if offer_percent > 0.
        This is used for both display and order creation.
        """
        if self.offer_percent > 0:
            percent = Decimal(str(self.offer_percent))
            discount_multiplier = (Decimal("100") - percent) / Decimal("100")
            discounted = self.price * discount_multiplier
            return discounted.quantize(Decimal("0.01"))
        return self.price

    @property
    def is_orderable(self) -> bool:
        """Available to order = admin-enabled AND (untracked OR has stock)."""
        if not self.is_available:
            return False
        if self.track_stock and self.stock_quantity <= 0:
            return False
        return True


class StockMovement(models.Model):
    """Immutable audit trail of inventory updates (deliveries, sales, wastage, corrections)."""

    MOVEMENT_TYPES = [
        ("RESTOCK", "Restock / PO Delivery"),
        ("SALE", "Customer Sale"),
        ("WASTE", "Damaged / Waste / Expiry"),
        ("CORRECTION", "Inventory Audit Correction"),
        ("RETURN", "Customer Return"),
    ]

    item = models.ForeignKey(MenuItem, on_delete=models.CASCADE, related_name="stock_movements")
    movement_type = models.CharField(max_length=20, choices=MOVEMENT_TYPES, db_index=True)
    quantity = models.IntegerField(help_text="Positive for addition, negative for reduction")
    resulting_quantity = models.PositiveIntegerField()
    cost_per_unit = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    notes = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="stock_movements",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.item.name}: {self.movement_type} ({self.quantity:+d}) -> {self.resulting_quantity}"
