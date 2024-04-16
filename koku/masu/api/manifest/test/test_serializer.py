#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tests the Masu API `manifest` Serializers."""
import datetime
from uuid import uuid4

from django_tenants.utils import tenant_context
from rest_framework import serializers

from api.iam.test.iam_test_case import IamTestCase
from api.provider.models import Provider
from masu.api.manifest.serializers import ManifestSerializer
from masu.api.manifest.serializers import UsageReportStatusSerializer
from reporting_common.models import CostUsageReportManifest
from reporting_common.models import CostUsageReportStatus
from reporting_common.models import Status
from reporting_common.states import ManifestState
from reporting_common.states import ManifestStep


class ManifestSerializerTest(IamTestCase):
    """Manifest serializer tests."""

    def setUp(self):
        """Set up the tests."""
        super().setUp()
        self.manifest = CostUsageReportManifest.objects.first()
        self.serializer = ManifestSerializer(self.manifest)
        self.basic_model = {
            "id": 1,
            "assembly_id": "Test assembly id",
            "creation_datetime": datetime.datetime.now(),
            "completed_datetime": datetime.datetime.now(),
            "export_datetime": datetime.datetime.now(),
            "billing_period_start_datetime": datetime.datetime.now(),
            "provider_id": Provider.objects.first().uuid,
            "s3_csv_cleared": True,
            "s3_parquet_cleared": True,
            "operator_version": "1.0",
            "state": {ManifestStep.SUMMARY.value: {ManifestState.START.value: datetime.datetime.now().isoformat()}},
        }

    def test_manifest_contains_expected_fields(self):
        """Tests ManifestSerializer is utilizing expected fields."""
        data = self.serializer.data
        self.assertEqual(
            set(data.keys()),
            {
                "id",
                "assembly_id",
                "creation_datetime",
                "completed_datetime",
                "export_datetime",
                "billing_period_start_datetime",
                "provider_id",
                "s3_csv_cleared",
                "s3_parquet_cleared",
                "operator_version",
                "state",
            },
        )

    def test_valid_data(self):
        """Tests ManifestSerializer with all valid data."""
        with tenant_context(self.tenant):
            serializer = ManifestSerializer(data=self.basic_model)
            self.assertTrue(serializer.is_valid(raise_exception=True))

    def test_invalid_string_data(self):
        """Tests ManifestSerializer invalid string."""
        self.basic_model["assembly_id"] = 1
        serializer = ManifestSerializer(data=self.basic_model)
        self.assertRaises(TypeError, serializer.is_valid(raise_exception=True))

    def test_invalid_date_data(self):
        """Tests ManifestSerializer invalid date."""
        self.basic_model["creation_datetime"] = "invalid date"
        with tenant_context(self.tenant):
            serializer = ManifestSerializer(data=self.basic_model)
            with self.assertRaises(serializers.ValidationError):
                if serializer.is_valid(raise_exception=True):
                    serializer.save()

    def test_invalid_boolean_data(self):
        """Tests ManifestSerializer invalid boolean."""
        self.basic_model["s3_csv_cleared"] = 6
        with tenant_context(self.tenant):
            serializer = ManifestSerializer(data=self.basic_model)
            with self.assertRaises(serializers.ValidationError):
                if serializer.is_valid(raise_exception=True):
                    serializer.save()


class UsageReportStatusSerializerTest(IamTestCase):
    """UsageReportStatusSerializer Test."""

    def setUp(self):
        """Set up the tests."""
        super().setUp()
        self.cost_report = CostUsageReportStatus.objects.first()
        self.serializer = UsageReportStatusSerializer(self.cost_report)
        self.basic_model = {
            "id": 1,
            "manifest": CostUsageReportManifest.objects.first().id,
            "report_name": "test_report_name",
            "completed_datetime": datetime.datetime.now(),
            "started_datetime": datetime.datetime.now(),
            "etag": "test_etag",
            "status": Status.DONE.value,
            "celery_task_id": str(uuid4()),
            "failed_status": None,
        }

    def test_manifest_contains_expected_fields(self):
        """Tests UsageReportStatusSerializer is utilizing expected fields."""
        data = self.serializer.data
        self.assertEqual(
            set(data.keys()),
            {
                "id",
                "manifest",
                "report_name",
                "completed_datetime",
                "started_datetime",
                "etag",
                "status",
                "celery_task_id",
                "failed_status",
            },
        )

    def test_valid_data(self):
        """Tests UsageReportStatusSerializer valid data."""
        serializer = UsageReportStatusSerializer(data=self.basic_model)
        self.assertTrue(serializer.is_valid(raise_exception=True))

    def test_invalid_string_data(self):
        """Tests UsageReportStatusSerializer invalid string."""
        self.basic_model["report_name"] = 1
        serializer = UsageReportStatusSerializer(data=self.basic_model)
        self.assertRaises(TypeError, serializer.is_valid(raise_exception=True))

    def test_invalid_date_data(self):
        """Tests UsageReportStatusSerializer invalid date."""
        self.basic_model["completed_datetime"] = "invalid date"
        with tenant_context(self.tenant):
            serializer = UsageReportStatusSerializer(data=self.basic_model)
            with self.assertRaises(serializers.ValidationError):
                if serializer.is_valid(raise_exception=True):
                    serializer.save()
