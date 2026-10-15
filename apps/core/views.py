"""Core views — infrastructure endpoints + public landing page."""
from django.http import JsonResponse
from django.shortcuts import render

from apps.menu.models import MenuItem


def healthz(request):
    """Liveness probe — returns 200 with {"status": "ok"}."""
    return JsonResponse({"status": "ok"})


def home(request):
    """Public supermarket landing page served at "/".

    Pulls up to six available products for the "Featured Products" section.
    Falls back to curated sample groceries when the catalogue is empty so the
    section always renders. Purely presentational — no state is mutated.
    """
    highlights = list(
        MenuItem.objects.filter(is_available=True)
        .select_related("category")
        .order_by("category__sort_order", "name")[:6]
    )

    sample_dishes = [
        {"name": "Organic Farm Fresh Apples (1kg)",
         "description": "Crisp, sweet, locally sourced Himalayan apples", "price": "180"},
        {"name": "A2 Organic Cow Milk (1L)",
         "description": "Pasteurized, farm-fresh whole milk with natural cream", "price": "75"},
        {"name": "Cold-Pressed Virgin Olive Oil (500ml)",
         "description": "First cold extraction, rich in antioxidants", "price": "420"},
        {"name": "Organic Brown Eggs (Pack of 12)",
         "description": "Free-range, grain-fed, antibiotic-free farm eggs", "price": "140"},
        {"name": "Royal Aged Basmati Rice (5kg)",
         "description": "Extra-long grain, aromatic premium pantry staple", "price": "490"},
        {"name": "Artisan Sourdough Loaf (400g)",
         "description": "Naturally fermented, crusty bakery daily fresh", "price": "120"},
    ]

    context = {
        "highlights": highlights,
        "sample_dishes": sample_dishes,
    }
    return render(request, "pages/home.html", context)


def contact(request):
    """Contact page view — displays and processes contact form."""
    from django.contrib import messages
    from django.core.mail import send_mail
    from django.conf import settings
    from apps.core.forms import ContactForm

    if request.method == "POST":
        form = ContactForm(request.POST)
        if form.is_valid():
            name = form.cleaned_data["name"]
            sender_email = form.cleaned_data["email"]
            user_message = form.cleaned_data["message"]

            subject = f"New Contact Message from {name}"
            body = (
                f"You have received a new contact form submission:\n\n"
                f"Name: {name}\n"
                f"Email: {sender_email}\n\n"
                f"Message:\n{user_message}"
            )
            recipient = getattr(settings, "EMAIL_HOST_USER", None) or getattr(settings, "BRAND_EMAIL", "support@freshmart.com")
            from_email = getattr(settings, "DEFAULT_FROM_EMAIL", None) or getattr(settings, "EMAIL_HOST_USER", None) or recipient

            try:
                from django.core.mail import EmailMessage
                email = EmailMessage(
                    subject=subject,
                    body=body,
                    from_email=from_email,
                    to=[recipient],
                    reply_to=[sender_email],
                )
                email.send(fail_silently=False)
                messages.success(request, "Your message has been sent successfully!")
                form = ContactForm()  # reset form after success
            except Exception as e:
                messages.error(request, f"Failed to send email: {e}")
    else:
        form = ContactForm()

    return render(request, "pages/contact.html", {"form": form})

