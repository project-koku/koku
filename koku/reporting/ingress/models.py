# Copyright 2023 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
import logging
from uuid import uuid4

from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.db import transaction
from django.utils import timezone

from api.common import log_json


LOG = logging.getLogger(__name__)


class IngressReports(models.Model):
    uuid = models.UUIDField(default=uuid4)
    created_timestamp = models.DateTimeField(auto_now_add=True)
    completed_timestamp = models.DateTimeField(null=True)
    reports_list = ArrayField(models.CharField(max_length=256, blank=False))
    source = models.ForeignKey("api.Provider", on_delete=models.CASCADE)
    sources_id = models.IntegerField(null=True)
    bill_year = models.CharField(max_length=4, blank=False)
    bill_month = models.CharField(max_length=2, blank=False)
    status = models.TextField(default="pending")
    schema_name = models.ForeignKey("api.Customer", to_field="schema_name", null=True, on_delete=models.PROTECT)

    def __str__(self):
        """Get the string representation."""
        return (
            f"Sources ID: {self.sources_id}\n"
            f"Source UUID: {self.source}\n"
            f"Report location: {self.reports_list}\n"
            f"Report bill year: {self.bill_year}\n"
            f"Report bill month: {self.bill_month}\n"
            f"Created time: {self.created_timestamp}\n"
            f"Processing completed: {self.completed_timestamp}\n"
            f"Processing status: {self.status}\n"
            f"Processing ID: {self.uuid}\n"
        )

    def ingest(data):
        if settings.AUTO_DATA_INGEST:
            # Local import of task function to avoid potential import cycle.
            from masu.celery.tasks import check_report_updates

            LOG.info(f"Starting data ingest task for Provider {data.get('source')}")
            # Start check_report_updates task after Provider has been committed.
            transaction.on_commit(
                lambda: check_report_updates.s(
                    provider_uuid=data.get("source"),
                    bill_date=f"{data.get('bill_year')}{data.get('bill_month')}",
                    ingress_reports=data.get("reports_list"),
                    ingress_report_uuid=data.get("ingress_report_uuid"),
                )
                .set(queue="download")
                .apply_async()
            )

    def mark_completed(self):
        self.status = "Completed"
        self.completed_timestamp = timezone.now()
        self.save(update_fields=["completed_timestamp", "status"])
        LOG.info(
            log_json(
                msg="marking ingress report complete",
                ingress_report=self.uuid,
                provider_uuid=self.source.uuid,
            )
        )

    def set_status(self, status):
        """Update the status field for ingress reports."""
        self.status = status
        self.save(update_fields=["status"])
        LOG.info(
            log_json(
                msg="updating ingress report status",
                ingress_report=self.uuid,
                provider_uuid=self.source.uuid,
                status=status,
            )
        )
