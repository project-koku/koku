#
# Copyright 2022 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tests the OCIProvider implementation for the Koku interface."""
from unittest.mock import Mock
from unittest.mock import patch

from django.test import TestCase
from django.utils.translation import ugettext as _
from faker import Faker
from rest_framework.exceptions import ValidationError

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
    @patch(
        "providers.oci.provider._check_cost_report_access",
        return_value=(
            {
                "user": FAKE.md5(),
                "key_file": FAKE.md5(),
                "fingerprint": FAKE.md5(),
                "tenancy": FAKE.md5(),
                "region": FAKE.md5(),
            },
            FAKE.md5(),
        ),
    )
    def test_check_cost_report_access(self, mock_oci_client, check_cost_report_access):
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
            check_cost_report_access(FAKE.md5())
        except Exception as exc:
            self.fail(exc)

    @patch(
        "providers.oci.provider._check_cost_report_access",
        return_value=(
            {
                "user": FAKE.md5(),
                "key_file": FAKE.md5(),
                "fingerprint": FAKE.md5(),
                "tenancy": FAKE.md5(),
                "region": FAKE.md5(),
            },
            FAKE.md5(),
        ),
    )
    def test_cost_usage_source_is_reachable(self, check_cost_report_access):
        """Verify that the cost usage source is authenticated and created."""
        provider_interface = OCIProvider()
        credentials = "not-required"
        data_source = {"bucket": "my-bucket", "bucket_namespace": "my-namespace", "region": "my-region"}
        try:
            provider_interface.cost_usage_source_is_reachable(credentials, data_source)
        except Exception:
            self.fail("Unexpected Error")

    def test_cost_usage_source_is_reachable_no_bucket(self):
        """Verify that the cost usage source errors correctly with no bucket."""
        provider_interface = OCIProvider()
        credentials = "not-required"
        data_source = {"bucket": None, "bucket_namespace": "my-namespace", "region": "my-region"}
        with self.assertRaises(ValidationError):
            provider_interface.cost_usage_source_is_reachable(credentials, data_source)

    def test_cost_usage_source_is_reachable_no_bucket_namespace(self, check_cost_report_access):
        """Verify that the cost usage source errors correctly with no bucket namespace."""
        provider_interface = OCIProvider()
        credentials = "not-required"
        data_source = {"bucket": "my-bueckt", "bucket_namespace": None, "region": "my-region"}
        with self.assertRaises(ValidationError):
            provider_interface.cost_usage_source_is_reachable(credentials, data_source)

    def test_cost_usage_source_is_reachable_no_bucket_region(self, check_cost_report_access):
        """Verify that the cost usage source errors correctly with no bucket region."""
        provider_interface = OCIProvider()
        credentials = "not-required"
        data_source = {"bucket": "my-bueckt", "bucket_namespace": "my-namespace", "region": None}
        with self.assertRaises(ValidationError):
            provider_interface.cost_usage_source_is_reachable(credentials, data_source)
