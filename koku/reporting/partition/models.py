from django.contrib.postgres.indexes import GinIndex
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import JSONField


def validate_not_empty(value):
    if len(value) == 0:
        raise ValidationError("Value cannot be empty")


class PartitionedTable(models.Model):
    """
    Tracking table for table partitions
    """

    RANGE = "range"
    LIST = "list"

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
    # Sub-partition type
    subpartition_type = models.TextField(null=True)
    # Sub-partition key
    subpartition_col = models.TextField(null=True)

    def __repr__(self):
        return (
            f"< PartitionedTable: {self.schema_name}.{self.table_name} "
            + f"{self.partition_type}({self.partition_col}, {self.partition_parameters}) "
            + f"part of {self.partition_of_table_name} >"
        )
