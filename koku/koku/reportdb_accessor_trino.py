#
# Copyright 2025 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Trino database accessor implementation."""
import logging

from django.conf import settings
import trino.dbapi
from koku.reportdb_accessor import ColumnType, ReportDBAccessor

LOG = logging.getLogger(__name__)


class TrinoReportDBAccessor(ReportDBAccessor):
    """Trino implementation of report database accessor."""

    def connect(self, **kwargs):
        """
        Create Trino database connection.

        Args:
            **kwargs: Connection parameters (host, port, catalog, schema, etc.)

        Returns:
            Trino DB-API 2.0 compatible connection object
        """
        return trino.dbapi.connect(**kwargs)

    def get_schema_check_sql(self, schema_name: str):
        return f"SHOW SCHEMAS LIKE '{schema_name}'"

    def get_table_check_sql(self, table_name: str, schema_name: str):
        return f"SHOW TABLES LIKE '{table_name}'"

    def get_schema_create_sql(self, schema_name: str):
        return f"CREATE SCHEMA IF NOT EXISTS {schema_name}"

    def get_table_create_sql(self, table_name: str, schema_name: str, columns: list[tuple[str, ColumnType]], partition_columns: list[tuple[str, ColumnType]], s3_path: str):
        sql = f"CREATE TABLE IF NOT EXISTS {schema_name}.{table_name} ("

        for column in columns:
            sql += f"{column[0]} {self._get_column_type_sql(column[1])}, "
        for partition_column in partition_columns:
            sql += f"{partition_column[0]} {self._get_column_type_sql(partition_column[1])}, "
        sql = sql.rstrip(", ")
        
        partition_column_str = ", ".join([col_name for col_name, _ in partition_columns])

        sql += (
            f") WITH(external_location = '{settings.TRINO_S3A_OR_S3}://{s3_path}', format = 'PARQUET',"
            f" partitioned_by=ARRAY[{partition_column_str}])"
        )
        return sql

    def _get_column_type_sql(self, column_type: ColumnType):
        if column_type == ColumnType.NUMERIC:
            return "double"
        elif column_type == ColumnType.DATE:
            return "timestamp"
        elif column_type == ColumnType.BOOLEAN:
            return "boolean"
        else:
            return "varchar"