"""Query-count guard for the admin operational board.

The board renders many order cards; without select_related/prefetch_related it
would issue a query per card (N+1), inflating both latency and peak RAM. This
test pins the query count to a small CONSTANT that must NOT grow with the number
of orders — the regression guard for the board's eager-loading.
"""
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.accounts.models import AgentProfile, Role, User
from apps.menu.models import Category, MenuItem
from apps.orders.services import create_order


@pytest.fixture
def admin_user(db):
    return User.objects.create_user(
        username="q_admin", password="pw", role=Role.ADMIN,
        is_staff=True, is_superuser=True,
    )


def _make_orders(n: int):
    cat = Category.objects.create(name="QCat", is_active=True)
    mi = MenuItem.objects.create(
        category=cat, name="QItem", price=Decimal("5.00"), is_available=True,
    )
    for i in range(n):
        create_order(
            order_type="DELV",
            items=[{"menu_item_id": mi.pk, "quantity": 2}],
            contact_name=f"Cust{i}",
        )


@pytest.mark.django_db
def test_board_query_count_is_bounded(client, admin_user, django_assert_max_num_queries):
    """Board query count stays bounded regardless of order volume (no N+1)."""
    # Make an available agent so the assign control also renders.
    agent = User.objects.create_user(username="q_agent", password="pw", role=Role.AGENT)
    AgentProfile.objects.create(user=agent, is_available=True)
    _make_orders(8)
    client.force_login(admin_user)

    # A generous constant ceiling: auth/session + the handful of eager-loaded
    # order queries. The point is it does NOT scale with the 8 orders above.
    with django_assert_max_num_queries(20):
        resp = client.get(reverse("orders_admin:dashboard"))
    assert resp.status_code == 200
