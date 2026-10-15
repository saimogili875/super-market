"""Order state machine — the single finetunable table of allowed transitions.

This module is the ONE place a human edits to change the order workflow.
It is pure logic: no database imports, no Django models. This makes it
trivially unit-testable and keeps the workflow rules in one obvious spot.

To add a new status or change who can do what:
  1. Update TRANSITIONS below.
  2. Run the state-machine tests.
  3. Done — no other file needs changing.
"""


# ---------------------------------------------------------------------------
# TRANSITIONS: role -> from_status -> tuple of allowed to_statuses
#
# Read as: "A user with role X, when the order is in status Y,
#           may move it to any status in the tuple Z."
# ---------------------------------------------------------------------------
TRANSITIONS: dict[str, dict[str, tuple[str, ...]]] = {
    "ADMIN": {
        "PLACED": ("APPROVED", "DISPATCH", "PAID", "CANCEL"),
        "APPROVED": ("KITCHEN", "DISPATCH", "PAID", "CANCEL"),
        "KITCHEN": ("READY", "DISPATCH", "PAID", "CANCEL"),
        # PAID = dine-in cash cleared at table
        "READY": ("DISPATCH", "PAID", "CANCEL"),
        "DISPATCH": ("CANCEL",),
        "ARRIVED": ("CANCEL",),
        "COLLECT": ("CANCEL",),
    },
    "AGENT": {
        "PLACED": ("ARRIVED",),
        "APPROVED": ("ARRIVED",),
        "KITCHEN": ("ARRIVED",),
        "READY": ("ARRIVED",),
        "DISPATCH": ("ARRIVED",),
        "ARRIVED": ("COLLECT",),
        "COLLECT": ("PAID",),
    },
}


def can_transition(role: str, frm: str, to: str) -> bool:
    """Check whether a role is allowed to move an order from *frm* to *to*.

    Args:
        role: The actor's business role (e.g. "ADMIN", "AGENT").
        frm:  The order's current status value.
        to:   The desired target status value.

    Returns:
        True if the transition is explicitly allowed, False otherwise.

    This function is the single gatekeeper: services.transition() calls it
    before mutating any state. Because it uses TRANSITIONS (a plain dict),
    tuning the workflow means editing the dict, not rewriting logic.
    """
    role_map = TRANSITIONS.get(role, {})
    allowed = role_map.get(frm, ())
    return to in allowed


def allowed_targets(role: str, frm: str) -> tuple[str, ...]:
    """Return the statuses a role may transition an order to from *frm*.

    Args:
        role: The actor's business role.
        frm:  The order's current status value.

    Returns:
        A tuple of allowed target status strings (possibly empty).

    Useful for building UI buttons: only show the actions the actor can take.
    """
    return TRANSITIONS.get(role, {}).get(frm, ())
