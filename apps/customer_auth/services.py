import hashlib
import random
from django.conf import settings
from django.core.cache import cache
from django.core.mail import send_mail

OTP_TTL = 300  # 5 minutes
RATE_LIMIT_WINDOW = 600  # 10 minutes
MAX_OTP_REQUESTS = 3  # Max 3 requests per 10 minutes


MAX_VERIFY_ATTEMPTS = 5  # Max 5 wrong verification attempts before lockout


def generate_otp() -> str:
    """Generate a random 6-digit numeric OTP code string."""
    return f"{random.randint(100000, 999999)}"


def hash_otp(otp: str) -> str:
    """Hash an OTP code using SHA-256 for secure storage."""
    return hashlib.sha256(otp.encode("utf-8")).hexdigest()


def _get_cache_keys(phone: str, email: str) -> tuple[str, str, str]:
    """Generate cache keys for OTP, request rate limit, and verification attempt limit."""
    identifier = f"{phone.strip()}_{email.strip().lower()}"
    hashed_id = hashlib.sha256(identifier.encode("utf-8")).hexdigest()[:32]
    return (
        f"cust_otp:{hashed_id}",
        f"cust_otp_rate:{hashed_id}",
        f"cust_otp_verify:{hashed_id}",
    )


def check_rate_limit(phone: str, email: str) -> tuple[bool, int]:
    """Check if the user has exceeded the rate limit (max 3 requests per 10 mins).

    Returns (is_allowed, remaining_attempts).
    """
    _, rate_key, _ = _get_cache_keys(phone, email)
    current_count = cache.get(rate_key, 0)
    if current_count >= MAX_OTP_REQUESTS:
        return False, 0
    return True, MAX_OTP_REQUESTS - current_count


def increment_rate_limit(phone: str, email: str) -> None:
    """Increment rate limit counter in Redis/cache."""
    _, rate_key, _ = _get_cache_keys(phone, email)
    try:
        if cache.get(rate_key) is None:
            cache.set(rate_key, 1, timeout=RATE_LIMIT_WINDOW)
        else:
            cache.incr(rate_key)
    except Exception:
        # Fallback if cache incr fails on new key
        cache.set(rate_key, 1, timeout=RATE_LIMIT_WINDOW)


def check_verify_attempts(phone: str, email: str) -> tuple[bool, int]:
    """Check if the verification attempt limit (max 5 wrong attempts) has been reached.

    Returns (is_allowed, remaining_attempts).
    """
    _, _, verify_key = _get_cache_keys(phone, email)
    current_count = cache.get(verify_key, 0)
    if current_count >= MAX_VERIFY_ATTEMPTS:
        return False, 0
    return True, MAX_VERIFY_ATTEMPTS - current_count


def store_otp_in_redis(phone: str, email: str, otp: str) -> None:
    """Store the SHA-256 hashed OTP in Redis with a 5-minute expiry and reset verify attempts."""
    otp_key, _, verify_key = _get_cache_keys(phone, email)
    hashed_code = hash_otp(otp)
    cache.set(otp_key, hashed_code, timeout=OTP_TTL)
    cache.delete(verify_key)


def verify_otp_in_redis(phone: str, email: str, input_otp: str) -> tuple[bool, bool]:
    """Verify input OTP against hashed OTP in Redis.

    Returns tuple (is_valid, is_locked).
    Deletes the OTP key upon successful verification or when lockout threshold (5 attempts) is reached.
    """
    otp_key, _, verify_key = _get_cache_keys(phone, email)

    is_allowed, _ = check_verify_attempts(phone, email)
    if not is_allowed:
        cache.delete(otp_key)
        return False, True

    stored_hash = cache.get(otp_key)
    if not stored_hash:
        return False, False

    input_hash = hash_otp(input_otp)
    if input_hash == stored_hash:
        cache.delete(otp_key)
        cache.delete(verify_key)
        return True, False

    try:
        if cache.get(verify_key) is None:
            cache.set(verify_key, 1, timeout=OTP_TTL)
            attempts = 1
        else:
            attempts = cache.incr(verify_key)
    except Exception:
        cache.set(verify_key, 1, timeout=OTP_TTL)
        attempts = 1

    if attempts >= MAX_VERIFY_ATTEMPTS:
        cache.delete(otp_key)
        return False, True

    return False, False


import logging
import threading

from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger(__name__)


def _send_email_async(subject: str, message: str, from_email: str, recipient_list: list[str], otp: str = ""):
    """Background worker function for asynchronous email dispatch using Resend API or fallback."""
    email = recipient_list[0] if recipient_list else ""
    resend_key = getattr(settings, "RESEND_API_KEY", "")
    backend = getattr(settings, "EMAIL_BACKEND", "")
    is_test_or_console = backend.endswith("locmem.EmailBackend") or backend.endswith("console.EmailBackend")

    sent_via_resend = False
    if resend_key and not is_test_or_console:
        try:
            import resend
            resend.api_key = resend_key
            html_content = f"<p>Your OTP is <strong>{otp}</strong>. It expires in 5 minutes.</p>" if otp else f"<p>{message}</p>"
            brand_name = getattr(settings, "BRAND_NAME", "FreshMart")
            resend.Emails.send({
                "from": f"{brand_name} <otp@freshmart.com>",
                "to": [email],
                "subject": subject,
                "html": html_content,
            })
            logger.info(f"Successfully sent OTP email via Resend to {email}")
            sent_via_resend = True
        except (ImportError, ModuleNotFoundError):
            logger.info("resend package not installed in environment; falling back to SMTP send_mail")
        except Exception as exc:
            logger.warning(f"Resend dispatch failed ({exc}); falling back to SMTP send_mail")

    if not sent_via_resend:
        try:
            send_mail(
                subject=subject,
                message=message,
                from_email=from_email,
                recipient_list=recipient_list,
                fail_silently=False,
            )
            logger.info(f"Successfully sent OTP email to {email}")
        except Exception as exc:
            logger.exception(f"Failed to send OTP email to {email}: {exc}")



def send_otp_email(email: str, otp: str) -> bool:
    """Queue OTP email delivery to customer via background thread.

    Never logs the plaintext OTP. Returns True immediately once queued.
    """
    brand_name = getattr(settings, "BRAND_NAME", "FreshMart")
    brand_short = getattr(settings, "BRAND_SHORT", "FM")
    subject = f"Your {brand_name} Verification Code"
    message = (
        f"Hello,\n\n"
        f"Your verification code for {brand_name} Grocery Delivery is: {otp}\n\n"
        f"This code will expire in 5 minutes. Please do not share this code with anyone.\n\n"
        f"Thank you,\n"
        f"{brand_short} · {brand_name}"
    )
    from_email = (
        getattr(settings, "DEFAULT_FROM_EMAIL", None)
        or getattr(settings, "EMAIL_HOST_USER", None)
        or "support@freshmart.com"
    )
    logger.info(
        f"Queueing OTP email to {email} in background thread"
    )

    thread = threading.Thread(
        target=_send_email_async,
        args=(subject, message, from_email, [email], otp),
        daemon=True,
    )
    thread.start()
    return True

