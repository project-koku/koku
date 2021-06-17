#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tests the OCPProvider implementation for the Koku interface."""
from django.test import TestCase
from rest_framework.serializers import ValidationError

from api.models import Provider
from providers.ocp.provider import OCPProvider


class OCPProviderTestCase(TestCase):
    """Parent Class for OCPProvider test cases."""

    def test_get_name(self):
        """Get name of provider."""
        provider = OCPProvider()
        self.assertEqual(provider.name(), Provider.PROVIDER_OCP)

    def test_cost_usage_source_is_reachable_bucket_provided(self):
        """Verify that the cost usage source is authenticated and created."""
        credentials = {"cluster_id": "my-ocp-cluster-1"}
        report_source = "report_location"

        provider_interface = OCPProvider()

        with self.assertRaises(ValidationError):
            provider_interface.cost_usage_source_is_reachable(credentials, report_source)

    def test_cost_usage_source_no_cluster_id(self):
        """Verify that the cost usage source raises error with no cluster_id."""
        credentials = {"cluster_id": None}
        report_source = None

        provider_interface = OCPProvider()

        with self.assertRaises(ValidationError):
            provider_interface.cost_usage_source_is_reachable(credentials, report_source)

    def test_cost_usage_source_is_reachable_no_bucket_provided(self):
        """Verify that the cost usage source is not authenticated and created with no bucket provided."""
        credentials = {"cluster_id": "my-ocp-cluster-1"}
        report_source = None

        provider_interface = OCPProvider()

        try:
            provider_interface.cost_usage_source_is_reachable(credentials, report_source)
        except Exception:
            self.fail("Unexpected error ")
