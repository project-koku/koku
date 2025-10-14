#
# Copyright 2025 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Database accessor specifically for unit tests to mimic the trino logic."""
import pkgutil

from koku.database import SQLScriptAtomicExecutorMixin
from masu.database import OCP_REPORT_TABLE_MAP
from masu.database.ocp_report_db_accessor import OCPReportDBAccessor
from masu.database.report_db_accessor_base import ReportDBAccessorBase
from reporting.provider.aws.openshift.models import UI_SUMMARY_TABLES as OCPAWS_UI_SUMMARY_TABLES
from reporting.provider.azure.openshift.models import UI_SUMMARY_TABLES as OCPAZURE_UI_SUMMARY_TABLES
from reporting.provider.gcp.openshift.models import UI_SUMMARY_TABLES as OCPGCP_UI_SUMMARY_TABLES

base_dir = "api.report.test.util"


class ReportDBAccessor(SQLScriptAtomicExecutorMixin, ReportDBAccessorBase):
    """Class to interact with customer reporting tables."""

    def __init__(self, schema):
        """Establish the database connection.

        Args:
            schema (str): The customer schema to associate with
        """
        super().__init__(schema)
        self._table_map = OCP_REPORT_TABLE_MAP

    def populate_unit_test_tag_data(self, report_period_ids, start_date, end_date):
        """
        This method allows us to maintain our tag logic.
        """
        # Remove disabled keys from the tags field.
        with OCPReportDBAccessor(self.schema) as accessor:
            accessor.populate_pod_label_summary_table(report_period_ids, start_date, end_date)
            accessor.populate_volume_label_summary_table(report_period_ids, start_date, end_date)
        table_name = self._table_map["line_item_daily_summary"]
        sql = pkgutil.get_data(base_dir, "sql/openshift/mimic_remove_disabled_tags.sql")
        sql = sql.decode("utf-8")
        sql_params = {
            "start_date": start_date,
            "end_date": end_date,
            "report_period_ids": report_period_ids,
            "schema": self.schema,
        }
        self._prepare_and_execute_raw_sql_query(table_name, sql, sql_params)

    def populate_unit_test_virt_ui_table(self, report_period_ids, start_date, end_date, source_uuid):
        """
        This method populates the vm table
        """
        sql = pkgutil.get_data(base_dir, "sql/openshift/mimic_virt_ui.sql")
        sql = sql.decode("utf-8")
        sql_params = {
            "start_date": start_date,
            "end_date": end_date,
            "report_period_ids": report_period_ids,
            "schema": self.schema,
            "pod_request_cpu_core_hours": 1,
            "pod_request_mem_core_hours": 4,
            "source_uuid": source_uuid,
        }
        self._prepare_and_execute_raw_sql_query("reporting_ocp_vm_summary_p", sql, sql_params)

    def populate_unit_test_ocpaws_ui_summary_tables(self, sql_params, tables=OCPAWS_UI_SUMMARY_TABLES):
        """Populate our UI summary tables (formerly materialized views)."""
        for table_name in tables:
            sql = pkgutil.get_data(base_dir, f"sql/aws/openshift/ui_summary/{table_name}.sql")
            sql = sql.decode("utf-8")
            self._prepare_and_execute_raw_sql_query(table_name, sql, sql_params)

    def populate_unit_test_ocpazure_ui_summary_tables(self, sql_params, tables=OCPAZURE_UI_SUMMARY_TABLES):
        """Populate our UI summary tables (formerly materialized views)."""
        for table_name in tables:
            sql = pkgutil.get_data(base_dir, f"sql/azure/openshift/ui_summary/{table_name}.sql")
            sql = sql.decode("utf-8")
            self._prepare_and_execute_raw_sql_query(table_name, sql, sql_params)

    def populate_unit_test_ocpgcp_ui_summary_tables(self, sql_params, tables=OCPGCP_UI_SUMMARY_TABLES):
        """Populate our UI summary tables (formerly materialized views)."""
        invoice_month_list = self.date_helper.gcp_find_invoice_months_in_date_range(
            sql_params["start_date"], sql_params["end_date"]
        )
        for invoice_month in invoice_month_list:
            for table_name in tables:
                sql_params["invoice_month"] = invoice_month
                sql = pkgutil.get_data(base_dir, f"sql/gcp/openshift/ui_summary/{table_name}.sql")
                sql = sql.decode("utf-8")
                self._prepare_and_execute_raw_sql_query(table_name, sql, sql_params, operation="DELETE/INSERT")
