#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Serializers for Masu API `manifest`."""
from rest_framework import serializers

from reporting_common.models import CostUsageReportManifest
from reporting_common.models import CostUsageReportStatus


class ManifestSerializer(serializers.Serializer):
    """Serializer for CostUsageReportManifest."""

    class Meta:
        model = CostUsageReportManifest

    id = serializers.IntegerField()
    assembly_id = serializers.CharField()
    manifest_creation_datetime = serializers.DateTimeField()
    manifest_updated_datetime = serializers.DateTimeField()
    manifest_completed_datetime = serializers.DateTimeField()
    manifest_modified_datetime = serializers.DateTimeField()
    billing_period_start_datetime = serializers.DateTimeField()
    provider_id = serializers.PrimaryKeyRelatedField(read_only=True)
    s3_csv_cleared = serializers.BooleanField()
    s3_parquet_cleared = serializers.BooleanField()
    operator_version = serializers.CharField()
    export_time = serializers.DateTimeField()


class UsageReportStatusSerializer(serializers.Serializer):
    """Serializer for CostUsageReportStatus."""

    class Meta:
        model = CostUsageReportStatus

    id = serializers.IntegerField()
    manifest = serializers.PrimaryKeyRelatedField(read_only=True)
    report_name = serializers.CharField()
    last_completed_datetime = serializers.DateTimeField()
    last_started_datetime = serializers.DateTimeField()
    etag = serializers.CharField()
