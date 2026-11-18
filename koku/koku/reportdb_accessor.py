#
# Copyright 2025 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Abstract interface for report database accessors."""
from abc import ABC
from abc import abstractmethod
from enum import auto
from enum import Enum


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
    def get_schema_check_sql(self, schema_name: str):
        """Return the SQL to check if a schema exists"""
        pass

    @abstractmethod
    def get_table_check_sql(self, table_name: str, schema_name: str):
        """Return the SQL to check if a table exists"""
        pass

    @abstractmethod
    def get_delete_day_by_manifestid_sql(
        self, schema_name: str, table_name: str, source: str, year: str, month: str, manifestid: str
    ):
        """Return the SQL to delete data where manifestid doesn't match"""
        pass

    @abstractmethod
    def get_delete_day_by_reportnumhours_sql(
        self,
        schema_name: str,
        table_name: str,
        source: str,
        year: str,
        month: str,
        start_date: str,
        reportnumhours: int,
    ):
        """Return the SQL to delete a day's data where reportnumhours is less than specified value"""
        pass

    @abstractmethod
    def get_check_day_exists_sql(
        self, schema_name: str, table_name: str, source: str, year: str, month: str, start_date: str
    ):
        """Return the SQL to check if data exists for a specific day"""
        pass

    @abstractmethod
    def get_delete_by_month_sql(
        self, schema_name: str, table_name: str, source_column: str, source: str, year: str, month: str
    ):
        """Return the SQL to delete partitions by month"""
        pass

    @abstractmethod
    def get_delete_by_day_sql(
        self, schema_name: str, table_name: str, source_column: str, source: str, year: str, month: str, day: str
    ):
        """Return the SQL to delete partitions by day"""
        pass

    @abstractmethod
    def get_delete_by_source_sql(self, schema_name: str, table_name: str, partition_column: str, provider_uuid: str):
        """Return the SQL to delete partitions by source"""
        pass

    @abstractmethod
    def get_expired_data_ocp_sql(self, schema_name: str, table_name: str, source_column: str, expired_date: str):
        """Return SQL to find expired data (year, month, source) tuples before expired_date"""
        pass

    @abstractmethod
    def get_check_source_in_partitions_sql(self, schema_name: str, table_name: str, source_uuid: str):
        """Return SQL to check if source exists in table partitions"""
        pass

    @abstractmethod
    def get_nodes_query_sql(
        self, schema_name: str, source_uuid: str, year: str, month: str, start_date: str, end_date: str
    ):
        """Return SQL to get nodes from OpenShift cluster"""
        pass

    @abstractmethod
    def get_pvcs_query_sql(
        self, schema_name: str, source_uuid: str, year: str, month: str, start_date: str, end_date: str
    ):
        """Return SQL to get PVCs from OpenShift cluster"""
        pass

    @abstractmethod
    def get_projects_query_sql(
        self, schema_name: str, source_uuid: str, year: str, month: str, start_date: str, end_date: str
    ):
        """Return SQL to get projects from OpenShift cluster"""
        pass

    @abstractmethod
    def get_max_min_timestamp_sql(
        self, schema_name: str, source_uuid: str, year: str, month: str, start_date: str, end_date: str
    ):
        """Return SQL to get max/min timestamps from parquet data"""
        pass

    @abstractmethod
    def get_delete_by_day_ocp_on_cloud_sql(
        self, schema_name: str, table_name: str, cloud_source: str, ocp_source: str, year: str, month: str, day: str
    ):
        """Return SQL to delete partitions by day for OCP-on-cloud tables (with dual source columns)"""
        pass

    @abstractmethod
    def get_gcp_topology_sql(
        self, schema_name: str, source_uuid: str, year: str, month: str, start_date: str, end_date: str
    ):
        """Return SQL to get GCP topology (account, project, service, region)"""
        pass

    @abstractmethod
    def get_data_validation_sql(
        self,
        schema_name: str,
        table_name: str,
        source_column: str,
        provider_filter: str,
        metric: str,
        date_column: str,
        start_date: str,
        end_date: str,
        year: str,
        month: str,
    ):
        """Return SQL for data validation query (sum metric by date)"""
        pass

    @abstractmethod
    def get_bind_param_style(self):
        """
        Return the parameter binding style for this database.

        Returns:
            str: 'qmark' for Trino (? placeholders), 'pyformat' for PostgreSQL (%s placeholders)
        """
        pass


def get_report_db_accessor():
    from django.conf import settings
    from koku.reportdb_accessor_postgres import PostgresReportDBAccessor
    from koku.reportdb_accessor_trino import TrinoReportDBAccessor

    if settings.ONPREM:
        return PostgresReportDBAccessor()
    else:
        return TrinoReportDBAccessor()
