import pytest
from django.urls import reverse
from apps.accounts.models import Role, User
from apps.audit.models import AuditLog, log_audit_event


@pytest.mark.django_db
def test_audit_log_and_export(client):
    admin = User.objects.create_user(username="audadmin", password="password123", role=Role.ADMIN)
    client.force_login(admin)

    # 1. Log an event
    log_audit_event(
        user=admin,
        action="PRICE_CHANGE",
        category="Products",
        record_id="PRD-101",
        change_summary="Changed price from 120.00 to 110.00",
    )
    assert AuditLog.objects.filter(record_id="PRD-101").exists()

    # 2. View audit logs page
    resp = client.get(reverse("audit:list"))
    assert resp.status_code == 200
    assert "PRD-101" in resp.content.decode()

    # 3. Export audit logs CSV
    resp = client.get(reverse("audit:list") + "?export=csv")
    assert resp.status_code == 200
    assert resp["Content-Type"] == "text/csv"
    assert "PRD-101" in resp.content.decode()
