"""Realtime app configuration."""
from django.apps import AppConfig


class RealtimeConfig(AppConfig):
    """Configuration for the real-time notification layer."""

    name = "apps.realtime"
    label = "realtime"
