"""Rate limiting constants and thin wrappers for abuse-prone endpoints."""
from django_ratelimit.decorators import ratelimit

# Admin login POST: ~5/min -> 429 on exceed (blocks brute-force)
admin_login = ratelimit(key="ip", rate="5/m", method="POST", block=True)

# Front-door login POST: ~5/min (blocks brute-force on /accounts/login/)
login = ratelimit(key="ip", rate="5/m", method="POST", block=True)

# Customer delivery checkout POST: ~20/min (blocks spam orders)
checkout = ratelimit(key="ip", rate="20/m", method="POST", block=True)

# Dine-in place-order / add-items POST: ~20/min (blocks spam orders)
dine_in_order = ratelimit(key="ip", rate="20/m", method="POST", block=True)

# Quick messaging POST: ~10/min (blocks spam messages)
messaging = ratelimit(key="ip", rate="10/m", method="POST", block=True)

# Customer OTP verification POST: ~10/min (blocks OTP brute-force)
verify_otp = ratelimit(key="ip", rate="10/m", method="POST", block=True)
