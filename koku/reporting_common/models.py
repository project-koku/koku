#
# Copyright 2018 Red Hat, Inc.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
"""Models for shared reporting tables."""
from api.provider.models import Provider
from django.db import models
from django.utils import timezone


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
    billing_period_start_datetime = models.DateTimeField()
    num_processed_files = models.IntegerField(default=0)
    num_total_files = models.IntegerField()
    provider = models.ForeignKey("api.Provider", on_delete=models.CASCADE)
    task = models.UUIDField(null=True)


class CostUsageReportStatus(models.Model):
    """Information on the state of the cost usage report."""

    class Meta:
        """Meta for CostUsageReportStatus."""

        unique_together = ("manifest", "report_name")

    manifest = models.ForeignKey("CostUsageReportManifest", null=True, on_delete=models.CASCADE)
    report_name = models.CharField(max_length=128, null=False)
    last_completed_datetime = models.DateTimeField(null=True)
    last_started_datetime = models.DateTimeField(null=True)
    etag = models.CharField(max_length=64, null=True)


class ReportColumnMap(models.Model):
    """A mapping table for Cost Usage Reports.

    This maps a column name in a report to a database table
    and column in a customer schema.

    """

    class Meta:
        """Meta for ReportColumnMap."""

        unique_together = ("report_type", "provider_column_name")

    report_type = models.CharField(max_length=50, null=True)

    provider_type = models.CharField(
        max_length=50, null=False, choices=Provider.PROVIDER_CHOICES, default=Provider.PROVIDER_AWS
    )

    provider_column_name = models.CharField(max_length=128, null=False, unique=False)

    database_table = models.CharField(max_length=50, null=False)

    database_column = models.CharField(max_length=128, null=False)


class SIUnitScale(models.Model):
    """A range of common SI unit prefixes."""

    class Meta:
        """Meta for SIUnitScale."""

        db_table = "si_unit_scale"

    prefix = models.CharField(max_length=12, null=False, unique=True)
    prefix_symbol = models.CharField(max_length=1, null=False)
    multiplying_factor = models.DecimalField(max_digits=49, decimal_places=24)


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
