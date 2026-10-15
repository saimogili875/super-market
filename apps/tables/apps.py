"""App configuration for the tables app."""
from django.apps import AppConfig


class TablesConfig(AppConfig):
    """Configuration for tables domain models and workflows."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.tables"
    label = "tables"
