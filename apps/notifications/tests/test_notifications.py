import pytest
from django.urls import reverse
from apps.accounts.models import Role, User
from apps.notifications.models import AdminNotification


@pytest.mark.django_db
def test_notifications_actions(client):
    admin = User.objects.create_user(username="notifadmin", password="password123", role=Role.ADMIN)
    client.force_login(admin)

    notif = AdminNotification.objects.create(
        title="Low stock: Milk",
        message="Only 2 units remaining",
        notification_type="Low stock",
        severity="wn",
    )

    # 1. View notifications page
    resp = client.get(reverse("notifications:list"))
    assert resp.status_code == 200
    assert "Low stock: Milk" in resp.content.decode()

    # 2. Mark all as read
    resp = client.post(reverse("notifications:list"), {"action": "mark_all_read"})
    assert resp.status_code == 302
    notif.refresh_from_db()
    assert notif.is_read is True

    # 3. Resolve notification
    resp = client.post(reverse("notifications:list"), {"action": "mark_resolved", "notif_id": notif.pk})
    assert resp.status_code == 302
    notif.refresh_from_db()
    assert notif.is_resolved is True
