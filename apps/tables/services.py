"""Services for table QR code generation and session lifecycle.

Business rules:
  - QR codes encode the opaque qr_token, never the table number or database ID.
  - Multiple active TableSessions can exist per table (one per guest tab).
  - Guests are tied to their session via a signed cookie scoped to the table's qr_token.
"""
import io
from decimal import Decimal

import qrcode
from django.core import signing
from django.utils import timezone

from .models import Table, TableSession


def build_table_url(request, table: Table) -> str:
    """Build the absolute scan URL for a dining table.

    Args:
        request: The HTTP request object (used to determine host/scheme).
        table:   The Table instance.

    Returns:
        Absolute URL string (or relative path if request is None).
    """
    path = f"/t/{table.qr_token}/"
    if request is not None and hasattr(request, "build_absolute_uri"):
        return request.build_absolute_uri(path)
    return path


def make_qr_png(table: Table, request=None) -> bytes:
    """Generate PNG image bytes for a table's QR scan URL.

    Args:
        table:   The Table instance to encode.
        request: Optional HTTP request for absolute URL generation.

    Returns:
        Raw PNG bytes ready for HTTP response or file storage.
    """
    url = build_table_url(request, table)
    img = qrcode.make(url)
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()


def get_or_open_session(table: Table) -> TableSession:
    """Get the currently open session for a table, or open a new one.

    Args:
        table: The Table instance.

    Returns:
        An active TableSession where closed_at is None.
    """
    session = table.sessions.filter(closed_at__isnull=True).first()
    if session is None:
        session = TableSession.objects.create(table=table)
    return session


def start_tab(table: Table, guest_name: str = "") -> TableSession:
    """Create a new open TableSession for that table with guest_name.

    Args:
        table: The Table instance.
        guest_name: Optional name entered by the guest.

    Returns:
        A newly created active TableSession.
    """
    return TableSession.objects.create(table=table, guest_name=guest_name)


def resolve_session(request, table: Table) -> TableSession | None:
    """Resolve a guest's session (open or closed) for a table from their signed cookie.

    Args:
        request: The HTTP request containing cookies.
        table: The Table instance.

    Returns:
        The guest's TableSession if valid, else None.
    """
    if request is None:
        return None
    cookie_name = f"tab_{table.qr_token}"
    try:
        val = request.get_signed_cookie(cookie_name, salt=f"table_{table.qr_token}")
    except (KeyError, signing.BadSignature):
        return None

    if not isinstance(val, str) or not val.startswith("tab_"):
        return None

    try:
        session_id = int(val[4:])
    except ValueError:
        return None

    return table.sessions.filter(pk=session_id).first()


def resolve_active_session(request, table: Table) -> TableSession | None:
    """Resolve a guest's active open session for a table from their signed cookie.

    Args:
        request: The HTTP request containing cookies.
        table: The Table instance.

    Returns:
        The guest's open TableSession if valid and active, else None.
    """
    session = resolve_session(request, table)
    if session and session.closed_at is None:
        return session
    return None


def set_session_cookie(response, table: Table, session: TableSession):
    """Attach the signed session cookie for a guest tab to an HTTP response.

    Args:
        response: The HTTP response object.
        table: The Table instance.
        session: The TableSession instance.
    """
    cookie_name = f"tab_{table.qr_token}"
    val = f"tab_{session.pk}"
    response.set_signed_cookie(cookie_name, val, salt=f"table_{table.qr_token}")


def get_session_total(session: TableSession) -> Decimal:
    """Calculate the session total excluding cancelled orders.

    Args:
        session: The TableSession instance.

    Returns:
        Sum of total_amount for all non-cancelled orders in the session.
    """
    return session.total


def close_session(session: TableSession) -> TableSession:
    """Close an active table session when the bill is settled.

    Args:
        session: The TableSession to close.

    Returns:
        The updated TableSession instance.
    """
    if session.closed_at is None:
        session.closed_at = timezone.now()
        session.save(update_fields=["closed_at", "updated_at"])
    return session
