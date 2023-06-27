#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the Metrics views."""
from django.urls import reverse
from django_tenants.utils import schema_context
from rest_framework import status
from rest_framework.test import APIClient

from api.iam.test.iam_test_case import IamTestCase
from api.settings.utils import set_cost_type
from api.settings.utils import set_currency
from api.user_settings.settings import COST_TYPES
from api.user_settings.settings import USER_SETTINGS


class AccountSettingsViewTest(IamTestCase):
    """Tests for the user settings views"""

    def setUp(self):
        """Set up the account settings view tests."""
        super().setUp()
        self.client = APIClient()

    def test_account_settings(self):
        """Test grabbing a user settings"""
        url = reverse("account-settings")
        client = APIClient()
        expected = {"cost_type": "calculated_amortized_cost", "currency": "JPY"}
        new_cost_type = "calculated_amortized_cost"
        new_currency = "JPY"
        with schema_context(self.schema_name):
            set_cost_type(self.schema_name, cost_type_code=new_cost_type)
            set_currency(self.schema_name, currency_code=new_currency)
            response = client.get(url, **self.headers)
            self.assertEqual(response.status_code, status.HTTP_200_OK)

            data = response.data["data"]
            self.assertEqual(data, expected)

    def test_account_settings_defaults(self):
        """Test grabbing a user settings without settings used returns default settings"""
        url = reverse("account-settings")
        client = APIClient()
        expected = USER_SETTINGS["settings"]
        with schema_context(self.schema_name):
            response = client.get(url, **self.headers)
            self.assertEqual(response.status_code, status.HTTP_200_OK)

            data = response.data["data"]
            self.assertEqual(data, expected)

    def test_account_setting(self):
        """Test grabbing a specified user setting"""
        url = "%scurrency/" % reverse("account-settings")
        client = APIClient()
        expected = {"currency": "USD"}
        with schema_context(self.schema_name):
            response = client.get(url, **self.headers)
            self.assertEqual(response.status_code, status.HTTP_200_OK)

            data = response.data["data"]
            self.assertEqual(data, expected)

    def test_account_setting_currency_put(self):
        """Test grabbing a specified user setting"""
        url = "%scurrency/" % reverse("account-settings")
        client = APIClient()
        data = {"currency": "EUR"}
        with schema_context(self.schema_name):
            response = client.put(url, data, format="json", **self.headers)
            self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

    def test_account_setting_cost_type_put(self):
        """Test grabbing a specified user setting"""
        url = "%scost_type/" % reverse("account-settings")
        client = APIClient()
        data = {"cost_type": "calculated_amortized_cost"}
        with schema_context(self.schema_name):
            response = client.put(url, data, format="json", **self.headers)
            self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

    def test_account_setting_put_unknown_setting(self):
        """Test grabbing a specified user setting"""
        url = "%sunknown/" % reverse("account-settings")
        client = APIClient()
        data = {"cost_type": "calculated_amortized_cost"}
        with schema_context(self.schema_name):
            response = client.put(url, data, format="json", **self.headers)
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_account_setting_put_unknown_cost_type(self):
        """Test grabbing a specified user setting"""
        url = "%scost_type/" % reverse("account-settings")
        client = APIClient()
        data = {"cost_type": "unknown"}
        with schema_context(self.schema_name):
            response = client.put(url, data, format="json", **self.headers)
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_account_setting_put_unknown_currency(self):
        """Test grabbing a specified user setting"""
        url = "%scurrency/" % reverse("account-settings")
        client = APIClient()
        data = {"cost_type": "unknown"}
        with schema_context(self.schema_name):
            response = client.put(url, data, format="json", **self.headers)
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_account_setting_invalid(self):
        """Test grabbing a specified user setting invalid setting"""
        url = "%sinvalid/" % reverse("account-settings")
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
