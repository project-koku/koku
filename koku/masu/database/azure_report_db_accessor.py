#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Database accessor for Azure report data."""
import json
import logging
import pkgutil
import uuid
from datetime import datetime

from dateutil.parser import parse
from django.conf import settings
from django.db import connection
from django.db.models import F
from jinjasql import JinjaSql
from tenant_schemas.utils import schema_context
from trino.exceptions import TrinoExternalError

from api.utils import DateHelper
from koku.database import get_model
from koku.database import SQLScriptAtomicExecutorMixin
from masu.config import Config
from masu.database import AZURE_REPORT_TABLE_MAP
from masu.database.report_db_accessor_base import ReportDBAccessorBase
from masu.external.date_accessor import DateAccessor
from reporting.models import OCP_ON_ALL_PERSPECTIVES
from reporting.models import OCP_ON_AZURE_PERSPECTIVES
from reporting.models import OCPAllCostLineItemDailySummaryP
from reporting.models import OCPAllCostLineItemProjectDailySummaryP
from reporting.models import OCPAzureCostLineItemDailySummaryP
from reporting.provider.azure.models import AzureCostEntryBill
from reporting.provider.azure.models import AzureCostEntryLineItemDaily
from reporting.provider.azure.models import AzureCostEntryLineItemDailySummary
from reporting.provider.azure.models import AzureCostEntryProductService
from reporting.provider.azure.models import AzureMeter
from reporting.provider.azure.models import PRESTO_LINE_ITEM_TABLE
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
        self.date_accessor = DateAccessor()
        self.jinja_sql = JinjaSql()
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

    @property
    def line_item_daily_table(self):
        return AzureCostEntryLineItemDaily

    def get_cost_entry_bills(self):
        """Get all cost entry bill objects."""
        table_name = AzureCostEntryBill
        with schema_context(self.schema):
            columns = ["id", "billing_period_start", "provider_id"]
            bills = self._get_db_obj_query(table_name).values(*columns)
            return {(bill["billing_period_start"], bill["provider_id"]): bill["id"] for bill in bills}

    def get_products(self):
        """Make a mapping of product objects."""
        table_name = AzureCostEntryProductService
        with schema_context(self.schema):
            columns = ["id", "instance_id", "instance_type", "service_name", "service_tier"]
            products = self._get_db_obj_query(table_name, columns=columns).all()

            return {
                (
                    product["instance_id"],
                    product["instance_type"],
                    product["service_tier"],
                    product["service_name"],
                ): product["id"]
                for product in products
            }

    def get_meters(self):
        """Make a mapping of meter objects."""
        table_name = AzureMeter
        with schema_context(self.schema):
            columns = ["id", "meter_id"]
            meters = self._get_db_obj_query(table_name, columns=columns).all()

            return {(meter["meter_id"]): meter["id"] for meter in meters}

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

    def populate_line_item_daily_summary_table(self, start_date, end_date, bill_ids):
        """Populate the daily aggregated summary of line items table.

        Args:
            start_date (datetime.date) The date to start populating the table.
            end_date (datetime.date) The date to end on.

        Returns
            (None)

        """

        _start_date = start_date.date() if isinstance(start_date, datetime) else start_date
        _end_date = end_date.date() if isinstance(end_date, datetime) else end_date

        table_name = self._table_map["line_item_daily_summary"]
        summary_sql = pkgutil.get_data("masu.database", "sql/reporting_azurecostentrylineitem_daily_summary.sql")
        summary_sql = summary_sql.decode("utf-8")
        summary_sql_params = {
            "uuid": str(uuid.uuid4()).replace("-", "_"),
            "start_date": _start_date,
            "end_date": _end_date,
            "bill_ids": bill_ids,
            "schema": self.schema,
        }
        summary_sql, summary_sql_params = self.jinja_sql.prepare_query(summary_sql, summary_sql_params)
        self._execute_raw_sql_query(
            table_name, summary_sql, start_date, end_date, bind_params=list(summary_sql_params)
        )

    def populate_line_item_daily_summary_table_presto(self, start_date, end_date, source_uuid, bill_id, markup_value):
        """Populate the daily aggregated summary of line items table.

        Args:
            start_date (datetime.date) The date to start populating the table.
            end_date (datetime.date) The date to end on.

        Returns
            (None)

        """
        summary_sql = pkgutil.get_data(
            "masu.database", "presto_sql/reporting_azurecostentrylineitem_daily_summary.sql"
        )
        summary_sql = summary_sql.decode("utf-8")
        uuid_str = str(uuid.uuid4()).replace("-", "_")
        summary_sql_params = {
            "uuid": uuid_str,
            "start_date": start_date,
            "end_date": end_date,
            "schema": self.schema,
            "table": PRESTO_LINE_ITEM_TABLE,
            "source_uuid": source_uuid,
            "year": start_date.strftime("%Y"),
            "month": start_date.strftime("%m"),
            "bill_id": bill_id,
            "markup": markup_value if markup_value else 0,
        }
        summary_sql, summary_sql_params = self.jinja_sql.prepare_query(summary_sql, summary_sql_params)

        self._execute_presto_raw_sql_query(
            self.schema, summary_sql, log_ref="reporting_azurecostentrylineitem_daily_summary.sql"
        )

    def populate_tags_summary_table(self, bill_ids, start_date, end_date):
        """Populate the line item aggregated totals data table."""
        table_name = self._table_map["tags_summary"]

        agg_sql = pkgutil.get_data("masu.database", "sql/reporting_azuretags_summary.sql")
        agg_sql = agg_sql.decode("utf-8")
        agg_sql_params = {"schema": self.schema, "bill_ids": bill_ids, "start_date": start_date, "end_date": end_date}
        agg_sql, agg_sql_params = self.jinja_sql.prepare_query(agg_sql, agg_sql_params)
        self._execute_raw_sql_query(table_name, agg_sql, bind_params=list(agg_sql_params))

    def get_cost_entry_bills_by_date(self, start_date):
        """Return a cost entry bill for the specified start date."""
        table_name = AzureCostEntryBill
        with schema_context(self.schema):
            return self._get_db_obj_query(table_name).filter(billing_period_start=start_date)

    def populate_markup_cost(self, provider_uuid, markup, start_date, end_date, bill_ids=None):
        """Set markup costs in the database."""
        with schema_context(self.schema):
            if bill_ids and start_date and end_date:
                date_filters = {"usage_start__gte": start_date, "usage_start__lte": end_date}
            else:
                date_filters = {}

            MARKUP_MODELS_BILL = (AzureCostEntryLineItemDailySummary, OCPAzureCostLineItemDailySummaryP)
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
                    source_uuid=provider_uuid, source_type="Azure", **date_filters
                ).update(project_markup_cost=(F("pod_cost") * markup))

                for markup_model in OCPALL_MARKUP:
                    markup_model.objects.filter(source_uuid=provider_uuid, source_type="Azure", **date_filters).update(
                        markup_cost=(F("unblended_cost") * markup)
                    )

    def get_bill_query_before_date(self, date, provider_uuid=None):
        """Get the cost entry bill objects with billing period before provided date."""
        table_name = AzureCostEntryBill
        with schema_context(self.schema):
            base_query = self._get_db_obj_query(table_name)
            if provider_uuid:
                cost_entry_bill_query = base_query.filter(billing_period_start__lte=date, provider_id=provider_uuid)
            else:
                cost_entry_bill_query = base_query.filter(billing_period_start__lte=date)
            return cost_entry_bill_query

    def get_lineitem_query_for_billid(self, bill_id):
        """Get the Azure cost entry line item for a given bill query."""
        table_name = AzureCostEntryLineItemDaily
        with schema_context(self.schema):
            base_query = self._get_db_obj_query(table_name)
            line_item_query = base_query.filter(cost_entry_bill_id=bill_id)
            return line_item_query

    def get_summary_query_for_billid(self, bill_id):
        """Get the Azure cost summary item for a given bill query."""
        table_name = AzureCostEntryLineItemDailySummary
        with schema_context(self.schema):
            base_query = self._get_db_obj_query(table_name)
            summary_item_query = base_query.filter(cost_entry_bill_id=bill_id)
            return summary_item_query

    def populate_ocp_on_azure_cost_daily_summary(self, start_date, end_date, cluster_id, bill_ids, markup_value):
        """Populate the daily cost aggregated summary for OCP on Azure.

        Args:
            start_date (datetime.date) The date to start populating the table.
            end_date (datetime.date) The date to end on.

        Returns
            (None)

        """
        table_name = self._table_map["ocp_on_azure_daily_summary"]
        summary_sql = pkgutil.get_data("masu.database", "sql/reporting_ocpazurecostlineitem_daily_summary.sql")
        summary_sql = summary_sql.decode("utf-8")
        summary_sql_params = {
            "uuid": str(uuid.uuid4()).replace("-", "_"),
            "start_date": start_date,
            "end_date": end_date,
            "bill_ids": bill_ids,
            "cluster_id": cluster_id,
            "schema": self.schema,
            "markup": markup_value,
        }
        summary_sql, summary_sql_params = self.jinja_sql.prepare_query(summary_sql, summary_sql_params)

        self._execute_raw_sql_query(
            table_name, summary_sql, start_date, end_date, bind_params=list(summary_sql_params)
        )

    def populate_ocp_on_azure_tags_summary_table(self, bill_ids, start_date, end_date):
        """Populate the line item aggregated totals data table."""
        table_name = self._table_map["ocp_on_azure_tags_summary"]

        agg_sql = pkgutil.get_data("masu.database", "sql/reporting_ocpazuretags_summary.sql")
        agg_sql = agg_sql.decode("utf-8")
        agg_sql_params = {"schema": self.schema, "bill_ids": bill_ids, "start_date": start_date, "end_date": end_date}
        agg_sql, agg_sql_params = self.jinja_sql.prepare_query(agg_sql, agg_sql_params)
        self._execute_raw_sql_query(table_name, agg_sql, bind_params=list(agg_sql_params))

    def populate_ui_summary_tables(self, start_date, end_date, source_uuid, tables=UI_SUMMARY_TABLES):
        """Populate our UI summary tables (formerly materialized views)."""
        for table_name in tables:
            summary_sql = pkgutil.get_data("masu.database", f"sql/azure/{table_name}.sql")
            summary_sql = summary_sql.decode("utf-8")
            summary_sql_params = {
                "start_date": start_date,
                "end_date": end_date,
                "schema": self.schema,
                "source_uuid": source_uuid,
            }
            summary_sql, summary_sql_params = self.jinja_sql.prepare_query(summary_sql, summary_sql_params)
            self._execute_raw_sql_query(
                table_name,
                summary_sql,
                start_date,
                end_date,
                bind_params=list(summary_sql_params),
                operation="DELETE/INSERT",
            )

    def populate_ocp_on_azure_ui_summary_tables(self, sql_params, tables=OCPAZURE_UI_SUMMARY_TABLES):
        """Populate our UI summary tables (formerly materialized views)."""
        for table_name in tables:
            summary_sql = pkgutil.get_data("masu.database", f"sql/azure/openshift/{table_name}.sql")
            summary_sql = summary_sql.decode("utf-8")
            summary_sql, summary_sql_params = self.jinja_sql.prepare_query(summary_sql, sql_params)
            self._execute_raw_sql_query(table_name, summary_sql, bind_params=list(summary_sql_params))

    def delete_ocp_on_azure_hive_partition_by_day(self, days, az_source, ocp_source, year, month):
        """Deletes partitions individually for each day in days list."""
        table = "reporting_ocpazurecostlineitem_project_daily_summary"
        retries = settings.HIVE_PARTITION_DELETE_RETRIES
        if self.table_exists_trino(table):
            LOG.info(
                "Deleting Hive partitions for the following: \n\tSchema: %s "
                "\n\tOCP Source: %s \n\tAzure Source: %s \n\tTable: %s \n\tYear-Month: %s-%s \n\tDays: %s",
                self.schema,
                ocp_source,
                az_source,
                table,
                year,
                month,
                days,
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
                        self._execute_presto_raw_sql_query(
                            self.schema,
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

    def populate_ocp_on_azure_cost_daily_summary_presto(
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
        days = DateHelper().list_days(start_date, end_date)
        days_str = "','".join([str(day.day) for day in days])
        days_list = [str(day.day) for day in days]
        self.delete_ocp_on_azure_hive_partition_by_day(
            days_list, azure_provider_uuid, openshift_provider_uuid, year, month
        )

        # default to cpu distribution
        pod_column = "pod_effective_usage_cpu_core_hours"
        node_column = "node_capacity_cpu_core_hours"
        if distribution == "memory":
            pod_column = "pod_effective_usage_memory_gigabyte_hours"
            node_column = "node_capacity_memory_gigabyte_hours"

        summary_sql = pkgutil.get_data("masu.database", "presto_sql/reporting_ocpazurecostlineitem_daily_summary.sql")
        summary_sql = summary_sql.decode("utf-8")
        summary_sql_params = {
            "uuid": str(openshift_provider_uuid).replace("-", "_"),
            "schema": self.schema,
            "start_date": start_date,
            "end_date": end_date,
            "year": year,
            "month": month,
            "days": days_str,
            "azure_source_uuid": azure_provider_uuid,
            "ocp_source_uuid": openshift_provider_uuid,
            "report_period_id": report_period_id,
            "bill_id": bill_id,
            "markup": markup_value,
            "pod_column": pod_column,
            "node_column": node_column,
        }
        LOG.info("Running OCP on Azure SQL with params:")
        LOG.info(summary_sql_params)
        self._execute_presto_multipart_sql_query(self.schema, summary_sql, bind_params=summary_sql_params)

    def populate_enabled_tag_keys(self, start_date, end_date, bill_ids):
        """Populate the enabled tag key table.
        Args:
            start_date (datetime.date) The date to start populating the table.
            end_date (datetime.date) The date to end on.
            bill_ids (list) A list of bill IDs.
        Returns
            (None)
        """
        table_name = self._table_map["enabled_tag_keys"]
        summary_sql = pkgutil.get_data("masu.database", "sql/reporting_azureenabledtagkeys.sql")
        summary_sql = summary_sql.decode("utf-8")
        summary_sql_params = {
            "start_date": start_date,
            "end_date": end_date,
            "bill_ids": bill_ids,
            "schema": self.schema,
        }
        summary_sql, summary_sql_params = self.jinja_sql.prepare_query(summary_sql, summary_sql_params)
        self._execute_raw_sql_query(
            table_name, summary_sql, start_date, end_date, bind_params=list(summary_sql_params)
        )

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
        summary_sql = pkgutil.get_data(
            "masu.database", "sql/reporting_azurecostentryline_item_daily_summary_update_enabled_tags.sql"
        )
        summary_sql = summary_sql.decode("utf-8")
        summary_sql_params = {
            "start_date": start_date,
            "end_date": end_date,
            "bill_ids": bill_ids,
            "schema": self.schema,
        }
        summary_sql, summary_sql_params = self.jinja_sql.prepare_query(summary_sql, summary_sql_params)
        self._execute_raw_sql_query(
            table_name, summary_sql, start_date, end_date, bind_params=list(summary_sql_params)
        )

    def get_openshift_on_cloud_matched_tags(self, azure_bill_id, ocp_report_period_id):
        """Return a list of matched tags."""
        sql = pkgutil.get_data("masu.database", "sql/reporting_ocpazure_matched_tags.sql")
        sql = sql.decode("utf-8")
        sql_params = {"bill_id": azure_bill_id, "report_period_id": ocp_report_period_id, "schema": self.schema}
        sql, bind_params = self.jinja_sql.prepare_query(sql, sql_params)
        with connection.cursor() as cursor:
            cursor.db.set_schema(self.schema)
            cursor.execute(sql, params=bind_params)
            results = cursor.fetchall()

        return [json.loads(result[0]) for result in results]

    def get_openshift_on_cloud_matched_tags_trino(self, azure_source_uuid, ocp_source_uuid, start_date, end_date):
        """Return a list of matched tags."""
        sql = pkgutil.get_data("masu.database", "presto_sql/reporting_ocpazure_matched_tags.sql")
        sql = sql.decode("utf-8")

        days = DateHelper().list_days(start_date, end_date)
        days_str = "','".join([str(day.day) for day in days])

        sql_params = {
            "start_date": start_date,
            "end_date": end_date,
            "schema": self.schema,
            "azure_source_uuid": azure_source_uuid,
            "ocp_source_uuid": ocp_source_uuid,
            "year": start_date.strftime("%Y"),
            "month": start_date.strftime("%m"),
            "days": days_str,
        }
        sql, sql_params = self.jinja_sql.prepare_query(sql, sql_params)
        results = self._execute_presto_raw_sql_query(
            self.schema, sql, bind_params=sql_params, log_ref="reporting_ocpazure_matched_tags.sql"
        )

        return [json.loads(result[0]) for result in results]

    def back_populate_ocp_on_azure_daily_summary(self, start_date, end_date, report_period_id):
        """Populate the OCP on Azure and OCP daily summary tables. after populating the project table via trino."""
        table_name = AZURE_REPORT_TABLE_MAP["ocp_on_azure_daily_summary"]

        sql = pkgutil.get_data(
            "masu.database", "sql/reporting_ocpazurecostentrylineitem_daily_summary_back_populate.sql"
        )
        sql = sql.decode("utf-8")
        sql_params = {
            "schema": self.schema,
            "start_date": start_date,
            "end_date": end_date,
            "report_period_id": report_period_id,
        }
        sql, sql_params = self.jinja_sql.prepare_query(sql, sql_params)
        self._execute_raw_sql_query(table_name, sql, bind_params=list(sql_params))

    def check_for_matching_enabled_keys(self):
        """
        Checks the enabled tag keys for matching keys.
        """
        match_sql = f"""
            SELECT COUNT(*) FROM {self.schema}.reporting_azureenabledtagkeys as azure
                INNER JOIN {self.schema}.reporting_ocpenabledtagkeys as ocp ON azure.key = ocp.key;
        """
        with connection.cursor() as cursor:
            cursor.db.set_schema(self.schema)
            cursor.execute(match_sql)
            results = cursor.fetchall()
            if results[0][0] < 1:
                LOG.info(f"No matching enabled keys for OCP on Azure {self.schema}")
                return False
        return True
