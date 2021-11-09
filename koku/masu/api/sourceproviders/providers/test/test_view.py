#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tests the Masu API `manifest` Views."""
from unittest.mock import patch

from django.test.utils import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from api.iam.test.iam_test_case import IamTestCase
from api.provider.models import Provider


@override_settings(ROOT_URLCONF="masu.urls")
class ProviderViewTests(IamTestCase):
    """Tests provider views"""

    def setUp(self):
        """Set up the tests."""
        super().setUp()
        self.client = APIClient()

    @patch("koku.middleware.MASU", return_value=True)
    def test_get_providers(self, _):
        """Test providers"""
        response = self.client.get(reverse("providers"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    @patch("koku.middleware.MASU", return_value=True)
    def test_get_providers_invalid_parameter(self, _):
        """Test providers with invalid parameter for filter"""
        url = "%s?invalid=parameter" % reverse("providers")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @patch("koku.middleware.MASU", return_value=True)
    def test_get_provider_by_account_id(self, _):
        """Test get provider for account id"""
        provider = Provider.objects.first()
        account_id = provider.customer.account_id
        url = reverse("get_providers_by_account_id", kwargs={"customer": account_id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    @patch("koku.middleware.MASU", return_value=True)
    def test_provider_by_invalid_account_id_returns_null(self, _):
        """Test get provider invalid account id"""
        account_id = 20012707
        url = reverse("get_providers_by_account_id", kwargs={"customer": account_id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    @patch("koku.middleware.MASU", return_value=True)
    def test_provider_by_valid_account_id_returns_not_null(self, _):
        """Test get provider invalid account id"""
        account_id = 10001
        url = reverse("get_providers_by_account_id", kwargs={"customer": account_id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    @patch("koku.middleware.MASU", return_value=True)
    def test_provider_by_invalid_filter(self, _):
        """Test get provider invalid account id"""
        filter = "bad filter"
        url = reverse("providers") + filter
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
