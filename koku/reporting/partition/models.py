#
# Copyright 2020 Red Hat, Inc.
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
from django.contrib.postgres.fields import JSONField
from django.contrib.postgres.indexes import GinIndex
from django.core.exceptions import ValidationError
from django.db import models


def validate_not_empty(value):
    if len(value) == 0:
        raise ValidationError("Value cannot be empty")


class PartitionedTable(models.Model):
    """
    Tracking table for table partitions
    """

    RANGE = "range"

    class Meta:
        db_table = "partitioned_tables"
        unique_together = ("schema_name", "table_name")

        indexes = [
            models.Index(name="partable_table", fields=["schema_name", "table_name"]),
            models.Index(name="partable_partition_type", fields=["partition_type"]),
            GinIndex(name="partable_partition_parameters", fields=["partition_parameters"]),
        ]

    # Schema name for table partition
    schema_name = models.TextField(null=False, validators=[validate_not_empty])
    # Name of table partition
    table_name = models.TextField(null=False, validators=[validate_not_empty])
    # Name of parent partitioned table
    partition_of_table_name = models.TextField(null=False, validators=[validate_not_empty])
    # Type of partition ('range', 'list')
    partition_type = models.TextField(null=False, validators=[validate_not_empty])
    # Partition key
    partition_col = models.TextField(null=False, validators=[validate_not_empty])
    # Parameters used when creating partition (partition key values or range)
    partition_parameters = JSONField(null=False, validators=[validate_not_empty])
    # active flag will attach/detach partition
    active = models.BooleanField(null=False, default=True)
