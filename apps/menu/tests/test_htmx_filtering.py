"""Tests for server-side HTMX filtering across menu views."""
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.accounts.models import Role, User
from apps.menu.models import Category, MenuItem
from apps.tables.models import Table


@pytest.fixture
def sample_menu(db):
    cat1 = Category.objects.create(name="Pizzas", is_active=True, sort_order=1)
    cat2 = Category.objects.create(name="Burgers", is_active=True, sort_order=2)
    mi1 = MenuItem.objects.create(
        category=cat1, name="Margherita Pizza", price=Decimal("12.00"), is_available=True
    )
    mi2 = MenuItem.objects.create(
        category=cat2, name="Cheese Burger", price=Decimal("8.00"), is_available=True
    )
    return cat1, cat2, mi1, mi2


@pytest.fixture
def admin_client(client, db):
    user = User.objects.create_superuser(username="admin", password="password", role=Role.ADMIN)
    client.force_login(user)
    return client


@pytest.mark.django_db
def test_admin_menu_htmx_filtering(admin_client, sample_menu):
    url = reverse("menu:management")
    
    # Test normal GET
    response = admin_client.get(url)
    assert response.status_code == 200
    assert "Margherita Pizza" in response.content.decode()
    assert "Cheese Burger" in response.content.decode()
    
    # Test HTMX search filtering
    response = admin_client.get(f"{url}?q=Pizza", HTTP_HX_REQUEST="true")
    assert response.status_code == 200
    content = response.content.decode()
    assert "Margherita Pizza" in content
    assert "Cheese Burger" not in content
    assert "menu/admin/partials/results.html" in [t.name for t in response.templates if t.name]


@pytest.mark.django_db
def test_dine_in_menu_htmx_filtering(client, sample_menu):
    Table.objects.create(number=1, qr_token="test-token", is_active=True)
    client.post(
        reverse("tables:start_tab", kwargs={"qr_token": "test-token"}),
        {"guest_name": "Test Guest"},
    )
    url = reverse("tables:menu", kwargs={"qr_token": "test-token"})
    
    # Test normal GET
    response = client.get(url)
    assert response.status_code == 200
    assert "Margherita Pizza" in response.content.decode()
    
    # Test HTMX search filtering
    response = client.get(f"{url}?search=Burger", HTTP_HX_REQUEST="true")
    assert response.status_code == 200
    content = response.content.decode()
    assert "Cheese Burger" in content
    assert "Margherita Pizza" not in content
    assert "tables/partials/menu_results.html" in [t.name for t in response.templates if t.name]


@pytest.mark.django_db
def test_delivery_menu_htmx_filtering(client, sample_menu):
    from apps.customer_auth.models import Customer
    cust = Customer.objects.create(phone="9876543210", email="htmx@example.com")
    session = client.session
    session["customer_id"] = cust.pk
    session.save()

    url = reverse("orders_customer:menu")
    
    # Test normal GET
    response = client.get(url)
    assert response.status_code == 200
    assert "Margherita Pizza" in response.content.decode()
    
    # Test HTMX category filtering
    cat1, cat2, mi1, mi2 = sample_menu
    response = client.get(f"{url}?category=Pizzas", HTTP_HX_REQUEST="true")
    assert response.status_code == 200
    content = response.content.decode()
    assert "Margherita Pizza" in content
    assert "Cheese Burger" not in content
    templates = [t.name for t in response.templates if t.name]
    assert "orders/customer/partials/menu_results.html" in templates
