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

from django.db import models

from api.provider.models import Provider


class CostUsageReportStatus(models.Model):
    """Information on the state of the cost usage report."""

    provider = models.ForeignKey('api.Provider', null=True,
                                 on_delete=models.CASCADE)
    report_name = models.CharField(max_length=128, null=False, unique=True)
    cursor_position = models.PositiveIntegerField()
    last_completed_datetime = models.DateTimeField(null=True)
    last_started_datetime = models.DateTimeField(null=True)
    etag = models.CharField(max_length=64, null=True)


class ReportColumnMap(models.Model):
    """A mapping table for Cost Usage Reports.

    This maps a column name in a report to a database table
    and column in a customer schema.

    """

    provider_type = models.CharField(
        max_length=50,
        null=False,
        choices=Provider.PROVIDER_CHOICES,
        default=Provider.PROVIDER_AWS
    )

    provider_column_name = models.CharField(
        max_length=128,
        null=False,
        unique=True
    )

    database_table = models.CharField(max_length=50, null=False)

    database_column = models.CharField(max_length=128, null=False)


class SIUnitScale(models.Model):
    """A range of common SI unit prefixes."""

    class Meta:
        """Meta for SIUnitScale."""

        db_table = 'si_unit_scale'

    prefix = models.CharField(max_length=12, null=False, unique=True)
    prefix_symbol = models.CharField(max_length=1, null=False)
    multiplying_factor = models.DecimalField(max_digits=49, decimal_places=24)
