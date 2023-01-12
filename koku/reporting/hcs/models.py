# Copyright 2023 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
import logging
from uuid import uuid4

from django.conf import settings
from django.db import models
from django.db import transaction

LOG = logging.getLogger(__name__)


class HCSReport(models.Model):
    task_uuid = models.UUIDField(default=uuid4, primary_key=True)
    created_timestamp = models.DateTimeField(auto_now_add=True)
    completed_timestamp = models.DateTimeField(null=True)
    report_location = models.CharField(max_length=256)
    provider = models.ForeignKey("api.Provider", on_delete=models.CASCADE, null=True)

    def __str__(self):
        """Get the string representation."""
        return (
            f"Provider UUID: {self.provider}\n"
            f"AWS bucket location: {self.report_location}\n"
            f"Created time: {self.created_timestamp}\n"
            f"Processing completed: {self.completed_timestamp}\n"
            f"Processing task ID: {self.task_uuid}\n"
        )

    def ingest(data):
        if settings.AUTO_DATA_INGEST:
            # Local import of task function to avoid potential import cycle.
            from masu.celery.tasks import check_report_updates

            LOG.info(f"Starting HCS data ingest task for Provider {data.get('provider')}")
            # Start check_report_updates task after Provider has been committed.
            transaction.on_commit(
                lambda: check_report_updates.s(provider_uuid=data.get("provider")).set(queue="priority").apply_async()
            )
