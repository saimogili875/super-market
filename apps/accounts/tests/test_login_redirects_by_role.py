"""Test that login redirects each role to its designated home page."""
import pytest
from django.test import Client
from django.urls import reverse

from apps.accounts.models import Role, User


@pytest.fixture()
def admin_user(db):
    return User.objects.create_user(
        username="testadmin", password="testpass123", role=Role.ADMIN,
    )


@pytest.fixture()
def agent_user(db):
    return User.objects.create_user(
        username="testagent", password="testpass123", role=Role.AGENT,
    )


@pytest.fixture()
def customer_user(db):
    return User.objects.create_user(
        username="testcustomer", password="testpass123", role=Role.CUSTOMER,
    )


@pytest.mark.django_db
def test_admin_redirects_to_dashboard(admin_user):
    client = Client()
    resp = client.post(
        reverse("accounts:login"),
        {"username": "testadmin", "password": "testpass123"},
    )
    assert resp.status_code == 302
    assert resp.url == reverse("orders_admin:dashboard")


@pytest.mark.django_db
def test_agent_redirects_to_agent_dashboard(agent_user):
    client = Client()
    resp = client.post(
        reverse("accounts:login"),
        {"username": "testagent", "password": "testpass123"},
    )
    assert resp.status_code == 302
    assert resp.url == reverse("orders_agent:dashboard")


@pytest.mark.django_db
def test_customer_redirects_to_delivery_menu(customer_user):
    client = Client()
    resp = client.post(
        reverse("accounts:login"),
        {"username": "testcustomer", "password": "testpass123"},
    )
    assert resp.status_code == 302
    assert resp.url == reverse("orders_customer:menu")
