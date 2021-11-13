#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Models for OCP cost view tables."""
from django.conf import settings
from django.contrib.postgres.indexes import GinIndex
from django.db import models
from django.db.models import JSONField


class CostSummary(models.Model):
    """A summary table of OCP costs."""

    class Meta:
        """Meta for CostSummary."""

        db_table = "reporting_ocpcosts_summary"
        indexes = [
            models.Index(fields=["usage_start"], name="ocpcostsum_usage_start_idx"),
            models.Index(fields=["namespace"], name="ocpcostsum_namespace_idx", opclasses=["varchar_pattern_ops"]),
            models.Index(fields=["node"], name="ocpcostsum_node_idx", opclasses=["varchar_pattern_ops"]),
            GinIndex(fields=["pod_labels"], name="ocpcostsum_pod_labels_idx"),
        ]

    report_period = models.ForeignKey("OCPUsageReportPeriod", on_delete=models.CASCADE, null=True)

    cluster_id = models.CharField(max_length=50, null=True)

    cluster_alias = models.CharField(max_length=256, null=True)

    # Kubernetes objects by convention have a max name length of 253 chars
    namespace = models.CharField(max_length=253, null=True)

    pod = models.CharField(max_length=253, null=True)

    node = models.CharField(max_length=253, null=True)

    usage_start = models.DateField(null=False)
    usage_end = models.DateField(null=False)

    pod_charge_cpu_core_hours = models.DecimalField(
        max_digits=settings.NUMERIC_MAX_DIGITS, decimal_places=settings.NUMERIC_DECIMAL_PLACES, null=True
    )

    pod_charge_memory_gigabyte_hours = models.DecimalField(
        max_digits=settings.NUMERIC_MAX_DIGITS, decimal_places=settings.NUMERIC_DECIMAL_PLACES, null=True
    )

    persistentvolumeclaim_charge_gb_month = models.DecimalField(
        max_digits=settings.NUMERIC_MAX_DIGITS, decimal_places=settings.NUMERIC_DECIMAL_PLACES, null=True
    )

    # Need more precision on calculated fields, otherwise there will be
    # Rounding errors
    infra_cost = models.DecimalField(
        max_digits=settings.NUMERIC_MAX_DIGITS, decimal_places=settings.NUMERIC_DECIMAL_PLACES, null=True
    )

    # This field is used in place of infrastructure_cost when
    # grouping by project
    project_infra_cost = models.DecimalField(
        max_digits=settings.NUMERIC_MAX_DIGITS, decimal_places=settings.NUMERIC_DECIMAL_PLACES, null=True
    )

    markup_cost = models.DecimalField(
        max_digits=settings.NUMERIC_MAX_DIGITS, decimal_places=settings.NUMERIC_DECIMAL_PLACES, null=True
    )

    project_markup_cost = models.DecimalField(
        max_digits=settings.NUMERIC_MAX_DIGITS, decimal_places=settings.NUMERIC_DECIMAL_PLACES, null=True
    )

    pod_labels = JSONField(null=True)

    monthly_cost = models.DecimalField(
        max_digits=settings.NUMERIC_MAX_DIGITS, decimal_places=settings.NUMERIC_DECIMAL_PLACES, null=True
    )
