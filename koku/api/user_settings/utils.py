from tenant_schemas.utils import schema_context

from koku.settings import KOKU_DEFAULT_COST_TYPE
from reporting.user_settings.models import UserSettings


class CostTypeUtils:
    """Utilities for cost_type portion of user setting."""

    def get_selected_cost_type(schema):
        """Gets the current selected cost_type in user settings"""
        with schema_context(schema):
            if not UserSettings.objects.exists():
                cost_type = KOKU_DEFAULT_COST_TYPE
            else:
                cost_type = UserSettings.objects.all().first().settings["cost_type"]
        return cost_type
