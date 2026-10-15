"""Feature tests for the bespoke Tables admin dashboard CRUD + QR + sessions."""
import pytest
from django.urls import reverse

from apps.accounts.models import Role, User
from apps.tables.models import Table


@pytest.fixture
def admin_user(db):
    return User.objects.create_user(
        username="tables_admin", password="pw", role=Role.ADMIN,
        is_staff=True, is_superuser=True,
    )


@pytest.mark.django_db
def test_table_create_and_deactivate(client, admin_user):
    client.force_login(admin_user)
    resp = client.post(reverse("tables_admin:table_create"), {"number": 42, "is_active": "on"})
    assert resp.status_code == 302
    table = Table.objects.get(number=42)
    assert table.is_active is True
    assert table.qr_token  # auto-generated

    resp = client.post(reverse("tables_admin:table_deactivate", args=[table.pk]))
    assert resp.status_code == 302
    table.refresh_from_db()
    assert table.is_active is False


@pytest.mark.django_db
def test_qr_download_returns_png(client, admin_user):
    """The reused QR endpoint returns a PNG attachment for the table."""
    client.force_login(admin_user)
    table = Table.objects.create(number=43, is_active=True)
    resp = client.get(reverse("admin:tables_table_download_qr", args=[table.pk]))
    assert resp.status_code == 200
    assert resp["Content-Type"] == "image/png"
    assert resp.content[:8] == b"\x89PNG\r\n\x1a\n"  # PNG magic bytes


@pytest.mark.django_db
def test_sessions_page_lists_tabs(client, admin_user):
    client.force_login(admin_user)
    Table.objects.create(number=44, is_active=True)
    resp = client.get(reverse("tables_admin:sessions"))
    assert resp.status_code == 200
