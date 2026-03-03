#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Shared base test case for third-party Kubernetes provider implementations."""
from django.test import TestCase
from rest_framework.serializers import ValidationError


class ThirdPartyKubernetesProviderTestBase(TestCase):
    """Base test case for EKSProvider, AKSProvider, and GKEProvider.

    Subclasses must define:
        provider_class   -- the provider class under test
        provider_name    -- the expected Provider.PROVIDER_* constant
        infra_provider   -- the expected Provider.PROVIDER_* backing cloud constant
        cluster_prefix   -- short prefix used to build cluster id fixtures (e.g. "eks")
    """

    provider_class = None
    provider_name = None
    infra_provider = None
    cluster_prefix = None

    def _make_provider(self):
        return self.provider_class()

    def test_get_name(self):
        """Get name of provider."""
        self.assertEqual(self._make_provider().name(), self.provider_name)

    def test_cost_usage_source_is_reachable_bucket_provided(self):
        """Verify that a ValidationError is raised when a bucket/data source is provided."""
        credentials = {"cluster_id": f"my-{self.cluster_prefix}-cluster-1"}
        provider_interface = self._make_provider()
        with self.assertRaises(ValidationError):
            provider_interface.cost_usage_source_is_reachable(credentials, "report_location")

    def test_cost_usage_source_no_cluster_id(self):
        """Verify that the cost usage source raises error with no cluster_id."""
        credentials = {"cluster_id": None}
        provider_interface = self._make_provider()
        with self.assertRaises(ValidationError):
            provider_interface.cost_usage_source_is_reachable(credentials, None)

    def test_cost_usage_source_is_reachable_no_bucket_provided(self):
        """Verify that the cost usage source is reachable with a valid cluster_id and no bucket provided."""
        credentials = {"cluster_id": f"my-{self.cluster_prefix}-cluster-1"}
        provider_interface = self._make_provider()
        try:
            provider_interface.cost_usage_source_is_reachable(credentials, None)
        except Exception:
            self.fail("Unexpected error ")

    def test_infra_type_implementation(self):
        """Verify that infra_type_implementation returns the correct backing cloud."""
        self.assertEqual(self._make_provider().infra_type_implementation(None, None), self.infra_provider)

    def test_infra_key_list_implementation_returns_empty(self):
        """Verify that infra_key_list_implementation returns an empty list."""
        self.assertEqual(self._make_provider().infra_key_list_implementation(self.infra_provider, None), [])
