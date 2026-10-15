"""Shared test fixtures for all project apps."""
import pytest


@pytest.fixture(autouse=True)
def use_in_memory_channel_layer(settings):
    """Override CHANNEL_LAYERS to use in-memory backend during testing.

    Ensures tests run quickly and reliably without needing a live Redis server.
    """
    settings.CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels.layers.InMemoryChannelLayer",
        }
    }
