"""Tests for services.build_maps_url and is_within_delivery_radius (pure helpers)."""
import urllib.parse

from apps.orders.services import build_maps_url, is_within_delivery_radius

_BASE = "https://www.google.com/maps/dir/?api=1&destination="


def test_build_maps_url_with_lat_lng():
    """Exact coordinates are preferred and appended as 'lat,lng'."""
    assert build_maps_url(lat="17.4", lng="78.4") == f"{_BASE}17.4,78.4"


def test_build_maps_url_with_address_only():
    """An address (no coords) is URL-encoded onto the destination."""
    address = "123 Main St, City"
    expected = _BASE + urllib.parse.quote(address)
    assert build_maps_url(address=address) == expected


def test_build_maps_url_empty_coords_fall_back_to_address():
    """Blank lat/lng must not win over a provided address."""
    assert build_maps_url(lat="", lng="", address="42 Baker St") == _BASE + urllib.parse.quote(
        "42 Baker St"
    )


def test_build_maps_url_all_empty_returns_blank():
    """No location at all yields an empty string (nothing to link)."""
    assert build_maps_url() == ""
    assert build_maps_url(lat="", lng="", address="") == ""


def test_is_within_delivery_radius_boundary():
    """The 3.0 km limit is inclusive; beyond it is out of range."""
    assert is_within_delivery_radius(2.5, limit_km=3.0) is True
    assert is_within_delivery_radius(3.0, limit_km=3.0) is True
    assert is_within_delivery_radius(3.1, limit_km=3.0) is False
