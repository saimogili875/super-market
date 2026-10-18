"""Seed comprehensive demo data for FreshMart.

Runs catalog, products, categories, demo users, coupons, product images,
and sample delivery orders idempotently. Perfect for instant hydration
of Supabase Postgres or local development databases.

Run with:
    python manage.py seed_demo
"""
from decimal import Decimal
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.accounts.models import Role, User
from apps.customer_auth.models import Customer
from apps.menu.models import MenuItem
from apps.orders.models import Order, OrderItem, OrderStatus, OrderType


class Command(BaseCommand):
    help = "Seeds complete FreshMart demo dataset idempotently (users, catalog, photos, coupons, orders)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--skip-images",
            action="store_true",
            help="Skip downloading and optimizing product images.",
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("=== FreshMart Full Demo Data Hydration ==="))

        # 1. Seed base catalog, users, categories, coupons
        self.stdout.write("Running seed_freshmart...")
        call_command("seed_freshmart")

        # 2. Fetch and optimize product images
        if not options.get("skip_images"):
            self.stdout.write("\nFetching and optimizing real product photos (<120KB WebP)...")
            try:
                call_command("fetch_product_images")
            except Exception as e:
                self.stdout.write(self.style.WARNING(f"Image fetch skipped/errored: {e}"))

        # 3. Seed sample orders for live dashboard demo
        self.stdout.write("\nSeeding realistic sample delivery orders...")
        self._seed_sample_orders()

        self.stdout.write(self.style.SUCCESS("\n✓ Demo database hydration complete!"))
        self.stdout.write(self.style.SUCCESS("Demo accounts:"))
        self.stdout.write("  - Customer: customer_sneha / Pass1234! (Shop: /order/menu/)")
        self.stdout.write("  - Delivery Agent: agent_kiran / Pass1234! (Portal: /agent/)")
        self.stdout.write("  - Store Manager: manager_ravi / Pass1234! (Portal: /manager/)")
        self.stdout.write("  - Admin: admin / Admin1234! (Backoffice: /backoffice/)")

    def _seed_sample_orders(self):
        customer_user = User.objects.filter(username="customer_sneha").first()
        agent_user = User.objects.filter(username="agent_kiran").first()
        customer_obj = Customer.objects.filter(email="sneha.sharma@example.com").first()

        if not customer_user or not agent_user:
            return

        items = list(MenuItem.objects.filter(is_available=True)[:10])
        if len(items) < 4:
            return

        # Order 1: Dispatched (Active for Agent & Manager)
        ord1, created = Order.objects.get_or_create(
            customer=customer_user,
            contact_name="Sneha Sharma",
            contact_phone="9876543210",
            status=OrderStatus.DISPATCHED,
            order_type=OrderType.DELIVERY,
            defaults={
                "delivery_customer": customer_obj,
                "agent": agent_user,
                "total_amount": items[0].price * 2 + items[1].price,
                "maps_url": "https://www.google.com/maps/dir/?api=1&destination=Flat+402+Green+Meadows+Jubilee+Hills+Hyderabad",
                "instructions": "Leave near front door if doorbell rings.",
                "delivery_accepted_at": timezone.now(),
                "delivery_picked_at": timezone.now(),
            },
        )
        if created:
            OrderItem.objects.create(
                order=ord1,
                menu_item=items[0],
                name_snap=items[0].name,
                unit_price=items[0].price,
                quantity=2,
                is_picked=True,
            )
            OrderItem.objects.create(
                order=ord1,
                menu_item=items[1],
                name_snap=items[1].name,
                unit_price=items[1].price,
                quantity=1,
                is_picked=True,
            )
            self.stdout.write(f"  [+] Created active dispatched order #{ord1.pk}")

        # Order 2: Ready for Pickup
        ord2, created = Order.objects.get_or_create(
            customer=customer_user,
            contact_name="Sneha Sharma",
            contact_phone="9876543210",
            status=OrderStatus.READY,
            order_type=OrderType.DELIVERY,
            defaults={
                "delivery_customer": customer_obj,
                "agent": agent_user,
                "total_amount": items[2].price + items[3].price * 3,
                "maps_url": "https://www.google.com/maps/dir/?api=1&destination=Road+No+36+Jubilee+Hills+Hyderabad",
                "instructions": "Call upon arrival.",
                "delivery_accepted_at": timezone.now(),
            },
        )
        if created:
            OrderItem.objects.create(
                order=ord2,
                menu_item=items[2],
                name_snap=items[2].name,
                unit_price=items[2].price,
                quantity=1,
                is_picked=True,
            )
            OrderItem.objects.create(
                order=ord2,
                menu_item=items[3],
                name_snap=items[3].name,
                unit_price=items[3].price,
                quantity=3,
                is_picked=True,
            )
            self.stdout.write(f"  [+] Created ready order #{ord2.pk}")

        # Order 3: Completed / Paid (Order History)
        ord3, created = Order.objects.get_or_create(
            customer=customer_user,
            contact_name="Sneha Sharma",
            contact_phone="9876543210",
            status=OrderStatus.PAID,
            order_type=OrderType.DELIVERY,
            defaults={
                "delivery_customer": customer_obj,
                "agent": agent_user,
                "total_amount": Decimal("640.00"),
                "maps_url": "https://www.google.com/maps/dir/?api=1&destination=Road+No+36+Jubilee+Hills+Hyderabad",
                "instructions": "Handover directly.",
                "delivery_accepted_at": timezone.now(),
                "delivery_picked_at": timezone.now(),
                "delivery_completed_at": timezone.now(),
                "delivery_pod_type": "handover",
                "delivery_pod_detail": "Verified and received by customer",
            },
        )
        if created:
            OrderItem.objects.create(
                order=ord3,
                menu_item=items[0],
                name_snap=items[0].name,
                unit_price=items[0].price,
                quantity=1,
                is_picked=True,
            )
            self.stdout.write(f"  [+] Created completed order #{ord3.pk}")
