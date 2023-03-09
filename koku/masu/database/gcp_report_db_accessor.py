#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Database accessor for GCP report data."""
import datetime
import json
import logging
import pkgutil
import uuid
from os import path
from secrets import token_hex

from dateutil.parser import parse
from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.db import connection
from django.db.models import F
from jinjasql import JinjaSql
from tenant_schemas.utils import schema_context
from trino.exceptions import TrinoExternalError

from api.utils import DateHelper
from koku.database import SQLScriptAtomicExecutorMixin
from masu.database import GCP_REPORT_TABLE_MAP
from masu.database.koku_database_access import mini_transaction_delete
from masu.database.report_db_accessor_base import ReportDBAccessorBase
from masu.external.date_accessor import DateAccessor
from masu.util.gcp.common import check_resource_level
from masu.util.ocp.common import get_cluster_alias_from_cluster_id
from reporting.provider.gcp.models import GCPCostEntryBill
from reporting.provider.gcp.models import GCPCostEntryLineItem
from reporting.provider.gcp.models import GCPCostEntryLineItemDailySummary
from reporting.provider.gcp.models import GCPTopology
from reporting.provider.gcp.models import PRESTO_LINE_ITEM_TABLE
from reporting.provider.gcp.models import UI_SUMMARY_TABLES
from reporting.provider.gcp.openshift.models import UI_SUMMARY_TABLES as OCPGCP_UI_SUMMARY_TABLES
from reporting_common.models import CostUsageReportStatus

LOG = logging.getLogger(__name__)


class GCPReportDBAccessor(SQLScriptAtomicExecutorMixin, ReportDBAccessorBase):
    """Class to interact with GCP Report reporting tables."""

    def __init__(self, schema):
        """Establish the database connection.

        Args:
            schema (str): The customer schema to associate with
        """
        super().__init__(schema)
        self.date_accessor = DateAccessor()
        self.date_helper = DateHelper()
        self.jinja_sql = JinjaSql()
        self.trino_jinja_sql = JinjaSql(param_style="qmark")
        self._table_map = GCP_REPORT_TABLE_MAP

    @property
    def line_item_daily_summary_table(self):
        return GCPCostEntryLineItemDailySummary

    @property
    def line_item_table(self):
        return GCPCostEntryLineItem

    def populate_ui_summary_tables(self, start_date, end_date, source_uuid, tables=UI_SUMMARY_TABLES):
        """Populate our UI summary tables (formerly materialized views)."""
        invoice_month_list = self.date_helper.gcp_find_invoice_months_in_date_range(start_date, end_date)
        for invoice_month in invoice_month_list:
            for table_name in tables:
                summary_sql = pkgutil.get_data("masu.database", f"sql/gcp/{table_name}.sql")
                summary_sql = summary_sql.decode("utf-8")
                # Extend the end date past the end of the month & add the invoice month
                # in order to include cross over data.
                extended_end_date = end_date + relativedelta(days=2)
                summary_sql_params = {
                    "start_date": start_date,
                    "end_date": extended_end_date,
                    "schema": self.schema,
                    "source_uuid": source_uuid,
                    "invoice_month": invoice_month,
                }
                summary_sql, summary_sql_params = self.jinja_sql.prepare_query(summary_sql, summary_sql_params)
                self._execute_raw_sql_query(
                    table_name,
                    summary_sql,
                    start_date,
                    extended_end_date,
                    bind_params=list(summary_sql_params),
                    operation="DELETE/INSERT",
                )

    def get_cost_entry_bills_query_by_provider(self, provider_uuid):
        """Return all cost entry bills for the specified provider."""
        table_name = GCPCostEntryBill
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

    def get_bill_query_before_date(self, date, provider_uuid=None):
        """Get the cost entry bill objects with billing period before provided date."""
        table_name = GCPCostEntryBill
        with schema_context(self.schema):
            base_query = self._get_db_obj_query(table_name)
            if provider_uuid:
                cost_entry_bill_query = base_query.filter(billing_period_start__lte=date, provider_id=provider_uuid)
            else:
                cost_entry_bill_query = base_query.filter(billing_period_start__lte=date)
            return cost_entry_bill_query

    def populate_line_item_daily_summary_table_presto(
        self, start_date, end_date, source_uuid, bill_id, markup_value, invoice_month_date
    ):
        """Populate the daily aggregated summary of line items table.

        Args:
            start_date (datetime.date) The date to start populating the table.
            end_date (datetime.date) The date to end on.

        Returns
            (None)

        """
        last_month_end = datetime.date.today().replace(day=1) - datetime.timedelta(days=1)
        if end_date == last_month_end:

            # For gcp in order to catch what we are calling cross over data
            # we need to extend the end date by a couple of days. For more
            # information see: https://issues.redhat.com/browse/COST-1771
            new_end_date = end_date + relativedelta(days=2)
            self.delete_line_item_daily_summary_entries_for_date_range(source_uuid, end_date, new_end_date)
            end_date = new_end_date

        summary_sql = pkgutil.get_data("masu.database", "presto_sql/reporting_gcpcostentrylineitem_daily_summary.sql")
        summary_sql = summary_sql.decode("utf-8")
        uuid_str = str(uuid.uuid4()).replace("-", "_")
        summary_sql_params = {
            "uuid": uuid_str,
            "start_date": start_date,
            "end_date": end_date,
            "schema": self.schema,
            "table": PRESTO_LINE_ITEM_TABLE,
            "source_uuid": source_uuid,
            "year": invoice_month_date.strftime("%Y"),
            "month": invoice_month_date.strftime("%m"),
            "markup": markup_value or 0,
            "bill_id": bill_id,
        }
        summary_sql, summary_sql_params = self.trino_jinja_sql.prepare_query(summary_sql, summary_sql_params)

        self._execute_presto_raw_sql_query(
            self.schema, summary_sql, log_ref="reporting_gcpcostentrylineitem_daily_summary.sql"
        )

    def populate_tags_summary_table(self, bill_ids, start_date, end_date):
        """Populate the line item aggregated totals data table."""
        table_name = self._table_map["tags_summary"]

        agg_sql = pkgutil.get_data("masu.database", "sql/reporting_gcptags_summary.sql")
        agg_sql = agg_sql.decode("utf-8")
        agg_sql_params = {"schema": self.schema, "bill_ids": bill_ids, "start_date": start_date, "end_date": end_date}
        agg_sql, agg_sql_params = self.jinja_sql.prepare_query(agg_sql, agg_sql_params)
        self._execute_raw_sql_query(table_name, agg_sql, bind_params=list(agg_sql_params))

    def populate_markup_cost(self, markup, start_date, end_date, bill_ids=None):
        """Set markup costs in the database."""
        with schema_context(self.schema):
            if bill_ids and start_date and end_date:
                for bill_id in bill_ids:
                    GCPCostEntryLineItemDailySummary.objects.filter(
                        cost_entry_bill_id=bill_id, usage_start__gte=start_date, usage_start__lte=end_date
                    ).update(markup_cost=(F("unblended_cost") * markup))
            elif bill_ids:
                for bill_id in bill_ids:
                    GCPCostEntryLineItemDailySummary.objects.filter(cost_entry_bill_id=bill_id).update(
                        markup_cost=(F("unblended_cost") * markup)
                    )

    def get_gcp_scan_range_from_report_name(self, manifest_id=None, report_name=""):
        """Return the scan range given the manifest_id or the report_name."""
        scan_range = {}
        # Return range of report
        if report_name:
            try:
                report_name = path.splitext(report_name)[0]
                date_range = report_name.split("_")[-1]
                scan_start, scan_end = date_range.split(":")
                scan_range["start"] = scan_start
                scan_range["end"] = scan_end
                return scan_range
            except ValueError:
                LOG.warning(f"Could not find range of report name: {report_name}.")
                return scan_range
        # Grab complete range given manifest_id
        if manifest_id:
            start_dates = []
            end_dates = []
            records = CostUsageReportStatus.objects.filter(manifest_id=manifest_id)
            if not records:
                return scan_range
            for record in records:
                report_path = record.report_name
                report_name = path.basename(report_path)
                try:
                    report_name = path.splitext(report_name)[0]
                    date_range = report_name.split("_")[-1]
                    scan_start, scan_end = date_range.split(":")
                    start_dates.append(scan_start)
                    end_dates.append(scan_end)
                except ValueError:
                    LOG.warning(f"Could not find range of record {report_name} for manifest {manifest_id}.")
                    return scan_range
            scan_range["start"] = min(start_dates)
            scan_range["end"] = max(end_dates)
            return scan_range

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
        summary_sql = pkgutil.get_data("masu.database", "sql/reporting_gcpenabledtagkeys.sql")
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
            "masu.database", "sql/reporting_gcpcostentryline_item_daily_summary_update_enabled_tags.sql"
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

    def populate_gcp_topology_information_tables(self, provider, start_date, end_date, invoice_month_date):
        """Populate the GCP topology table."""
        msg = f"Populating GCP topology for {provider.uuid} from {start_date} to {end_date}"
        LOG.info(msg)
        topology = self.get_gcp_topology_trino(provider.uuid, start_date, end_date, invoice_month_date)

        with schema_context(self.schema):
            for record in topology:
                gcp_top = GCPTopology.objects.filter(
                    source_uuid=record[0],
                    account_id=record[1],
                    project_id=record[2],
                    project_name=record[3],
                    service_id=record[4],
                    service_alias=record[5],
                    region=record[6],
                ).first()
                if not gcp_top:
                    GCPTopology.objects.create(
                        source_uuid=record[0],
                        account_id=record[1],
                        project_id=record[2],
                        project_name=record[3],
                        service_id=record[4],
                        service_alias=record[5],
                        region=record[6],
                    )
        LOG.info("Finished populating GCP topology")

    def get_gcp_topology_trino(self, source_uuid, start_date, end_date, invoice_month_date):
        """Get the account topology for a GCP source."""
        sql = f"""
            SELECT source,
                billing_account_id,
                project_id,
                project_name,
                service_id,
                service_description,
                location_region
            FROM hive.{self.schema}.gcp_line_items as gcp
            WHERE gcp.source = '{source_uuid}'
                AND gcp.year = '{invoice_month_date.strftime("%Y")}'
                AND gcp.month = '{invoice_month_date.strftime("%m")}'
                AND gcp.usage_start_time >= TIMESTAMP '{start_date}'
                AND gcp.usage_start_time < date_add('day', 1, TIMESTAMP '{end_date}')
            GROUP BY source,
                billing_account_id,
                project_id,
                project_name,
                service_id,
                service_description,
                location_region
        """

        topology = self._execute_presto_raw_sql_query(self.schema, sql, log_ref="get_gcp_topology_trino")

        return topology

    def delete_line_item_daily_summary_entries_for_date_range(self, source_uuid, start_date, end_date, table=None):
        """Overwrite the parent class to include invoice month for gcp.

        Args:
            source_uuid (uuid): uuid of a given source
            start_date (datetime): start range date
            end_date (datetime): end range date
            table (string): table name
        """
        # We want to include the invoice month in the delete to make sure we
        # don't accidentially delete last month's data that flows into the
        # next month
        invoice_month = start_date.strftime("%Y%m")
        if table is None:
            table = self.line_item_daily_summary_table
        msg = f"Deleting records from {table} from {start_date} to {end_date} for invoice_month {invoice_month}"
        LOG.info(msg)
        select_query = table.objects.filter(
            source_uuid=source_uuid,
            usage_start__gte=start_date,
            usage_start__lte=end_date,
            invoice_month=invoice_month,
        )
        with schema_context(self.schema):
            count, _ = mini_transaction_delete(select_query)
        msg = f"Deleted {count} records from {table}"
        LOG.info(msg)

    def populate_ocp_on_gcp_cost_daily_summary_presto_by_node(
        self,
        start_date,
        end_date,
        openshift_provider_uuid,
        cluster_id,
        gcp_provider_uuid,
        report_period_id,
        bill_id,
        markup_value,
        distribution,
        node,
        node_count=None,
    ):
        """Populate the daily cost aggregated summary for OCP on GCP.

        This method is called for each node in the update_gcp_summary_tables
        if an unleash flag is enabled.

        Args:
            start_date (datetime.date) The date to start populating the table.
            end_date (datetime.date) The date to end on.

        Returns
            (None)

        """
        year = start_date.strftime("%Y")
        month = start_date.strftime("%m")
        days = self.date_helper.list_days(start_date, end_date)
        # days_str = "','".join([str(day.day) for day in days])
        days_list = [str(day.day) for day in days]
        self.delete_ocp_on_gcp_hive_partition_by_day(
            days_list, gcp_provider_uuid, openshift_provider_uuid, year, month
        )

        cluster_alias = get_cluster_alias_from_cluster_id(cluster_id)

        # Default to cpu distribution
        pod_column = "pod_effective_usage_cpu_core_hours"
        cluster_column = "cluster_capacity_cpu_core_hours"
        if distribution == "memory":
            pod_column = "pod_effective_usage_memory_gigabyte_hours"
            cluster_column = "cluster_capacity_memory_gigabyte_hours"

        summary_sql = pkgutil.get_data(
            "masu.database", "presto_sql/gcp/openshift/reporting_ocpgcpcostlineitem_daily_summary_by_node.sql"
        )
        summary_sql = summary_sql.decode("utf-8")
        summary_sql_params = {
            "temp_table_hash": token_hex(8),
            "schema": self.schema,
            "start_date": start_date,
            "year": year,
            "month": month,
            "days": tuple(str(day.day) for day in days),
            "end_date": end_date,
            "gcp_source_uuid": gcp_provider_uuid,
            "ocp_source_uuid": openshift_provider_uuid,
            "bill_id": bill_id,
            "report_period_id": report_period_id,
            "markup": markup_value,
            "pod_column": pod_column,
            "cluster_column": cluster_column,
            "cluster_id": cluster_id,
            "cluster_alias": cluster_alias,
            "node": node,
            "node_count": node_count,
        }

        LOG.info("Running OCP on GCP SQL with params (BY NODE):")
        LOG.info(summary_sql_params)
        self._execute_presto_multipart_sql_query(self.schema, summary_sql, bind_params=summary_sql_params)

    def populate_ocp_on_gcp_cost_daily_summary_presto(
        self,
        start_date,
        end_date,
        openshift_provider_uuid,
        cluster_id,
        gcp_provider_uuid,
        report_period_id,
        bill_id,
        markup_value,
        distribution,
    ):
        """Populate the daily cost aggregated summary for OCP on GCP.

        Args:
            start_date (datetime.date) The date to start populating the table.
            end_date (datetime.date) The date to end on.

        Returns
            (None)

        """
        # Check for GCP resource level data
        resource_level = check_resource_level(gcp_provider_uuid)

        year = start_date.strftime("%Y")
        month = start_date.strftime("%m")
        days = self.date_helper.list_days(start_date, end_date)
        days_list = [str(day.day) for day in days]
        self.delete_ocp_on_gcp_hive_partition_by_day(
            days_list, gcp_provider_uuid, openshift_provider_uuid, year, month
        )

        cluster_alias = get_cluster_alias_from_cluster_id(cluster_id)

        # Default to cpu distribution
        pod_column = "pod_effective_usage_cpu_core_hours"
        cluster_column = "cluster_capacity_cpu_core_hours"
        node_column = "node_capacity_cpu_core_hours"
        if distribution == "memory":
            pod_column = "pod_effective_usage_memory_gigabyte_hours"
            cluster_column = "cluster_capacity_memory_gigabyte_hours"
            node_column = "node_capacity_memory_gigabyte_hours"

        if resource_level:
            sql_level = "reporting_ocpgcpcostlineitem_daily_summary_resource_id"
            matching_type = "resource"
        else:
            sql_level = "reporting_ocpgcpcostlineitem_daily_summary"
            matching_type = "tag"

        summary_sql = pkgutil.get_data("masu.database", f"presto_sql/gcp/openshift/{sql_level}.sql")
        summary_sql = summary_sql.decode("utf-8")
        summary_sql_params = {
            "temp_table_hash": token_hex(8),
            "schema": self.schema,
            "start_date": start_date,
            "year": year,
            "month": month,
            "days": tuple(str(day.day) for day in days),
            "end_date": end_date,
            "gcp_source_uuid": gcp_provider_uuid,
            "ocp_source_uuid": openshift_provider_uuid,
            "bill_id": bill_id,
            "report_period_id": report_period_id,
            "markup": markup_value,
            "pod_column": pod_column,
            "cluster_column": cluster_column,
            "node_column": node_column,
            "cluster_id": cluster_id,
            "cluster_alias": cluster_alias,
            "matching_type": matching_type,
        }
        LOG.info("Running OCP on GCP SQL with params:")
        LOG.info(summary_sql_params)
        self._execute_presto_multipart_sql_query(self.schema, summary_sql, bind_params=summary_sql_params)

    def populate_ocp_on_gcp_ui_summary_tables(self, sql_params, tables=OCPGCP_UI_SUMMARY_TABLES):
        """Populate our UI summary tables (formerly materialized views)."""
        invoice_month_list = self.date_helper.gcp_find_invoice_months_in_date_range(
            sql_params["start_date"], sql_params["end_date"]
        )
        for invoice_month in invoice_month_list:
            for table_name in tables:
                sql_params["invoice_month"] = invoice_month
                summary_sql = pkgutil.get_data("masu.database", f"sql/gcp/openshift/{table_name}.sql")
                summary_sql = summary_sql.decode("utf-8")
                summary_sql, summary_sql_params = self.jinja_sql.prepare_query(summary_sql, sql_params)
                self._execute_raw_sql_query(
                    table_name, summary_sql, bind_params=list(summary_sql_params), operation="DELETE/INSERT"
                )

    def delete_ocp_on_gcp_hive_partition_by_day(self, days, gcp_source, ocp_source, year, month):
        """Deletes partitions individually for each day in days list."""
        table = "reporting_ocpgcpcostlineitem_project_daily_summary"
        retries = settings.HIVE_PARTITION_DELETE_RETRIES
        if self.table_exists_trino(table):
            LOG.info(
                "Deleting Hive partitions for the following: \n\tSchema: %s "
                "\n\tOCP Source: %s \n\tGCP Source: %s \n\tTable: %s \n\tYear-Month: %s-%s \n\tDays: %s",
                self.schema,
                ocp_source,
                gcp_source,
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
                                WHERE gcp_source = '{gcp_source}'
                                AND ocp_source = '{ocp_source}'
                                AND year = '{year}'
                                AND (month = replace(ltrim(replace('{month}', '0', ' ')),' ', '0') OR month = '{month}')
                                AND day = '{day}'"""
                        self._execute_presto_raw_sql_query(
                            self.schema,
                            sql,
                            log_ref=f"delete_ocp_on_gcp_hive_partition_by_day for {year}-{month}-{day}",
                            attempts_left=(retries - 1) - i,
                        )
                        break
                    except TrinoExternalError as err:
                        if err.error_name == "HIVE_METASTORE_ERROR" and i < (retries - 1):
                            continue
                        else:
                            raise err

    def get_openshift_on_cloud_matched_tags(self, gcp_bill_id):
        sql = pkgutil.get_data("masu.database", "sql/reporting_ocpgcp_matched_tags.sql")
        sql = sql.decode("utf-8")
        sql_params = {"bill_id": gcp_bill_id, "schema": self.schema}
        sql, bind_params = self.jinja_sql.prepare_query(sql, sql_params)
        with connection.cursor() as cursor:
            cursor.db.set_schema(self.schema)
            cursor.execute(sql, params=bind_params)
            results = cursor.fetchall()

        return [json.loads(result[0]) for result in results]

    def get_openshift_on_cloud_matched_tags_trino(
        self, gcp_source_uuid, ocp_source_uuids, start_date, end_date, **kwargs
    ):
        """Return a list of matched tags."""
        invoice_month_date = kwargs.get("invoice_month_date")
        sql = pkgutil.get_data("masu.database", "presto_sql/gcp/openshift/reporting_ocpgcp_matched_tags.sql")
        sql = sql.decode("utf-8")

        days = self.date_helper.list_days(start_date, end_date)

        sql_params = {
            "start_date": start_date,
            "end_date": end_date,
            "schema": self.schema,
            "gcp_source_uuid": gcp_source_uuid,
            "ocp_source_uuids": ocp_source_uuids,
            "year": invoice_month_date.strftime("%Y"),
            "month": invoice_month_date.strftime("%m"),
            "days": tuple(str(day.day) for day in days),
        }
        sql, sql_params = self.jinja_sql.prepare_query(sql, sql_params)
        results = self._execute_presto_raw_sql_query(
            self.schema, sql, bind_params=sql_params, log_ref="reporting_ocpgcp_matched_tags.sql"
        )
        return [json.loads(result[0]) for result in results]

    def populate_ocp_on_gcp_tags_summary_table(self, gcp_bill_ids, start_date, end_date):
        """Populate the line item aggregated totals data table."""
        table_name = self._table_map["ocp_on_gcp_tags_summary"]

        agg_sql = pkgutil.get_data("masu.database", "sql/gcp/openshift/reporting_ocpgcptags_summary.sql")
        agg_sql = agg_sql.decode("utf-8")
        agg_sql_params = {
            "schema": self.schema,
            "gcp_bill_ids": gcp_bill_ids,
            "start_date": start_date,
            "end_date": end_date,
        }
        agg_sql, agg_sql_params = self.jinja_sql.prepare_query(agg_sql, agg_sql_params)
        self._execute_raw_sql_query(table_name, agg_sql, bind_params=list(agg_sql_params))

    def back_populate_ocp_infrastructure_costs_trino(self, start_date, end_date, report_period_id):
        """Populate the OCP on GCP and OCP daily summary tables. after populating the project table."""
        # table_name = GCP_REPORT_TABLE_MAP["ocp_on_gcp_daily_summary"]

        sql = pkgutil.get_data(
            "masu.database",
            "presto_sql/gcp/openshift/reporting_ocpgcp_ocp_infrastructure_back_populate.sql",
        )
        sql = sql.decode("utf-8")
        sql_params = {
            "schema": self.schema,
            "start_date": start_date,
            "end_date": end_date,
            "report_period_id": report_period_id,
        }
        sql, sql_params = self.jinja_sql.prepare_query(sql, sql_params)
        self._execute_presto_multipart_sql_query(self.schema, sql, bind_params=sql_params)

    def check_for_matching_enabled_keys(self):
        """
        Checks the enabled tag keys for matching keys.
        """
        match_sql = f"""
            SELECT COUNT(*) FROM {self.schema}.reporting_gcpenabledtagkeys as gcp
                INNER JOIN {self.schema}.reporting_ocpenabledtagkeys as ocp ON gcp.key = ocp.key;
        """
        with connection.cursor() as cursor:
            cursor.db.set_schema(self.schema)
            cursor.execute(match_sql)
            results = cursor.fetchall()
            if results[0][0] < 1:
                LOG.info(f"No matching enabled keys for OCP on GCP {self.schema}")
                return False
        return True
