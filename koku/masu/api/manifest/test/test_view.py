#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tests the Masu API `manifest` Views."""
from unittest.mock import patch

from django.test.utils import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from api.iam.test.iam_test_case import IamTestCase
from api.provider.models import Provider
from reporting_common.models import CostUsageReportManifest
from reporting_common.models import CostUsageReportStatus


@override_settings(ROOT_URLCONF="masu.urls")
class ManifestViewTests(IamTestCase):
    """Tests manifests views"""

    def setUp(self):
        """Set up the tests."""
        super().setUp()
        self.client = APIClient()

    @patch("koku.middleware.MASU", return_value=True)
    def test_get_all_manifests(self, _):
        """Test Get all manifests"""
        response = self.client.get(reverse("all_manifests"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    @patch("koku.middleware.MASU", return_value=True)
    def test_get_all_manifests_invalid_parameter(self, _):
        """Test Manifests with invalid parameter for filter"""
        url = "%s?invalid=parameter" % reverse("all_manifests")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @patch("koku.middleware.MASU", return_value=True)
    def test_get_all_manifests_invalid_provider(self, _):
        """Test manifests invalid provider_name filter."""
        url = "%s?name=invalid_provider_name" % reverse("all_manifests")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    @patch("koku.middleware.MASU", return_value=True)
    def test_filter_manifest(self, _):
        """Tests manifests filter valid data."""
        provider = Provider.objects.first()
        name = provider.name
        url = reverse("all_manifests")
        qp = "?name=" + name
        response = self.client.get(url + qp)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        json_result = response.json()
        results = json_result.get("data")
        self.assertNotEqual(len(results), 0)

    @patch("koku.middleware.MASU", return_value=True)
    def test_manifests_by_source(self, _):
        """Test get manifests for provider source uuid."""
        manifest = CostUsageReportManifest.objects.first()
        provider_uuid = manifest.provider_id
        url = reverse("sources_manifests", kwargs={"source_uuid": provider_uuid})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    @patch("koku.middleware.MASU", return_value=True)
    def test_manifests_by_invalid_source(self, _):
        """Test get manifests invalid provider source uuid."""
        provider_uuid = "invalid provider uuid"
        url = reverse("sources_manifests", kwargs={"source_uuid": provider_uuid})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    @patch("koku.middleware.MASU", return_value=True)
    def test_single_manifests(self, _):
        """Test get a single manifest."""
        manifest = CostUsageReportManifest.objects.first()
        provider_uuid = manifest.provider_id
        manifest_id = manifest.id
        url = reverse("manifest", kwargs=dict(source_uuid=provider_uuid, manifest_id=manifest_id))
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    @patch("koku.middleware.MASU", return_value=True)
    def test_single_manifests_invalid_source(self, _):
        """Test get single manifest invalid provider."""
        manifest = CostUsageReportManifest.objects.first()
        provider_uuid = "invalid_provider_source_uuid"
        manifest_id = manifest.id
        url = reverse("manifest", kwargs=dict(source_uuid=provider_uuid, manifest_id=manifest_id))
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    @patch("koku.middleware.MASU", return_value=True)
    def test_single_manifests_invalid_manifest(self, _):
        """Test get single manifest invalid manifest id."""
        manifest = CostUsageReportManifest.objects.first()
        provider_uuid = manifest.provider_id
        manifest_id = 300000000
        url = reverse("manifest", kwargs=dict(source_uuid=provider_uuid, manifest_id=manifest_id))
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    @patch("koku.middleware.MASU", return_value=True)
    def test_manifests_files(self, _):
        """Test get files for one manifest."""
        manifest = CostUsageReportManifest.objects.first()
        provider_uuid = manifest.provider_id
        manifest_id = manifest.id
        url = reverse("manifest_files", kwargs=dict(source_uuid=provider_uuid, manifest_id=manifest_id))
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    @patch("koku.middleware.MASU", return_value=True)
    def test_manifests_files_invalid_manifest(self, _):
        """Test get files for one manifest invalid manifest."""
        manifest = CostUsageReportManifest.objects.first()
        provider_uuid = manifest.provider_id
        manifest_id = 30000000
        url = reverse("manifest_files", kwargs=dict(source_uuid=provider_uuid, manifest_id=manifest_id))
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    @patch("koku.middleware.MASU", return_value=True)
    def test_single_manifest_file(self, _):
        """Test get a specific file for manifest."""
        manifest = CostUsageReportManifest.objects.first()
        provider_uuid = manifest.provider_id
        manifest_id = manifest.id
        report = CostUsageReportStatus.objects.filter(manifest=manifest_id).first()
        file_id = report.id
        url = reverse(
            "get_one_manifest_file", kwargs=dict(source_uuid=provider_uuid, manifest_id=manifest_id, id=file_id)
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    @patch("koku.middleware.MASU", return_value=True)
    def test_single_manifest_file_invalid(self, _):
        """Test get a specific file invalid manifest id."""
        manifest = CostUsageReportManifest.objects.first()
        provider_uuid = manifest.provider_id
        manifest_id = manifest.id
        file_id = 3000000000
        url = reverse(
            "get_one_manifest_file", kwargs=dict(source_uuid=provider_uuid, manifest_id=manifest_id, id=file_id)
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
