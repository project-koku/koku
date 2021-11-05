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

from api.iam.models import Customer
from api.iam.test.iam_test_case import IamTestCase
from api.provider.models import Provider
from api.provider.models import Sources


@override_settings(ROOT_URLCONF="masu.urls")
class SourceViewTests(IamTestCase):
    """Tests manifests views"""

    def setUp(self):
        """Set up the tests."""
        super().setUp()
        self.test_account = "10001"
        user_data = self._create_user_data()
        customer = self._create_customer_data(account=self.test_account)
        self.request_context = self._create_request_context(customer, user_data, create_customer=True, is_admin=True)
        self.test_source_id = 1
        name = "Test sources"
        customer_obj = Customer.objects.get(account_id=customer.get("account_id"))
        self.aws_provider = Provider(name=name, type=Provider.PROVIDER_AWS, customer=customer_obj)
        self.aws_provider.save()
        self.source = Sources(
            source_id=self.test_source_id,
            source_uuid=self.aws_provider.uuid,
            name=name,
            auth_header=self.request_context["request"].META,
            offset=1,
            account_id=customer.get("account_id"),
            source_type=Provider.PROVIDER_AWS,
            authentication={
                "credentials": {"client_id": "test_client", "tenant_id": "test_tenant", "client_secret": "test_secret"}
            },
            billing_source={
                "data_source": {
                    "resource_group": {"directory": "", "export_name": "azure-report-v2"},
                    "storage_account": {"container": "", "local_dir": "/tmp/local_container"},
                }
            },
            koku_uuid=self.aws_provider.uuid,
            paused=False,
            pending_delete=False,
            pending_update=False,
            out_of_order_delete=False,
            status={},
        )
        self.source.save()
        self.client = APIClient()

    @patch("koku.middleware.MASU", return_value=True)
    def test_get_sources(self, _):
        """Test providers"""
        response = self.client.get(reverse("sources"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    @patch("koku.middleware.MASU", return_value=True)
    def test_get_sources_invalid_parameter(self, _):
        """Test providers with invalid parameter for filter"""
        url = "%s?invalid=parameter" % reverse("sources")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    @patch("koku.middleware.MASU", return_value=True)
    def test_provider_by_source(self, _):
        """Test get provider for account id"""
        provider = Provider.objects.first()
        account_id = provider.customer.account_id
        url = reverse("get_sources_by_account_id", kwargs={"account_id": account_id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    @patch("koku.middleware.MASU", return_value=True)
    def test_sources_by_invalid_account_id_returns_null(self, _):
        """Test get provider invalid account id"""
        account_id = 20012707
        url = reverse("get_sources_by_account_id", kwargs={"account_id": account_id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
