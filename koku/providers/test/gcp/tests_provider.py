"""Test GCP Provider."""
from unittest.mock import MagicMock
from unittest.mock import patch

from django.test import TestCase
from faker import Faker
from google.cloud.exceptions import GoogleCloudError
from rest_framework.serializers import ValidationError

from api.models import Provider
from providers.gcp.provider import GCPProvider
from providers.gcp.provider import REQUIRED_IAM_PERMISSIONS

FAKE = Faker()


class GCPProviderTestCase(TestCase):
    """Test cases for GCP Provider."""

    def test_name(self):
        """Test name property."""
        provider = GCPProvider()
        self.assertEqual(provider.name(), Provider.PROVIDER_GCP)

    @patch("providers.gcp.provider.discovery")
    @patch("providers.gcp.provider.google.auth.default")
    @patch("providers.gcp.provider.storage")
    def test_cost_usage_source_is_reachable_valid(self, mock_storage, mock_auth, mock_discovery):
        """Test that cost_usage_source_is_reachable succeeds."""
        gcp_creds = MagicMock()
        mock_auth.return_value = (gcp_creds, MagicMock())
        mock_discovery.build.return_value.projects.return_value.testIamPermissions.return_value.execute.return_value.get.return_value = (  # noqa: E501
            REQUIRED_IAM_PERMISSIONS
        )
        billing_source_param = {"dataset": FAKE.word(), "table_id": FAKE.word()}
        credentials_param = {"project_id": FAKE.word()}
        provider = GCPProvider()
        self.assertTrue(provider.cost_usage_source_is_reachable(credentials_param, billing_source_param))
        mock_discovery.build.assert_called_once_with(
            "cloudresourcemanager", "v1", credentials=gcp_creds, cache_discovery=False
        )
        mock_discovery.build.return_value.projects.assert_called_once()
        mock_discovery.build.return_value.projects.return_value.testIamPermissions.assert_called_once()

    @patch("providers.gcp.provider.discovery")
    @patch("providers.gcp.provider.google.auth.default")
    @patch("providers.gcp.provider.storage")
    def test_cost_usage_source_missing_required_permission(self, mock_storage, mock_auth, mock_discovery):
        """Test that cost_usage_source_is_reachable succeeds."""
        missing_permissions = [REQUIRED_IAM_PERMISSIONS[0]]
        mock_auth.return_value = (MagicMock(), MagicMock())
        mock_discovery.build.return_value.projects.return_value.testIamPermissions.return_value.execute.return_value.get.return_value = (  # noqa: E501
            missing_permissions
        )
        billing_source_param = {"dataset": FAKE.word(), "table_id": FAKE.word()}
        credentials_param = {"project_id": FAKE.word()}
        with self.assertRaises(ValidationError):
            provider = GCPProvider()
            provider.cost_usage_source_is_reachable(credentials_param, billing_source_param)

    @patch("providers.gcp.provider.discovery")
    @patch("providers.gcp.provider.google.auth.default")
    @patch("providers.gcp.provider.storage")
    def test_cost_usage_source_raise_google_cloud_error(self, mock_storage, mock_auth, mock_discovery):
        """Test that cost_usage_source_is_reachable succeeds."""
        err_msg = "GCP Error"
        mock_discovery.build.side_effect = GoogleCloudError(err_msg)
        mock_auth.return_value = (MagicMock(), MagicMock())
        billing_source_param = {"dataset": FAKE.word(), "table_id": FAKE.word()}
        credentials_param = {"project_id": FAKE.word()}
        with self.assertRaisesRegexp(ValidationError, err_msg):
            provider = GCPProvider()
            provider.cost_usage_source_is_reachable(credentials_param, billing_source_param)
