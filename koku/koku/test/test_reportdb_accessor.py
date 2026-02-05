#
# Copyright 2025 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tests for report database accessors."""
from django.test import TestCase
from django.test.utils import override_settings

from koku.reportdb_accessor import get_report_db_accessor
from koku.reportdb_accessor_postgres import PostgresReportDBAccessor


class TestGetReportDBAccessor(TestCase):
    """Test get_report_db_accessor factory function."""

    @override_settings(ONPREM=True)
    def test_returns_postgres_accessor_when_onprem(self):
        """Test that PostgresReportDBAccessor is returned when ONPREM=True."""
        accessor = get_report_db_accessor()
        self.assertIsInstance(accessor, PostgresReportDBAccessor)

    @override_settings(ONPREM=False)
    def test_returns_trino_accessor_when_not_onprem(self):
        """Test that TrinoReportDBAccessor is returned when ONPREM=False."""
        from koku.reportdb_accessor_trino import TrinoReportDBAccessor

        accessor = get_report_db_accessor()
        self.assertIsInstance(accessor, TrinoReportDBAccessor)


class TestPostgresReportDBAccessor(TestCase):
    """Test PostgresReportDBAccessor methods."""

    def setUp(self):
        self.accessor = PostgresReportDBAccessor()
        self.schema_name = "test_schema"
        self.table_name = "test_table"
        self.source_uuid = "12345678-1234-1234-1234-123456789012"

    def test_get_schema_check_sql(self):
        """Test schema check SQL generation."""
        sql = self.accessor.get_schema_check_sql(self.schema_name)
        self.assertIn("information_schema.schemata", sql)
        self.assertIn(self.schema_name, sql)

    def test_get_table_check_sql(self):
        """Test table check SQL generation."""
        sql = self.accessor.get_table_check_sql(self.table_name, self.schema_name)
        self.assertIn("information_schema.tables", sql)
        self.assertIn(self.table_name, sql)
        self.assertIn(self.schema_name, sql)

    def test_get_delete_day_by_manifestid_sql(self):
        """Test delete by manifest ID SQL generation."""
        sql = self.accessor.get_delete_day_by_manifestid_sql(
            self.schema_name, self.table_name, self.source_uuid, "2024", "01", "123"
        )
        self.assertIn("DELETE FROM", sql)
        self.assertIn("manifestid != '123'", sql)

    def test_get_delete_day_by_reportnumhours_sql(self):
        """Test delete by reportnumhours SQL generation."""
        sql = self.accessor.get_delete_day_by_reportnumhours_sql(
            self.schema_name,
            self.table_name,
            self.source_uuid,
            "2024",
            "01",
            "2024-01-15",
            24,
        )
        self.assertIn("DELETE FROM", sql)
        self.assertIn("reportnumhours < 24", sql)

    def test_get_check_day_exists_sql(self):
        """Test check day exists SQL generation."""
        sql = self.accessor.get_check_day_exists_sql(
            self.schema_name,
            self.table_name,
            self.source_uuid,
            "2024",
            "01",
            "2024-01-15",
        )
        self.assertIn("SELECT 1", sql)
        self.assertIn("LIMIT 1", sql)

    def test_get_delete_by_month_sql(self):
        """Test delete by month SQL generation."""
        sql = self.accessor.get_delete_by_month_sql(
            self.schema_name, self.table_name, "ocp_source", self.source_uuid, "2024", "01"
        )
        self.assertIn("DELETE FROM", sql)
        self.assertIn("year = '2024'", sql)

    def test_get_delete_by_day_sql(self):
        """Test delete by day SQL generation."""
        sql = self.accessor.get_delete_by_day_sql(
            self.schema_name, self.table_name, "ocp_source", self.source_uuid, "2024", "01", "15"
        )
        self.assertIn("DELETE FROM", sql)
        self.assertIn("day = '15'", sql)

    def test_get_delete_by_source_sql(self):
        """Test delete by source SQL generation."""
        sql = self.accessor.get_delete_by_source_sql(self.schema_name, self.table_name, "source", self.source_uuid)
        self.assertIn("DELETE FROM", sql)
        self.assertIn(self.source_uuid, sql)

    def test_get_bind_param_style(self):
        """Test bind parameter style."""
        self.assertEqual(self.accessor.get_bind_param_style(), "pyformat")

    def test_get_expired_data_ocp_sql(self):
        """Test expired data OCP SQL generation."""
        sql = self.accessor.get_expired_data_ocp_sql(self.schema_name, self.table_name, "ocp_source", "2024-01-01")
        self.assertIn("SELECT DISTINCT", sql)
        self.assertIn("usage_start <", sql)

    def test_get_check_source_in_partitions_sql(self):
        """Test check source in partitions SQL generation."""
        sql = self.accessor.get_check_source_in_partitions_sql(self.schema_name, self.table_name, self.source_uuid)
        self.assertIn("count(*)", sql)
        self.assertIn(self.source_uuid, sql)

    def test_get_nodes_query_sql(self):
        """Test nodes query SQL generation."""
        sql = self.accessor.get_nodes_query_sql(
            self.schema_name, self.source_uuid, "2024", "01", "2024-01-01", "2024-01-31"
        )
        self.assertIn("node", sql)
        self.assertIn("resource_id", sql)

    def test_get_pvcs_query_sql(self):
        """Test PVCs query SQL generation."""
        sql = self.accessor.get_pvcs_query_sql(
            self.schema_name, self.source_uuid, "2024", "01", "2024-01-01", "2024-01-31"
        )
        self.assertIn("persistentvolume", sql)
        self.assertIn("persistentvolumeclaim", sql)

    def test_get_projects_query_sql(self):
        """Test projects query SQL generation."""
        sql = self.accessor.get_projects_query_sql(
            self.schema_name, self.source_uuid, "2024", "01", "2024-01-01", "2024-01-31"
        )
        self.assertIn("namespace", sql)

    def test_get_max_min_timestamp_sql(self):
        """Test max/min timestamp SQL generation."""
        sql = self.accessor.get_max_min_timestamp_sql(
            self.schema_name, self.source_uuid, "2024", "01", "2024-01-01", "2024-01-31"
        )
        self.assertIn("min(interval_start)", sql)
        self.assertIn("max(interval_start)", sql)

    def test_get_gcp_topology_sql(self):
        """Test GCP topology SQL generation."""
        sql = self.accessor.get_gcp_topology_sql(
            self.schema_name, self.source_uuid, "2024", "01", "2024-01-01", "2024-01-31"
        )
        self.assertIn("billing_account_id", sql)
        self.assertIn("project_id", sql)

    def test_get_data_validation_sql(self):
        """Test data validation SQL generation."""
        sql = self.accessor.get_data_validation_sql(
            self.schema_name,
            self.table_name,
            "source",
            self.source_uuid,
            "usage_amount",
            "usage_start",
            "2024-01-01",
            "2024-01-31",
            "2024",
            "01",
        )
        self.assertIn("sum(usage_amount)", sql)

    def test_get_delete_by_day_ocp_on_cloud_sql(self):
        """Test delete by day OCP on cloud SQL generation."""
        sql = self.accessor.get_delete_by_day_ocp_on_cloud_sql(
            self.schema_name,
            self.table_name,
            self.source_uuid,
            "ocp-source-uuid",
            "2024",
            "01",
            "15",
        )
        self.assertIn("DELETE FROM", sql)
        self.assertIn("ocp_source", sql)
