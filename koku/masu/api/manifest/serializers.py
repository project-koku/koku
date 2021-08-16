from rest_framework import serializers

from reporting_common.models import CostUsageReportManifest
from reporting_common.models import CostUsageReportStatus


class ManifestSerializer(serializers.ModelSerializer):
    class Meta:
        model = CostUsageReportManifest

        fields = [
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
        ]


class UsageReportStatusSerializer(serializers.ModelSerializer):
    class Meta:
        model = CostUsageReportStatus

        fields = ["id", "report_name", "last_completed_datetime", "last_started_datetime", "etag", "manifest"]
