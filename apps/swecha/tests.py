"""Unit tests for Swecha AI Shopping Assistant."""
from decimal import Decimal
from unittest.mock import MagicMock, patch
import pytest
from django.urls import reverse

from apps.menu.models import Category, MenuItem
from apps.swecha.services import call_swecha_ai, search_catalog_for_query, format_product_card


@pytest.fixture
def catalog_items(db):
    cat = Category.objects.create(name="Staples", is_active=True)
    rice = MenuItem.objects.create(
        category=cat,
        name="Royal Basmati Rice",
        price=Decimal("220.00"),
        unit="kg",
        is_available=True,
        track_stock=True,
        stock_quantity=40,
    )
    oil = MenuItem.objects.create(
        category=cat,
        name="Pure Sunflower Oil",
        price=Decimal("170.00"),
        unit="L",
        is_available=True,
        track_stock=True,
        stock_quantity=25,
    )
    return {"rice": rice, "oil": oil}


@pytest.mark.django_db
def test_search_catalog_finds_real_products(catalog_items):
    """Test search_catalog_for_query finds actual in-stock items."""
    results = search_catalog_for_query("find basmati rice under 300")
    assert len(results) >= 1
    assert any(item.name == "Royal Basmati Rice" for item in results)

    oil_results = search_catalog_for_query("sunflower cooking oil")
    assert any(item.name == "Pure Sunflower Oil" for item in oil_results)


@pytest.mark.django_db
def test_format_product_card(catalog_items):
    """Test format_product_card produces correct frontend card dict."""
    rice = catalog_items["rice"]
    card = format_product_card(rice)
    assert card["name"] == "Royal Basmati Rice"
    assert card["price"] == "₹220"
    assert card["in_stock"] is True
    assert card["category"] == "Staples"


@pytest.mark.django_db
def test_swecha_offline_mode_graceful_response(catalog_items):
    """Test Swecha handles unconfigured GROQ_API_KEY gracefully without crashing."""
    with patch("django.conf.settings.GROQ_API_KEY", ""):
        res = call_swecha_ai("I need some rice")
        assert res["mode"] == "demo"
        assert len(res["products"]) >= 1
        assert "Royal Basmati Rice" in res["products"][0]["name"]
        assert res["audio_trigger"] is True


@pytest.mark.django_db
def test_swecha_chat_api(client, catalog_items):
    """Test POST to /order/assistant/api/chat/ returns valid JSON with message_id for sound deduplication."""
    url = reverse("swecha:chat_api")
    response = client.post(
        url,
        data={"message": "Do you have rice?"},
        content_type="application/json",
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "message_id" in data
    assert data["message_id"].startswith("swecha_msg_")
    assert isinstance(data["products"], list)
    assert len(data["products"]) >= 1
    assert data["audio_trigger"] is True


@pytest.mark.django_db
def test_swecha_assistant_page(client):
    """Test GET /order/assistant/ renders full-screen assistant page."""
    url = reverse("swecha:assistant")
    response = client.get(url)
    assert response.status_code == 200
    assert "Shopping Assistant" in response.content.decode("utf-8")


@pytest.mark.django_db
def test_swecha_mocked_groq_api_call(catalog_items):
    """Test Swecha calling Groq API when key is configured."""
    mock_choice = MagicMock()
    mock_choice.message.content = "I found Royal Basmati Rice for ₹220/kg. Would you like me to add it to your cart?"
    mock_completion = MagicMock()
    mock_completion.choices = [mock_choice]

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_completion

    with patch("django.conf.settings.GROQ_API_KEY", "gsk_test_mock_key_12345"):
        with patch("groq.Groq", return_value=mock_client):
            res = call_swecha_ai("Find basmati rice")
            assert res["mode"] == "live"
            assert "Royal Basmati Rice" in res["response"]
            assert len(res["products"]) >= 1
            assert res["audio_trigger"] is True
