"""Core views — infrastructure endpoints + public landing page."""
from django.http import JsonResponse
from django.shortcuts import render

from apps.menu.models import MenuItem


def healthz(request):
    """Liveness probe — returns 200 with {"status": "ok"}."""
    return JsonResponse({"status": "ok"})


def home(request):
    """Marketing landing page for FreshMart.

    If the visitor is already logged in, redirect them directly to their role portal:
    - Customer -> /order/menu/
    - Agent -> /agent/
    - Manager / Staff -> /manager/
    - Admin -> /<ADMIN_URL>/orders/dashboard/

    If the visitor is unauthenticated, render the minimal marketing page
    (brand, dark mode toggle, hero, 3 value points, tiny footer).
    Zero catalog items, prices, categories, or cart are exposed.
    """
    from django.shortcuts import redirect
    from apps.accounts.models import Role
    from apps.customer_auth.views import get_logged_in_customer

    user = getattr(request, "user", None)
    if user and user.is_authenticated:
        role = getattr(user, "role", None)
        if role == Role.ADMIN:
            return redirect("orders_admin:dashboard")
        elif role == Role.AGENT:
            return redirect("orders_agent:dashboard")
        elif role in (Role.MANAGER, Role.STAFF, Role.INVENTORY, Role.CASHIER):
            return redirect("manager:dashboard")
        elif role == Role.CUSTOMER:
            return redirect("orders_customer:menu")

    if get_logged_in_customer(request):
        return redirect("orders_customer:menu")

    context = {
        "brand_name": "FreshMart",
        "brand_tagline": "Fresh food. Everyday low prices.",
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


def admin_settings(request):
    """Supermarket store profile and operational configuration."""
    from django.conf import settings as django_settings
    from django.contrib import messages
    from django.shortcuts import redirect
    from apps.audit.models import log_audit_event
    from apps.core.permissions import role_required

    if not request.user.is_authenticated or not getattr(request.user, "is_admin_role", False):
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied

    if request.method == "POST":
        brand_name = request.POST.get("brand_name", "").strip()
        brand_tagline = request.POST.get("brand_tagline", "").strip()
        brand_phone = request.POST.get("brand_phone", "").strip()
        brand_email = request.POST.get("brand_email", "").strip()
        brand_location = request.POST.get("brand_location", "").strip()
        tax_rate = request.POST.get("tax_rate", "5.0").strip()

        request.session["custom_brand_settings"] = {
            "name": brand_name,
            "tagline": brand_tagline,
            "phone": brand_phone,
            "email": brand_email,
            "location": brand_location,
            "tax_rate": tax_rate,
        }

        log_audit_event(
            request=request,
            action="Settings updated",
            category="Security",
            change_summary=f"Updated store profile: {brand_name}, Tax: {tax_rate}%",
        )
        messages.success(request, "Supermarket settings updated successfully.")
        return redirect("core:admin_settings")

    custom_cfg = request.session.get("custom_brand_settings", {})
    return render(
        request,
        "admin/settings.html",
        {
            "brand_name": custom_cfg.get("name") or getattr(django_settings, "BRAND_NAME", "FreshMart"),
            "brand_tagline": custom_cfg.get("tagline") or getattr(django_settings, "BRAND_TAGLINE", "Fresh groceries, delivered fast"),
            "brand_phone": custom_cfg.get("phone") or getattr(django_settings, "BRAND_PHONE", "6281238410"),
            "brand_email": custom_cfg.get("email") or getattr(django_settings, "BRAND_EMAIL", "support@freshmart.in"),
            "brand_location": custom_cfg.get("location") or getattr(django_settings, "BRAND_LOCATION", "Hyderabad"),
            "tax_rate": custom_cfg.get("tax_rate", "5.0"),
            "active_nav": "settings",
        },
    )

