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
