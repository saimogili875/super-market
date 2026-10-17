"""Seed practical supermarket categories, products, suppliers, coupons, and sample records."""
from datetime import date, timedelta
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.accounts.models import Role, User
from apps.audit.models import AuditLog
from apps.coupons.models import Coupon
from apps.menu.models import Category, MenuItem, StockMovement
from apps.notifications.models import AdminNotification
from apps.payments.models import PaymentTransaction
from apps.suppliers.models import PurchaseOrder, Supplier


class Command(BaseCommand):
    help = "Seeds initial supermarket categories, products, suppliers, coupons, and records."

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write("Seeding Supermarket Catalog...")

        # 1. Categories
        categories_data = [
            ("Fruits and Vegetables", "Fresh Farm Harvest", 1),
            ("Rice, Pulses and Grains", "Daily Pantry Staples", 2),
            ("Dairy and Eggs", "Farm Fresh Dairy & Poultry", 3),
            ("Snacks and Biscuits", "Munchies & Namkeens", 4),
            ("Beverages", "Juices, Soda, Tea & Coffee", 5),
            ("Cooking Essentials", "Oils, Ghee, Masalas & Spices", 6),
            ("Personal Care", "Hygiene, Skincare & Oral Care", 7),
            ("Household Essentials", "Cleaners, Detergents & Paper", 8),
            ("Packaged Foods", "Noodles, Pasta, Sauces & Spreads", 9),
            ("Frozen Foods", "Ready-to-Cook & Frozen Treats", 10),
        ]

        cat_objs = {}
        for name, tag, sort_order in categories_data:
            cat, created = Category.objects.update_or_create(
                name=name,
                defaults={"tag": tag, "sort_order": sort_order, "is_active": True},
            )
            cat_objs[name] = cat
            if created:
                self.stdout.write(f"  + Category: {name}")

        # 2. Suppliers
        suppliers_data = [
            ("GreenFields Organic Farms", "Ramesh Patel", "ramesh@greenfields.com", "+91 98234 56789", "Nashik, Maharashtra", "Active"),
            ("Shri Krishna Agro Mills", "Anand Sharma", "orders@shrikrishnaagro.com", "+91 98450 11223", "Guntur, Andhra Pradesh", "Active"),
            ("Himalayan Dairy Coop", "Sunita Rao", "support@himalayandairy.in", "+91 98765 43210", "Anand, Gujarat", "Active"),
            ("Heritage Spices & Oils", "Vikram Verma", "vikram@heritagespices.com", "+91 97110 33445", "Kochi, Kerala", "Active"),
            ("Apex Consumer Goods Ltd", "Pooja Mehta", "sales@apexconsumer.com", "+91 98190 55667", "Mumbai, Maharashtra", "Active"),
        ]

        sup_objs = {}
        for name, contact, email, phone, addr, status in suppliers_data:
            sup, _ = Supplier.objects.update_or_create(
                name=name,
                defaults={
                    "contact": contact,
                    "email": email,
                    "phone": phone,
                    "address": addr,
                    "status": status,
                },
            )
            sup_objs[name] = sup

        # 3. Supermarket Products
        today = date.today()
        products_data = [
            # Fruits & Veg
            ("Fresh Red Onions (Nashik)", "Fruits and Vegetables", "FreshFields Organic Farms", "SKU-VEG-001", "8901030001", Decimal("35.00"), Decimal("24.00"), 120, "kg", 15, today + timedelta(days=20)),
            ("Farm Fresh Tomatoes", "Fruits and Vegetables", "GreenFields Organic Farms", "SKU-VEG-002", "8901030002", Decimal("40.00"), Decimal("28.00"), 85, "kg", 10, today + timedelta(days=7)),
            ("Shimla Crisp Apples (Royal Gala)", "Fruits and Vegetables", "GreenFields Organic Farms", "SKU-FRT-001", "8901030003", Decimal("180.00"), Decimal("130.00"), 45, "kg", 8, today + timedelta(days=14)),
            ("Organic Robusta Bananas", "Fruits and Vegetables", "GreenFields Organic Farms", "SKU-FRT-002", "8901030004", Decimal("60.00"), Decimal("42.00"), 4, "kg", 10, today + timedelta(days=4)), # Low stock + near expiry
            
            # Grains & Pulses
            ("Royal Basmati Rice (Aged 2 Yrs)", "Rice, Pulses and Grains", "Shri Krishna Agro Mills", "SKU-GRN-001", "8901030005", Decimal("145.00"), Decimal("110.00"), 200, "kg", 20, today + timedelta(days=365)),
            ("Organic Toor Dal (Unpolished)", "Rice, Pulses and Grains", "Shri Krishna Agro Mills", "SKU-GRN-002", "8901030006", Decimal("165.00"), Decimal("130.00"), 150, "kg", 15, today + timedelta(days=180)),
            ("Whole Wheat Sharbati Atta (5kg)", "Rice, Pulses and Grains", "Shri Krishna Agro Mills", "SKU-GRN-003", "8901030007", Decimal("260.00"), Decimal("210.00"), 60, "pack", 10, today + timedelta(days=90)),

            # Dairy & Eggs
            ("Pasteurized Full Cream Milk (1L)", "Dairy and Eggs", "Himalayan Dairy Coop", "SKU-DRY-001", "8901030008", Decimal("68.00"), Decimal("56.00"), 40, "L", 10, today + timedelta(days=3)), # Near expiry
            ("Fresh Farm Paneer (200g)", "Dairy and Eggs", "Himalayan Dairy Coop", "SKU-DRY-002", "8901030009", Decimal("95.00"), Decimal("75.00"), 25, "pack", 5, today + timedelta(days=5)),
            ("Farm Fresh Brown Eggs (Pack of 12)", "Dairy and Eggs", "Himalayan Dairy Coop", "SKU-DRY-003", "8901030010", Decimal("110.00"), Decimal("85.00"), 3, "pack", 8, today + timedelta(days=12)), # Low stock

            # Cooking Essentials
            ("Pure Cold Pressed Mustard Oil (1L)", "Cooking Essentials", "Heritage Spices & Oils", "SKU-OIL-001", "8901030011", Decimal("195.00"), Decimal("150.00"), 50, "L", 10, today + timedelta(days=240)),
            ("Danedar Pure Cow Ghee (500ml)", "Cooking Essentials", "Heritage Spices & Oils", "SKU-OIL-002", "8901030012", Decimal("340.00"), Decimal("270.00"), 35, "pack", 5, today + timedelta(days=300)),
            ("Kashmiri Red Chilli Powder (200g)", "Cooking Essentials", "Heritage Spices & Oils", "SKU-SPC-001", "8901030013", Decimal("120.00"), Decimal("90.00"), 70, "pack", 10, today + timedelta(days=360)),

            # Beverages
            ("Assam CTC Premium Black Tea (500g)", "Beverages", "Apex Consumer Goods Ltd", "SKU-BEV-001", "8901030014", Decimal("220.00"), Decimal("170.00"), 45, "pack", 10, today + timedelta(days=365)),
            ("Cold Pressed Valencia Orange Juice (1L)", "Beverages", "GreenFields Organic Farms", "SKU-BEV-002", "8901030015", Decimal("130.00"), Decimal("95.00"), 20, "L", 5, today + timedelta(days=6)), # Near expiry
            ("Sparkling Mineral Water (750ml)", "Beverages", "Apex Consumer Goods Ltd", "SKU-BEV-003", "8901030016", Decimal("80.00"), Decimal("50.00"), 0, "pcs", 10, today + timedelta(days=180)), # Out of stock

            # Snacks & Household
            ("Classic Marie Gold Biscuits (300g)", "Snacks and Biscuits", "Apex Consumer Goods Ltd", "SKU-SNK-001", "8901030017", Decimal("45.00"), Decimal("35.00"), 80, "pack", 15, today + timedelta(days=120)),
            ("Surface Disinfectant Floor Cleaner (1L)", "Household Essentials", "Apex Consumer Goods Ltd", "SKU-HSH-001", "8901030018", Decimal("165.00"), Decimal("120.00"), 30, "L", 5, today + timedelta(days=500)),
        ]

        admin_user = User.objects.filter(role=Role.ADMIN).first()

        for (p_name, c_name, s_name, sku, bcode, price, cost, stock, unit, low_th, exp) in products_data:
            cat = cat_objs.get(c_name)
            sup = sup_objs.get(s_name)
            item, created = MenuItem.objects.update_or_create(
                sku=sku,
                defaults={
                    "name": p_name,
                    "category": cat,
                    "barcode": bcode,
                    "price": price,
                    "cost_price": cost,
                    "stock_quantity": stock,
                    "track_stock": True,
                    "unit": unit,
                    "low_stock_threshold": low_th,
                    "expiry_date": exp,
                    "supplier": sup,
                    "is_available": stock > 0,
                },
            )
            if created and stock > 0:
                StockMovement.objects.create(
                    item=item,
                    movement_type="RESTOCK",
                    quantity=stock,
                    resulting_quantity=stock,
                    cost_per_unit=cost,
                    notes="Initial inventory setup",
                    created_by=admin_user,
                )

        # 4. Purchase Orders
        pos_data = [
            ("PO-1048", "GreenFields Organic Farms", "Fresh Red Onions (Nashik)", 100, Decimal("24.00"), "Complete", 100, today - timedelta(days=2)),
            ("PO-1049", "Shri Krishna Agro Mills", "Royal Basmati Rice (Aged 2 Yrs)", 150, Decimal("110.00"), "Complete", 150, today - timedelta(days=1)),
            ("PO-1050", "Himalayan Dairy Coop", "Farm Fresh Paneer (200g)", 50, Decimal("75.00"), "Partial", 25, None),
            ("PO-1051", "GreenFields Organic Farms", "Organic Robusta Bananas", 80, Decimal("42.00"), "Submitted", 0, None),
            ("PO-1052", "Apex Consumer Goods Ltd", "Sparkling Mineral Water (750ml)", 100, Decimal("50.00"), "Draft", 0, None),
        ]
        for po_num, s_name, prod_name, qty, cost, status, rec_qty, rec_at in pos_data:
            PurchaseOrder.objects.update_or_create(
                po_number=po_num,
                defaults={
                    "supplier": sup_objs[s_name],
                    "product_name": prod_name,
                    "quantity": qty,
                    "unit_cost": cost,
                    "total_cost": (Decimal(qty) * cost).quantize(Decimal("0.01")),
                    "status": status,
                    "received_quantity": rec_qty,
                    "received_at": rec_at,
                    "expected_delivery": today + timedelta(days=2) if not rec_at else None,
                },
            )

        # 5. Coupons
        coupons_data = [
            ("FRESH20", "Percentage", Decimal("20.00"), today - timedelta(days=5), today + timedelta(days=25), 200, 48, Decimal("499.00"), True),
            ("SUPER100", "Fixed", Decimal("100.00"), today - timedelta(days=2), today + timedelta(days=15), 150, 22, Decimal("899.00"), True),
            ("DIWALI500", "Fixed", Decimal("500.00"), today + timedelta(days=10), today + timedelta(days=20), 50, 0, Decimal("2499.00"), True),
            ("WELCOME10", "Percentage", Decimal("10.00"), today - timedelta(days=60), today - timedelta(days=1), 500, 312, Decimal("299.00"), True),
        ]
        for code, dtype, val, vf, vt, ulim, used, min_ord, act in coupons_data:
            Coupon.objects.update_or_create(
                code=code,
                defaults={
                    "discount_type": dtype,
                    "value": val,
                    "valid_from": vf,
                    "valid_to": vt,
                    "usage_limit": ulim,
                    "times_used": used,
                    "min_order": min_ord,
                    "is_active": act,
                },
            )

        # 6. Notifications
        notifications_data = [
            ("Low stock", "Low stock: Organic Robusta Bananas", "Available quantity (4 kg) is below threshold (10 kg).", "SKU-FRT-002", "wn"),
            ("Low stock", "Low stock: Farm Fresh Brown Eggs (Pack of 12)", "Available quantity (3 packs) is below threshold (8 packs).", "SKU-DRY-003", "wn"),
            ("Expiry", "Expiring soon: Pasteurized Full Cream Milk (1L)", "Batch expires in 3 days. Recommend promotional mark-down.", "SKU-DRY-001", "er"),
            ("Expiry", "Expiring soon: Cold Pressed Valencia Orange Juice (1L)", "Batch expires in 6 days.", "SKU-BEV-002", "er"),
            ("Order", "New counter order placed ORD-8941", "Store POS billing checkout completed.", "ORD-8941", "gd"),
            ("Delivery", "Goods received: PO-1048 from GreenFields Organic Farms", "100 kg of Red Onions verified and added to stock.", "PO-1048", "ok"),
        ]
        for ntype, title, msg, ref_id, sev in notifications_data:
            AdminNotification.objects.get_or_create(
                reference_id=ref_id,
                notification_type=ntype,
                defaults={"title": title, "message": msg, "severity": sev},
            )

        # 7. Audit Logs
        audits_data = [
            (admin_user, "Login", "Logins", "ADM-001", "Admin login successful", "127.0.0.1", "Success"),
            (admin_user, "Stock adjusted", "Inventory", "SKU-FRT-002", "Stock manually corrected (10 -> 4)", "127.0.0.1", "Success"),
            (admin_user, "Price changed", "Products", "SKU-GRN-001", "Price updated ₹140.00 -> ₹145.00", "127.0.0.1", "Success"),
            (admin_user, "Purchase order submitted", "Inventory", "PO-1051", "PO submitted to GreenFields Organic Farms", "127.0.0.1", "Success"),
            (admin_user, "Coupon created", "Security", "FRESH20", "20% discount coupon created with limit 200", "127.0.0.1", "Success"),
            (None, "Login", "Logins", "UNAUTH", "Failed login attempt for user 'root'", "192.168.1.104", "Failed"),
        ]
        for usr, act, cat, rec_id, chg, ip, st in audits_data:
            AuditLog.objects.get_or_create(
                action=act,
                record_id=rec_id,
                defaults={
                    "user": usr,
                    "user_display": usr.username if usr else "Unknown",
                    "category": cat,
                    "change_summary": chg,
                    "ip_address": ip,
                    "status": st,
                },
            )

        # 8. Payments
        from apps.orders.models import Order
        recent_orders = Order.objects.all().order_by("-created_at")[:5]
        methods = ["UPI", "Card", "Cash", "UPI", "NetBanking"]
        for idx, ord_obj in enumerate(recent_orders):
            PaymentTransaction.objects.get_or_create(
                txn_id=f"TXN-{8800 + ord_obj.pk}",
                defaults={
                    "order": ord_obj,
                    "order_ref": f"ORD-{ord_obj.pk}",
                    "customer_name": ord_obj.contact_name or "Walk-in Customer",
                    "method": methods[idx % len(methods)],
                    "amount": ord_obj.total_amount if ord_obj.total_amount > 0 else Decimal("450.00"),
                    "status": "Paid" if ord_obj.status in ["PAID", "READY", "COLLECT"] else "Pending",
                },
            )

        self.stdout.write(self.style.SUCCESS("Supermarket catalog and management sample data seeded successfully!"))
