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
    """Test Get all manifests"""

    def setUp(self):
        super().setUp()
        self.client = APIClient()

    @patch("koku.middleware.MASU", return_value=True)
    def test_get_all_manifests(self, _):
        response = self.client.get(reverse("all_manifests"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    @patch("koku.middleware.MASU", return_value=True)
    def test_get_all_manifests_invalid(self, _):
        """Test Manifests with invalid parameters"""
        url = "%s?invalid=parameter" % reverse("all_manifests")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @patch("koku.middleware.MASU", return_value=True)
    def test_filter_manifest(self, _):
        """Test that we can filter Manifests by provider name."""
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
        """Test get all manifests for provider source uuid."""
        manifest = CostUsageReportManifest.objects.first()
        provider_uuid = manifest.provider_id
        url = reverse("sources_manifests", kwargs={"source_uuid": provider_uuid})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    @patch("koku.middleware.MASU", return_value=True)
    def test_single_manifests(self, _):
        """Test that we can get a single manifest."""
        manifest = CostUsageReportManifest.objects.first()
        provider_uuid = manifest.provider_id
        manifest_id = manifest.id
        url = reverse("manifest", kwargs=dict(source_uuid=provider_uuid, manifest_id=manifest_id))
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    @patch("koku.middleware.MASU", return_value=True)
    def test_manifests_files(self, _):
        """Test that we can get files for one manifest."""
        manifest = CostUsageReportManifest.objects.first()
        provider_uuid = manifest.provider_id
        manifest_id = manifest.id
        url = reverse("manifest_files", kwargs=dict(source_uuid=provider_uuid, manifest_id=manifest_id))
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    @patch("koku.middleware.MASU", return_value=True)
    def test_single_manifest_file(self, _):
        """Test that we can get a specific file."""
        manifest = CostUsageReportManifest.objects.first()
        provider_uuid = manifest.provider_id
        manifest_id = manifest.id
        report = CostUsageReportStatus.objects.get(manifest=manifest_id)
        file_id = report.id
        url = reverse(
            "get_one_manifest_file", kwargs=dict(source_uuid=provider_uuid, manifest_id=manifest_id, id=file_id)
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
