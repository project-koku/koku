#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Database accessor for Azure report data."""
import json
import logging
import pkgutil
import uuid

from dateutil.parser import parse
from django.conf import settings
from django.db import connection
from django.db.models import F
from django_tenants.utils import schema_context
from trino.exceptions import TrinoExternalError

from api.common import log_json
from api.models import Provider
from koku.database import get_model
from koku.database import SQLScriptAtomicExecutorMixin
from masu.config import Config
from masu.database import AZURE_REPORT_TABLE_MAP
from masu.database import OCP_REPORT_TABLE_MAP
from masu.database.report_db_accessor_base import ReportDBAccessorBase
from reporting.models import OCP_ON_ALL_PERSPECTIVES
from reporting.models import OCP_ON_AZURE_PERSPECTIVES
from reporting.models import OCPAllCostLineItemDailySummaryP
from reporting.models import OCPAllCostLineItemProjectDailySummaryP
from reporting.models import OCPAzureCostLineItemProjectDailySummaryP
from reporting.provider.azure.models import AzureCostEntryBill
from reporting.provider.azure.models import AzureCostEntryLineItemDailySummary
from reporting.provider.azure.models import TRINO_LINE_ITEM_TABLE
from reporting.provider.azure.models import UI_SUMMARY_TABLES
from reporting.provider.azure.openshift.models import UI_SUMMARY_TABLES as OCPAZURE_UI_SUMMARY_TABLES


LOG = logging.getLogger(__name__)


class AzureReportDBAccessor(SQLScriptAtomicExecutorMixin, ReportDBAccessorBase):
    """Class to interact with Azure Report reporting tables."""

    def __init__(self, schema):
        """Establish the database connection.

        Args:
            schema (str): The customer schema to associate with
        """
        super().__init__(schema)
        self._datetime_format = Config.AZURE_DATETIME_STR_FORMAT
        self._table_map = AZURE_REPORT_TABLE_MAP

    @property
    def line_item_daily_summary_table(self):
        return AzureCostEntryLineItemDailySummary

    @property
    def ocpall_line_item_daily_summary_table(self):
        return get_model("OCPAllCostLineItemDailySummaryP")

    @property
    def ocpall_line_item_project_daily_summary_table(self):
        return get_model("OCPAllCostLineItemProjectDailySummaryP")

    def get_cost_entry_bills_query_by_provider(self, provider_uuid):
        """Return all cost entry bills for the specified provider."""
        table_name = AzureCostEntryBill
        with schema_context(self.schema):
            return self._get_db_obj_query(table_name).filter(provider_id=provider_uuid)

    def bills_for_provider_uuid(self, provider_uuid, start_date=None):
        """Return all cost entry bills for provider_uuid on date."""
        bills = self.get_cost_entry_bills_query_by_provider(provider_uuid)
        if start_date:
            if isinstance(start_date, str):
                start_date = parse(start_date)
            bill_date = start_date.replace(day=1)
            bills = bills.filter(billing_period_start=bill_date)
        return bills

    def populate_line_item_daily_summary_table_trino(self, start_date, end_date, source_uuid, bill_id, markup_value):
        """Populate the daily aggregated summary of line items table.

        Args:
            start_date (datetime.date) The date to start populating the table.
            end_date (datetime.date) The date to end on.

        Returns
            (None)

        """
        sql = pkgutil.get_data("masu.database", "trino_sql/reporting_azurecostentrylineitem_daily_summary.sql")
        sql = sql.decode("utf-8")
        uuid_str = str(uuid.uuid4()).replace("-", "_")
        sql_params = {
            "uuid": uuid_str,
            "start_date": start_date,
            "end_date": end_date,
            "schema": self.schema,
            "table": TRINO_LINE_ITEM_TABLE,
            "source_uuid": source_uuid,
            "year": start_date.strftime("%Y"),
            "month": start_date.strftime("%m"),
            "bill_id": bill_id,
            "markup": markup_value or 0,
        }

        self._execute_trino_raw_sql_query(
            sql, sql_params=sql_params, log_ref="reporting_azurecostentrylineitem_daily_summary.sql"
        )

    def populate_tags_summary_table(self, bill_ids, start_date, end_date):
        """Populate the line item aggregated totals data table."""
        table_name = self._table_map["tags_summary"]

        sql = pkgutil.get_data("masu.database", "sql/reporting_azuretags_summary.sql")
        sql = sql.decode("utf-8")
        sql_params = {"schema": self.schema, "bill_ids": bill_ids, "start_date": start_date, "end_date": end_date}
        self._prepare_and_execute_raw_sql_query(table_name, sql, sql_params)

    def populate_markup_cost(self, provider_uuid, markup, start_date, end_date, bill_ids=None):
        """Set markup costs in the database."""
        with schema_context(self.schema):
            if bill_ids and start_date and end_date:
                date_filters = {"usage_start__gte": start_date, "usage_start__lte": end_date}
            else:
                date_filters = {}

            MARKUP_MODELS_BILL = (AzureCostEntryLineItemDailySummary, OCPAzureCostLineItemProjectDailySummaryP)
            OCPALL_MARKUP = (OCPAllCostLineItemDailySummaryP, *OCP_ON_ALL_PERSPECTIVES)

            for bill_id in bill_ids:
                for markup_model in MARKUP_MODELS_BILL:
                    markup_model.objects.filter(cost_entry_bill_id=bill_id, **date_filters).update(
                        markup_cost=(F("pretax_cost") * markup)
                    )

                for ocpazure_model in OCP_ON_AZURE_PERSPECTIVES:
                    ocpazure_model.objects.filter(source_uuid=provider_uuid, **date_filters).update(
                        markup_cost=(F("pretax_cost") * markup)
                    )

                OCPAllCostLineItemProjectDailySummaryP.objects.filter(
                    source_uuid=provider_uuid, source_type=Provider.PROVIDER_AZURE, **date_filters
                ).update(project_markup_cost=(F("pod_cost") * markup))

                for markup_model in OCPALL_MARKUP:
                    markup_model.objects.filter(
                        source_uuid=provider_uuid, source_type=Provider.PROVIDER_AZURE, **date_filters
                    ).update(markup_cost=(F("unblended_cost") * markup))

    def get_bill_query_before_date(self, date, provider_uuid=None):
        """Get the cost entry bill objects with billing period before provided date."""
        table_name = AzureCostEntryBill
        with schema_context(self.schema):
            base_query = self._get_db_obj_query(table_name)
            filters = {"billing_period_start__lte": date}
            if provider_uuid:
                filters["provider_id"] = provider_uuid
            return base_query.filter(**filters)

    def populate_ocp_on_azure_cost_daily_summary(self, start_date, end_date, cluster_id, bill_ids, markup_value):
        """Populate the daily cost aggregated summary for OCP on Azure.

        Args:
            start_date (datetime.date) The date to start populating the table.
            end_date (datetime.date) The date to end on.

        Returns
            (None)

        """
        table_name = self._table_map["ocp_on_azure_daily_summary"]
        sql = pkgutil.get_data("masu.database", "sql/reporting_ocpazurecostlineitem_daily_summary.sql")
        sql = sql.decode("utf-8")
        sql_params = {
            "uuid": str(uuid.uuid4()).replace("-", "_"),
            "start_date": start_date,
            "end_date": end_date,
            "bill_ids": bill_ids,
            "cluster_id": cluster_id,
            "schema": self.schema,
            "markup": markup_value or 0,
        }
        self._prepare_and_execute_raw_sql_query(table_name, sql, sql_params)

    def populate_ocp_on_azure_tags_summary_table(self, bill_ids, start_date, end_date):
        """Populate the line item aggregated totals data table."""
        table_name = self._table_map["ocp_on_azure_tags_summary"]

        sql = pkgutil.get_data("masu.database", "sql/reporting_ocpazuretags_summary.sql")
        sql = sql.decode("utf-8")
        sql_params = {"schema": self.schema, "bill_ids": bill_ids, "start_date": start_date, "end_date": end_date}
        self._prepare_and_execute_raw_sql_query(table_name, sql, sql_params)

    def populate_ui_summary_tables(self, start_date, end_date, source_uuid, tables=UI_SUMMARY_TABLES):
        """Populate our UI summary tables (formerly materialized views)."""
        for table_name in tables:
            sql = pkgutil.get_data("masu.database", f"sql/azure/{table_name}.sql")
            sql = sql.decode("utf-8")
            sql_params = {
                "start_date": start_date,
                "end_date": end_date,
                "schema": self.schema,
                "source_uuid": source_uuid,
            }
            self._prepare_and_execute_raw_sql_query(table_name, sql, sql_params, operation="DELETE/INSERT")

    def populate_ocp_on_azure_ui_summary_tables(self, sql_params, tables=OCPAZURE_UI_SUMMARY_TABLES):
        """Populate our UI summary tables (formerly materialized views)."""
        for table_name in tables:
            sql = pkgutil.get_data("masu.database", f"sql/azure/openshift/{table_name}.sql")
            sql = sql.decode("utf-8")
            self._prepare_and_execute_raw_sql_query(table_name, sql, sql_params)

    def populate_ocp_on_azure_ui_summary_tables_trino(
        self, start_date, end_date, openshift_provider_uuid, azure_provider_uuid, tables=OCPAZURE_UI_SUMMARY_TABLES
    ):
        """Populate our UI summary tables (formerly materialized views)."""
        year = start_date.strftime("%Y")
        month = start_date.strftime("%m")
        days = self.date_helper.list_days(start_date, end_date)
        days_tup = tuple(str(day.day) for day in days)

        for table_name in tables:
            sql = pkgutil.get_data("masu.database", f"trino_sql/azure/openshift/{table_name}.sql")
            sql = sql.decode("utf-8")
            sql_params = {
                "schema_name": self.schema,
                "start_date": start_date,
                "end_date": end_date,
                "year": year,
                "month": month,
                "days": days_tup,
                "azure_source_uuid": azure_provider_uuid,
                "ocp_source_uuid": openshift_provider_uuid,
            }
            self._execute_trino_raw_sql_query(sql, sql_params=sql_params, log_ref=f"{table_name}.sql")

    def delete_ocp_on_azure_hive_partition_by_day(self, days, az_source, ocp_source, year, month):
        """Deletes partitions individually for each day in days list."""
        table = "reporting_ocpazurecostlineitem_project_daily_summary"
        retries = settings.HIVE_PARTITION_DELETE_RETRIES
        if self.schema_exists_trino() and self.table_exists_trino(table):
            LOG.info(
                log_json(
                    msg="deleting Hive partitions by day",
                    schema=self.schema,
                    ocp_source=ocp_source,
                    azure_source=az_source,
                    table=table,
                    year=year,
                    month=month,
                    days=days,
                )
            )
            for day in days:
                for i in range(retries):
                    try:
                        sql = f"""
                            DELETE FROM hive.{self.schema}.{table}
                                WHERE azure_source = '{az_source}'
                                AND ocp_source = '{ocp_source}'
                                AND year = '{year}'
                                AND (month = replace(ltrim(replace('{month}', '0', ' ')),' ', '0') OR month = '{month}')
                                AND day = '{day}'"""
                        self._execute_trino_raw_sql_query(
                            sql,
                            log_ref=f"delete_ocp_on_azure_hive_partition_by_day for {year}-{month}-{day}",
                            attempts_left=(retries - 1) - i,
                        )
                        break
                    except TrinoExternalError as err:
                        if err.error_name == "HIVE_METASTORE_ERROR" and i < (retries - 1):
                            continue
                        else:
                            raise err

    def populate_ocp_on_azure_cost_daily_summary_trino(
        self,
        start_date,
        end_date,
        openshift_provider_uuid,
        azure_provider_uuid,
        report_period_id,
        bill_id,
        markup_value,
        distribution,
    ):
        """Populate the daily cost aggregated summary for OCP on Azure."""
        year = start_date.strftime("%Y")
        month = start_date.strftime("%m")
        tables = [
            "reporting_ocpazurecostlineitem_project_daily_summary_temp",
            "azure_openshift_daily_resource_matched_temp",
            "azure_openshift_daily_tag_matched_temp",
        ]
        for table in tables:
            self.delete_hive_partition_by_month(table, openshift_provider_uuid, year, month)
        days = self.date_helper.list_days(start_date, end_date)
        days_tup = tuple(str(day.day) for day in days)
        self.delete_ocp_on_azure_hive_partition_by_day(
            days_tup, azure_provider_uuid, openshift_provider_uuid, year, month
        )

        # default to cpu distribution
        pod_column = "pod_effective_usage_cpu_core_hours"
        node_column = "node_capacity_cpu_core_hours"
        if distribution == "memory":
            pod_column = "pod_effective_usage_memory_gigabyte_hours"
            node_column = "node_capacity_memory_gigabyte_hours"

        sql = pkgutil.get_data("masu.database", "trino_sql/reporting_ocpazurecostlineitem_daily_summary.sql")
        sql = sql.decode("utf-8")
        sql_params = {
            "uuid": str(openshift_provider_uuid).replace("-", "_"),
            "schema": self.schema,
            "start_date": start_date,
            "end_date": end_date,
            "year": year,
            "month": month,
            "days": days_tup,
            "azure_source_uuid": azure_provider_uuid,
            "ocp_source_uuid": openshift_provider_uuid,
            "report_period_id": report_period_id,
            "bill_id": bill_id,
            "markup": markup_value or 0,
            "pod_column": pod_column,
            "node_column": node_column,
        }
        ctx = self.extract_context_from_sql_params(sql_params)
        LOG.info(log_json(msg="running OCP on Azure SQL", context=ctx))
        self._execute_trino_multipart_sql_query(sql, bind_params=sql_params)

    def populate_enabled_tag_keys(self, start_date, end_date, bill_ids):
        """Populate the enabled tag key table.
        Args:
            start_date (datetime.date) The date to start populating the table.
            end_date (datetime.date) The date to end on.
            bill_ids (list) A list of bill IDs.
        Returns
            (None)
        """
        table_name = "reporting_enabledtagkeys"
        sql = pkgutil.get_data("masu.database", "sql/reporting_azureenabledtagkeys.sql")
        sql = sql.decode("utf-8")
        sql_params = {
            "start_date": start_date,
            "end_date": end_date,
            "bill_ids": bill_ids,
            "schema": self.schema,
        }
        self._prepare_and_execute_raw_sql_query(table_name, sql, sql_params)

    def update_line_item_daily_summary_with_enabled_tags(self, start_date, end_date, bill_ids):
        """Populate the enabled tag key table.
        Args:
            start_date (datetime.date) The date to start populating the table.
            end_date (datetime.date) The date to end on.
            bill_ids (list) A list of bill IDs.
        Returns
            (None)
        """
        table_name = self._table_map["line_item_daily_summary"]
        sql = pkgutil.get_data(
            "masu.database", "sql/reporting_azurecostentryline_item_daily_summary_update_enabled_tags.sql"
        )
        sql = sql.decode("utf-8")
        sql_params = {
            "start_date": start_date,
            "end_date": end_date,
            "bill_ids": bill_ids,
            "schema": self.schema,
        }
        self._prepare_and_execute_raw_sql_query(table_name, sql, sql_params)

    def get_openshift_on_cloud_matched_tags(self, azure_bill_id):
        """Return a list of matched tags."""
        sql = pkgutil.get_data("masu.database", "sql/reporting_ocpazure_matched_tags.sql")
        sql = sql.decode("utf-8")
        sql_params = {"bill_id": azure_bill_id, "schema": self.schema}
        sql, bind_params = self.prepare_query(sql, sql_params)
        with connection.cursor() as cursor:
            cursor.db.set_schema(self.schema)
            cursor.execute(sql, params=bind_params)
            results = cursor.fetchall()

        return [json.loads(result[0]) for result in results]

    def get_openshift_on_cloud_matched_tags_trino(
        self, azure_source_uuid, ocp_source_uuids, start_date, end_date, **kwargs
    ):
        """Return a list of matched tags."""
        sql = pkgutil.get_data("masu.database", "trino_sql/reporting_ocpazure_matched_tags.sql")
        sql = sql.decode("utf-8")

        days = self.date_helper.list_days(start_date, end_date)

        sql_params = {
            "start_date": start_date,
            "end_date": end_date,
            "schema": self.schema,
            "azure_source_uuid": azure_source_uuid,
            "ocp_source_uuids": ocp_source_uuids,
            "year": start_date.strftime("%Y"),
            "month": start_date.strftime("%m"),
            "days": tuple(str(day.day) for day in days),
        }

        results = self._execute_trino_raw_sql_query(
            sql, sql_params=sql_params, log_ref="reporting_ocpazure_matched_tags.sql"
        )

        return [json.loads(result[0]) for result in results]

    def back_populate_ocp_infrastructure_costs(self, start_date, end_date, report_period_id):
        """Populate the OCP on Azure and OCP daily summary tables. after populating the project table via trino."""
        table_name = OCP_REPORT_TABLE_MAP["line_item_daily_summary"]

        sql = pkgutil.get_data("masu.database", "sql/reporting_ocpazure_ocp_infrastructure_back_populate.sql")
        sql = sql.decode("utf-8")
        sql_params = {
            "schema": self.schema,
            "start_date": start_date,
            "end_date": end_date,
            "report_period_id": report_period_id,
        }
        self._prepare_and_execute_raw_sql_query(table_name, sql, sql_params)

    def check_for_matching_enabled_keys(self):
        """
        Checks the enabled tag keys for matching keys.
        """
        match_sql = f"""
            SELECT COUNT(*) FROM (SELECT COUNT(provider_type) AS p_count FROM
                {self.schema}.reporting_enabledtagkeys WHERE enabled=True AND provider_type IN ('Azure', 'OCP')
                GROUP BY key) AS c WHERE c.p_count > 1;
        """
        with connection.cursor() as cursor:
            cursor.db.set_schema(self.schema)
            cursor.execute(match_sql)
            results = cursor.fetchall()
            if results[0][0] < 1:
                LOG.info(log_json(msg="no matching enabled keys for OCP on Azure", schema=self.schema))
                return False
        return True
