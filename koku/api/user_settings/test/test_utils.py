#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
from tenant_schemas.utils import schema_context

from api.settings.utils import set_cost_type
from api.user_settings.utils import CostTypeUtils
from koku.settings import KOKU_DEFAULT_COST_TYPE
from masu.test import MasuTestCase
from reporting.user_settings.models import UserSettings


class TestCostUtils(MasuTestCase):
    """Test cases for cost_type for user settings utils."""

    def setUp(self):
        """Set up test suite."""
        with schema_context(self.schema):
            UserSettings.objects.all().delete()

    def test_get_cost_type(self):
        cost_type = CostTypeUtils.get_selected_cost_type(self.schema)
        self.assertEqual(cost_type, KOKU_DEFAULT_COST_TYPE)

        user_cost_type = "blended_cost"
        set_cost_type(self.schema, cost_type_code=user_cost_type)
        cost_type = CostTypeUtils.get_selected_cost_type(self.schema)
        self.assertEqual(cost_type, user_cost_type)
