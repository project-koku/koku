#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Models for shared reporting tables."""
from django.db import models
from django.utils import timezone

from reporting_common.states import CombinedChoices
from reporting_common.states import ReportStep
from reporting_common.states import Status


class CostUsageReportManifest(models.Model):
    """Information gathered from a cost usage report manifest file."""

    class Meta:
        """Meta for CostUsageReportManifest."""

        unique_together = ("provider", "assembly_id")

    assembly_id = models.TextField()
    creation_datetime = models.DateTimeField(null=True, default=timezone.now)
    # completed_datetime indicates that our reporting tables have completed updating with current data
    completed_datetime = models.DateTimeField(null=True)
    # export_datetime indicates the last time the _data-source_ modified the data
    export_datetime = models.DateTimeField(null=True)
    # always `select_for_update` when updating the state field
    state = models.JSONField(default=dict, null=True)
    billing_period_start_datetime = models.DateTimeField()
    num_total_files = models.IntegerField()
    # s3_csv_cleared used in AWS/Azure to indicate csv's have been cleared for daily archive processing
    s3_csv_cleared = models.BooleanField(default=False, null=True)
    # s3_parquet_cleared used to indicate parquet files have been cleared prior to csv to parquet conversion
    s3_parquet_cleared = models.BooleanField(default=True, null=True)
    # Indicates what initial date to start at for daily processing
    daily_archive_start_date = models.DateTimeField(null=True)
    operator_version = models.TextField(null=True)
    cluster_channel = models.TextField(null=True)
    operator_certified = models.BooleanField(null=True)
    operator_airgapped = models.BooleanField(null=True)
    operator_errors = models.JSONField(default=dict, null=True)
    operator_daily_reports = models.BooleanField(null=True, default=False)
    cluster_id = models.TextField(null=True)
    provider = models.ForeignKey("api.Provider", on_delete=models.CASCADE)
    # report_tracker is additional context for OCI/GCP/OCP for managing file counts and file names
    report_tracker = models.JSONField(default=dict, null=True)
    # s3_parquet_cleared_tracker is additional parquet context for OCP daily operator payloads
    s3_parquet_cleared_tracker = models.JSONField(default=dict, null=True)


class CostUsageReportStatus(models.Model):
    """Information on the state of the cost usage report."""

    class Meta:
        """Meta for CostUsageReportStatus."""

        unique_together = ("manifest", "report_name")

    manifest = models.ForeignKey("CostUsageReportManifest", null=True, on_delete=models.CASCADE)
    report_name = models.CharField(max_length=128, null=False)
    completed_datetime = models.DateTimeField(null=True)
    started_datetime = models.DateTimeField(null=True)
    etag = models.CharField(max_length=64, null=True)
    # id of the task processing this report
    celery_task_id = models.UUIDField(null=True)
    # Current status of processing report
    status = models.IntegerField(choices=CombinedChoices.choices, default=ReportStep.DOWNLOADING)
    failed_status = models.IntegerField(choices=ReportStep.choices, null=True)

    def set_started_datetime(self):
        """
        Set the started_datetime field to the current date and time.
        """
        self.started_datetime = timezone.now()
        self.save(update_fields=["started_datetime"])

    def clear_started_datetime(self):
        """
        Clear the started_datetime field to the current date and time.
        """
        self.started_datetime = None
        self.save(update_fields=["started_datetime"])

    def set_completed_datetime(self):
        """
        Set the completed_datetime field to the current date and time.
        """
        self.completed_datetime = timezone.now()
        self.save(update_fields=["completed_datetime"])

    def set_celery_task_id(self, task_id):
        """
        Set celery_task_id field to match the report task id.
        """
        self.celery_task_id = task_id
        self.save(update_fields=["celery_task_id"])

    def update_status(self, status_id):
        """
        Update the status of the current report.
        """
        if status_id == Status.DONE:
            self.set_completed_datetime()
        elif status_id == Status.FAILED:
            self.set_failed_status(self.status)
        self.status = status_id
        self.save(update_fields=["status"])

    def set_failed_status(self, failed_status_id):
        """
        Set the failed state of a processing report.
        """
        self.failed_status = failed_status_id
        self.save(update_fields=["failed_status"])


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
