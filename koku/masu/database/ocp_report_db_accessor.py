#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Database accessor for OCP report data."""
import datetime
import json
import logging
import pkgutil
import uuid

import pytz
from dateutil.parser import parse
from dateutil.rrule import MONTHLY
from dateutil.rrule import rrule
from django.db import connection
from django.db.models import DecimalField
from django.db.models import F
from django.db.models import Value
from django.db.models.functions import Coalesce
from jinjasql import JinjaSql
from tenant_schemas.utils import schema_context

import koku.presto_database as kpdb
from api.metrics import constants as metric_constants
from api.utils import DateHelper
from koku.database import JSONBBuildObject
from masu.config import Config
from masu.database import AWS_CUR_TABLE_MAP
from masu.database import OCP_REPORT_TABLE_MAP
from masu.database.report_db_accessor_base import ReportDBAccessorBase
from masu.util.common import month_date_range_tuple
from reporting.provider.ocp.models import OCPUsageLineItemDailySummary
from reporting.provider.ocp.models import OCPUsageReport
from reporting.provider.ocp.models import OCPUsageReportPeriod

# from reporting.provider.ocp.models import PRESTO_LINE_ITEM_TABLE_MAP

LOG = logging.getLogger(__name__)


def create_filter(data_source, start_date, end_date, cluster_id):
    """Create filter with data source, start and end dates."""
    filters = {"data_source": data_source}
    if start_date:
        filters["usage_start__gte"] = start_date if isinstance(start_date, datetime.date) else start_date.date()
    if end_date:
        filters["usage_start__lte"] = end_date if isinstance(end_date, datetime.date) else end_date.date()
    if cluster_id:
        filters["cluster_id"] = cluster_id
    return filters


class OCPReportDBAccessor(ReportDBAccessorBase):
    """Class to interact with customer reporting tables."""

    def __init__(self, schema):
        """Establish the database connection.

        Args:
            schema (str): The customer schema to associate with
        """
        super().__init__(schema)
        self._datetime_format = Config.OCP_DATETIME_STR_FORMAT
        self.jinja_sql = JinjaSql()
        self.date_helper = DateHelper()

    @property
    def line_item_daily_summary_table(self):
        return OCPUsageLineItemDailySummary

    def get_current_usage_report(self):
        """Get the most recent usage report object."""
        table_name = OCP_REPORT_TABLE_MAP["report"]

        with schema_context(self.schema):
            return self._get_db_obj_query(table_name).order_by("-interval_start").first()

    def get_current_usage_period(self):
        """Get the most recent usage report period object."""
        table_name = OCP_REPORT_TABLE_MAP["report_period"]

        with schema_context(self.schema):
            return self._get_db_obj_query(table_name).order_by("-report_period_start").first()

    def get_usage_periods_by_date(self, start_date):
        """Return all report period entries for the specified start date."""
        table_name = OCP_REPORT_TABLE_MAP["report_period"]
        with schema_context(self.schema):
            return self._get_db_obj_query(table_name).filter(report_period_start=start_date).all()

    def get_usage_period_by_dates_and_cluster(self, start_date, end_date, cluster_id):
        """Return all report period entries for the specified start date."""
        table_name = OCP_REPORT_TABLE_MAP["report_period"]
        with schema_context(self.schema):
            return (
                self._get_db_obj_query(table_name)
                .filter(report_period_start=start_date, report_period_end=end_date, cluster_id=cluster_id)
                .first()
            )

    def get_usage_period_on_or_before_date(self, date, provider_uuid=None):
        """Get the usage report period objects before provided date."""
        table_name = OCP_REPORT_TABLE_MAP["report_period"]

        with schema_context(self.schema):
            base_query = self._get_db_obj_query(table_name)
            if provider_uuid:
                usage_period_query = base_query.filter(report_period_start__lte=date, provider_id=provider_uuid)
            else:
                usage_period_query = base_query.filter(report_period_start__lte=date)
            return usage_period_query

    def get_usage_period_query_by_provider(self, provider_uuid):
        """Return all report periods for the specified provider."""
        table_name = OCP_REPORT_TABLE_MAP["report_period"]
        with schema_context(self.schema):
            return self._get_db_obj_query(table_name).filter(provider_id=provider_uuid)

    def report_periods_for_provider_uuid(self, provider_uuid, start_date=None):
        """Return all report periods for provider_uuid on date."""
        report_periods = self.get_usage_period_query_by_provider(provider_uuid)
        with schema_context(self.schema):
            if start_date:
                if isinstance(start_date, str):
                    start_date = parse(start_date)
                report_date = start_date.replace(day=1)
                report_periods = report_periods.filter(report_period_start=report_date).all()

            return report_periods

    def get_lineitem_query_for_reportid(self, query_report_id):
        """Get the usage report line item for a report id query."""
        table_name = OCP_REPORT_TABLE_MAP["line_item"]
        with schema_context(self.schema):
            base_query = self._get_db_obj_query(table_name)
            line_item_query = base_query.filter(report_id=query_report_id)
            return line_item_query

    def get_daily_usage_query_for_clusterid(self, cluster_identifier):
        """Get the usage report daily item for a cluster id query."""
        table_name = OCP_REPORT_TABLE_MAP["line_item_daily"]
        with schema_context(self.schema):
            base_query = self._get_db_obj_query(table_name)
            daily_usage_query = base_query.filter(cluster_id=cluster_identifier)
            return daily_usage_query

    def get_summary_usage_query_for_clusterid(self, cluster_identifier):
        """Get the usage report summary for a cluster id query."""
        table_name = OCP_REPORT_TABLE_MAP["line_item_daily_summary"]
        with schema_context(self.schema):
            base_query = self._get_db_obj_query(table_name)
            summary_usage_query = base_query.filter(cluster_id=cluster_identifier)
            return summary_usage_query

    def get_item_query_report_period_id(self, report_period_id):
        """Get the usage report line item for a report id query."""
        table_name = OCP_REPORT_TABLE_MAP["line_item"]
        with schema_context(self.schema):
            base_query = self._get_db_obj_query(table_name)
            line_item_query = base_query.filter(report_period_id=report_period_id)
            return line_item_query

    def get_storage_item_query_report_period_id(self, report_period_id):
        """Get the storage report line item for a report id query."""
        table_name = OCP_REPORT_TABLE_MAP["storage_line_item"]
        with schema_context(self.schema):
            base_query = self._get_db_obj_query(table_name)
            line_item_query = base_query.filter(report_period_id=report_period_id)
            return line_item_query

    def get_daily_storage_item_query_cluster_id(self, cluster_identifier):
        """Get the daily storage report line item for a cluster id query."""
        table_name = OCP_REPORT_TABLE_MAP["storage_line_item_daily"]
        with schema_context(self.schema):
            base_query = self._get_db_obj_query(table_name)
            daily_item_query = base_query.filter(cluster_id=cluster_identifier)
            return daily_item_query

    def get_storage_summary_query_cluster_id(self, cluster_identifier):
        """Get the storage report summary for a cluster id query."""
        table_name = OCP_REPORT_TABLE_MAP["line_item_daily_summary"]
        filters = {"cluster_id": cluster_identifier, "data_source": "Storage"}
        with schema_context(self.schema):
            base_query = self._get_db_obj_query(table_name)
            daily_item_query = base_query.filter(**filters)
            return daily_item_query

    def get_node_label_item_query_report_period_id(self, report_period_id):
        """Get the node label report line item for a report id query."""
        table_name = OCP_REPORT_TABLE_MAP["node_label_line_item"]
        with schema_context(self.schema):
            base_query = self._get_db_obj_query(table_name)
            line_item_query = base_query.filter(report_period_id=report_period_id)
            return line_item_query

    def get_ocp_aws_summary_query_for_cluster_id(self, cluster_identifier):
        """Get the OCP-on-AWS report summary item for a given cluster id query."""
        table_name = AWS_CUR_TABLE_MAP["ocp_on_aws_daily_summary"]
        with schema_context(self.schema):
            base_query = self._get_db_obj_query(table_name)
            summary_item_query = base_query.filter(cluster_id=cluster_identifier)
            return summary_item_query

    def get_ocp_aws_project_summary_query_for_cluster_id(self, cluster_identifier):
        """Get the OCP-on-AWS report project summary item for a given cluster id query."""
        table_name = AWS_CUR_TABLE_MAP["ocp_on_aws_project_daily_summary"]
        with schema_context(self.schema):
            base_query = self._get_db_obj_query(table_name)
            summary_item_query = base_query.filter(cluster_id=cluster_identifier)
            return summary_item_query

    def get_report_query_report_period_id(self, report_period_id):
        """Get the usage report line item for a report id query."""
        table_name = OCP_REPORT_TABLE_MAP["report"]
        with schema_context(self.schema):
            base_query = self._get_db_obj_query(table_name)
            usage_report_query = base_query.filter(report_period_id=report_period_id)
            return usage_report_query

    def get_report_periods(self):
        """Get all usage period objects."""
        periods = []
        with schema_context(self.schema):
            periods = OCPUsageReportPeriod.objects.values("id", "cluster_id", "report_period_start", "provider_id")
            return_value = {(p["cluster_id"], p["report_period_start"], p["provider_id"]): p["id"] for p in periods}
            return return_value

    def get_reports(self):
        """Make a mapping of reports by time."""
        with schema_context(self.schema):
            reports = OCPUsageReport.objects.all()
            return {
                (entry.report_period_id, entry.interval_start.strftime(self._datetime_format)): entry.id
                for entry in reports
            }

    def get_pod_usage_cpu_core_hours(self, start_date, end_date, cluster_id=None):
        """Make a mapping of cpu pod usage hours."""
        table = OCPUsageLineItemDailySummary
        filters = create_filter("Pod", start_date, end_date, cluster_id)
        with schema_context(self.schema):
            reports = self._get_reports(table, filters)
            return {entry.uuid: entry.pod_usage_cpu_core_hours for entry in reports}

    def _get_reports(self, table, filters=None):
        """Return requested reports from given table.

        Args:
            table (Django models.Model object): The table to query against
            filters (dict): Columns to filter the query on

        Returns:
            (QuerySet): Django queryset of objects queried on

        """
        with schema_context(self.schema):
            if filters:
                reports = self._get_db_obj_query(table).filter(**filters).all()
            else:
                reports = self._get_db_obj_query(table).all()
            return reports

    def get_pod_request_cpu_core_hours(self, start_date, end_date, cluster_id=None):
        """Make a mapping of cpu pod request hours."""
        table = OCPUsageLineItemDailySummary
        filters = create_filter("Pod", start_date, end_date, cluster_id)
        with schema_context(self.schema):
            reports = self._get_reports(table, filters)
            return {entry.uuid: entry.pod_request_cpu_core_hours for entry in reports}

    def get_pod_usage_memory_gigabyte_hours(self, start_date, end_date, cluster_id=None):
        """Make a mapping of memory_usage hours."""
        table = OCPUsageLineItemDailySummary
        filters = create_filter("Pod", start_date, end_date, cluster_id)
        with schema_context(self.schema):
            reports = self._get_reports(table, filters)
            return {entry.uuid: entry.pod_usage_memory_gigabyte_hours for entry in reports}

    def get_pod_request_memory_gigabyte_hours(self, start_date, end_date, cluster_id=None):
        """Make a mapping of memory_request_hours."""
        table = OCPUsageLineItemDailySummary
        filters = create_filter("Pod", start_date, end_date, cluster_id)
        with schema_context(self.schema):
            reports = self._get_reports(table, filters)
            return {entry.uuid: entry.pod_request_memory_gigabyte_hours for entry in reports}

    def get_persistentvolumeclaim_usage_gigabyte_months(self, start_date, end_date, cluster_id=None):
        """Make a mapping of persistentvolumeclaim_usage_gigabyte_months."""
        table = OCPUsageLineItemDailySummary
        filters = create_filter("Storage", start_date, end_date, cluster_id)
        with schema_context(self.schema):
            reports = self._get_reports(table, filters)
            return {entry.uuid: entry.persistentvolumeclaim_usage_gigabyte_months for entry in reports}

    def get_volume_request_storage_gigabyte_months(self, start_date, end_date, cluster_id=None):
        """Make a mapping of volume_request_storage_gigabyte_months."""
        table = OCPUsageLineItemDailySummary
        filters = create_filter("Storage", start_date, end_date, cluster_id)
        with schema_context(self.schema):
            reports = self._get_reports(table, filters)
            return {entry.uuid: entry.volume_request_storage_gigabyte_months for entry in reports}

    def populate_line_item_daily_table(self, start_date, end_date, cluster_id):
        """Populate the daily aggregate of line items table.

        Args:
            start_date (datetime.date) The date to start populating the table.
            end_date (datetime.date) The date to end on.
            cluster_id (String) Cluster Identifier

        Returns
            (None)

        """
        # Cast start_date and end_date into date object instead of string
        if isinstance(start_date, str):
            start_date = datetime.datetime.strptime(start_date, "%Y-%m-%d").date()
            end_date = datetime.datetime.strptime(end_date, "%Y-%m-%d").date()
        if isinstance(start_date, datetime.datetime):
            start_date = start_date.date()
            end_date = end_date.date()

        table_name = OCP_REPORT_TABLE_MAP["line_item_daily"]

        daily_sql = pkgutil.get_data("masu.database", "sql/reporting_ocpusagelineitem_daily.sql")
        daily_sql = daily_sql.decode("utf-8")
        daily_sql_params = {
            "uuid": str(uuid.uuid4()).replace("-", "_"),
            "start_date": start_date,
            "end_date": end_date,
            "cluster_id": cluster_id,
            "schema": self.schema,
        }
        daily_sql, daily_sql_params = self.jinja_sql.prepare_query(daily_sql, daily_sql_params)
        self._execute_raw_sql_query(table_name, daily_sql, start_date, end_date, bind_params=list(daily_sql_params))

    def update_line_item_daily_summary_with_enabled_tags(self, start_date, end_date, report_period_ids):
        """Populate the enabled tag key table.
        Args:
            start_date (datetime.date) The date to start populating the table.
            end_date (datetime.date) The date to end on.
            bill_ids (list) A list of bill IDs.
        Returns
            (None)
        """
        table_name = OCP_REPORT_TABLE_MAP["line_item_daily_summary"]
        summary_sql = pkgutil.get_data(
            "masu.database", "sql/reporting_ocpusagelineitem_daily_summary_update_enabled_tags.sql"
        )
        summary_sql = summary_sql.decode("utf-8")
        summary_sql_params = {
            "start_date": start_date,
            "end_date": end_date,
            "report_period_ids": report_period_ids,
            "schema": self.schema,
        }
        summary_sql, summary_sql_params = self.jinja_sql.prepare_query(summary_sql, summary_sql_params)
        self._execute_raw_sql_query(
            table_name, summary_sql, start_date, end_date, bind_params=list(summary_sql_params)
        )

    def get_ocp_infrastructure_map(self, start_date, end_date, **kwargs):
        """Get the OCP on infrastructure map.

        Args:
            start_date (datetime.date) The date to start populating the table.
            end_date (datetime.date) The date to end on.

        Returns
            (None)

        """
        # kwargs here allows us to optionally pass in a provider UUID based on
        # the provider type this is run for
        ocp_provider_uuid = kwargs.get("ocp_provider_uuid")
        aws_provider_uuid = kwargs.get("aws_provider_uuid")
        azure_provider_uuid = kwargs.get("azure_provider_uuid")
        # In case someone passes this function a string instead of the date object like we asked...
        # Cast the string into a date object, end_date into date object instead of string
        if isinstance(start_date, str):
            start_date = datetime.datetime.strptime(start_date, "%Y-%m-%d").date()
            end_date = datetime.datetime.strptime(end_date, "%Y-%m-%d").date()
        infra_sql = pkgutil.get_data("masu.database", "sql/reporting_ocpinfrastructure_provider_map.sql")
        infra_sql = infra_sql.decode("utf-8")
        infra_sql_params = {
            "uuid": str(uuid.uuid4()).replace("-", "_"),
            "start_date": start_date,
            "end_date": end_date,
            "schema": self.schema,
            "aws_provider_uuid": aws_provider_uuid,
            "ocp_provider_uuid": ocp_provider_uuid,
            "azure_provider_uuid": azure_provider_uuid,
        }
        infra_sql, infra_sql_params = self.jinja_sql.prepare_query(infra_sql, infra_sql_params)
        with connection.cursor() as cursor:
            cursor.db.set_schema(self.schema)
            cursor.execute(infra_sql, list(infra_sql_params))
            results = cursor.fetchall()

        db_results = {}
        for entry in results:
            # This dictionary is keyed on an OpenShift provider UUID
            # and the tuple contains
            # (Infrastructure Provider UUID, Infrastructure Provider Type)
            db_results[entry[0]] = (entry[1], entry[2])

        return db_results

    def populate_storage_line_item_daily_table(self, start_date, end_date, cluster_id):
        """Populate the daily storage aggregate of line items table.

        Args:
            start_date (datetime.date) The date to start populating the table.
            end_date (datetime.date) The date to end on.
            cluster_id (String) Cluster Identifier

        Returns
            (None)

        """
        # Cast string to date object
        if isinstance(start_date, str):
            start_date = datetime.datetime.strptime(start_date, "%Y-%m-%d").date()
            end_date = datetime.datetime.strptime(end_date, "%Y-%m-%d").date()
        if isinstance(start_date, datetime.datetime):
            start_date = start_date.date()
            end_date = end_date.date()
        table_name = OCP_REPORT_TABLE_MAP["storage_line_item_daily"]

        daily_sql = pkgutil.get_data("masu.database", "sql/reporting_ocpstoragelineitem_daily.sql")
        daily_sql = daily_sql.decode("utf-8")
        daily_sql_params = {
            "uuid": str(uuid.uuid4()).replace("-", "_"),
            "start_date": start_date,
            "end_date": end_date,
            "cluster_id": cluster_id,
            "schema": self.schema,
        }
        daily_sql, daily_sql_params = self.jinja_sql.prepare_query(daily_sql, daily_sql_params)
        self._execute_raw_sql_query(table_name, daily_sql, start_date, end_date, bind_params=list(daily_sql_params))

    def populate_pod_charge(self, cpu_temp_table, mem_temp_table):
        """Populate the memory and cpu charge on daily summary table.

        Args:
            cpu_temp_table (String) Name of cpu charge temp table
            mem_temp_table (String) Name of mem charge temp table

        Returns
            (None)

        """
        table_name = OCP_REPORT_TABLE_MAP["line_item_daily_summary"]

        daily_charge_sql = pkgutil.get_data("masu.database", "sql/reporting_ocpusagelineitem_daily_pod_charge.sql")
        charge_line_sql = daily_charge_sql.decode("utf-8")
        charge_line_sql_params = {"cpu_temp": cpu_temp_table, "mem_temp": mem_temp_table, "schema": self.schema}
        charge_line_sql, charge_line_sql_params = self.jinja_sql.prepare_query(charge_line_sql, charge_line_sql_params)
        self._execute_raw_sql_query(table_name, charge_line_sql, bind_params=list(charge_line_sql_params))

    def populate_storage_charge(self, temp_table_name):
        """Populate the storage charge into the daily summary table.

        Args:
            storage_charge (Float) Storage charge.

        Returns
            (None)

        """
        table_name = OCP_REPORT_TABLE_MAP["line_item_daily_summary"]

        daily_charge_sql = pkgutil.get_data("masu.database", "sql/reporting_ocp_storage_charge.sql")
        charge_line_sql = daily_charge_sql.decode("utf-8")
        charge_line_sql_params = {"temp_table": temp_table_name, "schema": self.schema}
        charge_line_sql, charge_line_sql_params = self.jinja_sql.prepare_query(charge_line_sql, charge_line_sql_params)
        self._execute_raw_sql_query(table_name, charge_line_sql, bind_params=list(charge_line_sql_params))

    def populate_line_item_daily_summary_table(self, start_date, end_date, cluster_id):
        """Populate the daily aggregate of line items table.

        Args:
            start_date (datetime.date) The date to start populating the table.
            end_date (datetime.date) The date to end on.
            cluster_id (String) Cluster Identifier

        Returns
            (None)

        """
        # Cast start_date to date
        if isinstance(start_date, str):
            start_date = datetime.datetime.strptime(start_date, "%Y-%m-%d").date()
            end_date = datetime.datetime.strptime(end_date, "%Y-%m-%d").date()
        if isinstance(start_date, datetime.datetime):
            start_date = start_date.date()
            end_date = end_date.date()
        table_name = OCP_REPORT_TABLE_MAP["line_item_daily_summary"]

        summary_sql = pkgutil.get_data("masu.database", "sql/reporting_ocpusagelineitem_daily_summary.sql")
        summary_sql = summary_sql.decode("utf-8")
        summary_sql_params = {
            "uuid": str(uuid.uuid4()).replace("-", "_"),
            "start_date": start_date,
            "end_date": end_date,
            "cluster_id": cluster_id,
            "schema": self.schema,
        }
        summary_sql, summary_sql_params = self.jinja_sql.prepare_query(summary_sql, summary_sql_params)
        self._execute_raw_sql_query(
            table_name, summary_sql, start_date, end_date, bind_params=list(summary_sql_params)
        )

    def populate_storage_line_item_daily_summary_table(self, start_date, end_date, cluster_id):
        """Populate the daily aggregate of storage line items table.

        Args:
            start_date (datetime.date) The date to start populating the table.
            end_date (datetime.date) The date to end on.
            cluster_id (String) Cluster Identifier
        Returns
            (None)

        """
        # Cast start_date and end_date to date object, if they aren't already
        if isinstance(start_date, str):
            start_date = datetime.datetime.strptime(start_date, "%Y-%m-%d").date()
            end_date = datetime.datetime.strptime(end_date, "%Y-%m-%d").date()
        if isinstance(start_date, datetime.datetime):
            start_date = start_date.date()
            end_date = end_date.date()
        table_name = OCP_REPORT_TABLE_MAP["line_item_daily_summary"]

        summary_sql = pkgutil.get_data("masu.database", "sql/reporting_ocpstoragelineitem_daily_summary.sql")
        summary_sql = summary_sql.decode("utf-8")
        summary_sql_params = {
            "uuid": str(uuid.uuid4()).replace("-", "_"),
            "start_date": start_date,
            "end_date": end_date,
            "cluster_id": cluster_id,
            "schema": self.schema,
        }
        summary_sql, summary_sql_params = self.jinja_sql.prepare_query(summary_sql, summary_sql_params)
        self._execute_raw_sql_query(table_name, summary_sql, start_date, end_date, list(summary_sql_params))

    def populate_line_item_daily_summary_table_presto(
        self, start_date, end_date, report_period_id, cluster_id, cluster_alias, source
    ):
        """Populate the daily aggregate of line items table.

        Args:
            start_date (datetime.date) The date to start populating the table.
            end_date (datetime.date) The date to end on.
            report_period_id (int) : report period for which we are processing
            cluster_id (str) : Cluster Identifier
            cluster_alias (str) : Cluster alias
            source (UUID) : provider uuid

        Returns
            (None)

        """
        # Cast start_date to date
        if isinstance(start_date, str):
            start_date = datetime.datetime.strptime(start_date, "%Y-%m-%d").date()
            end_date = datetime.datetime.strptime(end_date, "%Y-%m-%d").date()
        if isinstance(start_date, datetime.datetime):
            start_date = start_date.date()
            end_date = end_date.date()

        tmpl_summary_sql = pkgutil.get_data("masu.database", "presto_sql/reporting_ocpusagelineitem_daily_summary.sql")
        tmpl_summary_sql = tmpl_summary_sql.decode("utf-8")
        summary_sql_params = {
            "uuid": str(source).replace("-", "_"),
            "start_date": start_date,
            "end_date": end_date,
            "report_period_id": report_period_id,
            "cluster_id": cluster_id,
            "cluster_alias": cluster_alias,
            "schema": self.schema,
            "source": str(source),
            "year": start_date.strftime("%Y"),
            "month": start_date.strftime("%m"),
        }

        LOG.info("PRESTO OCP: Connect")
        presto_conn = kpdb.connect(schema=self.schema)
        try:
            LOG.info("PRESTO OCP: executing SQL buffer for OCP usage processing")
            kpdb.executescript(
                presto_conn, tmpl_summary_sql, params=summary_sql_params, preprocessor=self.jinja_sql.prepare_query
            )
        except Exception as e:
            LOG.error(f"PRESTO OCP ERROR : {e}")
            try:
                presto_conn.rollback()
            except RuntimeError:
                # If presto has not started a transaction, it will throw
                # a RuntimeError that we just want to ignore.
                pass
            raise e
        else:
            LOG.info("PRESTO OCP: Commit actions")
            presto_conn.commit()
        finally:
            LOG.info("PRESTO OCP: Close connection")
            presto_conn.close()

    def populate_pod_label_summary_table_presto(self, report_period_ids, start_date, end_date, source):
        """
        Populate label usage summary tables

        Args:
            report_period_ids (list(int)) : List of report_period_ids for processing
            start_date (datetime.date) The date to start populating the table.
            end_date (datetime.date) The date to end on.
            source (UUID) : provider uuid

        Returns
            (None)
        """
        # Cast start_date to date
        if isinstance(start_date, str):
            start_date = datetime.datetime.strptime(start_date, "%Y-%m-%d").date()
            end_date = datetime.datetime.strptime(end_date, "%Y-%m-%d").date()
        if isinstance(start_date, datetime.datetime):
            start_date = start_date.date()
            end_date = end_date.date()

        agg_sql = pkgutil.get_data("masu.database", "presto_sql/reporting_ocp_usage_label_summary.sql")
        agg_sql = agg_sql.decode("utf-8")
        agg_sql_params = {
            "uuid": str(uuid.uuid4()).replace("-", "_"),
            "schema": self.schema,
            "report_period_ids": tuple(report_period_ids),
            "start_date": start_date,
            "end_date": end_date,
            "source": str(source),
            "year": start_date.strftime("%Y"),
            "month": start_date.strftime("%m"),
        }

        LOG.info("PRESTO OCP: Connect")
        presto_conn = kpdb.connect(schema=self.schema)
        try:
            LOG.info("PRESTO OCP: executing SQL buffer for OCP tag/label processing")
            kpdb.executescript(presto_conn, agg_sql, params=agg_sql_params, preprocessor=self.jinja_sql.prepare_query)
        except Exception as e:
            LOG.error(f"PRESTO OCP ERROR : {e}")
            try:
                presto_conn.rollback()
            except RuntimeError:
                # If presto has not started a transaction, it will throw
                # a RuntimeError that we just want to ignore.
                pass
            raise e
        else:
            LOG.info("PRESTO OCP: Commit actions")
            presto_conn.commit()
        finally:
            LOG.info("PRESTO OCP: Close connection")
            presto_conn.close()

    def update_summary_infrastructure_cost(self, cluster_id, start_date, end_date):
        """Populate the infrastructure costs on the daily usage summary table.

        Args:
            start_date (datetime.date) The date to start populating the table.
            end_date (datetime.date) The date to end on.
            cluster_id (String) Cluster Identifier
        Returns
            (None)

        """
        # Cast start_date to date object
        if isinstance(start_date, str):
            start_date = datetime.datetime.strptime(start_date, "%Y-%m-%d").date()
            end_date = datetime.datetime.strptime(end_date, "%Y-%m-%d").date()
        if isinstance(start_date, datetime.datetime):
            start_date = start_date.date()
            end_date = end_date.date()
        table_name = OCP_REPORT_TABLE_MAP["line_item_daily_summary"]
        if start_date is None:
            start_date_qry = self._get_db_obj_query(table_name).order_by("usage_start").first()
            start_date = str(start_date_qry.usage_start) if start_date_qry else None
        if end_date is None:
            end_date_qry = self._get_db_obj_query(table_name).order_by("-usage_start").first()
            end_date = str(end_date_qry.usage_start) if end_date_qry else None

        summary_sql = pkgutil.get_data("masu.database", "sql/reporting_ocpcosts_summary.sql")
        if start_date and end_date:
            summary_sql = summary_sql.decode("utf-8")
            summary_sql_params = {
                "uuid": str(uuid.uuid4()).replace("-", "_"),
                "start_date": start_date,
                "end_date": end_date,
                "cluster_id": cluster_id,
                "schema": self.schema,
            }
            summary_sql, summary_sql_params = self.jinja_sql.prepare_query(summary_sql, summary_sql_params)
            self._execute_raw_sql_query(
                table_name, summary_sql, start_date, end_date, bind_params=list(summary_sql_params)
            )

    def get_cost_summary_for_clusterid(self, cluster_identifier):
        """Get the cost summary for a cluster id query."""
        table_name = OCP_REPORT_TABLE_MAP["cost_summary"]
        base_query = self._get_db_obj_query(table_name)
        cost_summary_query = base_query.filter(cluster_id=cluster_identifier)
        return cost_summary_query

    def populate_pod_label_summary_table(self, report_period_ids, start_date, end_date):
        """Populate the line item aggregated totals data table."""
        table_name = OCP_REPORT_TABLE_MAP["pod_label_summary"]

        agg_sql = pkgutil.get_data("masu.database", "sql/reporting_ocpusagepodlabel_summary.sql")
        agg_sql = agg_sql.decode("utf-8")
        agg_sql_params = {
            "schema": self.schema,
            "report_period_ids": report_period_ids,
            "start_date": start_date,
            "end_date": end_date,
        }
        agg_sql, agg_sql_params = self.jinja_sql.prepare_query(agg_sql, agg_sql_params)
        self._execute_raw_sql_query(table_name, agg_sql, bind_params=list(agg_sql_params))

    def populate_volume_label_summary_table(self, report_period_ids, start_date, end_date):
        """Populate the OCP volume label summary table."""
        table_name = OCP_REPORT_TABLE_MAP["volume_label_summary"]

        agg_sql = pkgutil.get_data("masu.database", "sql/reporting_ocpstoragevolumelabel_summary.sql")
        agg_sql = agg_sql.decode("utf-8")
        agg_sql_params = {
            "schema": self.schema,
            "report_period_ids": report_period_ids,
            "start_date": start_date,
            "end_date": end_date,
        }
        agg_sql, agg_sql_params = self.jinja_sql.prepare_query(agg_sql, agg_sql_params)
        self._execute_raw_sql_query(table_name, agg_sql, bind_params=list(agg_sql_params))

    def populate_markup_cost(self, markup, start_date, end_date, cluster_id):
        """Set markup cost for OCP including infrastructure cost markup."""
        with schema_context(self.schema):
            OCPUsageLineItemDailySummary.objects.filter(
                cluster_id=cluster_id, usage_start__gte=start_date, usage_start__lte=end_date
            ).update(
                infrastructure_markup_cost=(
                    (Coalesce(F("infrastructure_raw_cost"), Value(0, output_field=DecimalField()))) * markup
                ),
                infrastructure_project_markup_cost=(
                    (Coalesce(F("infrastructure_project_raw_cost"), Value(0, output_field=DecimalField()))) * markup
                ),
            )

    def get_distinct_nodes(self, start_date, end_date, cluster_id):
        """Return a list of nodes for a cluster between given dates."""
        with schema_context(self.schema):
            unique_nodes = (
                OCPUsageLineItemDailySummary.objects.filter(
                    usage_start__gte=start_date, usage_start__lt=end_date, cluster_id=cluster_id, node__isnull=False
                )
                .values_list("node")
                .distinct()
            )
            return [node[0] for node in unique_nodes]

    def get_distinct_pvcs(self, start_date, end_date, cluster_id):
        """Return a list of tuples of (PVC, node) for a cluster between given dates."""
        with schema_context(self.schema):
            unique_pvcs = (
                OCPUsageLineItemDailySummary.objects.filter(
                    usage_start__gte=start_date,
                    usage_start__lt=end_date,
                    cluster_id=cluster_id,
                    persistentvolumeclaim__isnull=False,
                )
                .values_list("persistentvolumeclaim", "node")
                .distinct()
            )
            return [(pvc[0], pvc[1]) for pvc in unique_pvcs]

    def populate_monthly_cost(self, cost_type, rate_type, rate, start_date, end_date, cluster_id, cluster_alias):
        """
        Populate the monthly cost of a customer.

        Right now this is just the node/month cost. Calculated from
        node_cost * number_unique_nodes.

        args:
            node_cost (Decimal): The node cost per month
            start_date (datetime, str): The start_date to calculate monthly_cost.
            end_date (datetime, str): The end_date to calculate monthly_cost.

        """
        if isinstance(start_date, str):
            start_date = parse(start_date).date()
        if isinstance(end_date, str):
            end_date = parse(end_date).date()

        # usage_start, usage_end are date types
        first_month = datetime.datetime(*start_date.replace(day=1).timetuple()[:3]).replace(tzinfo=pytz.UTC)
        end_date = datetime.datetime(*end_date.timetuple()[:3]).replace(hour=23, minute=59, second=59, tzinfo=pytz.UTC)

        # Calculate monthly cost for each month from start date to end date
        for curr_month in rrule(freq=MONTHLY, until=end_date, dtstart=first_month):
            first_curr_month, first_next_month = month_date_range_tuple(curr_month)
            LOG.info("Populating monthly cost from %s to %s.", first_curr_month, first_next_month)
            if cost_type == "Node":
                if rate is None:
                    self.remove_monthly_cost(first_curr_month, first_next_month, cluster_id, cost_type)
                else:
                    self.upsert_monthly_node_cost_line_item(
                        first_curr_month, first_next_month, cluster_id, cluster_alias, rate_type, rate
                    )
            elif cost_type == "Cluster":
                if rate is None:
                    self.remove_monthly_cost(first_curr_month, first_next_month, cluster_id, cost_type)
                else:
                    self.upsert_monthly_cluster_cost_line_item(
                        first_curr_month, first_next_month, cluster_id, cluster_alias, rate_type, rate
                    )
            elif cost_type == "PVC":
                if rate is None:
                    self.remove_monthly_cost(first_curr_month, first_next_month, cluster_id, cost_type)
                else:
                    self.upsert_monthly_pvc_cost_line_item(
                        first_curr_month, first_next_month, cluster_id, cluster_alias, rate_type, rate
                    )

    def populate_monthly_tag_cost(
        self, cost_type, rate_type, rate_dict, start_date, end_date, cluster_id, cluster_alias
    ):
        """
        Populate the monthly cost of a customer based on tag rates.

        Right now this is just the node/month cost. Calculated from
        tag value cost * number_unique_nodes for each tag key value pair
        that is found on a line item with that node.
        """
        if isinstance(start_date, str):
            start_date = parse(start_date).date()
        if isinstance(end_date, str):
            end_date = parse(end_date).date()

        # usage_start, usage_end are date types
        first_month = datetime.datetime(*start_date.replace(day=1).timetuple()[:3]).replace(tzinfo=pytz.UTC)
        end_date = datetime.datetime(*end_date.timetuple()[:3]).replace(hour=23, minute=59, second=59, tzinfo=pytz.UTC)
        # Calculate monthly cost for each month from start date to end date for each tag key:value pair in the rate
        for curr_month in rrule(freq=MONTHLY, until=end_date, dtstart=first_month):
            first_curr_month, first_next_month = month_date_range_tuple(curr_month)
            LOG.info("Populating monthly tag based cost from %s to %s.", first_curr_month, first_next_month)
            if cost_type == "Node":
                self.tag_upsert_monthly_node_cost_line_item(
                    first_curr_month, first_next_month, cluster_id, cluster_alias, rate_type, rate_dict
                )
            elif cost_type == "Cluster":
                self.tag_upsert_monthly_cluster_cost_line_item(
                    first_curr_month, first_next_month, cluster_id, cluster_alias, rate_type, rate_dict
                )
            elif cost_type == "PVC":
                self.tag_upsert_monthly_pvc_cost_line_item(
                    first_curr_month, first_next_month, cluster_id, cluster_alias, rate_type, rate_dict
                )

    def populate_monthly_tag_default_cost(
        self, cost_type, rate_type, rate_dict, start_date, end_date, cluster_id, cluster_alias
    ):
        """
        Populate the monthly default cost of a customer based on tag rates.

        Right now this is just the node/month cost. Calculated from
        tag value cost * number_unique_nodes for each tag key value pair
        that is found on a line item with that node.
        """
        if isinstance(start_date, str):
            start_date = parse(start_date).date()
        if isinstance(end_date, str):
            end_date = parse(end_date).date()

        # usage_start, usage_end are date types
        first_month = datetime.datetime(*start_date.replace(day=1).timetuple()[:3]).replace(tzinfo=pytz.UTC)
        end_date = datetime.datetime(*end_date.timetuple()[:3]).replace(hour=23, minute=59, second=59, tzinfo=pytz.UTC)
        # Calculate monthly cost for each month from start date to end date for each tag key:value pair in the rate
        for curr_month in rrule(freq=MONTHLY, until=end_date, dtstart=first_month):
            first_curr_month, first_next_month = month_date_range_tuple(curr_month)
            LOG.info("Populating monthly tag based default cost from %s to %s.", first_curr_month, first_next_month)
            if cost_type == "Node":
                self.tag_upsert_monthly_default_node_cost_line_item(
                    first_curr_month, first_next_month, cluster_id, cluster_alias, rate_type, rate_dict
                )
            elif cost_type == "Cluster":
                self.tag_upsert_monthly_default_cluster_cost_line_item(
                    first_curr_month, first_next_month, cluster_id, cluster_alias, rate_type, rate_dict
                )
            elif cost_type == "PVC":
                self.tag_upsert_monthly_default_pvc_cost_line_item(
                    first_curr_month, first_next_month, cluster_id, cluster_alias, rate_type, rate_dict
                )

    def upsert_monthly_node_cost_line_item(
        self, start_date, end_date, cluster_id, cluster_alias, rate_type, node_cost
    ):
        """Update or insert daily summary line item for node cost."""
        unique_nodes = self.get_distinct_nodes(start_date, end_date, cluster_id)
        report_period = self.get_usage_period_by_dates_and_cluster(start_date, end_date, cluster_id)
        with schema_context(self.schema):
            for node in unique_nodes:
                line_item = OCPUsageLineItemDailySummary.objects.filter(
                    usage_start=start_date,
                    usage_end=start_date,
                    report_period=report_period,
                    cluster_id=cluster_id,
                    cluster_alias=cluster_alias,
                    monthly_cost_type="Node",
                    node=node,
                ).first()
                if not line_item:
                    line_item = OCPUsageLineItemDailySummary(
                        uuid=uuid.uuid4(),
                        usage_start=start_date,
                        usage_end=start_date,
                        report_period=report_period,
                        cluster_id=cluster_id,
                        cluster_alias=cluster_alias,
                        monthly_cost_type="Node",
                        node=node,
                    )
                if rate_type == metric_constants.INFRASTRUCTURE_COST_TYPE:
                    LOG.info("Node (%s) has a monthly infrastructure cost of %s.", node, node_cost)
                    line_item.infrastructure_monthly_cost = node_cost
                elif rate_type == metric_constants.SUPPLEMENTARY_COST_TYPE:
                    LOG.info("Node (%s) has a monthly supplemenarty cost of %s.", node, node_cost)
                    line_item.supplementary_monthly_cost = node_cost
                line_item.save()

    def tag_upsert_monthly_node_cost_line_item(
        self, start_date, end_date, cluster_id, cluster_alias, rate_type, rate_dict
    ):
        """
        Update or insert daily summary line item for node cost.

        It checks to see if a line item exists for each node
        that contains the tag key:value pair,
        if it does then the price is added to the monthly cost.
        """
        unique_nodes = self.get_distinct_nodes(start_date, end_date, cluster_id)
        report_period = self.get_usage_period_by_dates_and_cluster(start_date, end_date, cluster_id)
        with schema_context(self.schema):
            for node in unique_nodes:
                if rate_dict is not None:
                    for tag_key in rate_dict:
                        tag_values = rate_dict.get(tag_key)
                        for value_name, rate_value in tag_values.items():
                            # this makes sure that there is an entry for that node
                            # that contains the specified key_value pair
                            item_check = OCPUsageLineItemDailySummary.objects.filter(
                                usage_start__gte=start_date,
                                usage_end__lte=end_date,
                                report_period=report_period,
                                cluster_id=cluster_id,
                                cluster_alias=cluster_alias,
                                node=node,
                                pod_labels__contains={tag_key: value_name},
                            ).first()
                            if item_check:
                                line_item = OCPUsageLineItemDailySummary.objects.filter(
                                    usage_start=start_date,
                                    usage_end=start_date,
                                    report_period=report_period,
                                    cluster_id=cluster_id,
                                    cluster_alias=cluster_alias,
                                    monthly_cost_type="Node",
                                    node=node,
                                ).first()
                                if not line_item:
                                    line_item = OCPUsageLineItemDailySummary(
                                        uuid=uuid.uuid4(),
                                        usage_start=start_date,
                                        usage_end=start_date,
                                        report_period=report_period,
                                        cluster_id=cluster_id,
                                        cluster_alias=cluster_alias,
                                        monthly_cost_type="Node",
                                        node=node,
                                    )
                                if rate_type == metric_constants.INFRASTRUCTURE_COST_TYPE:
                                    LOG.info("Node (%s) has a monthly infrastructure cost of %s.", node, rate_value)
                                    line_item.infrastructure_monthly_cost = (
                                        Coalesce(
                                            line_item.infrastructure_monthly_cost,
                                            Value(0.0),
                                            output_field=DecimalField(),
                                        )
                                        + rate_value
                                    )
                                elif rate_type == metric_constants.SUPPLEMENTARY_COST_TYPE:
                                    LOG.info("Node (%s) has a monthly supplemenarty cost of %s.", node, rate_value)
                                    line_item.supplementary_monthly_cost = (
                                        Coalesce(
                                            line_item.supplementary_monthly_cost,
                                            Value(0.0),
                                            output_field=DecimalField(),
                                        )
                                        + rate_value
                                    )
                                line_item.save()

    def tag_upsert_monthly_default_node_cost_line_item(
        self, start_date, end_date, cluster_id, cluster_alias, rate_type, rate_dict
    ):
        """
        Update or insert daily summary line item for node cost.
        It checks to see if a line item exists for each node
        that contains the tag key:value pair,
        if it does then the price is added to the monthly cost.
        """
        unique_nodes = self.get_distinct_nodes(start_date, end_date, cluster_id)
        report_period = self.get_usage_period_by_dates_and_cluster(start_date, end_date, cluster_id)
        with schema_context(self.schema):
            for node in unique_nodes:
                if rate_dict is not None:
                    for tag_key in rate_dict:
                        tag_values = rate_dict.get(tag_key)
                        tag_default = tag_values.get("default_value")
                        values_to_skip = tag_values.get("defined_keys")
                        item_check = OCPUsageLineItemDailySummary.objects.filter(
                            usage_start__gte=start_date,
                            usage_end__lte=end_date,
                            report_period=report_period,
                            cluster_id=cluster_id,
                            cluster_alias=cluster_alias,
                            node=node,
                            pod_labels__has_key=tag_key,
                        )
                        for value in values_to_skip:
                            item_check = item_check.exclude(pod_labels__contains={tag_key: value})
                        # this won't run if there are no matching items and item_check will continue to be
                        # filtered until there are no items left
                        while item_check:
                            # get the first value for our tag key and exclude it from the queryset for the next check
                            # will remove values until there are none left
                            tag_key_value = item_check.first().pod_labels.get(tag_key)
                            item_check = item_check.exclude(pod_labels__contains={tag_key: tag_key_value})
                            line_item = OCPUsageLineItemDailySummary.objects.filter(
                                usage_start=start_date,
                                usage_end=start_date,
                                report_period=report_period,
                                cluster_id=cluster_id,
                                cluster_alias=cluster_alias,
                                monthly_cost_type="Node",
                                node=node,
                            ).first()
                            if not line_item:
                                line_item = OCPUsageLineItemDailySummary(
                                    uuid=uuid.uuid4(),
                                    usage_start=start_date,
                                    usage_end=start_date,
                                    report_period=report_period,
                                    cluster_id=cluster_id,
                                    cluster_alias=cluster_alias,
                                    monthly_cost_type="Node",
                                    node=node,
                                )
                            if rate_type == metric_constants.INFRASTRUCTURE_COST_TYPE:
                                LOG.info(
                                    "Node (%s) has a default monthly infrastructure cost of %s.", node, tag_default
                                )
                                line_item.infrastructure_monthly_cost = (
                                    Coalesce(
                                        line_item.infrastructure_monthly_cost, Value(0.0), output_field=DecimalField()
                                    )
                                    + tag_default
                                )
                            elif rate_type == metric_constants.SUPPLEMENTARY_COST_TYPE:
                                LOG.info(
                                    "Node (%s) has a default monthly supplemenarty cost of %s.", node, tag_default
                                )
                                line_item.supplementary_monthly_cost = (
                                    Coalesce(
                                        line_item.supplementary_monthly_cost, Value(0.0), output_field=DecimalField()
                                    )
                                    + tag_default
                                )
                            line_item.save()

    def tag_upsert_monthly_default_pvc_cost_line_item(
        self, start_date, end_date, cluster_id, cluster_alias, rate_type, rate_dict
    ):
        """
        Update or insert daily summary line item for node cost.
        It checks to see if a line item exists for each node
        that contains the tag key:value pair,
        if it does then the price is added to the monthly cost.
        """
        unique_pvcs = self.get_distinct_pvcs(start_date, end_date, cluster_id)
        report_period = self.get_usage_period_by_dates_and_cluster(start_date, end_date, cluster_id)
        with schema_context(self.schema):
            for pvc, node in unique_pvcs:
                if rate_dict is not None:
                    for tag_key in rate_dict:
                        tag_values = rate_dict.get(tag_key)
                        tag_default = tag_values.get("default_value")
                        values_to_skip = tag_values.get("defined_keys")
                        item_check = OCPUsageLineItemDailySummary.objects.filter(
                            usage_start__gte=start_date,
                            usage_end__lte=end_date,
                            report_period=report_period,
                            cluster_id=cluster_id,
                            cluster_alias=cluster_alias,
                            persistentvolumeclaim=pvc,
                            node=node,
                            volume_labels__has_key=tag_key,
                        )
                        for value in values_to_skip:
                            item_check = item_check.exclude(volume_labels__contains={tag_key: value})
                        # this won't run if there are no matching items and item_check will continue to be
                        # filtered until there are no items left
                        while item_check:
                            # get the first value for our tag key and exclude it from the queryset for the next check
                            # will remove values until there are none left
                            tag_key_value = item_check.first().volume_labels.get(tag_key)
                            item_check = item_check.exclude(volume_labels__contains={tag_key: tag_key_value})
                            line_item = OCPUsageLineItemDailySummary.objects.filter(
                                usage_start=start_date,
                                usage_end=start_date,
                                report_period=report_period,
                                cluster_id=cluster_id,
                                cluster_alias=cluster_alias,
                                monthly_cost_type="PVC",
                                persistentvolumeclaim=pvc,
                                node=node,
                            ).first()
                            if not line_item:
                                line_item = OCPUsageLineItemDailySummary(
                                    uuid=uuid.uuid4(),
                                    usage_start=start_date,
                                    usage_end=start_date,
                                    report_period=report_period,
                                    cluster_id=cluster_id,
                                    cluster_alias=cluster_alias,
                                    monthly_cost_type="PVC",
                                    persistentvolumeclaim=pvc,
                                    node=node,
                                )
                            if rate_type == metric_constants.INFRASTRUCTURE_COST_TYPE:
                                LOG.info("PVC (%s) has a default monthly infrastructure cost of %s.", pvc, tag_default)
                                line_item.infrastructure_monthly_cost = (
                                    Coalesce(
                                        line_item.infrastructure_monthly_cost, Value(0.0), output_field=DecimalField()
                                    )
                                    + tag_default
                                )
                            elif rate_type == metric_constants.SUPPLEMENTARY_COST_TYPE:
                                LOG.info("PVC (%s) has a default monthly supplemenarty cost of %s.", pvc, tag_default)
                                line_item.supplementary_monthly_cost = (
                                    Coalesce(
                                        line_item.supplementary_monthly_cost, Value(0.0), output_field=DecimalField()
                                    )
                                    + tag_default
                                )
                            line_item.save()

    def upsert_monthly_cluster_cost_line_item(
        self, start_date, end_date, cluster_id, cluster_alias, rate_type, cluster_cost
    ):
        """Update or insert a daily summary line item for cluster cost."""
        report_period = self.get_usage_period_by_dates_and_cluster(start_date, end_date, cluster_id)
        if report_period:
            with schema_context(self.schema):
                line_item = OCPUsageLineItemDailySummary.objects.filter(
                    usage_start=start_date,
                    usage_end=start_date,
                    report_period=report_period,
                    cluster_id=cluster_id,
                    cluster_alias=cluster_alias,
                    monthly_cost_type="Cluster",
                ).first()
                if not line_item:
                    line_item = OCPUsageLineItemDailySummary(
                        uuid=uuid.uuid4(),
                        usage_start=start_date,
                        usage_end=start_date,
                        report_period=report_period,
                        cluster_id=cluster_id,
                        cluster_alias=cluster_alias,
                        monthly_cost_type="Cluster",
                    )
                if rate_type == metric_constants.INFRASTRUCTURE_COST_TYPE:
                    LOG.info("Cluster (%s) has a monthly infrastructure cost of %s.", cluster_id, cluster_cost)
                    line_item.infrastructure_monthly_cost = cluster_cost
                elif rate_type == metric_constants.SUPPLEMENTARY_COST_TYPE:
                    LOG.info("Cluster (%s) has a monthly supplemenarty cost of %s.", cluster_id, cluster_cost)
                    line_item.supplementary_monthly_cost = cluster_cost
                line_item.save()

    def tag_upsert_monthly_pvc_cost_line_item(
        self, start_date, end_date, cluster_id, cluster_alias, rate_type, rate_dict
    ):
        """
        Update or insert daily summary line item for PVC cost.

        It checks to see if a line item exists for each PVC
        that contains the tag key:value pair,
        if it does then the price is added to the monthly cost.
        """
        unique_pvcs = self.get_distinct_pvcs(start_date, end_date, cluster_id)
        report_period = self.get_usage_period_by_dates_and_cluster(start_date, end_date, cluster_id)
        with schema_context(self.schema):
            for pvc, node in unique_pvcs:
                if rate_dict is not None:
                    for tag_key in rate_dict:
                        tag_values = rate_dict.get(tag_key)
                        for value_name, rate_value in tag_values.items():
                            item_check = OCPUsageLineItemDailySummary.objects.filter(
                                usage_start__gte=start_date,
                                usage_end__lte=end_date,
                                report_period=report_period,
                                cluster_id=cluster_id,
                                cluster_alias=cluster_alias,
                                persistentvolumeclaim=pvc,
                                node=node,
                                volume_labels__contains={tag_key: value_name},
                            ).first()
                            if item_check:
                                line_item = OCPUsageLineItemDailySummary.objects.filter(
                                    usage_start=start_date,
                                    usage_end=start_date,
                                    report_period=report_period,
                                    cluster_id=cluster_id,
                                    cluster_alias=cluster_alias,
                                    monthly_cost_type="PVC",
                                    persistentvolumeclaim=pvc,
                                    node=node,
                                ).first()
                                if not line_item:
                                    line_item = OCPUsageLineItemDailySummary(
                                        uuid=uuid.uuid4(),
                                        usage_start=start_date,
                                        usage_end=start_date,
                                        report_period=report_period,
                                        cluster_id=cluster_id,
                                        cluster_alias=cluster_alias,
                                        monthly_cost_type="PVC",
                                        persistentvolumeclaim=pvc,
                                        node=node,
                                    )
                                if rate_type == metric_constants.INFRASTRUCTURE_COST_TYPE:
                                    LOG.info("PVC (%s) has a monthly infrastructure cost of %s.", pvc, rate_value)
                                    line_item.infrastructure_monthly_cost = (
                                        Coalesce(
                                            line_item.infrastructure_monthly_cost,
                                            Value(0.0),
                                            output_field=DecimalField(),
                                        )
                                        + rate_value
                                    )
                                elif rate_type == metric_constants.SUPPLEMENTARY_COST_TYPE:
                                    LOG.info("PVC (%s) has a monthly supplemenarty cost of %s.", pvc, rate_value)
                                    line_item.supplementary_monthly_cost = (
                                        Coalesce(
                                            line_item.supplementary_monthly_cost,
                                            Value(0.0),
                                            output_field=DecimalField(),
                                        )
                                        + rate_value
                                    )
                                line_item.save()

    def upsert_monthly_pvc_cost_line_item(self, start_date, end_date, cluster_id, cluster_alias, rate_type, pvc_cost):
        """Update or insert daily summary line item for pvc cost."""
        unique_pvcs = self.get_distinct_pvcs(start_date, end_date, cluster_id)
        report_period = self.get_usage_period_by_dates_and_cluster(start_date, end_date, cluster_id)
        with schema_context(self.schema):
            for pvc, node in unique_pvcs:
                line_item = OCPUsageLineItemDailySummary.objects.filter(
                    usage_start=start_date,
                    usage_end=start_date,
                    report_period=report_period,
                    cluster_id=cluster_id,
                    cluster_alias=cluster_alias,
                    monthly_cost_type="PVC",
                    persistentvolumeclaim=pvc,
                    node=node,
                ).first()
                if not line_item:
                    line_item = OCPUsageLineItemDailySummary(
                        uuid=uuid.uuid4(),
                        usage_start=start_date,
                        usage_end=start_date,
                        report_period=report_period,
                        cluster_id=cluster_id,
                        cluster_alias=cluster_alias,
                        monthly_cost_type="PVC",
                        persistentvolumeclaim=pvc,
                        node=node,
                    )
                if rate_type == metric_constants.INFRASTRUCTURE_COST_TYPE:
                    LOG.info("PVC (%s) has a monthly infrastructure cost of %s.", pvc, pvc_cost)
                    line_item.infrastructure_monthly_cost = pvc_cost
                elif rate_type == metric_constants.SUPPLEMENTARY_COST_TYPE:
                    LOG.info("PVC (%s) has a monthly supplemenarty cost of %s.", pvc, pvc_cost)
                    line_item.supplementary_monthly_cost = pvc_cost
                line_item.save()

    def tag_upsert_monthly_cluster_cost_line_item(
        self, start_date, end_date, cluster_id, cluster_alias, rate_type, rate_dict
    ):
        """
        Update or insert a daily summary line item for cluster cost based on tag rates.
        It checks to see if a line item exists for the cluster
        that contains the tag key:value pair,
        if it does then the price is added to the monthly cost.
        """
        report_period = self.get_usage_period_by_dates_and_cluster(start_date, end_date, cluster_id)
        if report_period:
            with schema_context(self.schema):
                if rate_dict is not None:
                    for tag_key in rate_dict:
                        tag_values = rate_dict.get(tag_key)
                        for value_name, rate_value in tag_values.items():
                            # this makes sure that there is an entry for that node
                            # that contains the specified key_value pair
                            item_check = line_item = OCPUsageLineItemDailySummary.objects.filter(
                                usage_start__gte=start_date,
                                usage_end__lte=end_date,
                                report_period=report_period,
                                cluster_id=cluster_id,
                                cluster_alias=cluster_alias,
                                pod_labels__contains={tag_key: value_name},
                            ).first()
                            if item_check:
                                line_item = OCPUsageLineItemDailySummary.objects.filter(
                                    usage_start=start_date,
                                    usage_end=start_date,
                                    report_period=report_period,
                                    cluster_id=cluster_id,
                                    cluster_alias=cluster_alias,
                                    monthly_cost_type="Cluster",
                                ).first()
                                if not line_item:
                                    line_item = OCPUsageLineItemDailySummary(
                                        uuid=uuid.uuid4(),
                                        usage_start=start_date,
                                        usage_end=start_date,
                                        report_period=report_period,
                                        cluster_id=cluster_id,
                                        cluster_alias=cluster_alias,
                                        monthly_cost_type="Cluster",
                                    )
                                if rate_type == metric_constants.INFRASTRUCTURE_COST_TYPE:
                                    LOG.info(
                                        "Cluster (%s) has a monthly infrastructure cost of %s from tag rates.",
                                        cluster_id,
                                        rate_value,
                                    )
                                    line_item.infrastructure_monthly_cost = (
                                        Coalesce(
                                            line_item.infrastructure_monthly_cost,
                                            Value(0.0),
                                            output_field=DecimalField(),
                                        )
                                        + rate_value
                                    )
                                elif rate_type == metric_constants.SUPPLEMENTARY_COST_TYPE:
                                    LOG.info(
                                        "Cluster (%s) has a monthly supplemenarty cost of %s from tag rates.",
                                        cluster_id,
                                        rate_value,
                                    )
                                    line_item.supplementary_monthly_cost = (
                                        Coalesce(
                                            line_item.supplementary_monthly_cost,
                                            Value(0.0),
                                            output_field=DecimalField(),
                                        )
                                        + rate_value
                                    )
                                line_item.save()

    def tag_upsert_monthly_default_cluster_cost_line_item(
        self, start_date, end_date, cluster_id, cluster_alias, rate_type, rate_dict
    ):
        """
        Update or insert daily summary line item for cluster cost.

        It checks to see if a line item exists for each cluster
        that contains the tag key:value pair,
        if it does then the price is added to the monthly cost.
        """
        report_period = self.get_usage_period_by_dates_and_cluster(start_date, end_date, cluster_id)
        with schema_context(self.schema):
            if rate_dict is not None:
                for tag_key in rate_dict:
                    tag_values = rate_dict.get(tag_key)
                    tag_default = tag_values.get("default_value")
                    values_to_skip = tag_values.get("defined_keys")
                    item_check = OCPUsageLineItemDailySummary.objects.filter(
                        usage_start__gte=start_date,
                        usage_end__lte=end_date,
                        report_period=report_period,
                        cluster_id=cluster_id,
                        cluster_alias=cluster_alias,
                        pod_labels__has_key=tag_key,
                    )
                    for value in values_to_skip:
                        item_check = item_check.exclude(pod_labels__contains={tag_key: value})
                    # this won't run if there are no matching items and item_check will continue to be
                    # filtered until there are no items left
                    while item_check:
                        # get the first value for our tag key and exclude it from the queryset for the next check
                        # will remove values until there are none left
                        tag_key_value = item_check.first().pod_labels.get(tag_key)
                        item_check = item_check.exclude(pod_labels__contains={tag_key: tag_key_value})
                        line_item = OCPUsageLineItemDailySummary.objects.filter(
                            usage_start=start_date,
                            usage_end=start_date,
                            report_period=report_period,
                            cluster_id=cluster_id,
                            cluster_alias=cluster_alias,
                            monthly_cost_type="Cluster",
                        ).first()
                        if not line_item:
                            line_item = OCPUsageLineItemDailySummary(
                                uuid=uuid.uuid4(),
                                usage_start=start_date,
                                usage_end=start_date,
                                report_period=report_period,
                                cluster_id=cluster_id,
                                cluster_alias=cluster_alias,
                                monthly_cost_type="Cluster",
                            )
                        if rate_type == metric_constants.INFRASTRUCTURE_COST_TYPE:
                            LOG.info(
                                "Cluster (%s) has a default monthly infrastructure cost of %s.",
                                cluster_id,
                                tag_default,
                            )
                            line_item.infrastructure_monthly_cost = (
                                Coalesce(
                                    line_item.infrastructure_monthly_cost, Value(0.0), output_field=DecimalField()
                                )
                                + tag_default
                            )
                        elif rate_type == metric_constants.SUPPLEMENTARY_COST_TYPE:
                            LOG.info(
                                "Cluster (%s) has a default monthly supplemenarty cost of %s.", cluster_id, tag_default
                            )
                            line_item.supplementary_monthly_cost = (
                                Coalesce(line_item.supplementary_monthly_cost, Value(0.0), output_field=DecimalField())
                                + tag_default
                            )
                        line_item.save()

    def remove_monthly_cost(self, start_date, end_date, cluster_id, cost_type):
        """Delete all monthly costs of a specific type over a date range."""
        report_period = self.get_usage_period_by_dates_and_cluster(start_date, end_date, cluster_id)

        filters = {
            "usage_start": start_date.date(),
            "usage_end": start_date.date(),
            "report_period": report_period,
            "cluster_id": cluster_id,
            "monthly_cost_type": cost_type,
        }

        for rate_type, __ in metric_constants.COST_TYPE_CHOICES:
            cost_filter = f"{rate_type.lower()}_monthly_cost__isnull"
            filters.update({cost_filter: False})
            LOG.info(
                "Removing %s %s monthly costs \n\tfor %s \n\tfrom %s - %s.",
                cost_type,
                rate_type,
                cluster_id,
                start_date,
                end_date,
            )
            with schema_context(self.schema):
                OCPUsageLineItemDailySummary.objects.filter(**filters).all().delete()
            filters.pop(cost_filter)

    def populate_node_label_line_item_daily_table(self, start_date, end_date, cluster_id):
        """Populate the daily node label aggregate of line items table.

        Args:
            start_date (datetime.date) The date to start populating the table.
            end_date (datetime.date) The date to end on.
            cluster_id (String) Cluster Identifier

        Returns
            (None)

        """
        # Cast string to date object
        if isinstance(start_date, str):
            start_date = datetime.datetime.strptime(start_date, "%Y-%m-%d").date()
            end_date = datetime.datetime.strptime(end_date, "%Y-%m-%d").date()
        if isinstance(start_date, datetime.datetime):
            start_date = start_date.date()
            end_date = end_date.date()
        table_name = OCP_REPORT_TABLE_MAP["node_label_line_item_daily"]

        daily_sql = pkgutil.get_data("masu.database", "sql/reporting_ocpnodelabellineitem_daily.sql")
        daily_sql = daily_sql.decode("utf-8")
        daily_sql_params = {
            "uuid": str(uuid.uuid4()).replace("-", "_"),
            "start_date": start_date,
            "end_date": end_date,
            "cluster_id": cluster_id,
            "schema": self.schema,
        }
        daily_sql, daily_sql_params = self.jinja_sql.prepare_query(daily_sql, daily_sql_params)
        self._execute_raw_sql_query(table_name, daily_sql, start_date, end_date, bind_params=list(daily_sql_params))

    def populate_usage_costs(self, infrastructure_rates, supplementary_rates, start_date, end_date, cluster_id):
        """Update the reporting_ocpusagelineitem_daily_summary table with usage costs."""
        # Cast start_date and end_date to date object, if they aren't already
        if isinstance(start_date, str):
            start_date = datetime.datetime.strptime(start_date, "%Y-%m-%d").date()
            end_date = datetime.datetime.strptime(end_date, "%Y-%m-%d").date()
        if isinstance(start_date, datetime.datetime):
            start_date = start_date.date()
            end_date = end_date.date()

        OCPUsageLineItemDailySummary.objects.filter(
            cluster_id=cluster_id, usage_start__gte=start_date, usage_start__lte=end_date
        ).update(
            infrastructure_usage_cost=JSONBBuildObject(
                Value("cpu"),
                Coalesce(
                    Value(infrastructure_rates.get("cpu_core_usage_per_hour", 0), output_field=DecimalField())
                    * Coalesce(F("pod_usage_cpu_core_hours"), Value(0), output_field=DecimalField())
                    + Value(infrastructure_rates.get("cpu_core_request_per_hour", 0), output_field=DecimalField())
                    * Coalesce(F("pod_request_cpu_core_hours"), Value(0), output_field=DecimalField()),
                    0,
                    output_field=DecimalField(),
                ),
                Value("memory"),
                Coalesce(
                    Value(infrastructure_rates.get("memory_gb_usage_per_hour", 0), output_field=DecimalField())
                    * Coalesce(F("pod_usage_memory_gigabyte_hours"), Value(0), output_field=DecimalField())
                    + Value(infrastructure_rates.get("memory_gb_request_per_hour", 0), output_field=DecimalField())
                    * Coalesce(F("pod_request_memory_gigabyte_hours"), Value(0), output_field=DecimalField()),
                    0,
                    output_field=DecimalField(),
                ),
                Value("storage"),
                Coalesce(
                    Value(infrastructure_rates.get("storage_gb_usage_per_month", 0), output_field=DecimalField())
                    * Coalesce(F("persistentvolumeclaim_usage_gigabyte_months"), Value(0), output_field=DecimalField())
                    + Value(infrastructure_rates.get("storage_gb_request_per_month", 0), output_field=DecimalField())
                    * Coalesce(F("volume_request_storage_gigabyte_months"), Value(0), output_field=DecimalField()),
                    0,
                    output_field=DecimalField(),
                ),
            ),
            supplementary_usage_cost=JSONBBuildObject(
                Value("cpu"),
                Coalesce(
                    Value(supplementary_rates.get("cpu_core_usage_per_hour", 0), output_field=DecimalField())
                    * Coalesce(F("pod_usage_cpu_core_hours"), Value(0), output_field=DecimalField())
                    + Value(supplementary_rates.get("cpu_core_request_per_hour", 0), output_field=DecimalField())
                    * Coalesce(F("pod_request_cpu_core_hours"), Value(0), output_field=DecimalField()),
                    0,
                    output_field=DecimalField(),
                ),
                Value("memory"),
                Coalesce(
                    Value(supplementary_rates.get("memory_gb_usage_per_hour", 0), output_field=DecimalField())
                    * Coalesce(F("pod_usage_memory_gigabyte_hours"), Value(0), output_field=DecimalField())
                    + Value(supplementary_rates.get("memory_gb_request_per_hour", 0), output_field=DecimalField())
                    * Coalesce(F("pod_request_memory_gigabyte_hours"), Value(0), output_field=DecimalField()),
                    0,
                    output_field=DecimalField(),
                ),
                Value("storage"),
                Coalesce(
                    Value(supplementary_rates.get("storage_gb_usage_per_month", 0), output_field=DecimalField())
                    * Coalesce(F("persistentvolumeclaim_usage_gigabyte_months"), Value(0), output_field=DecimalField())
                    + Value(supplementary_rates.get("storage_gb_request_per_month", 0), output_field=DecimalField())
                    * Coalesce(F("volume_request_storage_gigabyte_months"), Value(0), output_field=DecimalField()),
                    0,
                    output_field=DecimalField(),
                ),
            ),
        )

    def populate_tag_usage_costs(  # noqa: C901
        self, infrastructure_rates, supplementary_rates, start_date, end_date, cluster_id
    ):
        """
        Update the reporting_ocpusagelineitem_daily_summary table with
        usage costs based on tag rates.
        Due to the way the tag_keys are stored it loops through all of
        the tag keys to filter and update costs.

        The data structure for infrastructure and supplementary rates are
        a dictionary that include the metric name, the tag key,
        the tag value names, and the tag value, for example:
            {'cpu_core_usage_per_hour': {
                'app': {
                    'far': '0.2000000000', 'manager': '100.0000000000', 'walk': '5.0000000000'
                    }
                }
            }
        """
        # defines the usage type for each metric
        metric_usage_type_map = {
            "cpu_core_usage_per_hour": "cpu",
            "cpu_core_request_per_hour": "cpu",
            "memory_gb_usage_per_hour": "memory",
            "memory_gb_request_per_hour": "memory",
            "storage_gb_usage_per_month": "storage",
            "storage_gb_request_per_month": "storage",
        }
        # define the rates so the loop can operate on both rate types
        rate_types = [
            {"rates": infrastructure_rates, "sql_file": "sql/infrastructure_tag_rates.sql"},
            {"rates": supplementary_rates, "sql_file": "sql/supplementary_tag_rates.sql"},
        ]
        # Cast start_date and end_date to date object, if they aren't already
        if isinstance(start_date, str):
            start_date = datetime.datetime.strptime(start_date, "%Y-%m-%d").date()
            end_date = datetime.datetime.strptime(end_date, "%Y-%m-%d").date()
        if isinstance(start_date, datetime.datetime):
            start_date = start_date.date()
            end_date = end_date.date()
        # updates costs from tags
        for rate_type in rate_types:
            rate = rate_type.get("rates")
            sql_file = rate_type.get("sql_file")
            for metric in rate:
                tags = rate.get(metric, {})
                usage_type = metric_usage_type_map.get(metric)
                if usage_type == "storage":
                    labels_field = "volume_labels"
                else:
                    labels_field = "pod_labels"
                table_name = OCP_REPORT_TABLE_MAP["line_item_daily_summary"]
                for tag_key in tags:
                    tag_vals = tags.get(tag_key, {})
                    value_names = list(tag_vals.keys())
                    for val_name in value_names:
                        rate_value = tag_vals[val_name]
                        key_value_pair = json.dumps({tag_key: val_name})
                        tag_rates_sql = pkgutil.get_data("masu.database", sql_file)
                        tag_rates_sql = tag_rates_sql.decode("utf-8")
                        tag_rates_sql_params = {
                            "start_date": start_date,
                            "end_date": end_date,
                            "rate": rate_value,
                            "cluster_id": cluster_id,
                            "schema": self.schema,
                            "usage_type": usage_type,
                            "metric": metric,
                            "k_v_pair": key_value_pair,
                            "labels_field": labels_field,
                        }
                        tag_rates_sql, tag_rates_sql_params = self.jinja_sql.prepare_query(
                            tag_rates_sql, tag_rates_sql_params
                        )
                        msg = f"Running populate_tag_usage_costs SQL with params: {tag_rates_sql_params}"
                        LOG.info(msg)
                        self._execute_raw_sql_query(
                            table_name, tag_rates_sql, start_date, end_date, bind_params=list(tag_rates_sql_params)
                        )

    def populate_tag_usage_default_costs(  # noqa: C901
        self, infrastructure_rates, supplementary_rates, start_date, end_date, cluster_id
    ):
        """
        Update the reporting_ocpusagelineitem_daily_summary table
        with usage costs based on tag rates.

        The data structure for infrastructure and supplementary rates
        are a dictionary that includes the metric, the tag key,
        the default value, and the values for that key that have
        rates defined and do not need the default applied,
        for example:
            {
                'cpu_core_usage_per_hour': {
                    'app': {
                        'default_value': '100.0000000000', 'defined_keys': ['far', 'manager', 'walk']
                    }
                }
            }
        """
        # defines the usage type for each metric
        metric_usage_type_map = {
            "cpu_core_usage_per_hour": "cpu",
            "cpu_core_request_per_hour": "cpu",
            "memory_gb_usage_per_hour": "memory",
            "memory_gb_request_per_hour": "memory",
            "storage_gb_usage_per_month": "storage",
            "storage_gb_request_per_month": "storage",
        }
        # define the rates so the loop can operate on both rate types
        rate_types = [
            {"rates": infrastructure_rates, "sql_file": "sql/default_infrastructure_tag_rates.sql"},
            {"rates": supplementary_rates, "sql_file": "sql/default_supplementary_tag_rates.sql"},
        ]
        # Cast start_date and end_date to date object, if they aren't already
        if isinstance(start_date, str):
            start_date = datetime.datetime.strptime(start_date, "%Y-%m-%d").date()
            end_date = datetime.datetime.strptime(end_date, "%Y-%m-%d").date()
        if isinstance(start_date, datetime.datetime):
            start_date = start_date.date()
            end_date = end_date.date()

        # updates costs from tags
        for rate_type in rate_types:
            rate = rate_type.get("rates")
            sql_file = rate_type.get("sql_file")
            for metric in rate:
                tags = rate.get(metric, {})
                usage_type = metric_usage_type_map.get(metric)
                if usage_type == "storage":
                    labels_field = "volume_labels"
                else:
                    labels_field = "pod_labels"
                table_name = OCP_REPORT_TABLE_MAP["line_item_daily_summary"]
                for tag_key in tags:
                    key_value_pair = []
                    tag_vals = tags.get(tag_key)
                    rate_value = tag_vals.get("default_value", 0)
                    if rate_value == 0:
                        continue
                    value_names = tag_vals.get("defined_keys", [])
                    for value_to_skip in value_names:
                        key_value_pair.append(json.dumps({tag_key: value_to_skip}))
                    json.dumps(key_value_pair)
                    tag_rates_sql = pkgutil.get_data("masu.database", sql_file)
                    tag_rates_sql = tag_rates_sql.decode("utf-8")
                    tag_rates_sql_params = {
                        "start_date": start_date,
                        "end_date": end_date,
                        "rate": rate_value,
                        "cluster_id": cluster_id,
                        "schema": self.schema,
                        "usage_type": usage_type,
                        "metric": metric,
                        "tag_key": tag_key,
                        "k_v_pair": key_value_pair,
                        "labels_field": labels_field,
                    }
                    tag_rates_sql, tag_rates_sql_params = self.jinja_sql.prepare_query(
                        tag_rates_sql, tag_rates_sql_params
                    )
                    msg = f"Running populate_tag_usage_default_costs SQL with params: {tag_rates_sql_params}"
                    LOG.info(msg)
                    self._execute_raw_sql_query(
                        table_name, tag_rates_sql, start_date, end_date, bind_params=list(tag_rates_sql_params)
                    )
