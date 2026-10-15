"""The analytics dashboard is ADMIN-only (403 for AGENT/CUSTOMER, 200 for ADMIN)."""
import pytest
from django.urls import reverse


@pytest.mark.django_db
def test_admin_gets_200(client, admin):
    client.force_login(admin)
    response = client.get(reverse("analytics:dashboard"))
    assert response.status_code == 200


@pytest.mark.django_db
def test_agent_forbidden(client, agent):
    client.force_login(agent)
    response = client.get(reverse("analytics:dashboard"))
    assert response.status_code == 403


@pytest.mark.django_db
def test_customer_forbidden(client, customer):
    client.force_login(customer)
    response = client.get(reverse("analytics:dashboard"))
    assert response.status_code == 403
