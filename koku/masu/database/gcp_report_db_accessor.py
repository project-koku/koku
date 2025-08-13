#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Database accessor for GCP report data."""
import json
import logging
import pkgutil
import uuid
from os import path

from dateutil.parser import parse
from django.db import connection
from django.db.models import F
from django.db.models import Q
from django_tenants.utils import schema_context

from api.common import log_json
from api.provider.models import Provider
from api.utils import DateHelper
from koku.database import SQLScriptAtomicExecutorMixin
from masu.database import GCP_REPORT_TABLE_MAP
from masu.database import OCP_REPORT_TABLE_MAP
from masu.database.report_db_accessor_base import ReportDBAccessorBase
from masu.processor import is_tag_processing_disabled
from masu.processor.parquet.summary_sql_metadata import SummarySqlMetadata
from reporting.provider.all.models import EnabledTagKeys
from reporting.provider.all.models import TagMapping
from reporting.provider.gcp.models import GCPCostEntryBill
from reporting.provider.gcp.models import GCPCostEntryLineItemDailySummary
from reporting.provider.gcp.models import GCPTopology
from reporting.provider.gcp.models import TRINO_LINE_ITEM_TABLE
from reporting.provider.gcp.models import TRINO_OCP_GCP_DAILY_SUMMARY_TABLE
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
        self._table_map = GCP_REPORT_TABLE_MAP

    @property
    def line_item_daily_summary_table(self):
        return GCPCostEntryLineItemDailySummary

    def populate_ui_summary_tables(self, start_date, end_date, source_uuid, invoice_month, tables=UI_SUMMARY_TABLES):
        """Populate our UI summary tables (formerly materialized views)."""
        for table_name in tables:
            sql = pkgutil.get_data("masu.database", f"sql/gcp/{table_name}.sql")
            sql = sql.decode("utf-8")
            sql_params = {
                "start_date": start_date,
                "end_date": end_date,
                "schema": self.schema,
                "source_uuid": source_uuid,
                "invoice_month": invoice_month,
            }

            self._prepare_and_execute_raw_sql_query(table_name, sql, sql_params, operation="DELETE/INSERT")

    def get_cost_entry_bills_query_by_provider(self, provider_uuid):
        """Return all cost entry bills for the specified provider."""
        return GCPCostEntryBill.objects.filter(provider_id=provider_uuid)

    def bills_for_provider_uuid(self, provider_uuid, start_date=None, invoice_month=None):
        """Return all cost entry bills for provider_uuid on date."""
        if invoice_month:
            start_date = DateHelper().invoice_month_start(invoice_month).date()
        bills = self.get_cost_entry_bills_query_by_provider(provider_uuid)
        if start_date:
            if isinstance(start_date, str):
                start_date = parse(start_date)
            bill_date = start_date.replace(day=1)
            bills = bills.filter(billing_period_start=bill_date)
        return bills

    def get_bill_query_before_date(self, date):
        """Get the cost entry bill objects with billing period before provided date."""
        return GCPCostEntryBill.objects.filter(billing_period_start__lte=date)

    def populate_line_item_daily_summary_table_trino(
        self, start_date, end_date, source_uuid, bill_id, markup_value, invoice_month
    ):
        """Populate the daily aggregated summary of line items table.

        Args:
            start_date (datetime.date) The date to start populating the table.
            end_date (datetime.date) The date to end on.

        Returns
            (None)

        """

        sql = pkgutil.get_data("masu.database", "trino_sql/reporting_gcpcostentrylineitem_daily_summary.sql")
        sql = sql.decode("utf-8")
        uuid_str = str(uuid.uuid4()).replace("-", "_")
        sql_params = {
            "uuid": uuid_str,
            "start_date": start_date,
            "end_date": end_date,
            "schema": self.schema,
            "table": TRINO_LINE_ITEM_TABLE,
            "source_uuid": source_uuid,
            "invoice_month": invoice_month,
            "markup": markup_value or 0,
            "bill_id": bill_id,
        }

        self._execute_trino_raw_sql_query(
            sql, sql_params=sql_params, log_ref="reporting_gcpcostentrylineitem_daily_summary.sql"
        )

    def fetch_invoice_months_and_dates(self, start_date, end_date, source_uuid):
        """Get invoice months and valid dates from date ranges."""
        sql = pkgutil.get_data("masu.database", "trino_sql/gcp/get_invoice_months_and_dates.sql")
        sql = sql.decode("utf-8")
        sql_params = {
            "schema": self.schema,
            "start_date": start_date,
            "end_date": end_date,
            "source_uuid": str(source_uuid),
        }
        return self._execute_trino_raw_sql_query(sql, sql_params=sql_params, log_ref="get_invoice_months_and_dates")

    def populate_tags_summary_table(self, bill_ids, start_date, end_date):
        """Populate the line item aggregated totals data table."""
        table_name = self._table_map["tags_summary"]

        sql = pkgutil.get_data("masu.database", "sql/reporting_gcptags_summary.sql")
        sql = sql.decode("utf-8")
        sql_params = {"schema": self.schema, "bill_ids": bill_ids, "start_date": start_date, "end_date": end_date}
        self._prepare_and_execute_raw_sql_query(table_name, sql, sql_params)

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

    def populate_gcp_topology_information_tables(self, provider, start_date, end_date, invoice_month):
        """Populate the GCP topology table."""
        ctx = {
            "schema": self.schema,
            "provider_uuid": provider.uuid,
            "start_date": start_date,
            "end_date": end_date,
        }
        LOG.info(log_json(msg="populating GCP topology table", context=ctx))
        topology = self.get_gcp_topology_trino(provider.uuid, start_date, end_date, invoice_month)

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
        LOG.info(log_json(msg="finished populating GCP topology table", context=ctx))

    def get_gcp_topology_trino(self, source_uuid, start_date, end_date, invoice_month):
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
                AND gcp.year = '{invoice_month[:4]}'
                AND gcp.month = '{invoice_month[4:]}'
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
        context = {
            "schema": self.schema,
            "start": start_date,
            "end": end_date,
            "provider_uuid": source_uuid,
            "invoice_id": invoice_month,
        }
        return self._execute_trino_raw_sql_query(sql, context=context, log_ref="get_gcp_topology_trino")

    def _get_matched_tags_strings(self, bill_id, gcp_provider_uuid, ocp_provider_uuid, start_date, end_date):
        """Returns the matched tags"""
        ctx = {
            "schema": self.schema,
            "bill_id": bill_id,
            "gcp_provider_uuid": gcp_provider_uuid,
            "ocp_provider_uuid": ocp_provider_uuid,
            "start_date": start_date,
            "end_date": end_date,
        }
        matched_tags = []
        with schema_context(self.schema):
            enabled_tags = self.check_for_matching_enabled_keys()
            if EnabledTagKeys.objects.filter(provider_type=Provider.PROVIDER_OCP).exists() and enabled_tags:
                matched_tags = self.get_openshift_on_cloud_matched_tags(bill_id)
        if not matched_tags and enabled_tags:
            LOG.info(log_json(msg="matched tags not available via Postgres", context=ctx))
            if is_tag_processing_disabled(self.schema):
                LOG.info(log_json(msg="trino tag matching disabled for customer", context=ctx))
                return []
            LOG.info(log_json(msg="getting matching tags from Trino", context=ctx))
            matched_tags = self.get_openshift_on_cloud_matched_tags_trino(
                gcp_provider_uuid, [ocp_provider_uuid], start_date, end_date, invoice_month_date=start_date
            )
        if matched_tags:
            return [json.dumps(match).replace("{", "").replace("}", "") for match in matched_tags]
        return matched_tags

    def populate_ocp_on_gcp_cost_daily_summary_trino(
        self,
        start_date,
        end_date,
        openshift_provider_uuid,
        gcp_provider_uuid,
        report_period_id,
        bill_id,
    ):
        """Populate the daily cost aggregated summary for OCP on GCP.

        Args:
            start_date (datetime.date) The date to start populating the table.
            end_date (datetime.date) The date to end on.

        Returns
            (None)

        """
        sql_metadata = SummarySqlMetadata(
            self.schema,
            openshift_provider_uuid,
            gcp_provider_uuid,
            start_date,
            end_date,
            self._get_matched_tags_strings(bill_id, gcp_provider_uuid, openshift_provider_uuid, start_date, end_date),
            bill_id,
            report_period_id,
        )
        managed_path = "trino_sql/gcp/openshift/populate_daily_summary/"
        prepare_sql, prepare_params = sql_metadata.prepare_template(
            f"{managed_path}/0_prepare_daily_summary_tables.sql"
        )
        LOG.info(log_json(msg="Preparing tables for OCP on GCP flow", **prepare_params))
        self._execute_trino_multipart_sql_query(prepare_sql, bind_params=prepare_params)
        self.delete_ocp_on_gcp_hive_partition_by_day(
            sql_metadata.days_tup,
            sql_metadata.cloud_provider_uuid,
            sql_metadata.ocp_provider_uuid,
            sql_metadata.year,
            sql_metadata.month,
        )
        # Resource Matching
        resource_matching_sql, resource_matching_params = sql_metadata.prepare_template(
            f"{managed_path}/1_resource_matching_by_cluster.sql",
            {
                "matched_tag_array": self.find_openshift_keys_expected_values(sql_metadata),
            },
        )
        LOG.info(log_json(msg="Resource matching for OCP on GCP flow", **resource_matching_params))
        self._execute_trino_multipart_sql_query(resource_matching_sql, bind_params=resource_matching_params)
        # Data Transformation for Daily Summary
        daily_summary_sql, daily_summary_params = sql_metadata.prepare_template(
            f"{managed_path}/2_summarize_data_by_cluster.sql",
            {
                **sql_metadata.build_cost_model_params(),
            },
        )
        LOG.info(log_json(msg="executing data transformations for ocp on gcp daily summary", **daily_summary_params))
        self._execute_trino_multipart_sql_query(daily_summary_sql, bind_params=daily_summary_params)
        # Insert into postgresql
        psql_insert, psql_params = sql_metadata.prepare_template(
            f"{managed_path}/3_reporting_ocpgcpcostlineitem_project_daily_summary_p.sql",
        )
        LOG.info(log_json(msg="running OCP on GCP SQL managed flow", **psql_params))
        self._execute_trino_multipart_sql_query(psql_insert, bind_params=psql_params)

    def populate_ocp_on_gcp_ui_summary_tables(self, sql_params, tables=OCPGCP_UI_SUMMARY_TABLES):
        """Populate our UI summary tables (formerly materialized views)."""
        invoice_month_list = self.date_helper.gcp_find_invoice_months_in_date_range(
            sql_params["start_date"], sql_params["end_date"]
        )
        for invoice_month in invoice_month_list:
            for table_name in tables:
                sql_params["invoice_month"] = invoice_month
                sql = pkgutil.get_data("masu.database", f"sql/gcp/openshift/{table_name}.sql")
                sql = sql.decode("utf-8")
                self._prepare_and_execute_raw_sql_query(table_name, sql, sql_params, operation="DELETE/INSERT")

    def populate_ocp_on_gcp_ui_summary_tables_trino(
        self, start_date, end_date, openshift_provider_uuid, gcp_provider_uuid, tables=OCPGCP_UI_SUMMARY_TABLES
    ):
        """Populate our UI summary tables (formerly materialized views)."""
        year = start_date.strftime("%Y")
        month = start_date.strftime("%m")
        days = self.date_helper.list_days(start_date, end_date)
        days_tup = tuple(str(day.day) for day in days)

        for table_name in tables:
            sql = pkgutil.get_data("masu.database", f"trino_sql/gcp/openshift/{table_name}.sql")
            sql = sql.decode("utf-8")
            sql_params = {
                "schema": self.schema,
                "start_date": start_date,
                "end_date": end_date,
                "year": year,
                "month": month,
                "days": days_tup,
                "gcp_source_uuid": gcp_provider_uuid,
                "ocp_source_uuid": openshift_provider_uuid,
            }
            self._execute_trino_raw_sql_query(sql, sql_params=sql_params, log_ref=f"{table_name}.sql")

    def delete_ocp_on_gcp_hive_partition_by_day(self, days, gcp_source, ocp_source, year, month):
        """Deletes partitions individually for each day in days list."""
        if self.schema_exists_trino() and self.table_exists_trino(TRINO_OCP_GCP_DAILY_SUMMARY_TABLE):
            LOG.info(
                log_json(
                    msg="deleting Hive partitions by day",
                    schema=self.schema,
                    ocp_source=ocp_source,
                    gcp_source=gcp_source,
                    table=TRINO_OCP_GCP_DAILY_SUMMARY_TABLE,
                    year=year,
                    month=month,
                    days=days,
                )
            )
            for day in days:
                sql = f"""
                    DELETE FROM hive.{self.schema}.{TRINO_OCP_GCP_DAILY_SUMMARY_TABLE}
                        WHERE source = '{gcp_source}'
                        AND ocp_source = '{ocp_source}'
                        AND year = '{year}'
                        AND (month = replace(ltrim(replace('{month}', '0', ' ')),' ', '0') OR month = '{month}')
                        AND day = '{day}'"""
                self._execute_trino_raw_sql_query(
                    sql,
                    context={"year": year, "month": month, "day": day, "table": TRINO_OCP_GCP_DAILY_SUMMARY_TABLE},
                    log_ref="delete_ocp_on_gcp_hive_partition_by_day",
                )

    def get_openshift_on_cloud_matched_tags(self, gcp_bill_id):
        sql = pkgutil.get_data("masu.database", "sql/reporting_ocpgcp_matched_tags.sql")
        sql = sql.decode("utf-8")
        sql_params = {"bill_id": gcp_bill_id, "schema": self.schema}
        sql, bind_params = self.prepare_query(sql, sql_params)
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
        sql = pkgutil.get_data("masu.database", "trino_sql/gcp/openshift/reporting_ocpgcp_matched_tags.sql")
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

        results = self._execute_trino_raw_sql_query(
            sql, sql_params=sql_params, log_ref="reporting_ocpgcp_matched_tags.sql"
        )
        return [json.loads(result[0]) for result in results]

    def populate_ocp_on_gcp_tag_information(self, gcp_bill_ids, start_date, end_date, report_period_id):
        """Populate the line item aggregated totals data table."""
        sql_params = {
            "schema": self.schema,
            "gcp_bill_ids": gcp_bill_ids,
            "start_date": start_date,
            "end_date": end_date,
            "report_period_id": report_period_id,
        }
        # Tag Summary
        sql = pkgutil.get_data("masu.database", "sql/gcp/openshift/reporting_ocpgcptags_summary.sql")
        sql = sql.decode("utf-8")
        self._prepare_and_execute_raw_sql_query(self._table_map["ocp_on_gcp_tags_summary"], sql, sql_params)
        # Tag Mapping
        with schema_context(self.schema):
            # Early return check to see if they have any tag mappings set.
            if not TagMapping.objects.filter(
                Q(child__provider_type=Provider.PROVIDER_GCP) | Q(child__provider_type=Provider.PROVIDER_OCP)
            ).exists():
                LOG.debug("No tag mappings for GCP.")
                return
        sql = pkgutil.get_data("masu.database", "sql/gcp/openshift/ocpgcp_tag_mapping_update_daily_summary.sql")
        sql = sql.decode("utf-8")
        self._prepare_and_execute_raw_sql_query(self._table_map["ocp_on_gcp_project_daily_summary"], sql, sql_params)

    def update_line_item_daily_summary_with_tag_mapping(self, start_date, end_date, bill_ids=None):
        """
        Updates the line item daily summary table with tag mapping pieces.

        Args:
            start_date (datetime.date) The date to start populating the table.
            end_date (datetime.date) The date to end on.
            bill_ids (list) A list of bill IDs.
        Returns:
            (None)
        """
        with schema_context(self.schema):
            # Early return check to see if they have any tag mappings set.
            if not TagMapping.objects.filter(child__provider_type=Provider.PROVIDER_GCP).exists():
                LOG.debug("No tag mappings for GCP.")
                return

        table_name = self._table_map["line_item_daily_summary"]
        sql = pkgutil.get_data("masu.database", "sql/gcp/gcp_tag_mapping_update_daily_summary.sql")
        sql = sql.decode("utf-8")
        sql_params = {
            "start_date": start_date,
            "end_date": end_date,
            "bill_ids": bill_ids,
            "schema": self.schema,
        }
        self._prepare_and_execute_raw_sql_query(table_name, sql, sql_params)

    def back_populate_ocp_infrastructure_costs(self, start_date, end_date, report_period_id):
        """Populate the OCP on GCP and OCP daily summary tables. after populating the project table."""
        table_name = OCP_REPORT_TABLE_MAP["line_item_daily_summary"]

        sql = pkgutil.get_data(
            "masu.database",
            "sql/reporting_ocpgcp_ocp_infrastructure_back_populate.sql",
        )
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
                {self.schema}.reporting_enabledtagkeys WHERE enabled=True AND provider_type IN ('GCP', 'OCP')
                GROUP BY key) AS c WHERE c.p_count > 1;
        """
        with connection.cursor() as cursor:
            cursor.db.set_schema(self.schema)
            cursor.execute(match_sql)
            results = cursor.fetchall()
            if results[0][0] < 1:
                LOG.info(log_json(msg="no matching enabled keys for OCP on GCP", schema=self.schema))
                return False
        return True
