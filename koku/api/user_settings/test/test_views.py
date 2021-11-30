#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the Metrics views."""
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from tenant_schemas.utils import schema_context

from api.iam.test.iam_test_case import IamTestCase
from api.settings.utils import set_cost_type
from api.user_settings.settings import COST_TYPES
from koku.settings import KOKU_DEFAULT_COST_TYPE


class UserSettingsCostViewTest(IamTestCase):
    """Tests for the metrics view."""

    def setUp(self):
        """Set up the user settings cost_type view tests."""
        super().setUp()
        self.client = APIClient()

    def test_no_userset_cost_type(self):
        """Test that a list GET call returns the supported cost_types with meta data cost-type=default."""
        qs = "?limit=20"
        url = reverse("cost-type") + qs

        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        data = response.data
        self.assertEqual(data.get("data"), COST_TYPES)

        meta = data.get("meta", {})
        self.assertEqual(meta.get("cost-type"), KOKU_DEFAULT_COST_TYPE)

    def test_userset_cost_type(self):
        """Test that a list GET call returns the supported cost_types and returns meta users current cost_type."""
        qs = "?limit=20"
        url = reverse("cost-type") + qs
        client = APIClient()
        new_cost_type = "savingsplan_effective_cost"
        with schema_context(self.schema_name):
            set_cost_type(self.schema_name, cost_type_code=new_cost_type)
            response = client.get(url, **self.headers)
            self.assertEqual(response.status_code, status.HTTP_200_OK)

            data = response.data
            self.assertEqual(data.get("data"), COST_TYPES)
            meta = data.get("meta", {})
            self.assertEqual(meta.get("cost-type"), new_cost_type)
