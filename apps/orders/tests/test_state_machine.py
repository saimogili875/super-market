"""Tests for the order state machine (pure logic, no database).

These tests import ONLY from apps.orders.state and exercise the
transition table without touching Django or the database.
"""
from apps.orders.state import allowed_targets, can_transition

# ---------------------------------------------------------------------------
# ADMIN transitions
# ---------------------------------------------------------------------------

def test_admin_can_placed_to_approved():
    """ADMIN may approve a newly placed order."""
    assert can_transition("ADMIN", "PLACED", "APPROVED") is True


def test_admin_can_placed_to_cancelled():
    """ADMIN may cancel a newly placed order."""
    assert can_transition("ADMIN", "PLACED", "CANCEL") is True


def test_admin_can_approved_to_kitchen():
    """ADMIN may send an approved order to the kitchen."""
    assert can_transition("ADMIN", "APPROVED", "KITCHEN") is True


def test_admin_can_ready_to_paid():
    """ADMIN may mark a ready dine-in order as paid."""
    assert can_transition("ADMIN", "READY", "PAID") is True


def test_admin_cannot_collect_to_paid():
    """ADMIN may not clear a collected delivery — assigned AGENT owns payment collection."""
    assert can_transition("ADMIN", "COLLECT", "PAID") is False


# ---------------------------------------------------------------------------
# AGENT transitions
# ---------------------------------------------------------------------------

def test_agent_can_dispatch_to_arrived():
    """AGENT may mark a dispatched order as arrived."""
    assert can_transition("AGENT", "DISPATCH", "ARRIVED") is True


def test_agent_can_arrived_to_collect():
    """AGENT may mark an arrived order as amount collected."""
    assert can_transition("AGENT", "ARRIVED", "COLLECT") is True


def test_agent_can_collect_to_paid():
    """AGENT may mark a collected delivery as paid."""
    assert can_transition("AGENT", "COLLECT", "PAID") is True


# ---------------------------------------------------------------------------
# Disallowed transitions
# ---------------------------------------------------------------------------

def test_agent_cannot_placed_to_approved():
    """AGENT has no authority to approve orders."""
    assert can_transition("AGENT", "PLACED", "APPROVED") is False


def test_unknown_role_cannot_transition():
    """An unrecognised role has no transitions at all."""
    assert can_transition("CUSTOMER", "PLACED", "APPROVED") is False


def test_illegal_status_jump():
    """Skipping statuses is not allowed."""
    assert can_transition("ADMIN", "PLACED", "READY") is False


# ---------------------------------------------------------------------------
# allowed_targets helper
# ---------------------------------------------------------------------------

def test_allowed_targets_admin_placed():
    """ADMIN at PLACED can go to APPROVED or CANCEL."""
    targets = allowed_targets("ADMIN", "PLACED")
    assert "APPROVED" in targets
    assert "CANCEL" in targets


def test_allowed_targets_unknown_role():
    """An unknown role has no targets from any status."""
    assert allowed_targets("NOBODY", "PLACED") == ()
