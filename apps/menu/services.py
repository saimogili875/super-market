"""Business logic for the menu app."""
import io
import logging

from django.core.files.base import ContentFile
from django.db.models import Prefetch

from .models import Category, MenuItem

logger = logging.getLogger(__name__)


def compress_image(image_field) -> None:
    """Downscale image to max 1024px longest side and compress.

    Operates in-place on the image_field to save space.
    Preserves transparency for PNGs. Uses JPEG for others.

    Pillow is imported HERE (not at module top) on purpose: menu.services is
    imported on every request that renders the cached menu, but image
    processing only runs on the rare admin upload. Lazy-importing keeps the
    ~15 MB Pillow/libjpeg working set out of idle web workers (RAM lever).
    """
    if not image_field:
        return

    from PIL import Image  # lazy: only load Pillow when an image is actually processed

    with Image.open(image_field) as img:
        # Calculate new size maintaining aspect ratio
        max_size = 1024
        if max(img.width, img.height) > max_size:
            img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
        
        # Save to memory buffer
        buffer = io.BytesIO()
        img_format = img.format if img.format in ("JPEG", "PNG") else "JPEG"
        
        if img_format == "JPEG":
            img = img.convert("RGB")
            img.save(buffer, format="JPEG", quality=80)
        else:
            img.save(buffer, format="PNG", optimize=True)

        # Overwrite field with compressed content
        file_name = image_field.name.split("/")[-1]
        image_field.save(
            file_name,
            ContentFile(buffer.getvalue()),
            save=False
        )


MENU_CACHE_KEY = "available_menu_data"


def invalidate_menu_cache() -> None:
    """Invalidate the cached available menu data."""
    from django.core.cache import cache
    try:
        cache.delete(MENU_CACHE_KEY)
    except Exception as exc:
        logger.debug("Menu cache delete failed: %s", exc)


def available_menu():
    """Return active categories with their available items.
    
    Uses prefetch_related and .only() to avoid N+1 queries.
    Categories and items are returned in their default sort orders.
    """
    items_qs = MenuItem.objects.filter(is_available=True).only(
        "id",
        "category_id",
        "name",
        "description",
        "price",
        "prep_minutes",
        "offer_percent",
        "image",
        "is_available",
        "track_stock",
        "stock_quantity",
    )
    return Category.objects.filter(is_active=True).prefetch_related(
        Prefetch("items", queryset=items_qs)
    )


def get_cached_menu():
    """Return evaluated menu categories from cache or DB."""
    from django.core.cache import cache
    try:
        data = cache.get(MENU_CACHE_KEY)
        if data is not None:
            return data
    except Exception as exc:
        logger.debug("Menu cache get failed: %s", exc)

    data = list(available_menu())
    try:
        cache.set(MENU_CACHE_KEY, data, timeout=3600)
    except Exception as exc:
        logger.debug("Menu cache set failed: %s", exc)
    return data


def toggle_availability(item: MenuItem) -> MenuItem:
    """Flip the is_available flag and save.
    
    Returns the updated item.
    """
    item.is_available = not item.is_available
    item.save(update_fields=["is_available"])
    invalidate_menu_cache()
    return item
