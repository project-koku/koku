from rest_framework import serializers

from reporting_common.models import CostUsageReportManifest


class ManifestSerializer(serializers.ModelSerializer):
    class Meta:
        model = CostUsageReportManifest

        fields = [
            "assembly_id",
            "manifest_creation_Datetime",
            "manifest_updated_datetime",
            "manifest_completed_datetime",
            "manifest_modified_datetime",
            "billing_period_start_datetime",
            "num_total_files",
            "provider_id",
            "s3_csv_cleared",
            "s3_parquet_cleared",
            "operator_version",
        ]

    # assembly_id = serializers.IntegerField()
    # manifest_creation_datetime = serializers.DateTimeField()
    # manifest_updated_datetime = serializers.DateTimeField()
    # manifest_completed_datetime = serializers.DateTimeField()
    # manifest_modified_datetime = serializers.DateTimeField()
    # billing_period_start_datetime = serializers.DateTimeField()
    # num_total_files = serializers.IntegerField()
    # s3_csv_cleared = serializers.BooleanField()
    # s3_parquet_cleared = serializers.BooleanField()
    # operator_version = serializers.IntegerField()
