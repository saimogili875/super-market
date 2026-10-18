"""Swecha AI Shopping Assistant service powered by Groq API.

Integrates with Groq API for natural language assistance and queries
the live FreshMart supermarket catalog (MenuItem, Category) to return authoritative
product recommendations, prices, availability, and budget planning.
"""
import logging
import re
from decimal import Decimal
from django.conf import settings
from django.db.models import Q
from apps.menu.models import MenuItem, Category

logger = logging.getLogger(__name__)

SWECHA_SYSTEM_PROMPT = """You are Swecha, the friendly, intelligent, and authoritative AI Shopping Assistant for FreshMart Online Supermarket.
Your role:
1. Help customers find groceries, fresh produce, staples, dairy, beverages, and household essentials.
2. Provide budget planning (e.g., finding meals or ingredient bundles under ₹100, ₹300, ₹500, etc.).
3. Compare product options, pack sizes, and prices transparently.
4. Assist with understanding delivery, shopping cart, and checkout steps.

CRITICAL POLICY & RULES:
- Never fabricate or invent product names, prices, discounts, stock quantities, or delivery promises.
- Only reference the actual product catalog provided in the context below.
- If a requested product is not available in our catalog, clearly state that FreshMart does not currently stock it, and suggest a close available alternative if one exists.
- Keep responses concise, warm, helpful, and formatted in clean markdown.
- When mentioning products, state their exact name, size/unit, and price in ₹.
"""

def extract_budget(query: str):
    """Detect if query mentions budget like 'under 300', 'below ₹500', 'less than 200'."""
    pattern = r'(?:under|below|less than|within|budget of)\s*(?:₹|rs\.?|inr)?\s*(\d+(?:\.\d+)?)'
    match = re.search(pattern, query, re.IGNORECASE)
    if match:
        try:
            return Decimal(match.group(1))
        except Exception:
            return None
    return None


def search_catalog_for_query(query: str, max_items: int = 6):
    """Retrieve real products from database matching user search terms and budget."""
    qs = MenuItem.objects.filter(is_available=True).select_related("category")
    
    budget = extract_budget(query)
    
    # Extract keywords from query, filtering out common stop words
    stop_words = {
        "find", "show", "me", "the", "a", "an", "and", "or", "in", "for", "with", "under", 
        "below", "within", "budget", "of", "can", "you", "i", "want", "need", "please",
        "some", "any", "best", "what", "is", "where", "how", "much", "to", "buy", "get"
    }
    words = [w.strip() for w in re.findall(r'[a-zA-Z0-9]+', query.lower()) if len(w) > 1 and w not in stop_words]
    
    matched_qs = qs.none()
    if words:
        name_q = Q()
        for word in words:
            name_q |= Q(name__icontains=word) | Q(category__name__icontains=word) | Q(description__icontains=word)
        matched_qs = qs.filter(name_q)
    
    # Apply budget filter if detected
    if budget:
        # Filter where price <= budget
        matched_qs = matched_qs.filter(price__lte=budget)
    
    items = list(matched_qs.order_by("-is_available", "price")[:max_items])
    
    # If no specific matches but budget specified, return best products under budget
    if not items and budget:
        items = list(qs.filter(price__lte=budget).order_by("price")[:max_items])
    elif not items and words:
        # Fallback to general popular items
        items = list(qs.order_by("sort_order" if hasattr(MenuItem, "sort_order") else "name")[:4])
        
    return items


def format_product_card(item: MenuItem) -> dict:
    """Format MenuItem into standard product card JSON for Swecha UI."""
    img_url = ""
    if item.image:
        img_url = item.image.url
    else:
        img_url = "/static/images/exterior.jpeg"

    effective_price = item.effective_price
    has_discount = item.offer_percent > 0

    return {
        "id": item.id,
        "name": item.name,
        "price": f"₹{effective_price:.0f}" if effective_price == int(effective_price) else f"₹{effective_price:.2f}",
        "raw_price": float(effective_price),
        "original_price": f"₹{item.price:.0f}" if item.price == int(item.price) else f"₹{item.price:.2f}" if has_discount else None,
        "discount_percent": item.offer_percent if has_discount else 0,
        "unit": f"1 {item.get_unit_display()}" if item.unit == "pcs" else f"{item.get_unit_display()}",
        "image_url": img_url,
        "in_stock": item.is_orderable,
        "category": item.category.name if item.category else "",
        "sku": item.sku or "",
    }


def call_swecha_ai(user_message: str, conversation_history: list = None) -> dict:
    """
    Execute AI shopping assistant call.
    Returns:
    {
        "response": str,
        "products": list[dict],
        "audio_trigger": bool,
        "mode": "live" | "demo",
        "error": str | None
    }
    """
    if conversation_history is None:
        conversation_history = []

    user_message = user_message.strip()
    if not user_message:
        return {
            "response": "Hello! How can I assist you with your grocery shopping today?",
            "products": [],
            "audio_trigger": False,
            "mode": "live",
            "error": None
        }

    # Always retrieve real matching products from authoritative catalog
    matching_items = search_catalog_for_query(user_message)
    product_cards = [format_product_card(item) for item in matching_items]

    # Check GROQ API KEY
    groq_api_key = getattr(settings, "GROQ_API_KEY", "") or ""
    groq_model = getattr(settings, "GROQ_MODEL", "llama-3.3-70b-versatile")

    # Catalog context for the model
    catalog_summary = []
    if matching_items:
        for it in matching_items:
            stock_str = "In stock" if it.is_orderable else "Out of stock"
            catalog_summary.append(
                f"- {it.name} ({it.get_unit_display()}): ₹{it.effective_price} [{stock_str}, Category: {it.category.name if it.category else 'General'}]"
            )
    else:
        # Give a small slice of real categories so AI knows what is available
        categories = list(Category.objects.filter(is_active=True).values_list("name", flat=True)[:8])
        catalog_summary.append(f"Available Categories: {', '.join(categories)}")

    context_prompt = (
        f"{SWECHA_SYSTEM_PROMPT}\n\n"
        f"CURRENT REAL CATALOG DATA:\n" + "\n".join(catalog_summary) + "\n"
    )

    if not groq_api_key or groq_api_key.startswith("your_actual_") or groq_api_key == "placeholder":
        # Graceful Demo Mode when GROQ_API_KEY is not configured
        if product_cards:
            item_names = ", ".join([p["name"] + f" ({p['price']})" for p in product_cards[:3]])
            msg = (
                f"I found {len(product_cards)} matching product(s) in our fresh catalog: {item_names}.\n\n"
                f"You can add any of these directly to your cart below! "
                f"*(Note: Server running with GROQ_API_KEY in offline demo mode. Configure your API key to enable full natural language chat.)*"
            )
        else:
            msg = (
                "Welcome to FreshMart! I searched our current catalog for you. "
                "Try searching for staples like 'Rice', 'Milk', 'Oil', 'Poha', or 'Dal'. "
                "*(Note: Set GROQ_API_KEY in your environment to activate generative responses.)*"
            )
        return {
            "response": msg,
            "products": product_cards,
            "audio_trigger": True,
            "mode": "demo",
            "error": "GROQ_API_KEY not configured"
        }

    # Live Groq API Execution
    try:
        from groq import Groq
        client = Groq(api_key=groq_api_key)

        messages = [{"role": "system", "content": context_prompt}]
        for turn in conversation_history[-6:]:  # Keep recent context
            role = turn.get("role")
            content = turn.get("content")
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content})

        messages.append({"role": "user", "content": user_message})

        completion = client.chat.completions.create(
            model=groq_model,
            messages=messages,
            max_tokens=600,
            temperature=0.7,
        )

        ai_text = completion.choices[0].message.content or "I am ready to help you with your groceries. What items do you need?"

        return {
            "response": ai_text,
            "products": product_cards,
            "audio_trigger": True,
            "mode": "live",
            "error": None
        }

    except Exception as e:
        logger.warning("Groq API call failed: %s. Using catalog fallback.", str(e))
        fallback_msg = (
            f"Here are the matching items from our live catalog for your request.\n\n"
            f"*(AI communication temporary fallback: {str(e)})*"
        )
        return {
            "response": fallback_msg,
            "products": product_cards,
            "audio_trigger": True,
            "mode": "fallback",
            "error": str(e)
        }
