import time

from django.contrib import messages
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from apps.customer_auth.forms import ExistingCustomerLoginForm, NewCustomerSignupForm, OTPVerifyForm
from apps.customer_auth.models import Customer
from apps.customer_auth import services


def get_logged_in_customer(request) -> Customer | None:
    """Helper function to fetch the currently logged-in Customer from session."""
    customer_id = request.session.get("customer_id")
    if not customer_id:
        return None
    try:
        return Customer.objects.filter(pk=customer_id).first()
    except Exception:
        return None


@require_http_methods(["GET", "POST"])
def customer_login(request):
    """Page 1: Existing Customer Login — accepts Email only."""
    if get_logged_in_customer(request):
        cart_raw = request.session.get("delv_cart", {})
        if cart_raw:
            return redirect("orders_customer:checkout")
        return redirect("orders_customer:menu")

    login_form = ExistingCustomerLoginForm()

    if request.method == "POST":
        action = request.POST.get("action", "login")
        if action == "signup" or ("phone" in request.POST and "email" in request.POST):
            return customer_signup(request)

        login_form = ExistingCustomerLoginForm(request.POST)
        if login_form.is_valid():
            email = login_form.cleaned_data["email"]
            customer = Customer.objects.filter(email=email).first()
            if not customer:
                login_form.add_error(
                    "email",
                    "No account found with this email. Would you like to create one?",
                )
            else:
                phone = customer.phone or "0000000000"
                is_allowed, _ = services.check_rate_limit(phone, email)
                if not is_allowed:
                    messages.error(
                        request,
                        "Too many OTP requests for this account. Please wait 10 minutes before requesting a new code.",
                    )
                else:
                    otp = services.generate_otp()
                    services.store_otp_in_redis(phone, email, otp)
                    services.increment_rate_limit(phone, email)
                    services.send_otp_email(email, otp)

                    request.session["pending_otp_phone"] = phone
                    request.session["pending_otp_email"] = email
                    request.session["pending_otp_timestamp"] = int(time.time())
                    request.session["pending_otp_auth_mode"] = "login"
                    request.session.modified = True

                    messages.success(request, f"We've sent a verification code to {email}")
                    return redirect("customer_auth:verify_otp")

    context = {
        "login_form": login_form,
        "form": login_form,
    }
    return render(request, "customer_auth/login.html", context)


@require_http_methods(["GET", "POST"])
def customer_signup(request):
    """Page 2: New Customer Create Account — accepts Phone & Email."""
    if get_logged_in_customer(request):
        cart_raw = request.session.get("delv_cart", {})
        if cart_raw:
            return redirect("orders_customer:checkout")
        return redirect("orders_customer:menu")

    signup_form = NewCustomerSignupForm()

    if request.method == "POST":
        action = request.POST.get("action", "signup")
        if action == "login" or ("email" in request.POST and "phone" not in request.POST):
            return customer_login(request)

        signup_form = NewCustomerSignupForm(request.POST)
        if signup_form.is_valid():
            phone = signup_form.cleaned_data["phone"]
            email = signup_form.cleaned_data["email"]

            if Customer.objects.filter(email=email).exists():
                signup_form.add_error(
                    "email",
                    "An account already exists with this email. Please log in with your existing account instead.",
                )
            elif Customer.objects.filter(phone=phone).exists():
                signup_form.add_error(
                    "phone",
                    "An account already exists with this phone number. Please use 'Existing Customer — Login' instead.",
                )
            else:
                is_allowed, _ = services.check_rate_limit(phone, email)
                if not is_allowed:
                    messages.error(
                        request,
                        "Too many OTP requests for this phone/email. Please wait 10 minutes before requesting a new code.",
                    )
                else:
                    otp = services.generate_otp()
                    services.store_otp_in_redis(phone, email, otp)
                    services.increment_rate_limit(phone, email)
                    services.send_otp_email(email, otp)

                    request.session["pending_otp_phone"] = phone
                    request.session["pending_otp_email"] = email
                    request.session["pending_otp_timestamp"] = int(time.time())
                    request.session["pending_otp_auth_mode"] = "signup"
                    request.session.modified = True

                    messages.success(
                        request,
                        f"We've sent a verification code to {email} to create your account",
                    )
                    return redirect("customer_auth:verify_otp")

    context = {
        "signup_form": signup_form,
        "form": signup_form,
    }
    return render(request, "customer_auth/signup.html", context)


from apps.core.ratelimits import verify_otp as verify_otp_ratelimit


@verify_otp_ratelimit
@require_http_methods(["GET", "POST"])
def verify_otp(request):
    """OTP verification page — customer enters the 6-digit code received via email."""
    phone = request.session.get("pending_otp_phone")
    email = request.session.get("pending_otp_email")
    timestamp = request.session.get("pending_otp_timestamp", 0)
    auth_mode = request.session.get("pending_otp_auth_mode", "login")

    if not phone or not email:
        messages.warning(request, "Please enter your email to receive a verification code.")
        return redirect("customer_auth:login")

    elapsed = int(time.time()) - timestamp
    cooldown_left = max(0, 45 - elapsed)

    if request.method == "POST":
        form = OTPVerifyForm(request.POST)
        if form.is_valid():
            otp = form.cleaned_data["otp"]
            is_valid, is_locked = services.verify_otp_in_redis(phone, email, otp)

            if is_valid:
                customer, created = Customer.objects.get_or_create(
                    email=email,
                    defaults={"phone": phone, "name": ""},
                )
                if not created:
                    if phone and not customer.phone:
                        customer.phone = phone
                    customer.save()

                request.session["customer_id"] = customer.pk
                request.session.set_expiry(7 * 24 * 3600)

                request.session.pop("pending_otp_phone", None)
                request.session.pop("pending_otp_email", None)
                request.session.pop("pending_otp_timestamp", None)
                request.session.pop("pending_otp_auth_mode", None)
                request.session.modified = True

                if created or auth_mode == "signup":
                    from django.conf import settings
                    brand = getattr(settings, "BRAND_NAME", "FreshMart")
                    messages.success(request, f"You're all set! Welcome to {brand}.")
                else:
                    name_str = f", {customer.name}" if customer.name else ""
                    messages.success(request, f"Welcome back{name_str}!")

                cart_raw = request.session.get("delv_cart", {})
                if cart_raw:
                    return redirect("orders_customer:checkout")
                return redirect("orders_customer:menu")
            elif is_locked:
                messages.error(
                    request,
                    "Too many failed verification attempts. This code has been invalidated. Please request a new code.",
                )
            else:
                messages.error(
                    request,
                    "Invalid or expired verification code. Please check your code or request a new one.",
                )
    else:
        form = OTPVerifyForm()

    context = {
        "form": form,
        "phone": phone,
        "email": email,
        "cooldown_left": cooldown_left,
        "auth_mode": auth_mode,
        "is_returning_customer": (auth_mode == "login"),
    }
    return render(request, "customer_auth/verify_otp.html", context)


@require_POST
def resend_otp(request):
    """AJAX/POST endpoint to resend OTP with rate limiting."""
    phone = request.session.get("pending_otp_phone")
    email = request.session.get("pending_otp_email")

    if not phone or not email:
        messages.error(request, "Session expired. Please enter your email and phone number again.")
        return redirect("customer_auth:login")

    is_allowed, remaining = services.check_rate_limit(phone, email)
    if not is_allowed:
        messages.error(
            request,
            "Too many OTP requests. Please wait 10 minutes before requesting a new code.",
        )
        return redirect("customer_auth:verify_otp")

    otp = services.generate_otp()
    services.store_otp_in_redis(phone, email, otp)
    services.increment_rate_limit(phone, email)

    sent = services.send_otp_email(email, otp)
    if sent:
        request.session["pending_otp_timestamp"] = int(time.time())
        request.session.modified = True
        messages.success(request, f"We've sent a verification code to {email}")
    else:
        messages.error(request, "Failed to send email. Please try again.")

    return redirect("customer_auth:verify_otp")


@require_http_methods(["GET", "POST"])
def customer_logout(request):
    """Customer logout — clears customer session and redirects to login."""
    if "customer_id" in request.session:
        del request.session["customer_id"]
        request.session.set_expiry(0)
        request.session.modified = True
        messages.success(request, "You have been logged out.")
    return redirect("customer_auth:login")
