from rest_framework import serializers

from reporting_common.models import CostUsageReportManifest


class ManifestSerializer(serializers.ModelSerializer):

    assembly_id = serializers.CharField()
    manifest_creation_datetime = serializers.DateTimeField()
    manifest_updated_datetime = serializers.DateTimeField()
    manifest_completed_datetime = serializers.DateTimeField()
    manifest_modified_datetime = serializers.DateTimeField()
    billing_period_start_datetime = serializers.DateTimeField()
    num_total_files = serializers.IntegerField()
    s3_csv_cleared = serializers.BooleanField()
    s3_parquet_cleared = serializers.BooleanField
    operator_version = serializers.CharField

    class Meta:
        model = CostUsageReportManifest
        fields = "__all__"
