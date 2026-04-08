#
# Copyright 2024 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Django models for the Kessel ReBAC integration."""
from django.db import models


class KesselSyncedResource(models.Model):
    """Tracks resources that have been reported to Kessel Inventory."""

    resource_type = models.CharField(max_length=128)
    resource_id = models.CharField(max_length=256)
    org_id = models.CharField(max_length=64)
    provider_uuid = models.CharField(max_length=64, default="", blank=True)
    kessel_synced = models.BooleanField(default=False)
    last_synced_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        """Meta for KesselSyncedResource."""

        db_table = "kessel_synced_resource"
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["resource_type", "resource_id", "org_id"],
                name="uq_kessel_sync_type_id_org",
            ),
        ]
        indexes = [
            models.Index(fields=["org_id"], name="idx_kessel_sync_org"),
            models.Index(fields=["resource_type", "org_id"], name="idx_kessel_sync_type_org"),
            models.Index(fields=["provider_uuid", "org_id"], name="idx_kessel_sync_provider_org"),
        ]

    def __str__(self) -> str:
        return f"{self.resource_type}:{self.resource_id} (org={self.org_id})"
