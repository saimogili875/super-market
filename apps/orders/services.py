"""Order business logic — create, transition, and modify orders.

This is the FAT services layer. All order behaviour lives here:
  - create_order()     — build an order from a cart of menu items
  - transition()       — move an order through the state machine
  - add_item_to_order()— add a line item (dine-in iterative ordering)

Models hold data + validation. State machine rules live in state.py.
Views will be thin wrappers that call these functions. Nothing here
touches HTTP or templates — pure domain logic.
"""
import urllib.parse
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import F

from apps.menu.models import MenuItem
from apps.menu.services import invalidate_menu_cache

from . import state
from .models import Message, Order, OrderEvent, OrderItem, OrderStatus

# Statuses where the order can still be edited (items added/removed).
# Once the kitchen starts cooking, the cart is frozen.
_EDITABLE_STATUSES = (OrderStatus.PLACED, OrderStatus.APPROVED)


def create_order(
    *,
    order_type: str,
    items: list[dict],
    customer=None,
    delivery_customer=None,
    table=None,
    session=None,
    contact_name: str = "",
    contact_phone: str = "",
    maps_url: str = "",
    instructions: str = "",
) -> Order:
    """Create a new order, snapshotting prices from the menu.

    Args:
        order_type:    "DINE" or "DELV".
        items:         List of dicts: [{"menu_item_id": int, "quantity": int}].
                       Client-sent prices are IGNORED — we always read
                       effective_price from the database (anti-tamper).
        customer:      The ordering user (optional).
        table:         Required for dine-in; must be None for delivery.
        session:       The active TableSession (optional).
        contact_name:  Delivery contact name (optional).
        contact_phone: Delivery contact phone (optional).
        maps_url:      Google Maps link (built at checkout, Sprint 6).
        instructions:  Special instructions for the kitchen/driver.

    Returns:
        The newly created Order instance.

    Raises:
        ValidationError: If the cart is empty, or any item is unavailable.

    Pricing and totals are computed here from MenuItem.effective_price,
    NEVER from client-supplied prices. This is the anti-tamper guarantee.
    """
    if not items:
        raise ValidationError("Cart cannot be empty.")

    if order_type == "DINE" and table is None:
        raise ValidationError("Dine-in orders require a table.")
    if order_type == "DELV" and table is not None:
        raise ValidationError("Delivery orders cannot have a table.")

    item_ids = [entry["menu_item_id"] for entry in items]

    with transaction.atomic():
        # select_for_update prevents two orders racing on the same item on PostgreSQL;
        # on SQLite dev it is a harmless no-op.
        menu_items_by_id = {
            mi.pk: mi
            for mi in MenuItem.objects.select_for_update().filter(pk__in=item_ids)
        }

        requested_qtys = {}
        for entry in items:
            mid = entry["menu_item_id"]
            requested_qtys[mid] = requested_qtys.get(mid, 0) + entry["quantity"]

        # Validate every requested item exists and is available / in stock
        for entry in items:
            mi = menu_items_by_id.get(entry["menu_item_id"])
            if mi is None:
                raise ValidationError(
                    f"Menu item {entry['menu_item_id']} does not exist."
                )
            if not mi.is_available:
                raise ValidationError(
                    f"'{mi.name}' is currently unavailable."
                )
            requested_qty = requested_qtys[entry["menu_item_id"]]
            if mi.track_stock and mi.stock_quantity < requested_qty:
                if mi.stock_quantity:
                    raise ValidationError(f"Only {mi.stock_quantity} left of '{mi.name}'.")
                else:
                    raise ValidationError(f"'{mi.name}' is sold out.")

        # After validation passes, decrement stock for tracked items
        for mid, total_qty in requested_qtys.items():
            mi = menu_items_by_id[mid]
            if mi.track_stock:
                mi.stock_quantity = F("stock_quantity") - total_qty
                mi.save(update_fields=["stock_quantity"])
                invalidate_menu_cache()

        order = Order.objects.create(
            order_type=order_type,
            customer=customer,
            delivery_customer=delivery_customer,
            table=table,
            session=session,
            contact_name=contact_name,
            contact_phone=contact_phone,
            maps_url=maps_url,
            instructions=instructions,
        )

        # Snapshot each item's name and price at order time
        total = Decimal("0")
        order_items = []
        for entry in items:
            mi = menu_items_by_id[entry["menu_item_id"]]
            quantity = entry["quantity"]
            snapped_price = mi.effective_price

            order_items.append(
                OrderItem(
                    order=order,
                    menu_item=mi,
                    name_snap=mi.name,
                    unit_price=snapped_price,
                    quantity=quantity,
                )
            )
            total += snapped_price * quantity

        OrderItem.objects.bulk_create(order_items)

        order.total_amount = total
        order.save(update_fields=["total_amount"])

        # Record the initial event: "" -> PLACED
        OrderEvent.objects.create(
            order=order,
            from_status="",
            to_status=OrderStatus.PLACED,
            actor=customer,
        )

    # Lazy import to avoid circular dependencies between apps
    from apps.realtime.broadcast import broadcast

    payload = {
        "order_id": order.pk,
        "status": order.status,
        "at": order.created_at.isoformat(),
    }
    broadcast("admin.dashboard", "order.status", payload)
    if order.table_id:
        broadcast(f"table.{order.table.qr_token}", "order.status", payload)

    return order


def add_item_to_order(order: Order, menu_item_id: int, quantity: int = 1) -> OrderItem:
    """Add a line item to an editable order (e.g. dine-in iterative ordering)."""
    if order.status not in _EDITABLE_STATUSES:
        raise PermissionDenied(
            f"Cannot add items to an order in status '{order.status}'."
        )
    if quantity < 1:
        raise ValidationError("Quantity must be at least 1.")

    with transaction.atomic():
        # select_for_update prevents two orders racing on the same item on PostgreSQL;
        # on SQLite dev it is a harmless no-op.
        mi = MenuItem.objects.select_for_update().filter(pk=menu_item_id).first()
        if mi is None:
            raise ValidationError(f"Menu item {menu_item_id} does not exist.")
        if not mi.is_available:
            raise ValidationError(f"'{mi.name}' is currently unavailable.")
        if mi.track_stock and mi.stock_quantity < quantity:
            if mi.stock_quantity:
                raise ValidationError(f"Only {mi.stock_quantity} left of '{mi.name}'.")
            else:
                raise ValidationError(f"'{mi.name}' is sold out.")

        if mi.track_stock:
            mi.stock_quantity = F("stock_quantity") - quantity
            mi.save(update_fields=["stock_quantity"])
            invalidate_menu_cache()

        order_item = order.items.filter(menu_item=mi).first()
        if order_item:
            order_item.quantity = F("quantity") + quantity
            order_item.save(update_fields=["quantity"])
            order_item.refresh_from_db()
        else:
            order_item = OrderItem.objects.create(
                order=order,
                menu_item=mi,
                name_snap=mi.name,
                unit_price=mi.effective_price,
                quantity=quantity,
            )

        total = sum(item.unit_price * item.quantity for item in order.items.all())
        order.total_amount = total
        order.save(update_fields=["total_amount"])

    from apps.realtime.broadcast import broadcast

    payload = {
        "order_id": order.pk,
        "status": order.status,
        "at": order.updated_at.isoformat(),
    }
    broadcast(f"order.{order.pk}", "order.status", payload)
    broadcast("admin.dashboard", "order.status", payload)
    if order.table_id:
        broadcast(f"table.{order.table.qr_token}", "order.status", payload)

    return order_item


def transition(order: Order, to_status: str, actor) -> Order:
    """Move an order to a new status, enforcing the state machine.

    Args:
        order:     The Order to transition.
        to_status: The target OrderStatus value.
        actor:     The User performing the action.

    Returns:
        The updated Order instance.

    Raises:
        PermissionDenied: If the actor's role is not allowed to make
                          this transition.
        ValidationError:  If moving to DISPATCH without an assigned agent.

    The state machine in state.py is the single source of truth for
    which transitions are legal. This function consults it, updates the
    order, and appends an audit event — all atomically.
    """
    frm = order.status

    if not state.can_transition(actor.role, frm, to_status):
        raise PermissionDenied(
            f"Role '{actor.role}' cannot move order "
            f"from '{frm}' to '{to_status}'."
        )

    if actor.role == "AGENT" and order.agent_id != actor.pk:
        raise PermissionDenied("Agent is not assigned to this order.")

    DELIVERY_ONLY_STATUSES = (OrderStatus.DISPATCHED, OrderStatus.ARRIVED, OrderStatus.COLLECTED)
    if order.order_type == "DINE" and to_status in DELIVERY_ONLY_STATUSES:
        raise ValidationError(
            f"Dine-in order #{order.pk} cannot transition to delivery status '{OrderStatus(to_status).label}'."
        )

    if to_status == OrderStatus.DISPATCHED and order.agent_id is None:
        raise ValidationError("Assign a delivery agent before dispatching.")

    with transaction.atomic():
        order.status = to_status
        from django.utils.timezone import now
        current_time = now()
        update_fields = ["status"]

        if actor.role == "AGENT":
            if to_status == OrderStatus.ARRIVED and not order.delivery_arrived_at:
                order.delivery_arrived_at = current_time
                update_fields.append("delivery_arrived_at")
            elif to_status == OrderStatus.COLLECTED and not order.delivery_picked_at:
                order.delivery_picked_at = current_time
                update_fields.append("delivery_picked_at")
            elif to_status == OrderStatus.PAID and not order.delivery_completed_at:
                order.delivery_completed_at = current_time
                update_fields.append("delivery_completed_at")

        order.save(update_fields=update_fields)

        if to_status == OrderStatus.CANCELLED and frm != OrderStatus.CANCELLED:
            for item in order.items.select_related("menu_item").all():
                if item.menu_item.track_stock:
                    item.menu_item.stock_quantity = F("stock_quantity") + item.quantity
                    item.menu_item.save(update_fields=["stock_quantity"])
                    invalidate_menu_cache()

            if order.agent_id:
                from apps.notifications.models import AdminNotification
                AdminNotification.objects.create(
                    notification_type="Delivery",
                    severity="er",
                    title=f"Order #{order.pk} cancelled",
                    message=f"Order #{order.pk} was cancelled by administration.",
                    reference_id=f"ORD-{order.pk}",
                    recipient=order.agent,
                )

        OrderEvent.objects.create(
            order=order,
            from_status=frm,
            to_status=to_status,
            actor=actor,
        )

    # Broadcast status change fire-and-forget after DB transaction commits
    from apps.realtime.broadcast import broadcast

    payload = {
        "order_id": order.pk,
        "status": order.status,
        "at": order.updated_at.isoformat(),
    }
    broadcast(f"order.{order.pk}", "order.status", payload)
    broadcast("admin.dashboard", "order.status", payload)
    if order.agent_id:
        broadcast(f"agent.{order.agent_id}", "order.status", payload)
    if order.table_id:
        broadcast(f"table.{order.table.qr_token}", "order.status", payload)

    return order


def assign_agent(order: Order, agent_user, actor) -> Order:
    """Assign a delivery order to an available agent (admin/manager action).

    Assigning here IS the handoff: this is how the admin forwards the
    delivery to a courier. Assigning an agent sets order.agent AND
    transitions the order to DISPATCH atomically, so the agent immediately
    sees action buttons on their dashboard.
    """
    if actor.role not in ("ADMIN", "MANAGER") and not getattr(actor, "is_superuser", False):
        raise PermissionDenied("Only an admin may assign delivery agents.")

    if order.order_type != "DELV":
        raise PermissionDenied("Only delivery orders can be assigned a delivery agent.")

    if agent_user.role != "AGENT":
        raise PermissionDenied("Orders can only be assigned to delivery agents.")

    # Reverse OneToOne accessor; returns None if the agent has no profile.
    profile = getattr(agent_user, "agent", None)
    if profile is None or not profile.is_available:
        raise PermissionDenied("That agent is not currently available.")

    with transaction.atomic():
        order.agent = agent_user
        order.save(update_fields=["agent"])

        if order.status != OrderStatus.DISPATCHED:
            transition(order, OrderStatus.DISPATCHED, actor)

    # Create in-app operational alert for assigned agent
    from apps.notifications.models import AdminNotification
    AdminNotification.objects.create(
        notification_type="Delivery",
        severity="ok",
        title=f"New delivery assignment #{order.pk}",
        message=f"Store: SuperMarket Store 01 | Customer: {order.contact_name or 'Customer'} | Drop: {order.delivery_area}",
        reference_id=f"ORD-{order.pk}",
        recipient=agent_user,
    )

    # Notify the agent's room and the order room (fire-and-forget, after commit).
    from apps.realtime.broadcast import broadcast

    payload = {
        "order_id": order.pk,
        "status": order.status,
        "at": order.updated_at.isoformat(),
    }
    broadcast(f"agent.{agent_user.pk}", "order.status", payload)
    broadcast(f"order.{order.pk}", "order.status", payload)

    return order


def accept_delivery(order: Order, actor) -> Order:
    """Agent accepts an assigned delivery order."""
    if actor.role != "AGENT" or order.agent_id != actor.pk:
        raise PermissionDenied("Only the assigned agent may accept this delivery.")

    if order.status != OrderStatus.DISPATCHED:
        raise ValidationError(f"Order #{order.pk} is in status '{order.status}', cannot be accepted.")

    from django.utils.timezone import now
    with transaction.atomic():
        if not order.delivery_accepted_at:
            order.delivery_accepted_at = now()
            order.save(update_fields=["delivery_accepted_at"])

            OrderEvent.objects.create(
                order=order,
                from_status=order.status,
                to_status=order.status,
                actor=actor,
            )

    from apps.realtime.broadcast import broadcast
    payload = {
        "order_id": order.pk,
        "status": order.status,
        "accepted": True,
        "at": order.updated_at.isoformat(),
    }
    broadcast(f"agent.{actor.pk}", "order.status", payload)
    broadcast(f"order.{order.pk}", "order.status", payload)
    broadcast("admin.dashboard", "order.status", payload)
    return order


def reject_delivery(order: Order, reason: str, actor) -> Order:
    """Agent rejects an assigned delivery order.

    Unassigns agent, returns order to READY pool for reassignment,
    logs OrderEvent, and notifies admin/manager.
    """
    if actor.role != "AGENT" or order.agent_id != actor.pk:
        raise PermissionDenied("Only the assigned agent may reject this delivery.")

    if order.status in (OrderStatus.PAID, OrderStatus.CANCELLED):
        raise ValidationError("Cannot reject a completed or cancelled order.")

    reason = reason.strip() or "Unavailable"

    with transaction.atomic():
        order.delivery_issue_reason = f"Rejected: {reason}"
        order.agent = None
        order.delivery_accepted_at = None
        if order.status == OrderStatus.DISPATCHED:
            order.status = OrderStatus.READY
        order.save(update_fields=["agent", "status", "delivery_issue_reason", "delivery_accepted_at"])

        OrderEvent.objects.create(
            order=order,
            from_status=OrderStatus.DISPATCHED,
            to_status=OrderStatus.READY,
            actor=actor,
        )

    from apps.notifications.models import AdminNotification
    AdminNotification.objects.create(
        notification_type="Delivery",
        severity="wn",
        title=f"Delivery Rejected: Order #{order.pk}",
        message=f"Agent {actor.username} rejected order #{order.pk}. Reason: {reason}. Order returned to pool.",
        reference_id=f"ORD-{order.pk}",
    )

    from apps.realtime.broadcast import broadcast
    payload = {
        "order_id": order.pk,
        "status": order.status,
        "at": order.updated_at.isoformat(),
        "unassigned": True,
    }
    broadcast("admin.dashboard", "order.status", payload)
    broadcast(f"agent.{actor.pk}", "order.status", payload)
    broadcast(f"order.{order.pk}", "order.status", payload)

    return order


def report_delivery_issue(order: Order, reason: str, notes: str, actor) -> Order:
    """Agent reports an operational issue on an active delivery."""
    if actor.role != "AGENT" or order.agent_id != actor.pk:
        raise PermissionDenied("Only the assigned agent may report an issue on this delivery.")

    reason = reason.strip() or "Operational issue"
    notes = notes.strip()

    with transaction.atomic():
        order.delivery_issue_reason = reason
        order.delivery_issue_notes = notes
        order.save(update_fields=["delivery_issue_reason", "delivery_issue_notes"])

        OrderEvent.objects.create(
            order=order,
            from_status=order.status,
            to_status=order.status,
            actor=actor,
        )
        post_message(order, actor, f"Issue reported: {reason}. {notes}".strip())

    from apps.notifications.models import AdminNotification
    AdminNotification.objects.create(
        notification_type="Delivery",
        severity="er",
        title=f"Delivery Issue: Order #{order.pk}",
        message=f"Agent {actor.username} reported issue on Order #{order.pk}: {reason}. Notes: {notes}",
        reference_id=f"ORD-{order.pk}",
    )

    from apps.realtime.broadcast import broadcast
    broadcast(f"order.{order.pk}", "order.status", {"order_id": order.pk, "issue": reason})
    broadcast("admin.dashboard", "order.status", {"order_id": order.pk, "issue": reason})

    return order


def complete_delivery(
    order: Order,
    pod_type: str = "otp",
    pod_detail: str = "",
    notes: str = "",
    pod_image=None,
    actor=None,
) -> Order:
    """Complete a delivery order with POD and transition to PAID."""
    if actor.role != "AGENT" or order.agent_id != actor.pk:
        raise PermissionDenied("Only the assigned agent may complete this delivery.")

    if order.status != OrderStatus.COLLECTED:
        raise ValidationError(f"Order must be out for delivery (collected) before completion. Current status: '{order.status}'.")

    from django.utils.timezone import now
    with transaction.atomic():
        order.delivery_completed_at = now()
        order.delivery_pod_type = pod_type or "handover"
        order.delivery_pod_detail = pod_detail
        order.delivery_notes = notes
        update_fields = [
            "delivery_completed_at",
            "delivery_pod_type",
            "delivery_pod_detail",
            "delivery_notes",
        ]
        if pod_image:
            order.delivery_pod_image = pod_image
            update_fields.append("delivery_pod_image")

        order.save(update_fields=update_fields)

        # Transition to PAID (Delivered)
        transition(order, OrderStatus.PAID, actor)

    from apps.notifications.models import AdminNotification
    AdminNotification.objects.create(
        notification_type="Delivery",
        severity="ok",
        title=f"Delivery Completed: Order #{order.pk}",
        message=f"Agent {actor.username} completed delivery of Order #{order.pk}. POD: {pod_type}.",
        reference_id=f"ORD-{order.pk}",
    )

    return order


def post_message(order: Order, sender, body: str) -> Message:
    """Persist a short chat note on an order and broadcast it live.

    Used by the customer tracking page and the assigned agent to swap quick
    notes ("I'm at the gate"). The body is trimmed to the model's cap (300
    chars) here so an over-long POST can never blow up the insert, and it is
    always rendered auto-escaped in templates (XSS defense).

    The broadcast carries ONLY the short text and identifiers — never
    maps_url, coordinates, prices, or other PII. The socket is a best-effort
    notification bus; the database row is the source of truth.

    Args:
        order:  The Order the message belongs to.
        sender: The posting User, or None for a guest customer.
        body:   The raw message text (trimmed + capped before saving).

    Returns:
        The newly created Message instance.
    """
    max_len = Message._meta.get_field("body").max_length
    body = body.strip()[:max_len]

    with transaction.atomic():
        message = Message.objects.create(order=order, sender=sender, body=body)

    from apps.realtime.broadcast import broadcast

    broadcast(
        f"order.{order.pk}",
        "order.message",
        {
            "order_id": order.pk,
            "message_id": message.pk,
            "body": message.body,
            "at": message.at.isoformat(),
        },
    )
    return message


# ---------------------------------------------------------------------------
# Delivery location helpers (no live geo — we only build a link)
# ---------------------------------------------------------------------------

def build_maps_url(*, lat=None, lng=None, address: str = "") -> str:
    """Compose a canonical Google Maps directions URL for a delivery.

    We only BUILD and store this string; the server NEVER fetches it, so
    there is no SSRF surface. It is saved once on Order.maps_url at checkout
    and rendered as a link the agent taps to open their Maps app.

    Prefers exact coordinates; falls back to a URL-encoded address; returns
    "" when no location was provided.
    """
    base = "https://www.google.com/maps/dir/?api=1&destination="
    if lat and lng:
        return f"{base}{lat},{lng}"
    if address:
        return base + urllib.parse.quote(address)
    return ""


def is_within_delivery_radius(distance_km: float, limit_km: float = 3.0) -> bool:
    """Return True if a delivery distance is within the service radius.

    Pure check — the caller supplies the distance (computed elsewhere). We do
    NOT do live geolocation; this just enforces the <3 km business rule.
    """
    return distance_km <= limit_km


def toggle_item_picked(order_item_id: int, actor) -> OrderItem:
    """Toggle is_picked for an order item in the store pick & pack checklist."""
    item = OrderItem.objects.select_related("order", "menu_item").get(pk=order_item_id)
    item.is_picked = not item.is_picked
    item.save(update_fields=["is_picked"])
    return item


def all_items_picked(order: Order) -> bool:
    """Return True if all line items in an order have been picked and verified."""
    return order.items.exists() and not order.items.filter(is_picked=False).exists()

