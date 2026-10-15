"""Tests for the healthz endpoint."""
import json

import pytest
from django.test import Client


@pytest.mark.django_db
def test_healthz_returns_200_and_ok():
    """GET /healthz returns 200 with {"status": "ok"}."""
    client = Client()
    response = client.get("/healthz")
    assert response.status_code == 200
    data = json.loads(response.content)
    assert data == {"status": "ok"}
