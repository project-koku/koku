#
# Copyright 2022 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tests the OCIProvider implementation for the Koku interface."""
from unittest.mock import patch

from django.test import TestCase
from django.utils.translation import gettext
from faker import Faker
from oci._vendor.urllib3.exceptions import LocationParseError
from oci.exceptions import ClientError
from oci.exceptions import RequestException
from oci.exceptions import ServiceError
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
        expected = {test_key: [gettext(test_message)]}
        error = error_obj(test_key, test_message)
        self.assertEqual(error, expected)

    @patch("providers.oci.provider.storage_client.ObjectStorageClient")
    def test_check_cost_report_access(self, mock_storage_client):
        """Test_check_cost_report_access success."""
        mock_storage_client.list_objects = {}
        provider_interface = OCIProvider()
        data_source = {"bucket": "bucket", "bucket_namespace": "namespace", "bucket_region": "region"}
        provider_interface.cost_usage_source_is_reachable(FAKE.md5(), data_source)
        mock_storage_client.assert_called()

    @patch("providers.oci.provider.storage_client.ObjectStorageClient")
    def test_check_cost_report_access_parse_error(self, mock_storage_client):
        """Test_check_cost_report_access error."""
        exception_table = [
            LocationParseError("test location parse exception"),
            ServiceError(
                code="code", headers={"opc-request-id": "1"}, message="OCI authentication error", status="400"
            ),
            ClientError("test client error"),
            RequestException("test request exception"),
        ]
        for test in exception_table:
            with self.subTest(test=test):
                mock_storage_client.return_value.list_objects.side_effect = test
                provider_interface = OCIProvider()
                data_source = {
                    "bucket": "bucket stupid",
                    "bucket_namespace": "namespace stupid",
                    "bucket_region": "region stupid",
                }
                with self.assertRaises(ValidationError):
                    provider_interface.cost_usage_source_is_reachable(FAKE.md5(), data_source)

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
        data_source = {"bucket": "my-bucket", "bucket_namespace": "my-namespace", "bucket_region": "my-region"}
        try:
            provider_interface.cost_usage_source_is_reachable(credentials, data_source)
            check_cost_report_access.assert_called()
        except Exception:
            self.fail("Unexpected Error")

    def test_cost_usage_source_is_reachable_no_bucket(self):
        """Verify that the cost usage source errors correctly with no bucket."""
        provider_interface = OCIProvider()
        credentials = "not-required"
        data_source = {"bucket": None, "bucket_namespace": "my-namespace", "bucket_region": "my-region"}
        with self.assertRaises(ValidationError):
            provider_interface.cost_usage_source_is_reachable(credentials, data_source)

    def test_cost_usage_source_is_reachable_no_bucket_namespace(self):
        """Verify that the cost usage source errors correctly with no bucket namespace."""
        provider_interface = OCIProvider()
        credentials = "not-required"
        data_source = {"bucket": "my-bucket", "bucket_namespace": None, "bucket_region": "my-region"}
        with self.assertRaises(ValidationError):
            provider_interface.cost_usage_source_is_reachable(credentials, data_source)

    def test_cost_usage_source_is_reachable_no_bucket_region(self):
        """Verify that the cost usage source errors correctly with no bucket region."""
        provider_interface = OCIProvider()
        credentials = "not-required"
        data_source = {"bucket": "my-buckett", "bucket_namespace": "my-namespace", "bucket_region": None}
        with self.assertRaises(ValidationError):
            provider_interface.cost_usage_source_is_reachable(credentials, data_source)
