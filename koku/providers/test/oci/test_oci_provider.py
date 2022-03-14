#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tests the OCIProvider implementation for the Koku interface."""
from unittest.mock import Mock
from unittest.mock import patch

from django.test import TestCase
from django.utils.translation import ugettext as _
from faker import Faker
from oci.exceptions import ServiceError
from rest_framework.exceptions import ValidationError

from providers.oci.provider import _check_cost_report_access
from providers.oci.provider import error_obj
from providers.oci.provider import OCIProvider

FAKE = Faker()


class OCIProviderTestCase(TestCase):
    """Parent Class for OCIProvider test cases."""

    def test_get_name(self):
        """Get name of provider."""
        provider = OCIProvider()
        self.assertEqual(provider.name(), "OCI")

    def test_error_obj(self):
        """Test the error_obj method."""
        test_key = "tkey"
        test_message = "tmessage"
        expected = {test_key: [_(test_message)]}
        error = error_obj(test_key, test_message)
        self.assertEqual(error, expected)

    @patch("providers.oci.provider.oci")
    def test_check_cost_report_access(self, mock_oci_client):
        """Test_check_cost_report_access success."""
        oci_client = Mock()
        oci_client.data.objects = {
            "archival_state": None,
            "etag": None,
            "md5": None,
            "name": "reports/cost-csv/0001000000539138.csv.gz",
            "size": None,
            "storage_tier": None,
            "time_created": None,
            "time_modified": None,
        }
        mock_oci_client.return_value = oci_client
        try:
            _check_cost_report_access(FAKE.md5())
        except Exception as exc:
            self.fail(exc)

    @patch("providers.oci.provider._check_cost_report_access", return_value=True)
    def test_cost_usage_source_is_reachable(self, check_cost_report_access):
        """Verify that the cost usage source is authenticated and created."""
        provider_interface = OCIProvider()
        try:
            credentials = {"tenant": "ocid1.tenancy.oc1..my_tenant"}
            data_source = None
            provider_interface.cost_usage_source_is_reachable(credentials, data_source)
        except Exception:
            self.fail("Unexpected Error")

    def test_cost_usage_source_is_reachable_no_tenant(self):
        """Verify that the cost usage source errors correctly with no tenant."""
        provider_interface = OCIProvider()
        with self.assertRaises(ValidationError):
            credentials = {"tenant": None}
            data_source = None
            provider_interface.cost_usage_source_is_reachable(credentials, data_source)

    def test_cost_usage_source_is_reachable_no_bucket_access(self):
        """Verify that the cost usage source bukcet is not accessible."""
        provider_interface = OCIProvider()
        with self.assertRaises(ServiceError):
            credentials = {"tenant": "fake"}
            data_source = None
            provider_interface.cost_usage_source_is_reachable(credentials, data_source)
