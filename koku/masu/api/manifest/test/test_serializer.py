import datetime
from unittest import TestCase

from tenant_schemas.utils import tenant_context

from api.iam.test.iam_test_case import IamTestCase
from masu.api.manifest.serializers import ManifestSerializer
from masu.api.manifest.serializers import UsageReportStatusSerializer
from reporting_common.models import CostUsageReportManifest
from reporting_common.models import CostUsageReportStatus


class ManifestSerializerTest(IamTestCase):
    def setUp(self):
        super().setUp()
        self.manifest = CostUsageReportManifest.objects.first()
        self.serializer = ManifestSerializer(self.manifest)

    def test_manifest_contains_expected_fields(self):
        """Tests the ManifestSerializer is utilizing expected fields."""
        data = self.serializer.data
        self.assertEqual(
            set(data.keys()),
            {
                "id",
                "assembly_id",
                "manifest_creation_datetime",
                "manifest_updated_datetime",
                "manifest_completed_datetime",
                "manifest_modified_datetime",
                "billing_period_start_datetime",
                "provider_id",
                "s3_csv_cleared",
                "s3_parquet_cleared",
                "operator_version",
            },
        )

    def test_valid_data(self):
        """Test rate and markup for valid entries."""
        basic_model = {
            "id": 1,
            "assembly_id": "Test assembly id",
            "manifest_creation_datetime": datetime.datetime.now(),
            "manifest_updated_datetime": datetime.datetime.now(),
            "manifest_completed_datetime": datetime.datetime.now(),
            "manifest_modified_datetime": datetime.datetime.now(),
            "billing_period_start_datetime": datetime.datetime.now(),
            "provider_id": "test provider id",
            "s3_csv_cleared": True,
            "s3_parquet_cleared": True,
            "operator_version": "1.0",
        }
        with tenant_context(self.tenant):
            serializer = ManifestSerializer(data=basic_model)
            self.assertTrue(serializer.is_valid(raise_exception=True))

    def test_invalid_data(self):
        """Test rate and markup for valid entries."""
        basic_model = {
            "id": 1,
            "assembly_id": 3,
            "manifest_creation_datetime": datetime.datetime.now(),
            "manifest_updated_datetime": datetime.datetime.now(),
            "manifest_completed_datetime": datetime.datetime.now(),
            "manifest_modified_datetime": datetime.datetime.now(),
            "billing_period_start_datetime": datetime.datetime.now(),
            "provider_id": "test provider id",
            "s3_csv_cleared": True,
            "s3_parquet_cleared": True,
            "operator_version": "1.0",
        }

        serializer = ManifestSerializer(data=basic_model)
        self.assertRaises(TypeError, serializer.is_valid(raise_exception=True))


class UsageReportStatusSerializerTest(TestCase):
    """Tests the UsageReportStatusSerializer."""

    def setUp(self):
        super().setUp()
        self.manifest = CostUsageReportStatus.objects.first()
        self.serializer = UsageReportStatusSerializer(self.manifest)

    def test_manifest_contains_expected_fields(self):
        """Tests the ManifestSerializer is utilizing expected fields."""
        data = self.serializer.data
        self.assertEqual(
            set(data.keys()),
            {"id", "manifest", "report_name", "last_completed_datetime", "last_started_datetime", "etag"},
        )

    def test_valid_manifest_key(self):
        manifest = CostUsageReportManifest.objects.first()
        manifest_id = manifest.id
        basic_model = {
            "id": 1,
            "manifest": manifest_id,
            "report_name": "test_report_name",
            "last_completed_datetime": datetime.datetime.now(),
            "last_started_datetime": datetime.datetime.now(),
            "etag": "test etag",
        }

        serializer = UsageReportStatusSerializer(data=basic_model)
        self.assertTrue(serializer.is_valid(raise_exception=True))
