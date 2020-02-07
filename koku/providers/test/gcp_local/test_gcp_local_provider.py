"""Tests the GCPLocalProvider."""
from django.test import TestCase
from rest_framework.exceptions import ValidationError

from api.models import Provider
from providers.gcp_local.provider import GCPLocalProvider


class GCPLocalProviderTestCase(TestCase):
    """Parent Class for GCPLocalProvider test cases."""

    def test_get_name(self):
        """Get name of provider."""
        provider = GCPLocalProvider()
        self.assertEqual(provider.name(), Provider.PROVIDER_GCP_LOCAL)

    def test_cost_usage_source_is_reachable(self):
        """Verify that the file where local gcp ifles are stored is reachable."""
        authentication = {}
        bucket_name = "/tmp/path/to/bucket"

        provider = GCPLocalProvider()

        self.assertTrue(provider.cost_usage_source_is_reachable(authentication, bucket_name))

    def test_cost_usage_source_is_reachable_no_bucket(self):
        """Verify that the cost usage source is not created when no bucket is provided."""
        authentication = {}
        bucket_name = None
        provider_interface = GCPLocalProvider()

        with self.assertRaises(ValidationError):
            provider_interface.cost_usage_source_is_reachable(authentication, bucket_name)
