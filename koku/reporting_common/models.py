#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Models for shared reporting tables."""
import json
import logging

from django.db import models
from django.db.models.signals import pre_delete
from django.dispatch import receiver
from django.utils import timezone

from api.common import log_json
from koku import celery_app
from masu.config import Config
from reporting_common.states import CombinedChoices
from reporting_common.states import ReportStep
from reporting_common.states import Status

LOG = logging.getLogger(__name__)


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
    export_time = models.DateTimeField(null=True)
    last_reports = models.JSONField(default=dict, null=True)
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
    last_completed_datetime = models.DateTimeField(null=True)
    last_started_datetime = models.DateTimeField(null=True)
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


class DelayedCeleryTasks(models.Model):
    """This table tracks summary tasks that are delaying execution."""

    class Meta:
        db_table = "delayed_celery_tasks"

    task_name = models.CharField(max_length=255)
    task_args = models.TextField()
    task_kwargs = models.TextField()
    timeout_timestamp = models.DateTimeField()
    provider_uuid = models.UUIDField()
    queue_name = models.CharField(max_length=255)

    def set_task_args(self, args):
        self.task_args = json.dumps(args)

    def get_task_args(self):
        return json.loads(self.task_args)

    def set_task_kwargs(self, kwargs):
        self.task_kwargs = json.dumps(kwargs)

    def get_task_kwargs(self):
        return json.loads(self.task_kwargs)

    def set_timeout(self, timeout_seconds):
        now = timezone.now()
        self.timeout_timestamp = now + timezone.timedelta(seconds=timeout_seconds)

    @classmethod
    def remove_expired_records(cls):
        now = timezone.now()
        expired_records = cls.objects.filter(timeout_timestamp__lt=now)
        expired_records.delete()

    @classmethod
    def create_or_reset_timeout(
        cls,
        task_name,
        task_args,
        task_kwargs,
        provider_uuid,
        queue_name,
        timeout_seconds=Config.DELAYED_RESUMMARY_TIME,
    ):
        existing_task = cls.objects.filter(task_name=task_name, provider_uuid=provider_uuid).first()

        if existing_task:
            existing_task.set_timeout(timeout_seconds)
            existing_task.save()
            return existing_task

        new_task = cls(
            task_name=task_name,
            task_args=json.dumps(task_args),
            task_kwargs=json.dumps(task_kwargs),
            provider_uuid=provider_uuid,
            queue_name=queue_name,
        )
        new_task.set_timeout(timeout_seconds)
        new_task.save()
        return new_task


# Define the pre_delete signal receiver function
@receiver(pre_delete, sender=DelayedCeleryTasks)
def trigger_celery_task(sender, instance, **kwargs):
    task_args = instance.get_task_args()
    task_kwargs = instance.get_task_kwargs()
    result = celery_app.send_task(instance.task_name, args=task_args, kwargs=task_kwargs, queue=instance.queue_name)
    log_msg = "Delay period ended, starting task."
    log_context = {
        "task_name": instance.task_name,
        "task_args": task_args,
        "task_kwargs": task_kwargs,
        "queue_name": instance.queue_name,
    }
    LOG.info(log_json(tracing_id=result.id, msg=log_msg, context=log_context))
