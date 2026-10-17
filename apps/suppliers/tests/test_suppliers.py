import pytest
from django.urls import reverse
from apps.accounts.models import Role, User
from apps.suppliers.models import Supplier, PurchaseOrder
from apps.menu.models import Category, MenuItem


@pytest.mark.django_db
def test_supplier_list_and_po_creation(client):
    admin = User.objects.create_user(username="supadmin", password="password123", role=Role.ADMIN)
    client.force_login(admin)

    # 1. Access supplier list
    resp = client.get(reverse("suppliers:list"))
    assert resp.status_code == 200

    # 2. Create supplier via POST
    resp = client.post(
        reverse("suppliers:list"),
        {
            "action": "add_supplier",
            "name": "Evergreen Organics",
            "contact": "Anita Rao",
            "phone": "+91 98765 43210",
            "email": "anita@evergreen.in",
            "address": "Sector 4, Market Yard",
            "status": "Active",
        },
    )
    assert resp.status_code == 302
    assert Supplier.objects.filter(name="Evergreen Organics").exists()
    sup = Supplier.objects.get(name="Evergreen Organics")

    # 3. Create a category and item, then create a Purchase Order
    cat = Category.objects.create(name="Fresh Produce")
    item = MenuItem.objects.create(
        category=cat,
        name="Organic Spinach",
        price="30.00",
        cost_price="20.00",
        track_stock=True,
        stock_quantity=10,
    )

    resp = client.post(
        reverse("suppliers:list"),
        {
            "action": "create_po",
            "supplier_id": sup.pk,
            "product_name": "Organic Spinach",
            "quantity": "50",
            "unit_cost": "18.50",
            "status": "Submitted",
        },
    )
    assert resp.status_code == 302
    po = PurchaseOrder.objects.filter(supplier=sup).first()
    assert po is not None
    assert po.quantity == 50
    assert po.status == "Submitted"
    assert po.item == item

    # 4. Receive Purchase Order
    resp = client.post(reverse("suppliers:receive_po", args=[po.pk]))
    assert resp.status_code == 302
    po.refresh_from_db()
    assert po.status == "Complete"
    item.refresh_from_db()
    assert item.stock_quantity == 60  # 10 + 50
