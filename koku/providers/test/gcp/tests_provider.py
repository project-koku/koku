"""Test GCP Provider."""
from unittest.mock import patch

from django.test import TestCase
from faker import Faker
from google.cloud.exceptions import GoogleCloudError
from rest_framework.serializers import ValidationError

from providers.gcp.provider import GCPProvider

FAKE = Faker()


class GCPProviderTestCase(TestCase):
    """Test cases for GCP Provider."""

    def test_name(self):
        """Test name property."""
        provider = GCPProvider()
        self.assertEqual(provider.name(), 'GCP')

    @patch('providers.gcp.provider.storage')
    def test_cost_usage_source_is_reachable_valid(self, mock_storage):
        """Test that cost_usage_source_is_reachable succeeds."""
        storage_resource_name = {'bucket': FAKE.word()}
        credentials = {'project_id': FAKE.word()}

        provider = GCPProvider()
        self.assertTrue(provider.cost_usage_source_is_reachable(
            credentials, storage_resource_name)
        )

    @patch('providers.gcp.provider.storage.Client',)
    def test_no_bucket_exists_exception(self, mock_storage):
        """Test that ValidationError is raised when GoogleCloudError is raised."""
        gcp_client = mock_storage.return_value
        gcp_client.lookup_bucket.return_value = None

        credentials = {'project_id': FAKE.word()}
        storage_resource_name = {'bucket': FAKE.word()}

        with self.assertRaises(ValidationError):
            GCPProvider().cost_usage_source_is_reachable(credentials, storage_resource_name)

    @patch('providers.gcp.provider.storage.Client',)
    def test_bucket_access_exception(self, mock_storage):
        """Test that ValidationError is raised when GoogleCloudError is raised."""
        gcp_client = mock_storage.return_value
        gcp_client.lookup_bucket.side_effect = GoogleCloudError('GCP Error')
        credentials = {'project_id': FAKE.word()}
        storage_resource_name = {'bucket': FAKE.word()}
        with self.assertRaises(ValidationError):
            GCPProvider().cost_usage_source_is_reachable(credentials, storage_resource_name)
