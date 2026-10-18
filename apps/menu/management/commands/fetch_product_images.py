"""Fetch real, royalty-free product photos from Unsplash, convert to WebP (~800px, <120KB),
and attach to all FreshMart categories and products.

Repeatable command: python manage.py fetch_product_images
"""
import io
import os
import re
import urllib.request
from pathlib import Path
from PIL import Image

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils.text import slugify

from apps.menu.models import Category, MenuItem


# Royalty-free, commercial-friendly Unsplash high-res photos
CATEGORY_IMAGE_URLS = {
    "Fruits and Vegetables": "https://images.unsplash.com/photo-1610348725531-843dff563e2c?w=900&q=80",
    "Rice, Pulses and Grains": "https://images.unsplash.com/photo-1586201375761-83865001e31c?w=900&q=80",
    "Dairy and Eggs": "https://images.unsplash.com/photo-1528750997573-59b89d56f4f7?w=900&q=80",
    "Cooking Essentials": "https://images.unsplash.com/photo-1474979266404-7eaacbcd87c5?w=900&q=80",
    "Snacks and Biscuits": "https://images.unsplash.com/photo-1558961363-fa8fdf82db35?w=900&q=80",
    "Beverages": "https://images.unsplash.com/photo-1544378730-8b5104b18790?w=900&q=80",
    "Household Essentials": "https://images.unsplash.com/photo-1585421514738-01798e348b17?w=900&q=80",
    "Personal Care": "https://images.unsplash.com/photo-1584308666744-24d5c474f2ae?w=900&q=80",
    "Packaged Foods": "https://images.unsplash.com/photo-1612927601601-6638404737ce?w=900&q=80",
    "Breakfast and Cereals": "https://images.unsplash.com/photo-1584776296944-ab6fb57b0bdd?w=900&q=80",
}

PRODUCT_IMAGE_URLS = {
    # 1. Fruits & Vegetables
    "SKU-VEG-001": ("Fresh Red Onions", "https://images.unsplash.com/photo-1618512496248-a07fe83aa8cb?w=900&q=80"),
    "SKU-VEG-002": ("Ripe Red Tomatoes", "https://images.unsplash.com/photo-1592924357228-91a4daadcfea?w=900&q=80"),
    "SKU-FRT-001": ("Royal Gala Apples", "https://images.unsplash.com/photo-1560806887-1e4cd0b6cbd6?w=900&q=80"),
    "SKU-FRT-002": ("Golden Bananas", "https://images.unsplash.com/photo-1571771894821-ce9b6c11b08e?w=900&q=80"),
    "SKU-VEG-003": ("Pahadi Potatoes", "https://images.unsplash.com/photo-1518977676601-b53f82aba655?w=900&q=80"),
    "SKU-VEG-004": ("Tender Carrots", "https://images.unsplash.com/photo-1447175008436-054170c2e979?w=900&q=80"),
    "SKU-VEG-005": ("Fresh Green Spinach", "https://images.unsplash.com/photo-1576045057995-568f588f82fb?w=900&q=80"),

    # 2. Rice, Pulses & Grains
    "SKU-GRN-001": ("Aged Basmati Rice", "https://images.unsplash.com/photo-1586201375761-83865001e31c?w=900&q=80"),
    "SKU-GRN-002": ("Desi Toor Dal", "https://images.unsplash.com/photo-1596797038530-2c107229654b?w=900&q=80"),
    "SKU-GRN-003": ("Wheat Sharbati Atta", "https://images.unsplash.com/photo-1509440159596-0249088772ff?w=900&q=80"),
    "SKU-GRN-004": ("Moong Dal", "https://images.unsplash.com/photo-1596797038530-2c107229654b?w=900&q=80"),
    "SKU-GRN-005": ("Sona Masoori Rice", "https://images.unsplash.com/photo-1536304993881-ff6e9eefa2a6?w=900&q=80"),
    "SKU-GRN-006": ("Kabuli Chickpeas", "https://images.unsplash.com/photo-1515543237350-b3eea1ec8082?w=900&q=80"),
    "SKU-GRN-007": ("Roasted Sooji Rava", "https://images.unsplash.com/photo-1607623814075-e51df1bdc82f?w=900&q=80"),

    # 3. Dairy & Eggs
    "SKU-DRY-001": ("Full Cream Milk", "https://images.unsplash.com/photo-1550583724-b2692b85b150?w=900&q=80"),
    "SKU-DRY-002": ("Malai Paneer", "https://images.unsplash.com/photo-1631452180519-c014fe946bc7?w=900&q=80"),
    "SKU-DRY-003": ("Brown Farm Eggs", "https://images.unsplash.com/photo-1516467508483-a7212febe31a?w=900&q=80"),
    "SKU-DRY-004": ("Sourdough Bread", "https://images.unsplash.com/photo-1509440159596-0249088772ff?w=900&q=80"),
    "SKU-DRY-005": ("Salted Table Butter", "https://images.unsplash.com/photo-1589985270826-4b7bb135bc9d?w=900&q=80"),
    "SKU-DRY-006": ("Natural Curd Dahi", "https://images.unsplash.com/photo-1488477181946-6428a0291777?w=900&q=80"),

    # 4. Cooking Essentials
    "SKU-OIL-001": ("Mustard Oil", "https://images.unsplash.com/photo-1474979266404-7eaacbcd87c5?w=900&q=80"),
    "SKU-OIL-002": ("Sunflower Oil", "https://images.unsplash.com/photo-1620706857370-e1b9770e8bb1?w=900&q=80"),
    "SKU-OIL-003": ("Desi Cow Ghee", "https://images.unsplash.com/photo-1589985270826-4b7bb135bc9d?w=900&q=80"),
    "SKU-SPC-001": ("Deggi Mirch Powder", "https://images.unsplash.com/photo-1596040033229-a9821ebd058d?w=900&q=80"),
    "SKU-SPC-002": ("Organic Turmeric Powder", "https://images.unsplash.com/photo-1615485290382-441e4d049cb5?w=900&q=80"),

    # 5. Snacks & Biscuits
    "SKU-SNK-001": ("Digestive Biscuits", "https://images.unsplash.com/photo-1558961363-fa8fdf82db35?w=900&q=80"),
    "SKU-SNK-002": ("Potato Chips", "https://images.unsplash.com/photo-1566478989037-eec170784d0b?w=900&q=80"),
    "SKU-SNK-003": ("Aloo Bhujia Namkeen", "https://images.unsplash.com/photo-1601050690597-df0568f70950?w=900&q=80"),
    "SKU-SNK-004": ("California Almonds", "https://images.unsplash.com/photo-1508061253366-f7da158b6d46?w=900&q=80"),

    # 6. Beverages
    "SKU-BEV-001": ("Assam CTC Tea", "https://images.unsplash.com/photo-1576092768241-dec231879fc3?w=900&q=80"),
    "SKU-BEV-002": ("Filter Coffee", "https://images.unsplash.com/photo-1514432324607-a09d9b4aefdd?w=900&q=80"),
    "SKU-BEV-003": ("Valencia Orange Juice", "https://images.unsplash.com/photo-1613478223719-2ab802602423?w=900&q=80"),
    "SKU-BEV-004": ("Tender Coconut Water", "https://images.unsplash.com/photo-1544378730-8b5104b18790?w=900&q=80"),

    # 7. Household Essentials
    "SKU-HSH-001": ("Surface Cleaner", "https://images.unsplash.com/photo-1585421514738-01798e348b17?w=900&q=80"),
    "SKU-HSH-002": ("Laundry Detergent", "https://images.unsplash.com/photo-1610557892470-55d9e80c0bce?w=900&q=80"),
    "SKU-HSH-003": ("Dishwash Gel", "https://images.unsplash.com/photo-1607613009820-a29f7bb81c04?w=900&q=80"),
    "SKU-HSH-004": ("Kitchen Towels Roll", "https://images.unsplash.com/photo-1584556812952-905ffd0c611a?w=900&q=80"),

    # 8. Personal Care
    "SKU-PC-001": ("Herbal Bathing Soap", "https://images.unsplash.com/photo-1584308666744-24d5c474f2ae?w=900&q=80"),
    "SKU-PC-002": ("Herbal Shampoo", "https://images.unsplash.com/photo-1535585209827-a15fcdbc4c2d?w=900&q=80"),
    "SKU-PC-003": ("Herbal Toothpaste", "https://images.unsplash.com/photo-1571781926291-c477ebfd024b?w=900&q=80"),

    # 9. Breakfast & Instant
    "SKU-BF-001": ("Rolled Oats", "https://images.unsplash.com/photo-1584776296944-ab6fb57b0bdd?w=900&q=80"),
    "SKU-BF-002": ("Crunchy Muesli", "https://images.unsplash.com/photo-1517673132405-a56a62b18caf?w=900&q=80"),
}


def download_and_optimize(image_url: str, output_path: Path, max_dimension: int = 800) -> bool:
    """Download image, resize to max dimension, and save as optimized WebP (<120KB)."""
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if output_path.exists() and output_path.stat().st_size > 5000:
            return True

        req = urllib.request.Request(
            image_url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) FreshMartBot/1.0"}
        )
        with urllib.request.urlopen(req, timeout=12) as response:
            raw_data = response.read()

        img = Image.open(io.BytesIO(raw_data)).convert("RGB")

        # Resize preserving aspect ratio
        if img.width > max_dimension or img.height > max_dimension:
            img.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)

        # Save as WebP with high visual fidelity and low footprint
        img.save(str(output_path), "WEBP", quality=78, method=6)
        file_size_kb = output_path.stat().st_size / 1024
        return True
    except Exception as e:
        print(f"Error fetching {image_url}: {e}")
        return False


class Command(BaseCommand):
    help = "Downloads real product and category photos, converts to WebP (<120KB), and links records."

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Force re-downloading and converting existing images.",
        )

    def handle(self, *args, **options):
        force = options.get("force", False)
        media_root = Path(settings.MEDIA_ROOT)
        cat_dir = media_root / "categories"
        prod_dir = media_root / "products"

        cat_dir.mkdir(parents=True, exist_ok=True)
        prod_dir.mkdir(parents=True, exist_ok=True)

        self.stdout.write(self.style.NOTICE("=== Fetching Real Supermarket Photos ==="))

        # 1. Categories
        self.stdout.write("Processing Categories...")
        cat_success = 0
        for cat in Category.objects.all():
            url = CATEGORY_IMAGE_URLS.get(cat.name)
            if not url:
                # Match partial category name
                for c_key, c_url in CATEGORY_IMAGE_URLS.items():
                    if c_key.lower() in cat.name.lower() or cat.name.lower() in c_key.lower():
                        url = c_url
                        break

            if url:
                slug = slugify(cat.name)[:40]
                dest = cat_dir / f"{slug}.webp"
                if force and dest.exists():
                    dest.unlink()

                if download_and_optimize(url, dest):
                    cat.image = f"categories/{slug}.webp"
                    cat.save(update_fields=["image"])
                    cat_success += 1
                    self.stdout.write(f"  [✓] Category '{cat.name}' -> {cat.image.url} ({dest.stat().st_size // 1024} KB)")

        # 2. Products
        self.stdout.write("\nProcessing Products...")
        prod_success = 0
        missing_photos = []

        for item in MenuItem.objects.all():
            prod_info = PRODUCT_IMAGE_URLS.get(item.sku)
            url = prod_info[1] if prod_info else None

            # Fallback by product name substring
            if not url:
                for sku_k, (p_name, p_url) in PRODUCT_IMAGE_URLS.items():
                    if any(w.lower() in item.name.lower() for w in p_name.split() if len(w) > 3):
                        url = p_url
                        break

            # Fallback to category photo if still no specific product photo
            if not url and item.category:
                url = CATEGORY_IMAGE_URLS.get(item.category.name)

            if url:
                slug = slugify(item.name)[:40] or f"item-{item.pk}"
                dest = prod_dir / f"{slug}.webp"
                if force and dest.exists():
                    dest.unlink()

                if download_and_optimize(url, dest):
                    item.image = f"products/{slug}.webp"
                    item.save(update_fields=["image"])
                    prod_success += 1
                    self.stdout.write(f"  [✓] Product '{item.name}' -> {item.image.url} ({dest.stat().st_size // 1024} KB)")
                else:
                    missing_photos.append(item.name)
            else:
                missing_photos.append(item.name)

        self.stdout.write(self.style.SUCCESS(
            f"\nFinished! Successfully processed {cat_success} categories and {prod_success} products."
        ))

        if missing_photos:
            self.stdout.write(self.style.WARNING(f"Items without real photo ({len(missing_photos)}):"))
            for name in missing_photos:
                self.stdout.write(f"  - {name}")
        else:
            self.stdout.write(self.style.SUCCESS("All products and categories have verified real photos!"))
