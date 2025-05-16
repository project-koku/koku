#
# Copyright 2023 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Models for provider management."""
from uuid import uuid4

from django.db import models


class TenantAPIProvider(models.Model):
    """A tenant specific provider model"""

    class Meta:
        """Meta for Provider."""

        db_table = "reporting_tenant_api_provider"

    uuid = models.UUIDField(default=uuid4, primary_key=True)
    name = models.TextField(null=False)
    type = models.TextField(null=False)
    provider = models.ForeignKey("api.Provider", on_delete=models.CASCADE, null=True)


class SubsLastProcessed(models.Model):
    """A model for storing last processed time for a subs provider"""

    class Meta:
        """Meta for subs last processed"""

        db_table = "reporting_subs_last_processed_time"
        unique_together = ("source_uuid", "resource_id", "year", "month")

    source_uuid = models.ForeignKey(
        "reporting.TenantAPIProvider", on_delete=models.CASCADE, unique=False, null=False, db_column="source_uuid"
    )
    resource_id = models.TextField(null=False, default="")
    year = models.CharField(null=False, max_length=4)
    month = models.CharField(null=False, max_length=2)
    # records the latest processed time when the csv files are created
    latest_processed_time = models.DateTimeField(null=True)
    # records the last latest_processed_time sent using kafka
    latest_event_sent = models.DateTimeField(null=True)


class SubsIDMap(models.Model):
    """A model for storing IDs and what provider they belong to."""

    class Meta:
        """Meta for subs id map"""

        db_table = "reporting_subs_id_map"

    source_uuid = models.ForeignKey(
        "reporting.TenantAPIProvider", on_delete=models.CASCADE, unique=False, null=False, db_column="source_uuid"
    )
    usage_id = models.TextField(null=False, unique=True)
