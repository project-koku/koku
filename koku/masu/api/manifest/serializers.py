#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Serializers for Masu API `manifest`."""
from rest_framework import serializers

from reporting_common.models import CostUsageReportManifest
from reporting_common.models import CostUsageReportStatus
from reporting_common.models import Status


class ManifestSerializer(serializers.Serializer):
    """Serializer for CostUsageReportManifest."""

    class Meta:
        model = CostUsageReportManifest

    id = serializers.IntegerField()
    assembly_id = serializers.CharField()
    creation_datetime = serializers.DateTimeField()
    manifest_updated_datetime = serializers.DateTimeField()
    completed_datetime = serializers.DateTimeField()
    export_datetime = serializers.DateTimeField()
    billing_period_start_datetime = serializers.DateTimeField()
    provider_id = serializers.PrimaryKeyRelatedField(read_only=True)
    s3_csv_cleared = serializers.BooleanField()
    s3_parquet_cleared = serializers.BooleanField()
    operator_version = serializers.CharField()
    state = serializers.JSONField()


class UsageReportStatusSerializer(serializers.Serializer):
    """Serializer for CostUsageReportStatus."""

    class Meta:
        model = CostUsageReportStatus

    id = serializers.IntegerField()
    manifest = serializers.PrimaryKeyRelatedField(read_only=True)
    report_name = serializers.CharField()
    completed_datetime = serializers.DateTimeField()
    started_datetime = serializers.DateTimeField()
    etag = serializers.CharField()
    status = serializers.IntegerField()
    failed_status = serializers.IntegerField()
    celery_task_id = serializers.UUIDField()

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["status"] = Status(data["status"]).label
        return data


class CustomSerializer(serializers.Serializer):
    manifest = ManifestSerializer()
    failed_reports = UsageReportStatusSerializer(many=True)
