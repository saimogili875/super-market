import pytest
from decimal import Decimal
from django.urls import reverse
from apps.accounts.models import Role, User
from apps.orders.models import Order
from apps.payments.models import PaymentTransaction


@pytest.mark.django_db
def test_payments_and_refunds(client):
    admin = User.objects.create_user(username="payadmin", password="password123", role=Role.ADMIN)
    cust = User.objects.create_user(username="paycust", password="password123", role=Role.CUSTOMER)
    client.force_login(admin)

    order = Order.objects.create(customer=cust, total_amount=Decimal("450.00"), status="PAID", order_type="DELV")
    tx = PaymentTransaction.objects.create(
        order=order,
        txn_id="TXN-TEST-12345",
        order_ref=f"ORD-{order.pk}",
        customer_name="Rohan Sharma",
        method="UPI",
        amount=Decimal("450.00"),
        status="Paid",
    )

    # 1. View payments ledger
    resp = client.get(reverse("payments:list"))
    assert resp.status_code == 200
    assert "TXN-TEST-12345" in resp.content.decode()

    # 2. Process refund
    resp = client.post(
        reverse("payments:list"),
        {
            "action": "issue_refund",
            "txn_id": tx.txn_id,
            "refund_amount": "200.00",
            "reason": "Damaged goods return",
        },
    )
    assert resp.status_code == 302
    tx.refresh_from_db()
    assert tx.status == "Refunded"
    assert tx.refund_amount == Decimal("200.00")
