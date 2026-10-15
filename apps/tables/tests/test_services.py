"""Unit tests for table services and model constraints."""
import pytest
from django.test import RequestFactory

from apps.tables.models import Table, TableSession
from apps.tables.services import (
    build_table_url,
    close_session,
    get_or_open_session,
    make_qr_png,
)


@pytest.fixture
def table(db):
    """Create a dining table."""
    return Table.objects.create(number=5)


@pytest.mark.django_db
def test_table_qr_token_opaque(table):
    """QR token is random alphanumeric, not table ID or number."""
    assert table.qr_token
    assert str(table.pk) not in table.qr_token or len(table.qr_token) >= 12
    assert str(table.number) != table.qr_token


@pytest.mark.django_db
def test_build_table_url_relative(table):
    """build_table_url without request returns relative path with qr_token."""
    url = build_table_url(None, table)
    assert url == f"/t/{table.qr_token}/"


@pytest.mark.django_db
def test_build_table_url_absolute(table):
    """build_table_url with request returns full URI."""
    rf = RequestFactory()
    req = rf.get("/")
    url = build_table_url(req, table)
    assert url.startswith("http://testserver/t/")
    assert table.qr_token in url


@pytest.mark.django_db
def test_make_qr_png(table):
    """make_qr_png returns valid PNG bytes."""
    png = make_qr_png(table)
    assert isinstance(png, bytes)
    # PNG header magic bytes
    assert png.startswith(b"\x89PNG\r\n\x1a\n")


@pytest.mark.django_db
def test_get_or_open_session(table):
    """get_or_open_session creates new session if none open, reuses if open."""
    s1 = get_or_open_session(table)
    assert s1.closed_at is None
    s2 = get_or_open_session(table)
    assert s1.pk == s2.pk


@pytest.mark.django_db
def test_close_session(table):
    """close_session sets closed_at timestamp."""
    s = get_or_open_session(table)
    closed = close_session(s)
    assert closed.closed_at is not None

    # Opening session now creates a new one
    s3 = get_or_open_session(table)
    assert s3.pk != closed.pk


@pytest.mark.django_db
def test_multiple_open_tabs_per_table_allowed(table):
    """Multiple open sessions for the same table are allowed (one per guest)."""
    s1 = TableSession.objects.create(table=table, guest_name="Alice")
    s2 = TableSession.objects.create(table=table, guest_name="Bob")
    assert s1.pk != s2.pk
    assert table.sessions.filter(closed_at__isnull=True).count() == 2
