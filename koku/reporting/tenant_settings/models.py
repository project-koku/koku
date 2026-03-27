#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Models for per-tenant configuration."""
from django.core.validators import MaxValueValidator
from django.core.validators import MinValueValidator
from django.db import models


class TenantSettings(models.Model):
    """Per-tenant configuration that applies to all users within a schema."""

    DEFAULT_RETENTION_MONTHS = 3
    MIN_RETENTION_MONTHS = 3
    MAX_RETENTION_MONTHS = 120

    class Meta:
        db_table = "tenant_settings"

    data_retention_months = models.IntegerField(
        default=DEFAULT_RETENTION_MONTHS,
        validators=[
            MinValueValidator(MIN_RETENTION_MONTHS),
            MaxValueValidator(MAX_RETENTION_MONTHS),
        ],
    )
