"""Views for Swecha AI Shopping Assistant."""
import json
import uuid
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST, require_GET
from .services import call_swecha_ai


@require_GET
def assistant_page(request):
    """Full-screen Customer Shopping Assistant page matching reference design."""
    return render(
        request,
        "swecha/assistant.html",
        {
            "page_title": "Shopping Assistant",
            "active_nav": "assistant",
        },
    )


@require_POST
def chat_api(request):
    """JSON API endpoint for Swecha shopping assistant.
    
    Accepts:
    - message (str)
    - history (list of {role, content})
    
    Returns:
    - response: AI answer markdown/text
    - products: list of real matching product cards from database
    - message_id: unique ID for sound deduplication
    - mode: "live" | "demo" | "fallback"
    """
    try:
        if request.content_type == "application/json":
            data = json.loads(request.body.decode("utf-8"))
        else:
            data = request.POST.dict()
    except Exception:
        data = {}

    user_message = data.get("message", "").strip()
    history = data.get("history", [])
    if isinstance(history, str):
        try:
            history = json.loads(history)
        except Exception:
            history = []

    result = call_swecha_ai(user_message, history)
    
    # Generate stable message_id for client audio deduplication
    message_id = f"swecha_msg_{uuid.uuid4().hex[:10]}"

    return JsonResponse({
        "status": "success",
        "message_id": message_id,
        "response": result["response"],
        "products": result["products"],
        "audio_trigger": result["audio_trigger"],
        "mode": result["mode"],
        "error": result.get("error"),
    })
