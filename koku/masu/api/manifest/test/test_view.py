#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tests the Masu API `manifest` Views."""
from datetime import date
from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

from django.test.utils import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from api.iam.test.iam_test_case import IamTestCase
from reporting_common.models import CostUsageReportManifest
from reporting_common.models import CostUsageReportStatus
from reporting_common.models import Status
from reporting_common.states import CombinedChoices


@override_settings(ROOT_URLCONF="masu.urls")
class ManifestViewTests(IamTestCase):
    """Tests manifests views"""

    def setUp(self):
        """Set up the tests."""
        super().setUp()
        manifests = CostUsageReportManifest.objects.all()
        self.manifest = CostUsageReportManifest.objects.first()
        self.manifest_count = manifests.count()
        reports = CostUsageReportStatus.objects.all()
        self.report_status_count = reports.filter(manifest_id=self.manifest.id).count()
        self.failed_processing_count = reports.filter(
            manifest_id=self.manifest.id, failed_status=CombinedChoices.PROCESSING
        ).count()
        self.done_report_count = reports.filter(manifest_id=self.manifest.id, status=Status.DONE).count()
        self.client = APIClient()

    @patch("koku.middleware.MASU", return_value=True)
    def test_get_all_manifests(self, _):
        """Test Get all manifests"""
        response = self.client.get(
            reverse("manifests-list"), content_type="application/json", **self.request_context["request"].META
        )
        body = response.json()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(body.get("meta").get("count"), self.manifest_count)

    def test_get_one_manifests(self):
        """Test Get a single manifest"""
        response = self.client.get(
            reverse("manifests-detail", kwargs={"pk": self.manifest.id}),
            content_type="application/json",
            **self.request_context["request"].META,
        )
        body = response.json()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(body.get("manifest"))

    def test_get_one_manifests_reports(self):
        """Test getting a single manifests reports returns reports."""
        response = self.client.get(
            reverse("manifests-reports", kwargs={"pk": self.manifest.id}),
            content_type="application/json",
            **self.request_context["request"].META,
        )
        body = response.json()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(body.get("meta").get("count") > 0)

    def test_get_manifests_filters(self):
        """Test the filters on the manifests endpoint."""
        url = reverse("manifests-list")
        filters = {
            "provider": self.manifest.provider.uuid,
            "account_id": "10002",
            "org_id": "222222",
            "schema_name": "org222222",
            "created_after": (date.today() + timedelta(days=5)).isoformat(),
        }
        for key, value in filters.items():
            with self.subTest(filter=key):
                filter_url = url + f"?{key}={value}"
                response = self.client.get(
                    filter_url, content_type="application/json", **self.request_context["request"].META
                )
                body = response.json()
                self.assertEqual(response.status_code, 200)
                self.assertLess(body.get("meta").get("count"), self.manifest_count)

    def test_get_manifests_boolean_filters(self):
        """Test the filters on the manifests endpoint."""
        url = reverse("manifests-list")
        filter_keys = ["failed", "running", "started"]
        values = [True, False]
        for key in filter_keys:
            for value in values:
                with self.subTest(filter=key, value=value):
                    filter_url = url + f"?{key}={value}"
                    response = self.client.get(
                        filter_url, content_type="application/json", **self.request_context["request"].META
                    )
                    body = response.json()
                    self.assertEqual(response.status_code, 200)
                    count = body.get("meta").get("count")
                    if key == "started" and not value:
                        self.assertEqual(count, self.manifest_count)
                    else:
                        self.assertLess(count, self.manifest_count)

    def test_get_status_reports_filters(self):
        """Test the filters on the manifest report status endpoint."""
        url = reverse("manifests-reports", kwargs={"pk": self.manifest.id})
        filters = [
            ("status", Status.DONE.value, self.done_report_count),
            ("celery_task_id", str(uuid4()), 0),
            ("failed_status", CombinedChoices.PROCESSING.value, self.failed_processing_count),
        ]
        for key, value, expected_count in filters:
            with self.subTest(filter=key):
                filter_url = url + f"?{key}={value}"
                response = self.client.get(
                    filter_url, content_type="application/json", **self.request_context["request"].META
                )
                body = response.json()
                self.assertEqual(response.status_code, 200)
                self.assertEqual(body.get("meta").get("count"), expected_count)
