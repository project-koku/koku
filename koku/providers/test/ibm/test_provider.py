#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test IBM Provider."""
from unittest.mock import MagicMock
from unittest.mock import patch

from django.test import TestCase
from faker import Faker
from ibm_cloud_sdk_core.api_exception import ApiException
from rest_framework.serializers import ValidationError

from api.models import Provider
from providers.ibm.provider import IBMProvider


FAKE = Faker()


class IBMProviderTestCase(TestCase):
    """Test cases for IBM Provider."""

    def test_name(self):
        """Test name property."""
        provider = IBMProvider()
        self.assertEqual(provider.name(), Provider.PROVIDER_IBM)

    @patch("providers.ibm.provider.EnterpriseUsageReportsV1")
    def test_cost_usage_source_is_reachable_success(self, usage_reports):
        """Test that cost_usage_source_is_reachable succeeds."""
        service = MagicMock()
        usage_reports.return_value = service

        provider = IBMProvider()
        creds = {"iam_token": FAKE.word()}
        billing = {"enterprise_id": FAKE.word()}

        self.assertTrue(provider.cost_usage_source_is_reachable(creds, billing))
        service.get_resource_usage_report.assert_called_with(
            enterprise_id=billing.get("enterprise_id"), children=True, limit=1
        )

    @patch("providers.ibm.provider.EnterpriseUsageReportsV1")
    def test_cost_usage_source_is_reachable_bad_iam_token(self, usage_reports):
        """Test that cost_usage_source_is_reachable raises ValidationError on invalid IAM token."""
        service = MagicMock()
        service.get_resource_usage_report.side_effect = ApiException(code=400, message="API key is wrong")
        usage_reports.return_value = service

        provider = IBMProvider()
        creds = {"iam_token": FAKE.word()}
        billing = {"enterprise_id": FAKE.word()}

        with self.assertRaises(ValidationError) as ve:
            provider.cost_usage_source_is_reachable(creds, billing)
        self.assertIsNotNone(ve.exception.get_full_details().get("credentials.iam_token", None))

    @patch("providers.ibm.provider.EnterpriseUsageReportsV1")
    def test_cost_usage_source_is_reachable_bad_enterprise_id(self, usage_reports):
        """Test that cost_usage_source_is_reachable raises ValidationError on invalid enterprise ID."""
        service = MagicMock()
        service.get_resource_usage_report.side_effect = ApiException(code=400, message="enterprise id is invalid")
        usage_reports.return_value = service

        provider = IBMProvider()
        creds = {"iam_token": FAKE.word()}
        billing = {"enterprise_id": FAKE.word()}

        with self.assertRaises(ValidationError) as ve:
            provider.cost_usage_source_is_reachable(creds, billing)
        self.assertIsNotNone(ve.exception.get_full_details().get("data_source.enterprise_id", None))
