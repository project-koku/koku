#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Models for shared reporting tables."""
from django.db import models
from django.utils import timezone


class CostUsageReportManifest(models.Model):
    """Information gathered from a cost usage report manifest file."""

    class Meta:
        """Meta for CostUsageReportManifest."""

        unique_together = ("provider", "assembly_id")

    assembly_id = models.TextField()
    manifest_creation_datetime = models.DateTimeField(null=True, default=timezone.now)
    manifest_updated_datetime = models.DateTimeField(null=True, default=timezone.now)
    # Completed should indicate that our reporting materialzed views have refreshed
    manifest_completed_datetime = models.DateTimeField(null=True)
    # This timestamp indicates the last time the manifest was modified on the data source's end, not ours.
    manifest_modified_datetime = models.DateTimeField(null=True)
    billing_period_start_datetime = models.DateTimeField()
    num_total_files = models.IntegerField()
    s3_csv_cleared = models.BooleanField(default=False, null=True)
    s3_parquet_cleared = models.BooleanField(default=False, null=True)
    provider = models.ForeignKey("api.Provider", on_delete=models.CASCADE)


class CostUsageReportStatus(models.Model):
    """Information on the state of the cost usage report."""

    class Meta:
        """Meta for CostUsageReportStatus."""

        unique_together = ("manifest", "report_name")

    manifest = models.ForeignKey("CostUsageReportManifest", null=True, on_delete=models.CASCADE)
    report_name = models.CharField(max_length=128, null=False)
    last_completed_datetime = models.DateTimeField(null=True)
    last_started_datetime = models.DateTimeField(null=True)
    etag = models.CharField(max_length=64, null=True)


class RegionMapping(models.Model):
    """Mapping table of AWS region names.

    example:
      "Region Name": "EU (London)"
      "Region": "eu-west-2"

    """

    class Meta:
        """Meta for RegionMapping."""

        db_table = "region_mapping"

    region = models.CharField(max_length=32, null=False, unique=True)
    region_name = models.CharField(max_length=64, null=False, unique=True)
