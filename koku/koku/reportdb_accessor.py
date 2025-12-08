#
# Copyright 2025 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Abstract interface for report database accessors."""
from abc import ABC, abstractmethod
from enum import Enum, auto


class ColumnType(Enum):
    NUMERIC = auto()
    DATE = auto()
    BOOLEAN = auto()
    STRING = auto()

class ReportDBAccessor(ABC):
    """Abstract base class for database accessors."""

    @abstractmethod
    def connect(self, **kwargs):
        """
        Create database connection.

        Args:
            **kwargs: Connection parameters (host, port, catalog, schema, etc.)

        Returns:
            DB-API 2.0 compatible connection object
        """
        pass

    @abstractmethod
    def get_schema_check_sql(self,schema_name: str):
        """Return the SQL to check if a schema exists"""
        pass

    
    @abstractmethod
    def get_table_check_sql(self, table_name: str, schema_name: str):
        """Return the SQL to check if a table exists"""
        pass

    @abstractmethod
    def get_schema_create_sql(self, schema_name: str):
        """Return the SQL to create a new schema"""
        pass

    @abstractmethod
    def get_table_create_sql(self, table_name: str, schema_name: str, columns: list[tuple[str, ColumnType]], partition_columns: list[tuple[str, ColumnType]], s3_path: str):
        """Return the SQL to create a new table"""
        pass

    @abstractmethod
    def get_partition_create_sql(self, schema_name: str, table_name: str, partition_name: str, partition_values_lower: list[str], partition_values_upper: list[str]):
        """Return the SQL to create a new partition"""
        """ For now we assume that the partition values are strings"""
        pass

    @abstractmethod
    def get_delete_day_by_manifestid_sql(self, schema_name: str, table_name: str, source: str, year: str, month: str, start_date: str, manifestid: str):
        """Return the SQL to delete a day's data where manifestid doesn't match"""
        pass

    @abstractmethod
    def get_delete_day_by_reportnumhours_sql(self, schema_name: str, table_name: str, source: str, year: str, month: str, start_date: str, reportnumhours: int):
        """Return the SQL to delete a day's data where reportnumhours is less than specified value"""
        pass

    @abstractmethod
    def get_check_day_exists_sql(self, schema_name: str, table_name: str, source: str, year: str, month: str, start_date: str):
        """Return the SQL to check if data exists for a specific day"""
        pass

def get_report_db_accessor():
      from django.conf import settings
      from koku.reportdb_accessor_postgres import PostgresReportDBAccessor
      from koku.reportdb_accessor_trino import TrinoReportDBAccessor

      if settings.ONPREM:
          return PostgresReportDBAccessor()
      else:
          return TrinoReportDBAccessor()