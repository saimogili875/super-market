"""WebSocket consumers — thin relays that authenticate, join groups, and forward.

No business logic here. Consumers check permissions on connect, join the
right channel-layer groups, and relay incoming group messages to the
connected client as JSON. All real actions remain authenticated HTTP
requests that write to Postgres via services.py.
"""
import logging

from asgiref.sync import async_to_sync
from channels.generic.websocket import JsonWebsocketConsumer
from django.core import signing

from apps.orders.models import Order
from apps.tables.models import Table

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Shared auth helper (DRY — reused across consumers)
# ---------------------------------------------------------------------------

def _is_authorised_for_order(user, order: Order) -> bool:
    """Check whether the user may watch a specific order's room.

    Allowed if the user:
      - is the customer who placed the order, OR
      - is the agent assigned to deliver it, OR
      - has the ADMIN role.

    This prevents IDOR over sockets — a customer can't spy on orders
    that aren't theirs.
    """
    if not user or not user.is_authenticated:
        return False
    if getattr(user, "role", None) == "ADMIN":
        return True
    if order.customer_id and order.customer_id == user.pk:
        return True
    if order.agent_id and order.agent_id == user.pk:
        return True
    return False


# ---------------------------------------------------------------------------
# OrderConsumer — per-order room
# ---------------------------------------------------------------------------

class OrderConsumer(JsonWebsocketConsumer):
    """WebSocket for a single order: ws/orders/<order_id>/.

    On connect: authenticates via scope["user"] or signed delv_token cookie,
    loads the order, checks ownership/role, then joins group "order.<id>".
    Group messages are relayed to the client as JSON.
    """

    def connect(self):
        """Authenticate, authorise, and join the order group."""
        self.order_id = self.scope["url_route"]["kwargs"]["order_id"]
        self.group_name = f"order.{self.order_id}"

        try:
            order = Order.objects.get(pk=self.order_id)
        except Order.DoesNotExist:
            self.close()
            return

        user = self.scope.get("user")
        is_allowed = False

        if user and user.is_authenticated:
            is_allowed = _is_authorised_for_order(user, order)

        if not is_allowed:
            cookies = self.scope.get("cookies")
            if not cookies:
                cookies = {}
                headers = dict(self.scope.get("headers", []))
                cookie_header = headers.get(b"cookie", b"").decode("utf-8", errors="ignore")
                if cookie_header:
                    from http.cookies import SimpleCookie
                    c = SimpleCookie()
                    c.load(cookie_header)
                    cookies = {k: v.value for k, v in c.items()}

            cookie_key = f"delv_token_{self.order_id}"
            if cookie_key in cookies:
                try:
                    val = signing.get_cookie_signer(salt=cookie_key + "delv_tracking").unsign(
                        cookies[cookie_key]
                    )
                    if val == str(self.order_id):
                        is_allowed = True
                except (signing.BadSignature, Exception):
                    pass

        if not is_allowed:
            self.close()
            return

        async_to_sync(self.channel_layer.group_add)(
            self.group_name, self.channel_name
        )
        self.accept()

    def disconnect(self, close_code):
        """Leave the order group on disconnect."""
        if hasattr(self, "group_name"):
            async_to_sync(self.channel_layer.group_discard)(
                self.group_name, self.channel_name
            )

    def order_status(self, event):
        """Relay a status-change event from the group to the client."""
        self.send_json(event)

    def order_message(self, event):
        """Relay a short chat message from the group to the client.

        Carries only order id, message id, escaped body text, and timestamp
        — never maps_url, coordinates, prices, or other PII.
        """
        self.send_json(event)


# ---------------------------------------------------------------------------
# DashboardConsumer — admin-only live feed
# ---------------------------------------------------------------------------

class DashboardConsumer(JsonWebsocketConsumer):
    """WebSocket for the admin dashboard: ws/dashboard/.

    Only ADMIN users may connect. Joins the "admin.dashboard" group
    to receive new-order and status-change notifications.
    """

    group_name = "admin.dashboard"

    def connect(self):
        """Authenticate and verify ADMIN role."""
        user = self.scope.get("user")

        if not user or not user.is_authenticated:
            self.close()
            return

        if user.role != "ADMIN":
            self.close()
            return

        async_to_sync(self.channel_layer.group_add)(
            self.group_name, self.channel_name
        )
        self.accept()

    def disconnect(self, close_code):
        """Leave the dashboard group on disconnect."""
        async_to_sync(self.channel_layer.group_discard)(
            self.group_name, self.channel_name
        )

    def order_status(self, event):
        """Relay a status-change event to the admin client."""
        self.send_json(event)


# ---------------------------------------------------------------------------
# AgentConsumer — per-agent personal feed
# ---------------------------------------------------------------------------

class AgentConsumer(JsonWebsocketConsumer):
    """WebSocket for an individual agent: ws/agent/.

    The authenticated AGENT joins "agent.<user_id>" to receive
    dispatch and status notifications for their assigned deliveries.
    """

    def connect(self):
        """Authenticate and verify AGENT role."""
        user = self.scope.get("user")

        if not user or not user.is_authenticated:
            self.close()
            return

        if user.role != "AGENT":
            self.close()
            return

        self.group_name = f"agent.{user.pk}"
        async_to_sync(self.channel_layer.group_add)(
            self.group_name, self.channel_name
        )
        self.accept()

    def disconnect(self, close_code):
        """Leave the agent group on disconnect."""
        if hasattr(self, "group_name"):
            async_to_sync(self.channel_layer.group_discard)(
                self.group_name, self.channel_name
            )

    def order_status(self, event):
        """Relay a status-change event to the agent client."""
        self.send_json(event)


# ---------------------------------------------------------------------------
# TableConsumer — per-table dine-in status room (guest, token-scoped)
# ---------------------------------------------------------------------------

class TableConsumer(JsonWebsocketConsumer):
    """WebSocket for a dine-in table's status page: ws/tables/<qr_token>/.

    Guests are not logged in, so authorisation is by the opaque qr_token
    they scanned (never the table id/number). If the token matches an
    active table, the client joins "table.<qr_token>" to receive live
    status pushes ("Food is Ready", bill cleared, etc.). This mirrors the
    HTTP-side IDOR defence: you can only watch the table you scanned.
    """

    def connect(self):
        """Validate the scanned token, then join the table group."""
        self.qr_token = self.scope["url_route"]["kwargs"]["qr_token"]

        if not Table.objects.filter(qr_token=self.qr_token, is_active=True).exists():
            self.close()
            return

        self.group_name = f"table.{self.qr_token}"
        async_to_sync(self.channel_layer.group_add)(
            self.group_name, self.channel_name
        )
        self.accept()

    def disconnect(self, close_code):
        """Leave the table group on disconnect."""
        if hasattr(self, "group_name"):
            async_to_sync(self.channel_layer.group_discard)(
                self.group_name, self.channel_name
            )

    def order_status(self, event):
        """Relay a status-change event to the dine-in client."""
        self.send_json(event)

    def order_message(self, event):
        """Relay a short chat message to the dine-in client (escaped text only)."""
        self.send_json(event)
