#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Models for shared reporting tables."""
import logging
from uuid import uuid4

from django.conf import settings
from django.db import models
from django.db.models.signals import pre_delete
from django.dispatch import receiver
from django.utils import timezone

from api.common import log_json
from api.provider.models import Provider
from koku import celery_app
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
    s3_parquet_cleared = models.BooleanField(default=False, null=True)
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
    # report_tracker is additional context for GCP/OCP for managing file counts and file names
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


class DelayedCeleryTasks(models.Model):
    """This table tracks summary tasks that are delaying execution."""

    class Meta:
        db_table = "delayed_celery_tasks"

    task_name = models.CharField(max_length=255)
    task_args = models.JSONField()
    task_kwargs = models.JSONField()
    timeout_timestamp = models.DateTimeField()
    provider_uuid = models.UUIDField()
    queue_name = models.CharField(max_length=255)
    metadata = models.JSONField(default=dict, null=True)

    def set_timeout(self, timeout_seconds):
        now = timezone.now()
        self.timeout_timestamp = now + timezone.timedelta(seconds=timeout_seconds)

    @classmethod
    def trigger_delayed_tasks(cls):
        """Removes expired records triggering the celery task
        through the pre_delete signal trigger_celery_task.
        """
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
        timeout_seconds=settings.DELAYED_TASK_TIME,
    ):
        """
        Saves data regarding to the celery task being delayed.
        """
        existing_task = cls.objects.filter(task_name=task_name, provider_uuid=provider_uuid).first()

        if existing_task:
            # The task already exist extend the timeout.
            existing_task.set_timeout(timeout_seconds)
            existing_task.save()
            return existing_task

        if not task_kwargs.get("tracing_id"):
            task_kwargs["tracing_id"] = str(uuid4())

        new_task = cls(
            task_name=task_name,
            task_args=task_args,
            task_kwargs=task_kwargs,
            provider_uuid=provider_uuid,
            queue_name=queue_name,
        )
        new_task.set_timeout(timeout_seconds)
        new_task.save()
        return new_task


@receiver(pre_delete, sender=DelayedCeleryTasks)
def trigger_celery_task(sender, instance, **kwargs):
    """Triggers celery task prior to removing the rows from the table."""
    tracing_id = instance.task_kwargs.get("tracing_id")
    result = celery_app.send_task(
        instance.task_name, args=instance.task_args, kwargs=instance.task_kwargs, queue=instance.queue_name
    )
    log_msg = "delay period ended starting task"
    log_context = {
        "task_name": instance.task_name,
        "task_args": instance.task_args,
        "task_kwargs": instance.task_kwargs,
        "queue_name": instance.queue_name,
        "result_id": result.id,
    }
    LOG.info(log_json(tracing_id=tracing_id, msg=log_msg, context=log_context))


class DiskCapacity(models.Model):
    """Mapping of product substrings to capacity in GiB.

    Azure bills do not report capacity so we build this information externally.
    """

    class Meta:
        """Meta for CostUsageReportStatus."""

        # table: reporting_common_diskcapacity

        unique_together = ("product_substring", "capacity", "provider_type")

    product_substring = models.CharField(max_length=20, primary_key=True)
    capacity = models.IntegerField()  # GiB
    provider_type = models.CharField(max_length=50, null=False, choices=Provider.CLOUD_PROVIDER_CHOICES)
