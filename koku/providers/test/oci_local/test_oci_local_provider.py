#
# Copyright 2022 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tests the OCILocalProvider implementation for the Koku interface."""
import os
import tempfile

from django.test import TestCase
from rest_framework.exceptions import ValidationError

from api.models import Provider
from providers.oci_local.provider import OCILocalProvider


class OCILocalProviderTestCase(TestCase):
    """Parent Class for OCILocalProvider test cases."""

    def setUp(self):
        """Create test case objects."""
        super().setUp()
        self.cur_source = tempfile.mkdtemp()

    def tearDown(self):
        """Tear down test case objects."""
        os.rmdir(self.cur_source)
        super().tearDown()

    def test_get_name(self):
        """Get name of provider."""
        provider = OCILocalProvider()
        self.assertEqual(provider.name(), Provider.PROVIDER_OCI_LOCAL)

    def test_cost_usage_tenant_is_reachable(self):
        """Verify that the cost usage source is authenticated and created."""
        data_source = {"bucket": "my-bucket", "bucket_namespace": "my-namespace", "bucket_region": "my-region"}
        credentials = "not-required"
        provider_interface = OCILocalProvider()
        try:
            provider_interface.cost_usage_source_is_reachable(credentials, data_source)
        except Exception as error:
            self.fail(f"Unexpected Error: {str(error)}")

    def test_cost_usage_tenant_not_reachable(self):
        """Verify that the cost usage source is not authenticated and created when tenant/bucket is not provided."""
        data_source = {"bucket": None, "bucket_namespace": None, "bucket_region": None}
        credentials = "not-required"
        provider_interface = OCILocalProvider()
        with self.assertRaises(ValidationError):
            provider_interface.cost_usage_source_is_reachable(credentials, data_source)
