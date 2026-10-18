"""Seed comprehensive FreshMart catalog, 40+ products, categories, coupons, and 4 role demo accounts."""
from datetime import date, timedelta
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.accounts.models import AgentProfile, Role, StaffProfile, User
from apps.coupons.models import Coupon
from apps.customer_auth.models import CustomerAddress
from apps.menu.models import Category, MenuItem, StockMovement
from apps.suppliers.models import Supplier


class Command(BaseCommand):
    help = "Seeds FreshMart supermarket categories, 40+ products, demo accounts, and active coupons."

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write("Seeding FreshMart Supermarket System...")

        # =========================================================================
        # 1. DEMO ACCOUNTS (Admin, Store Manager, Delivery Agent, Customer)
        # =========================================================================
        self.stdout.write("1. Creating Demo User Accounts...")

        # 1a. Super Admin
        admin_user, _ = User.objects.update_or_create(
            username="admin",
            defaults={
                "email": "admin@freshmart.com",
                "first_name": "FreshMart",
                "last_name": "Admin",
                "role": Role.ADMIN,
                "is_staff": True,
                "is_superuser": True,
                "is_active": True,
            },
        )
        admin_user.set_password("Admin1234!")
        admin_user.save()
        self.stdout.write("  [+] Admin: admin / Admin1234!")

        # 1b. Store Manager (manager_ravi)
        mgr_user, _ = User.objects.update_or_create(
            username="manager_ravi",
            defaults={
                "email": "ravi.kumar@freshmart.com",
                "first_name": "Ravi",
                "last_name": "Kumar",
                "role": Role.MANAGER,
                "phone": "9845012345",
                "is_staff": True,
                "is_active": True,
            },
        )
        mgr_user.set_password("Pass1234!")
        mgr_user.save()
        StaffProfile.objects.update_or_create(
            user=mgr_user,
            defaults={
                "department": "Store Operations",
                "employee_id": "MGR-001",
                "responsibilities": "Supermarket store operations, inventory oversight, and staff management",
            },
        )
        self.stdout.write("  [+] Store Manager: manager_ravi / Pass1234!")

        # 1c. Delivery Agent (agent_kiran)
        agent_user, _ = User.objects.update_or_create(
            username="agent_kiran",
            defaults={
                "email": "kiran.agent@freshmart.com",
                "first_name": "Kiran",
                "last_name": "Venkatesh",
                "role": Role.AGENT,
                "phone": "9876500001",
                "is_active": True,
            },
        )
        agent_user.set_password("Pass1234!")
        agent_user.save()
        AgentProfile.objects.update_or_create(
            user=agent_user,
            defaults={
                "is_available": True,
                "vehicle_type": "Motorbike",
                "vehicle_number": "TS 09 FM 4589",
            },
        )
        self.stdout.write("  [+] Delivery Agent: agent_kiran / Pass1234!")

        # 1d. Customer (customer_sneha)
        cust_user, _ = User.objects.update_or_create(
            username="customer_sneha",
            defaults={
                "email": "sneha.sharma@example.com",
                "first_name": "Sneha",
                "last_name": "Sharma",
                "role": Role.CUSTOMER,
                "phone": "9876543210",
                "is_active": True,
            },
        )
        cust_user.set_password("Pass1234!")
        cust_user.save()

        from apps.customer_auth.models import Customer, CustomerAddress
        customer_obj, _ = Customer.objects.update_or_create(
            phone="9876543210",
            email="sneha.sharma@example.com",
            defaults={
                "name": "Sneha Sharma",
                "default_address": "Flat 402, Green Meadows, Jubilee Hills Road No. 36, Hyderabad",
            },
        )
        CustomerAddress.objects.update_or_create(
            customer=customer_obj,
            title="Home",
            defaults={
                "recipient_name": "Sneha Sharma",
                "phone": "9876543210",
                "address": "Flat 402, Green Meadows, Jubilee Hills Road No. 36",
                "city": "Hyderabad",
                "is_default": True,
            },
        )
        self.stdout.write("  [+] Customer: customer_sneha / Pass1234!")

        # =========================================================================
        # 2. SUPERMARKET CATEGORIES (10 Categories)
        # =========================================================================
        self.stdout.write("2. Creating Supermarket Categories...")
        categories_data = [
            ("Fruits and Vegetables", "Fresh Farm Harvest Daily", 1),
            ("Rice, Pulses and Grains", "Daily Pantry & Atta Staples", 2),
            ("Dairy and Eggs", "Farm Fresh Dairy, Bread & Poultry", 3),
            ("Cooking Essentials", "Pure Cold-Pressed Oils, Ghee & Masalas", 4),
            ("Snacks and Biscuits", "Crisps, Cookies, Namkeens & Rusks", 5),
            ("Beverages", "Juices, Soft Drinks, Tea & Coffee", 6),
            ("Household Essentials", "Floor Cleaners, Detergents & Tissues", 7),
            ("Personal Care", "Soaps, Oral Care, Shampoos & Hygiene", 8),
            ("Packaged Foods", "Noodles, Pasta, Sauces & Spreads", 9),
            ("Breakfast and Cereals", "Oats, Corn Flakes & Muesli", 10),
        ]

        cat_objs = {}
        for name, tag, sort_order in categories_data:
            cat, _ = Category.objects.update_or_create(
                name=name,
                defaults={"tag": tag, "sort_order": sort_order, "is_active": True},
            )
            cat_objs[name] = cat

        # =========================================================================
        # 3. SUPPLIERS
        # =========================================================================
        suppliers_data = [
            ("GreenFields Organic Farms", "Ramesh Patel", "ramesh@greenfields.com", "+91 98234 56789", "Nashik, Maharashtra"),
            ("Shri Krishna Agro Mills", "Anand Sharma", "orders@shrikrishnaagro.com", "+91 98450 11223", "Guntur, Andhra Pradesh"),
            ("Himalayan Dairy Coop", "Sunita Rao", "support@himalayandairy.in", "+91 98765 43210", "Anand, Gujarat"),
            ("Heritage Spices & Oils", "Vikram Verma", "vikram@heritagespices.com", "+91 97110 33445", "Kochi, Kerala"),
            ("Apex Consumer Products", "Pooja Mehta", "sales@apexconsumer.com", "+91 98190 55667", "Mumbai, Maharashtra"),
        ]
        sup_objs = {}
        for name, contact, email, phone, addr in suppliers_data:
            sup, _ = Supplier.objects.update_or_create(
                name=name,
                defaults={"contact": contact, "email": email, "phone": phone, "address": addr, "status": "Active"},
            )
            sup_objs[name] = sup

        # =========================================================================
        # 4. 42 SUPERMARKET PRODUCTS ACROSS ALL DEPARTMENTS
        # =========================================================================
        self.stdout.write("3. Seeding 42 Supermarket Products (with MRP & % Discounts)...")
        today = date.today()

        # Format: (Name, Category, Supplier, SKU, Barcode, MRP_price, Cost, Stock, Unit, LowThreshold, ExpiryDays, OfferPercent)
        products_catalog = [
            # 1. Fruits & Veg (1-7)
            ("Fresh Red Onions (Nashik Grade-A)", "Fruits and Vegetables", "GreenFields Organic Farms", "SKU-VEG-001", "8901001", Decimal("40.00"), Decimal("24.00"), 180, "kg", 20, 25, 25),
            ("Farm Fresh Ripe Red Tomatoes", "Fruits and Vegetables", "GreenFields Organic Farms", "SKU-VEG-002", "8901002", Decimal("45.00"), Decimal("28.00"), 120, "kg", 15, 8, 20),
            ("Shimla Crisp Royal Gala Apples", "Fruits and Vegetables", "GreenFields Organic Farms", "SKU-FRT-001", "8901003", Decimal("220.00"), Decimal("150.00"), 65, "kg", 10, 18, 30),
            ("Organic Robusta Golden Bananas", "Fruits and Vegetables", "GreenFields Organic Farms", "SKU-FRT-002", "8901004", Decimal("65.00"), Decimal("42.00"), 85, "kg", 12, 5, 23),
            ("Fresh Pahadi Potatoes (5kg Bag)", "Fruits and Vegetables", "GreenFields Organic Farms", "SKU-VEG-003", "8901005", Decimal("180.00"), Decimal("125.00"), 90, "pack", 10, 30, 28),
            ("Farm Fresh Tender Carrots (1kg)", "Fruits and Vegetables", "GreenFields Organic Farms", "SKU-VEG-004", "8901006", Decimal("55.00"), Decimal("38.00"), 70, "kg", 10, 10, 18),
            ("Fresh Green Spinach / Palak Bunch", "Fruits and Vegetables", "GreenFields Organic Farms", "SKU-VEG-005", "8901007", Decimal("30.00"), Decimal("18.00"), 50, "pcs", 10, 4, 33),

            # 2. Staples & Grains (8-14)
            ("Royal Aged Basmati Rice (5kg Bag)", "Rice, Pulses and Grains", "Shri Krishna Agro Mills", "SKU-GRN-001", "8901008", Decimal("599.00"), Decimal("420.00"), 140, "pack", 15, 365, 30),
            ("Unpolished Desi Toor Dal (1kg)", "Rice, Pulses and Grains", "Shri Krishna Agro Mills", "SKU-GRN-002", "8901009", Decimal("185.00"), Decimal("135.00"), 160, "kg", 20, 180, 24),
            ("Whole Wheat Sharbati Atta (10kg Bag)", "Rice, Pulses and Grains", "Shri Krishna Agro Mills", "SKU-GRN-003", "8901010", Decimal("480.00"), Decimal("360.00"), 95, "pack", 10, 90, 25),
            ("Organic Moong Dal Washed (1kg)", "Rice, Pulses and Grains", "Shri Krishna Agro Mills", "SKU-GRN-004", "8901011", Decimal("170.00"), Decimal("125.00"), 80, "kg", 15, 180, 21),
            ("Brown Sona Masoori Rice (5kg)", "Rice, Pulses and Grains", "Shri Krishna Agro Mills", "SKU-GRN-005", "8901012", Decimal("380.00"), Decimal("290.00"), 110, "pack", 15, 300, 26),
            ("Premium Kabuli Chana / Chickpeas (1kg)", "Rice, Pulses and Grains", "Shri Krishna Agro Mills", "SKU-GRN-006", "8901013", Decimal("160.00"), Decimal("115.00"), 75, "kg", 10, 240, 25),
            ("Coarse Roasted Rava / Sooji (1kg)", "Rice, Pulses and Grains", "Shri Krishna Agro Mills", "SKU-GRN-007", "8901014", Decimal("65.00"), Decimal("48.00"), 130, "pack", 15, 120, 20),

            # 3. Dairy & Bakery (15-20)
            ("Pasteurized Full Cream Fresh Milk (1L)", "Dairy and Eggs", "Himalayan Dairy Coop", "SKU-DRY-001", "8901015", Decimal("72.00"), Decimal("58.00"), 65, "L", 15, 3, 11),
            ("Farm Fresh Malai Paneer (200g)", "Dairy and Eggs", "Himalayan Dairy Coop", "SKU-DRY-002", "8901016", Decimal("105.00"), Decimal("78.00"), 45, "pack", 10, 6, 19),
            ("Farm Fresh Brown Eggs (Pack of 12)", "Dairy and Eggs", "Himalayan Dairy Coop", "SKU-DRY-003", "8901017", Decimal("120.00"), Decimal("88.00"), 60, "pack", 10, 14, 25),
            ("Artisan Whole Wheat Sourdough Bread (400g)", "Dairy and Eggs", "Himalayan Dairy Coop", "SKU-DRY-004", "8901018", Decimal("60.00"), Decimal("42.00"), 40, "pack", 8, 4, 25),
            ("Pure Salted Table Butter (500g Block)", "Dairy and Eggs", "Himalayan Dairy Coop", "SKU-DRY-005", "8901019", Decimal("285.00"), Decimal("230.00"), 50, "pack", 10, 90, 16),
            ("Fresh Thick Dahi / Natural Curd (400g)", "Dairy and Eggs", "Himalayan Dairy Coop", "SKU-DRY-006", "8901020", Decimal("45.00"), Decimal("34.00"), 55, "pack", 10, 7, 18),

            # 4. Cooking Essentials (21-25)
            ("Pure Cold Pressed Mustard Oil (1L Bottle)", "Cooking Essentials", "Heritage Spices & Oils", "SKU-OIL-001", "8901021", Decimal("210.00"), Decimal("155.00"), 75, "L", 10, 270, 24),
            ("Refined Sunflower Cooking Oil (1L Pouch)", "Cooking Essentials", "Heritage Spices & Oils", "SKU-OIL-002", "8901022", Decimal("165.00"), Decimal("125.00"), 120, "L", 15, 240, 21),
            ("Danedar Pure Desi Cow Ghee (500ml Jar)", "Cooking Essentials", "Heritage Spices & Oils", "SKU-OIL-003", "8901023", Decimal("380.00"), Decimal("295.00"), 60, "pack", 8, 300, 21),
            ("Kashmiri Deggi Mirch Powder (200g)", "Cooking Essentials", "Heritage Spices & Oils", "SKU-SPC-001", "8901024", Decimal("130.00"), Decimal("95.00"), 90, "pack", 10, 365, 23),
            ("Organic Turmeric Powder (200g Box)", "Cooking Essentials", "Heritage Spices & Oils", "SKU-SPC-002", "8901025", Decimal("80.00"), Decimal("55.00"), 110, "pack", 15, 365, 25),

            # 5. Snacks & Biscuits (26-29)
            ("Classic Marie Digestive Biscuits (300g)", "Snacks and Biscuits", "Apex Consumer Products", "SKU-SNK-001", "8901026", Decimal("45.00"), Decimal("32.00"), 140, "pack", 20, 150, 22),
            ("Crunchy Salted Potato Chips (150g)", "Snacks and Biscuits", "Apex Consumer Products", "SKU-SNK-002", "8901027", Decimal("50.00"), Decimal("35.00"), 100, "pack", 15, 90, 20),
            ("Spicy Aloo Bhujia Namkeen (400g Family Pack)", "Snacks and Biscuits", "Apex Consumer Products", "SKU-SNK-003", "8901028", Decimal("110.00"), Decimal("80.00"), 95, "pack", 12, 180, 27),
            ("Roasted California Almonds (250g Pouch)", "Snacks and Biscuits", "Apex Consumer Products", "SKU-SNK-004", "8901029", Decimal("299.00"), Decimal("210.00"), 65, "pack", 10, 240, 30),

            # 6. Beverages (30-33)
            ("Assam CTC Golden Blend Tea (500g)", "Beverages", "Apex Consumer Products", "SKU-BEV-001", "8901030", Decimal("240.00"), Decimal("175.00"), 80, "pack", 10, 365, 25),
            ("Filter Coffee Roasted Chicory Blend (200g)", "Beverages", "Heritage Spices & Oils", "SKU-BEV-002", "8901031", Decimal("145.00"), Decimal("105.00"), 60, "pack", 8, 270, 24),
            ("Cold Pressed Valencia Orange Juice (1L)", "Beverages", "GreenFields Organic Farms", "SKU-BEV-003", "8901032", Decimal("140.00"), Decimal("99.00"), 40, "L", 8, 8, 29),
            ("Pure Natural Coconut Water (200ml Tetra)", "Beverages", "GreenFields Organic Farms", "SKU-BEV-004", "8901033", Decimal("50.00"), Decimal("35.00"), 90, "pack", 15, 60, 20),

            # 7. Household Essentials (34-37)
            ("Citrus Disinfectant Surface Cleaner (1L)", "Household Essentials", "Apex Consumer Products", "SKU-HSH-001", "8901034", Decimal("185.00"), Decimal("130.00"), 65, "L", 10, 500, 27),
            ("Bio-Enzyme Laundry Detergent Powder (2kg)", "Household Essentials", "Apex Consumer Products", "SKU-HSH-002", "8901035", Decimal("320.00"), Decimal("225.00"), 50, "pack", 8, 500, 30),
            ("Lemon Fresh Dishwash Gel (750ml Bottle)", "Household Essentials", "Apex Consumer Products", "SKU-HSH-003", "8901036", Decimal("155.00"), Decimal("110.00"), 75, "pack", 10, 500, 26),
            ("Virgin Wood 2-Ply Kitchen Towels (Pack of 4)", "Household Essentials", "Apex Consumer Products", "SKU-HSH-004", "8901037", Decimal("199.00"), Decimal("135.00"), 45, "pack", 8, 700, 32),

            # 8. Personal Care (38-40)
            ("Moisturizing Neem & Aloe Bathing Soap (Pack of 4)", "Personal Care", "Apex Consumer Products", "SKU-PC-001", "8901038", Decimal("180.00"), Decimal("120.00"), 85, "pack", 12, 365, 33),
            ("Anti-Dandruff Tea Tree Herbal Shampoo (300ml)", "Personal Care", "Apex Consumer Products", "SKU-PC-002", "8901039", Decimal("250.00"), Decimal("170.00"), 60, "pack", 10, 365, 32),
            ("Ayurvedic Herbal Toothpaste (150g + 50g Free)", "Personal Care", "Apex Consumer Products", "SKU-PC-003", "8901040", Decimal("125.00"), Decimal("85.00"), 105, "pack", 15, 365, 32),

            # 9. Breakfast & Instant (41-42)
            ("Rolled Whole Grain Oats (1kg Pouch)", "Breakfast and Cereals", "Shri Krishna Agro Mills", "SKU-BF-001", "8901041", Decimal("199.00"), Decimal("140.00"), 70, "pack", 10, 240, 30),
            ("Almond & Honey Crunchy Muesli (400g Box)", "Breakfast and Cereals", "Apex Consumer Products", "SKU-BF-002", "8901042", Decimal("280.00"), Decimal("195.00"), 55, "pack", 8, 240, 30),
        ]

        for p_name, c_name, s_name, sku, bcode, price, cost, stock, unit, low_th, exp_days, off_pct in products_catalog:
            cat = cat_objs.get(c_name)
            sup = sup_objs.get(s_name)
            exp_date = today + timedelta(days=exp_days)
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
                    "expiry_date": exp_date,
                    "supplier": sup,
                    "offer_percent": off_pct,
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
                    notes="FreshMart initial supermarket catalog setup",
                    created_by=admin_user,
                )

        # =========================================================================
        # 5. ACTIVE SUPERMARKET COUPONS
        # =========================================================================
        self.stdout.write("4. Seeding Active Supermarket Coupons (FRESH20, SAVE100, DMART50)...")
        coupons = [
            ("FRESH20", "Percentage", Decimal("20.00"), today - timedelta(days=3), today + timedelta(days=60), 1000, 48, Decimal("499.00"), True),
            ("SAVE100", "Fixed", Decimal("100.00"), today - timedelta(days=3), today + timedelta(days=45), 500, 26, Decimal("799.00"), True),
            ("DMART50", "Fixed", Decimal("50.00"), today - timedelta(days=3), today + timedelta(days=30), 500, 14, Decimal("399.00"), True),
        ]
        for code, dtype, val, vf, vt, ulim, used, min_ord, act in coupons:
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

        self.stdout.write(self.style.SUCCESS("FreshMart supermarket data seeded successfully!"))
        self.stdout.write(self.style.SUCCESS("All 4 demo accounts are ready:"))
        self.stdout.write("  - Admin: admin / Admin1234!")
        self.stdout.write("  - Store Manager: manager_ravi / Pass1234!")
        self.stdout.write("  - Delivery Agent: agent_kiran / Pass1234!")
        self.stdout.write("  - Customer: customer_sneha / Pass1234!")
