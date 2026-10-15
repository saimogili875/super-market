"""Tests for the broadcast helper."""
from unittest.mock import patch

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from apps.realtime.broadcast import broadcast


def test_broadcast_sends_envelope():
    """broadcast() sends a correctly formatted envelope to the group."""
    group_name = "test.group"
    payload = {"order_id": 42, "status": "PLACED", "at": "2026-07-03T00:00:00Z"}

    broadcast(group_name, "order.status", payload)

    layer = get_channel_layer()
    # Receive message from the in-memory channel layer group
    channel_name = async_to_sync(layer.new_channel)()
    async_to_sync(layer.group_add)(group_name, channel_name)

    # Broadcast again now that channel is subscribed
    broadcast(group_name, "order.status", payload)

    message = async_to_sync(layer.receive)(channel_name)
    assert message == {
        "type": "order.status",
        "order_id": 42,
        "status": "PLACED",
        "at": "2026-07-03T00:00:00Z",
    }


def test_broadcast_swallows_exception():
    """broadcast() logs a warning and does not raise on channel layer failure."""
    with patch("apps.realtime.broadcast.get_channel_layer", side_effect=Exception("Redis dead")):
        # Must not raise
        broadcast("test.group", "order.status", {"order_id": 1})
