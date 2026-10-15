"""Accounts business logic — user profiles and agent availability.

This module contains services for account management, including agent availability.
"""
from django.db import transaction

from .models import AgentProfile


def set_agent_availability(agent_user, available: bool) -> AgentProfile:
    """Set the availability status of a delivery agent.

    Flips AgentProfile.is_available inside transaction.atomic.
    The admin dashboard reads this availability flag to route delivery orders
    to active agents.

    Args:
        agent_user: The User instance representing the delivery agent.
        available: Boolean indicating if the agent is available for deliveries.

    Returns:
        The updated AgentProfile instance.
    """
    with transaction.atomic():
        profile, _ = AgentProfile.objects.select_for_update().get_or_create(
            user=agent_user
        )
        profile.is_available = available
        profile.save(update_fields=["is_available"])
        return profile
