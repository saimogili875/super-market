from django.apps import AppConfig


class CustomerAuthConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.customer_auth"
    label = "customer_auth"
    verbose_name = "Customer Delivery Authentication"

    def ready(self):
        import sys
        from django.conf import settings

        # Only warn on server startup when DEBUG=False and not running collectstatic
        if not getattr(settings, "DEBUG", True) and "collectstatic" not in sys.argv:
            email_user = getattr(settings, "EMAIL_HOST_USER", "")
            email_pass = getattr(settings, "EMAIL_HOST_PASSWORD", "")
            if not email_user or not email_pass:
                import logging
                logger = logging.getLogger("apps.customer_auth")
                logger.warning(
                    "PRODUCTION EMAIL WARNING: EMAIL_HOST_USER or EMAIL_HOST_PASSWORD is blank in settings! "
                    "Customer OTP emails will fail to send until credentials are set in Environment variables."
                )

