#
# Copyright 2025 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""PostgreSQL database accessor implementation."""
import logging

from koku.reportdb_accessor import ColumnType, ReportDBAccessor

LOG = logging.getLogger(__name__)


class DjangoConnectionWrapper:
    """Wrapper to make Django connection work like a DB-API connection with context manager."""

    def __init__(self, schema=None):
        from django.db import connection

        # Set schema if provided
        if schema and schema != 'default':
            with connection.cursor() as cursor:
                cursor.execute("SET search_path TO %s", [schema])

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        # Django manages connection lifecycle, we don't close it
        return False

    def cursor(self):
        from django.db import connection
        return connection.cursor()

    def getConnection(self):
        """Return the underlying Django connection for compatibility."""
        from django.db import connection
        return connection.connection


class PostgresReportDBAccessor(ReportDBAccessor):
    """PostgreSQL implementation of report database accessor using Django DB API."""

    def connect(self, **kwargs):
        """
        Create PostgreSQL database connection.

        Args:
            **kwargs: Connection parameters (ignored for Django)

        Returns:
            DB-API 2.0 compatible connection object
        """
        schema = kwargs.get('schema')
        return DjangoConnectionWrapper(schema=schema)
    
    def get_schema_check_sql(self, schema_name: str):
        """Return the SQL to check if a schema exists."""
        return f"SELECT 1 FROM information_schema.schemata WHERE schema_name = '{schema_name}'"

    def get_table_check_sql(self, table_name: str, schema_name: str):
        return f"SELECT 1 FROM information_schema.tables WHERE table_name = '{table_name}' AND table_schema = '{schema_name}'"
    
    def get_schema_create_sql(self, schema_name: str):
        return f"CREATE SCHEMA IF NOT EXISTS {schema_name}"

    def get_table_create_sql(self, table_name: str, schema_name: str, columns: list[tuple[str, ColumnType]], partition_columns: list[tuple[str, ColumnType]], s3_path: str):
        sql = f"CREATE TABLE IF NOT EXISTS \"{schema_name}\".\"{table_name}\" ("

        for column in columns:
            sql += f"{column[0]} {self._get_column_type_sql(column[1])}, "
        for partition_column in partition_columns:
            sql += f"{partition_column[0]} {self._get_column_type_sql(partition_column[1])}, "
        sql = sql.rstrip(", ")

        partition_column_str = ", ".join([col_name for col_name, _ in partition_columns])

        sql += f") PARTITION BY RANGE({partition_column_str})"

        return sql

    def _get_column_type_sql(self, column_type: ColumnType):
        if column_type == ColumnType.NUMERIC:
            return "float"
        elif column_type == ColumnType.DATE:
            return "timestamp"
        elif column_type == ColumnType.BOOLEAN:
            return "boolean"
        else:
            return "varchar"
    
    def get_partition_create_sql(self, schema_name: str, table_name: str, partition_name: str, partition_values_lower: list[str], partition_values_upper: list[str]):
        return f"CREATE TABLE IF NOT EXISTS \"{schema_name}\".\"{partition_name}\" PARTITION OF \"{schema_name}\".\"{table_name}\" FOR VALUES FROM ({', '.join(partition_values_lower)}) TO ({', '.join(partition_values_upper)})"