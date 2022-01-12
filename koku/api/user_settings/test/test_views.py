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
from api.settings.utils import set_currency
from api.user_settings.settings import COST_TYPES
from api.user_settings.settings import USER_SETTINGS
from koku.settings import KOKU_DEFAULT_COST_TYPE


class UserSettingsViewTest(IamTestCase):
    """Tests for the user settings views"""

    def setUp(self):
        """Set up the user settings view tests."""
        super().setUp()
        self.client = APIClient()

    def test_user_settings(self):
        """Test grabbing a user settings"""
        url = reverse("account-settings")
        client = APIClient()
        expected = {"cost_type": "savingsplan_effective_cost", "currency": "JPY"}
        new_cost_type = "savingsplan_effective_cost"
        new_currency = "JPY"
        with schema_context(self.schema_name):
            set_cost_type(self.schema_name, cost_type_code=new_cost_type)
            set_currency(self.schema_name, currency_code=new_currency)
            response = client.get(url, **self.headers)
            self.assertEqual(response.status_code, status.HTTP_200_OK)

            data = response.data["data"]
            self.assertEqual(data, expected)

    def test_user_settings_defaults(self):
        """Test grabbing a user settings without settings used returns default settings"""
        url = reverse("account-settings")
        client = APIClient()
        expected = USER_SETTINGS["settings"]
        with schema_context(self.schema_name):
            response = client.get(url, **self.headers)
            self.assertEqual(response.status_code, status.HTTP_200_OK)

            data = response.data["data"]
            self.assertEqual(data, expected)

    def test_user_setting(self):
        """Test grabbing a specified user setting"""
        url = url = "%scurrency/" % reverse("account-settings")
        client = APIClient()
        expected = {"currency": "USD"}
        with schema_context(self.schema_name):
            response = client.get(url, **self.headers)
            self.assertEqual(response.status_code, status.HTTP_200_OK)

            data = response.data["data"]
            self.assertEqual(data, expected)

    def test_user_setting_invalid(self):
        """Test grabbing a specified user setting invalid setting"""
        url = url = "%sinvalid/" % reverse("account-settings")
        client = APIClient()
        with schema_context(self.schema_name):
            response = client.get(url, **self.headers)
            self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class UserSettingsCostViewTest(IamTestCase):
    """Tests for the cost-type view."""

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
