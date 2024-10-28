#
# Copyright 2024 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
from unittest.mock import Mock
from unittest.mock import patch

from django.test import TestCase
from django.test.utils import override_settings
from django.urls import reverse
from rest_framework import status

from api.models import Provider


@override_settings(ROOT_URLCONF="masu.urls")
class RecheckInfraMapViewTest(TestCase):
    def setUp(self):
        super().setUp()
        self.url = reverse("recheck_infra_map")

    @patch("koku.middleware.MASU", return_value=True)
    def test_missing_parameters(self, _):
        """Test response when parameters are missing."""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Parameter missing", response.data["Error"])

    @patch("koku.middleware.MASU", return_value=True)
    @patch("api.models.Provider.objects.get")
    def test_provider_does_not_exist(self, mock_get, _):
        """Test response when provider does not exist."""
        mock_get.side_effect = Provider.DoesNotExist
        response = self.client.get(
            self.url, {"provider_uuid": "nonexistent-uuid", "start_date": "2023-01-01", "end_date": "2023-01-02"}
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("does not exist", response.data["Error"])

    @patch("koku.middleware.MASU", return_value=True)
    @patch("api.models.Provider.objects.get")
    @patch("masu.processor.ocp.ocp_cloud_updater_base.OCPCloudUpdaterBase._generate_ocp_infra_map_from_sql_trino")
    def test_successful_infra_map_generation(self, mock_generate_map, mock_get, _):
        """Test successful infra map generation."""
        # Mock the Provider object
        provider_mock = Mock()
        provider_mock.account = {"schema_name": "test_schema"}
        mock_get.return_value = provider_mock
        # Mock the infra map generation
        mock_generate_map.return_value = {"node1": "clusterA"}

        response = self.client.get(
            self.url, {"provider_uuid": "test-uuid", "start_date": "2023-01-01", "end_date": "2023-01-02"}
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["Infrastructure map"], str(mock_generate_map.return_value))
