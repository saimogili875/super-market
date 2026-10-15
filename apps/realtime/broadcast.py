"""Fire-and-forget broadcast helper for status-change notifications.

This is the ONE function the rest of the codebase calls to push a small
status event onto a channel-layer group. It wraps the async channel
layer with async_to_sync (or loop.create_task if running in an async loop)
so callers don't need to worry about async context.

Design contract:
  - Payloads are TINY: status codes only, never coordinates or PII.
  - Failures are SWALLOWED: a Redis outage logs a warning and returns,
    never raises into the caller's DB write path. The database is the
    source of truth; the socket is best-effort.
  - The socket is a NOTIFICATION BUS, not a command channel.
"""
import asyncio
import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

logger = logging.getLogger(__name__)


def broadcast(group: str, event_type: str, payload: dict) -> None:
    """Send a small status event to a channel group (fire-and-forget).

    Args:
        group:      The channel-layer group name (e.g. "order.42").
        event_type: The Channels event type (e.g. "order.status").
                    Must use dots, which Channels converts to underscores
                    when dispatching to consumer methods.
        payload:    A small dict with the event data. Must contain only
                    JSON-serialisable values. Keep it tiny — status codes
                    only, never maps_url, coordinates, or prices.

    Side effects:
        Sends a message to the channel layer. If the layer is down or
        misconfigured, logs a warning and returns silently — the caller's
        DB transaction is never affected.
    """
    try:
        layer = get_channel_layer()
        if layer is None:
            logger.warning("No channel layer configured; skipping broadcast.")
            return

        message = {"type": event_type, **payload}

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            loop.create_task(layer.group_send(group, message))
        else:
            async_to_sync(layer.group_send)(group, message)
    except Exception:
        # Redis down, misconfigured, etc. — log and move on.
        # The DB write already committed; the socket is best-effort.
        logger.warning(
            "broadcast to group '%s' failed (channel layer error); "
            "continuing without real-time notification.",
            group,
            exc_info=True,
        )
