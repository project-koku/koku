#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Serializers for Masu API `manifest`."""
from rest_framework import serializers

from api.provider.models import Provider
from reporting_common.models import CostUsageReportManifest

# from reporting_common.models import CostUsageReportStatus

# this needs replaced


class SourceSerializer(serializers.Serializer):
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


class ProviderSerializer(serializers.Serializer):
    """Serializer for CostUsageReportManifest."""

    class Meta:
        model = Provider

    uuid = serializers.IntegerField()
    name = serializers.CharField()
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

    #     uuid = models.UUIDField(default=uuid4, primary_key=True)
    # name = models.CharField(max_length=256, null=False)
    # type = models.CharField(max_length=50, null=False, choices=PROVIDER_CHOICES, default=PROVIDER_AWS)
    # authentication = models.ForeignKey("ProviderAuthentication", null=True, on_delete=models.DO_NOTHING)
    # billing_source = models.ForeignKey("ProviderBillingSource", null=True, on_delete=models.DO_NOTHING, blank=True)
    # customer = models.ForeignKey("Customer", null=True, on_delete=models.PROTECT)
    # created_by = models.ForeignKey("User", null=True, on_delete=models.SET_NULL)
    # setup_complete = models.BooleanField(default=False)

    # created_timestamp = models.DateTimeField(auto_now_add=True, blank=True, null=True)

    # data_updated_timestamp = models.DateTimeField(null=True)

    # active = models.BooleanField(default=True)
    # paused = models.BooleanField(default=False)

    # infrastructure = models.ForeignKey("ProviderInfrastructureMap", null=True, on_delete=models.SET_NULL)
