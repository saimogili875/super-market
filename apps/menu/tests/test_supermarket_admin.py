import io
import pytest
from decimal import Decimal
from django.urls import reverse
from apps.accounts.models import Role, User
from apps.menu.models import Category, MenuItem, StockMovement


@pytest.mark.django_db
def test_supermarket_dashboard_and_inventory(client):
    admin = User.objects.create_user(username="supdashadmin", password="password123", role=Role.ADMIN)
    client.force_login(admin)

    cat = Category.objects.create(name="Dairy & Eggs")
    item = MenuItem.objects.create(
        category=cat,
        name="Fresh Whole Milk 1L",
        sku="MLK-001",
        price=Decimal("60.00"),
        cost_price=Decimal("45.00"),
        track_stock=True,
        stock_quantity=3,
        low_stock_threshold=5,
    )

    # 1. Executive dashboard (item appears in attention table because it is low stock)
    resp = client.get(reverse("menu:dashboard"))
    assert resp.status_code == 200
    assert "Fresh Whole Milk 1L" in resp.content.decode()

    # 2. Inventory & Stock Adjustments
    resp = client.get(reverse("menu:inventory"))
    assert resp.status_code == 200

    # Restock by 20
    resp = client.post(
        reverse("menu:inventory"),
        {
            "action": "stock_adjust",
            "item_id": item.pk,
            "movement_type": "RESTOCK",
            "quantity": "20",
            "notes": "Morning supplier delivery",
        },
    )
    assert resp.status_code == 302
    item.refresh_from_db()
    assert item.stock_quantity == 23
    assert StockMovement.objects.filter(item=item, movement_type="RESTOCK").exists()

    # 3. Import / Export
    resp = client.get(reverse("menu:import_export"))
    assert resp.status_code == 200

    # CSV Export
    resp = client.get(reverse("menu:import_export") + "?dataset=products")
    assert resp.status_code == 200
    assert resp["Content-Type"] == "text/csv"
    assert "Fresh Whole Milk 1L" in resp.content.decode()

    # CSV Import
    csv_data = (
        "name,price,sku\n"
        "Almond Milk 1L,180.00,ALM-001\n"
    )
    csv_file = io.BytesIO(csv_data.encode("utf-8"))
    csv_file.name = "products.csv"

    # Step 1: Preview (stores rows in session)
    resp = client.post(
        reverse("menu:import_export"),
        {"action": "upload_preview", "file": csv_file},
    )
    assert resp.status_code == 200
    assert "Almond Milk 1L" in resp.content.decode()

    # Step 2: Commit
    resp = client.post(reverse("menu:import_export"), {"action": "commit_import"})
    assert resp.status_code == 302
    assert MenuItem.objects.filter(name="Almond Milk 1L").exists()
