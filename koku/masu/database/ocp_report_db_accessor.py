#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Database accessor for OCP report data."""
import copy
import datetime
import json
import logging
import pkgutil
import uuid
from decimal import Decimal

import pytz
from dateutil.parser import parse
from dateutil.rrule import MONTHLY
from dateutil.rrule import rrule
from django.db import connection
from django.db.models import DecimalField
from django.db.models import F
from django.db.models import Sum
from django.db.models import Value
from django.db.models.functions import Coalesce
from jinjasql import JinjaSql
from tenant_schemas.utils import schema_context

import koku.presto_database as kpdb
from api.metrics import constants as metric_constants
from api.utils import DateHelper
from koku.database import JSONBBuildObject
from koku.database import SQLScriptAtomicExecutorMixin
from masu.config import Config
from masu.database import AWS_CUR_TABLE_MAP
from masu.database import OCP_REPORT_TABLE_MAP
from masu.database.report_db_accessor_base import ReportDBAccessorBase
from masu.util.common import month_date_range_tuple
from reporting.provider.aws.models import PRESTO_LINE_ITEM_DAILY_TABLE as AWS_PRESTO_LINE_ITEM_DAILY_TABLE
from reporting.provider.azure.models import PRESTO_LINE_ITEM_DAILY_TABLE as AZURE_PRESTO_LINE_ITEM_DAILY_TABLE
from reporting.provider.gcp.models import PRESTO_LINE_ITEM_DAILY_TABLE as GCP_PRESTO_LINE_ITEM_DAILY_TABLE
from reporting.provider.ocp.models import OCPCluster
from reporting.provider.ocp.models import OCPNode
from reporting.provider.ocp.models import OCPProject
from reporting.provider.ocp.models import OCPPVC
from reporting.provider.ocp.models import OCPUsageLineItemDailySummary
from reporting.provider.ocp.models import OCPUsageReport
from reporting.provider.ocp.models import OCPUsageReportPeriod
from reporting.provider.ocp.models import PRESTO_LINE_ITEM_TABLE_DAILY_MAP

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


class OCPReportDBAccessor(SQLScriptAtomicExecutorMixin, ReportDBAccessorBase):
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
        self._table_map = OCP_REPORT_TABLE_MAP
        self._aws_table_map = AWS_CUR_TABLE_MAP

    @property
    def line_item_daily_summary_table(self):
        return OCPUsageLineItemDailySummary

    def get_current_usage_report(self):
        """Get the most recent usage report object."""
        table_name = self._table_map["report"]

        with schema_context(self.schema):
            return self._get_db_obj_query(table_name).order_by("-interval_start").first()

    def get_current_usage_period(self):
        """Get the most recent usage report period object."""
        table_name = self._table_map["report_period"]

        with schema_context(self.schema):
            return self._get_db_obj_query(table_name).order_by("-report_period_start").first()

    def get_usage_periods_by_date(self, start_date):
        """Return all report period entries for the specified start date."""
        table_name = self._table_map["report_period"]
        with schema_context(self.schema):
            return self._get_db_obj_query(table_name).filter(report_period_start=start_date).all()

    def get_usage_period_by_dates_and_cluster(self, start_date, end_date, cluster_id):
        """Return all report period entries for the specified start date."""
        table_name = self._table_map["report_period"]
        with schema_context(self.schema):
            return (
                self._get_db_obj_query(table_name)
                .filter(report_period_start=start_date, report_period_end=end_date, cluster_id=cluster_id)
                .first()
            )

    def get_usage_period_on_or_before_date(self, date, provider_uuid=None):
        """Get the usage report period objects before provided date."""
        table_name = self._table_map["report_period"]

        with schema_context(self.schema):
            base_query = self._get_db_obj_query(table_name)
            if provider_uuid:
                usage_period_query = base_query.filter(report_period_start__lte=date, provider_id=provider_uuid)
            else:
                usage_period_query = base_query.filter(report_period_start__lte=date)
            return usage_period_query

    def get_usage_period_query_by_provider(self, provider_uuid):
        """Return all report periods for the specified provider."""
        table_name = self._table_map["report_period"]
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
                report_periods = report_periods.filter(report_period_start=report_date).first()

            return report_periods

    def get_lineitem_query_for_reportid(self, query_report_id):
        """Get the usage report line item for a report id query."""
        table_name = self._table_map["line_item"]
        with schema_context(self.schema):
            base_query = self._get_db_obj_query(table_name)
            line_item_query = base_query.filter(report_id=query_report_id)
            return line_item_query

    def get_daily_usage_query_for_clusterid(self, cluster_identifier):
        """Get the usage report daily item for a cluster id query."""
        table_name = self._table_map["line_item_daily"]
        with schema_context(self.schema):
            base_query = self._get_db_obj_query(table_name)
            daily_usage_query = base_query.filter(cluster_id=cluster_identifier)
            return daily_usage_query

    def get_summary_usage_query_for_clusterid(self, cluster_identifier):
        """Get the usage report summary for a cluster id query."""
        table_name = self._table_map["line_item_daily_summary"]
        with schema_context(self.schema):
            base_query = self._get_db_obj_query(table_name)
            summary_usage_query = base_query.filter(cluster_id=cluster_identifier)
            return summary_usage_query

    def get_item_query_report_period_id(self, report_period_id):
        """Get the usage report line item for a report id query."""
        table_name = self._table_map["line_item"]
        with schema_context(self.schema):
            base_query = self._get_db_obj_query(table_name)
            line_item_query = base_query.filter(report_period_id=report_period_id)
            return line_item_query

    def get_storage_item_query_report_period_id(self, report_period_id):
        """Get the storage report line item for a report id query."""
        table_name = self._table_map["storage_line_item"]
        with schema_context(self.schema):
            base_query = self._get_db_obj_query(table_name)
            line_item_query = base_query.filter(report_period_id=report_period_id)
            return line_item_query

    def get_daily_storage_item_query_cluster_id(self, cluster_identifier):
        """Get the daily storage report line item for a cluster id query."""
        table_name = self._table_map["storage_line_item_daily"]
        with schema_context(self.schema):
            base_query = self._get_db_obj_query(table_name)
            daily_item_query = base_query.filter(cluster_id=cluster_identifier)
            return daily_item_query

    def get_storage_summary_query_cluster_id(self, cluster_identifier):
        """Get the storage report summary for a cluster id query."""
        table_name = self._table_map["line_item_daily_summary"]
        filters = {"cluster_id": cluster_identifier, "data_source": "Storage"}
        with schema_context(self.schema):
            base_query = self._get_db_obj_query(table_name)
            daily_item_query = base_query.filter(**filters)
            return daily_item_query

    def get_node_label_item_query_report_period_id(self, report_period_id):
        """Get the node label report line item for a report id query."""
        table_name = self._table_map["node_label_line_item"]
        with schema_context(self.schema):
            base_query = self._get_db_obj_query(table_name)
            line_item_query = base_query.filter(report_period_id=report_period_id)
            return line_item_query

    def get_ocp_aws_summary_query_for_cluster_id(self, cluster_identifier):
        """Get the OCP-on-AWS report summary item for a given cluster id query."""
        table_name = self._aws_table_map["ocp_on_aws_daily_summary"]
        with schema_context(self.schema):
            base_query = self._get_db_obj_query(table_name)
            summary_item_query = base_query.filter(cluster_id=cluster_identifier)
            return summary_item_query

    def get_ocp_aws_project_summary_query_for_cluster_id(self, cluster_identifier):
        """Get the OCP-on-AWS report project summary item for a given cluster id query."""
        table_name = self._aws_table_map["ocp_on_aws_project_daily_summary"]
        with schema_context(self.schema):
            base_query = self._get_db_obj_query(table_name)
            summary_item_query = base_query.filter(cluster_id=cluster_identifier)
            return summary_item_query

    def get_report_query_report_period_id(self, report_period_id):
        """Get the usage report line item for a report id query."""
        table_name = self._table_map["report"]
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

        table_name = self._table_map["line_item_daily"]

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
        table_name = self._table_map["line_item_daily_summary"]
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

    def get_ocp_infrastructure_map_trino(self, start_date, end_date, **kwargs):
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
        gcp_provider_uuid = kwargs.get("gcp_provider_uuid")

        if not self.table_exists_trino(PRESTO_LINE_ITEM_TABLE_DAILY_MAP.get("pod_usage")):
            return {}
        if aws_provider_uuid and not self.table_exists_trino(AWS_PRESTO_LINE_ITEM_DAILY_TABLE):
            return {}
        if azure_provider_uuid and not self.table_exists_trino(AZURE_PRESTO_LINE_ITEM_DAILY_TABLE):
            return {}
        if gcp_provider_uuid and not self.table_exists_trino(GCP_PRESTO_LINE_ITEM_DAILY_TABLE):
            return {}

        if isinstance(start_date, str):
            start_date = datetime.datetime.strptime(start_date, "%Y-%m-%d").date()
            end_date = datetime.datetime.strptime(end_date, "%Y-%m-%d").date()
        infra_sql = pkgutil.get_data("masu.database", "presto_sql/reporting_ocpinfrastructure_provider_map.sql")
        infra_sql = infra_sql.decode("utf-8")
        infra_sql_params = {
            "start_date": start_date,
            "end_date": end_date,
            "year": start_date.strftime("%Y"),
            "month": start_date.strftime("%m"),
            "schema": self.schema,
            "aws_provider_uuid": aws_provider_uuid,
            "ocp_provider_uuid": ocp_provider_uuid,
            "azure_provider_uuid": azure_provider_uuid,
            "gcp_provider_uuid": gcp_provider_uuid,
        }
        infra_sql, infra_sql_params = self.jinja_sql.prepare_query(infra_sql, infra_sql_params)
        results = self._execute_presto_raw_sql_query(self.schema, infra_sql, bind_params=infra_sql_params)
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
        table_name = self._table_map["storage_line_item_daily"]

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
        table_name = self._table_map["line_item_daily_summary"]

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
        table_name = self._table_map["line_item_daily_summary"]

        daily_charge_sql = pkgutil.get_data("masu.database", "sql/reporting_ocp_storage_charge.sql")
        charge_line_sql = daily_charge_sql.decode("utf-8")
        charge_line_sql_params = {"temp_table": temp_table_name, "schema": self.schema}
        charge_line_sql, charge_line_sql_params = self.jinja_sql.prepare_query(charge_line_sql, charge_line_sql_params)
        self._execute_raw_sql_query(table_name, charge_line_sql, bind_params=list(charge_line_sql_params))

    def populate_line_item_daily_summary_table(self, start_date, end_date, cluster_id, source):
        """Populate the daily aggregate of line items table.

        Args:
            start_date (datetime.date) The date to start populating the table.
            end_date (datetime.date) The date to end on.
            cluster_id (String) Cluster Identifier
            source (String) Source UUID

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
        table_name = self._table_map["line_item_daily_summary"]

        summary_sql = pkgutil.get_data("masu.database", "sql/reporting_ocpusagelineitem_daily_summary.sql")
        summary_sql = summary_sql.decode("utf-8")
        summary_sql_params = {
            "uuid": str(uuid.uuid4()).replace("-", "_"),
            "start_date": start_date,
            "end_date": end_date,
            "cluster_id": cluster_id,
            "schema": self.schema,
            "source_uuid": source,
        }
        summary_sql, summary_sql_params = self.jinja_sql.prepare_query(summary_sql, summary_sql_params)
        self._execute_raw_sql_query(
            table_name, summary_sql, start_date, end_date, bind_params=list(summary_sql_params)
        )

    def populate_storage_line_item_daily_summary_table(self, start_date, end_date, cluster_id, source):
        """Populate the daily aggregate of storage line items table.

        Args:
            start_date (datetime.date) The date to start populating the table.
            end_date (datetime.date) The date to end on.
            cluster_id (String) Cluster Identifier
            source (String) Source UUID

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
        table_name = self._table_map["line_item_daily_summary"]

        summary_sql = pkgutil.get_data("masu.database", "sql/reporting_ocpstoragelineitem_daily_summary.sql")
        summary_sql = summary_sql.decode("utf-8")
        summary_sql_params = {
            "uuid": str(uuid.uuid4()).replace("-", "_"),
            "start_date": start_date,
            "end_date": end_date,
            "cluster_id": cluster_id,
            "schema": self.schema,
            "source_uuid": source,
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

    def get_cost_summary_for_clusterid(self, cluster_identifier):
        """Get the cost summary for a cluster id query."""
        table_name = self._table_map["cost_summary"]
        base_query = self._get_db_obj_query(table_name)
        cost_summary_query = base_query.filter(cluster_id=cluster_identifier)
        return cost_summary_query

    def populate_pod_label_summary_table(self, report_period_ids, start_date, end_date):
        """Populate the line item aggregated totals data table."""
        table_name = self._table_map["pod_label_summary"]

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
        table_name = self._table_map["volume_label_summary"]

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
                    namespace__isnull=False,
                )
                .values_list("persistentvolumeclaim", "node", "namespace")
                .distinct()
            )
            return [(pvc[0], pvc[1], pvc[2]) for pvc in unique_pvcs]

    def generate_monthly_cost_json_object(self, distribution, distributed_cost):
        """Generates the default monthly cost dict."""
        default_cost = Decimal(0)
        if not isinstance(distributed_cost, Decimal) and distributed_cost:
            distributed_cost = Decimal(distributed_cost)
        if not distributed_cost:
            distributed_cost = default_cost
        cost_mapping = {distribution: distributed_cost}
        return JSONBBuildObject(
            Value(metric_constants.CPU_DISTRIBUTION),
            cost_mapping.get(metric_constants.CPU_DISTRIBUTION, default_cost),
            Value(metric_constants.MEMORY_DISTRIBUTION),
            cost_mapping.get(metric_constants.MEMORY_DISTRIBUTION, default_cost),
            Value(metric_constants.PVC_DISTRIBUTION),
            cost_mapping.get(metric_constants.PVC_DISTRIBUTION, default_cost),
        )

    def populate_monthly_cost(
        self, cost_type, rate_type, rate, start_date, end_date, cluster_id, cluster_alias, distribution
    ):
        """
        Populate the monthly cost of a customer.

        There are three types of monthly rates Node, Cluster & PVC.

        args:
            cost_type (str): Contains the type of monthly cost. ex: "Node"
            rate_type(str): Contains the metric name. ex: "node_cost_per_month"
            rate (decimal): Contains the rate amount ex: 100.0
            node_cost (Decimal): The node cost per month
            start_date (datetime, str): The start_date to calculate monthly_cost.
            end_date (datetime, str): The end_date to calculate monthly_cost.
            cluster_id (str): The id of the cluster
            cluster_alias: The name of the cluster
            distribution: Choice of monthly distribution ex. memory
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
                        first_curr_month, first_next_month, cluster_id, cluster_alias, rate_type, rate, distribution
                    )
            elif cost_type == "Cluster":
                if rate is None:
                    self.remove_monthly_cost(first_curr_month, first_next_month, cluster_id, cost_type)
                else:
                    # start_date, end_date, cluster_id, cluster_alias, rate_type, cluster_cost
                    self.upsert_monthly_cluster_cost_line_item(
                        first_curr_month, first_next_month, cluster_id, cluster_alias, rate_type, rate, distribution
                    )
            elif cost_type == "PVC":
                if rate is None:
                    self.remove_monthly_cost(first_curr_month, first_next_month, cluster_id, cost_type)
                else:
                    self.upsert_monthly_pvc_cost_line_item(
                        first_curr_month, first_next_month, cluster_id, cluster_alias, rate_type, rate
                    )

    def populate_monthly_tag_cost(
        self, cost_type, rate_type, rate_dict, start_date, end_date, cluster_id, cluster_alias, distribution
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
                    first_curr_month, first_next_month, cluster_id, cluster_alias, rate_type, rate_dict, distribution
                )
            elif cost_type == "Cluster":
                self.tag_upsert_monthly_cluster_cost_line_item(
                    first_curr_month, first_next_month, cluster_id, cluster_alias, rate_type, rate_dict, distribution
                )
            elif cost_type == "PVC":
                self.tag_upsert_monthly_pvc_cost_line_item(
                    first_curr_month, first_next_month, cluster_id, cluster_alias, rate_type, rate_dict
                )

    def populate_monthly_tag_default_cost(
        self, cost_type, rate_type, rate_dict, start_date, end_date, cluster_id, cluster_alias, distribution
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
                    first_curr_month, first_next_month, cluster_id, cluster_alias, rate_type, rate_dict, distribution
                )
            elif cost_type == "Cluster":
                self.tag_upsert_monthly_default_cluster_cost_line_item(
                    first_curr_month, first_next_month, cluster_id, cluster_alias, rate_type, rate_dict, distribution
                )
            elif cost_type == "PVC":
                self.tag_upsert_monthly_default_pvc_cost_line_item(
                    first_curr_month, first_next_month, cluster_id, cluster_alias, rate_type, rate_dict
                )

    def get_node_to_project_distribution(self, start_date, end_date, cluster_id, node_cost):
        """Returns a list of dictionaries containing the distributed cost.

        args:
            start_date (datetime, str): The start_date to calculate monthly_cost.
            end_date (datetime, str): The end_date to calculate monthly_cost.
            cluster_id (str): The id of the cluster
            cluster_cost (dec): The flat cost of the cluster

        Node to Project Distribution:
            - Node to project distribution is based on a per node scenario
            - (node_cost) / (number of projects)

        Return nested dictionaries:
        - ex {'master_3': {'namespaces': ['openshift', 'kube-system'], 'distributed_cost': Decimal('500.0000000000')}

        """
        with schema_context(self.schema):
            distributed_project_list = (
                OCPUsageLineItemDailySummary.objects.filter(
                    usage_start__gte=start_date, usage_start__lt=end_date, cluster_id=cluster_id
                )
                .filter(namespace__isnull=False)
                .filter(node__isnull=False)
                .values("namespace", "node")
                .distinct()
            )
            node_mappings = {}
            for project in distributed_project_list:
                node_value = project.get("node")
                namespace_value = project.get("namespace")
                node_map = node_mappings.get(node_value)
                if node_map:
                    namespaces = copy.deepcopy(node_map.get("namespaces", []))
                    namespaces.append(namespace_value)
                    node_map["namespaces"] = namespaces
                    node_map["distributed_cost"] = Decimal(node_cost) / Decimal(len(namespaces))
                    node_mappings[node_value] = node_map
                else:
                    initial_map = {"namespaces": [namespace_value], "distributed_cost": Decimal(node_cost)}
                    node_mappings[node_value] = initial_map
        return node_mappings

    def upsert_monthly_node_cost_line_item(
        self, start_date, end_date, cluster_id, cluster_alias, rate_type, node_cost, distribution
    ):
        """Update or insert daily summary line item for node cost."""
        unique_nodes = self.get_distinct_nodes(start_date, end_date, cluster_id)
        report_period = self.get_usage_period_by_dates_and_cluster(start_date, end_date, cluster_id)
        project_distrib_map = self.get_node_to_project_distribution(start_date, end_date, cluster_id, node_cost)
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
                    data_source="Pod",
                    namespace__isnull=True,
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
                        data_source="Pod",
                    )
                monthly_cost = self.generate_monthly_cost_json_object(distribution, node_cost)
                if rate_type == metric_constants.INFRASTRUCTURE_COST_TYPE:
                    LOG.debug("Node (%s) has a monthly infrastructure cost of %s.", node, node_cost)
                    line_item.infrastructure_monthly_cost_json = monthly_cost
                elif rate_type == metric_constants.SUPPLEMENTARY_COST_TYPE:
                    LOG.debug("Node (%s) has a monthly supplemenarty cost of %s.", node, node_cost)
                    line_item.supplementary_monthly_cost_json = monthly_cost
                line_item.save()
            # How are we gonna handle distributing the node cost to the projects.
            project_nodes = project_distrib_map.keys()
            for project_node in project_nodes:
                for namespace in project_distrib_map[project_node]["namespaces"]:
                    distributed_cost = project_distrib_map[project_node]["distributed_cost"]
                    project_line_item = OCPUsageLineItemDailySummary.objects.filter(
                        usage_start=start_date,
                        usage_end=start_date,
                        report_period=report_period,
                        cluster_id=cluster_id,
                        cluster_alias=cluster_alias,
                        monthly_cost_type="Node",
                        node=project_node,
                        namespace=namespace,
                        data_source="Pod",
                    ).first()
                    if not project_line_item:
                        project_line_item = OCPUsageLineItemDailySummary(
                            uuid=uuid.uuid4(),
                            usage_start=start_date,
                            usage_end=start_date,
                            report_period=report_period,
                            cluster_id=cluster_id,
                            cluster_alias=cluster_alias,
                            monthly_cost_type="Node",
                            node=project_node,
                            namespace=namespace,
                            data_source="Pod",
                        )
                    monthly_cost = self.generate_monthly_cost_json_object(distribution, distributed_cost)
                    log_statement = (
                        f"Distributing Node Cost to Project:\n"
                        f" node ({project_node}) cost: {node_cost} \n"
                        f" project ({namespace}) distributed cost: {distributed_cost}\n"
                        f" distribution type: {distribution}\n"
                    )
                    if rate_type == metric_constants.INFRASTRUCTURE_COST_TYPE:
                        project_line_item.infrastructure_project_monthly_cost = monthly_cost
                    elif rate_type == metric_constants.SUPPLEMENTARY_COST_TYPE:
                        project_line_item.supplementary_project_monthly_cost = monthly_cost
                    project_line_item.save()
                    LOG.debug(log_statement)

    def tag_upsert_monthly_node_cost_line_item(  # noqa: C901
        self, start_date, end_date, cluster_id, cluster_alias, rate_type, rate_dict, distribution
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
                                    data_source="Pod",
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
                                        data_source="Pod",
                                    )
                                node_cost = rate_value
                                if rate_type == metric_constants.INFRASTRUCTURE_COST_TYPE:
                                    LOG.debug("Node (%s) has a monthly infrastructure cost of %s.", node, rate_value)
                                    if line_item.infrastructure_monthly_cost_json:
                                        node_cost = (
                                            line_item.infrastructure_monthly_cost_json.get(distribution, 0)
                                            + rate_value
                                        )
                                    monthly_cost = self.generate_monthly_cost_json_object(distribution, node_cost)
                                    line_item.infrastructure_monthly_cost_json = monthly_cost
                                elif rate_type == metric_constants.SUPPLEMENTARY_COST_TYPE:
                                    LOG.debug("Node (%s) has a monthly supplemenarty cost of %s.", node, rate_value)
                                    if line_item.supplementary_monthly_cost_json:
                                        node_cost = (
                                            line_item.supplementary_monthly_cost_json.get(distribution, 0) + rate_value
                                        )
                                    monthly_cost = self.generate_monthly_cost_json_object(distribution, node_cost)
                                    line_item.supplementary_monthly_cost_json = monthly_cost
                                line_item.save()

    def tag_upsert_monthly_default_node_cost_line_item(  # noqa: C901
        self, start_date, end_date, cluster_id, cluster_alias, rate_type, rate_dict, distribution
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
                                data_source="Pod",
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
                                    data_source="Pod",
                                )
                            node_cost = tag_default
                            if rate_type == metric_constants.INFRASTRUCTURE_COST_TYPE:
                                LOG.info(
                                    "Node (%s) has a default monthly infrastructure cost of %s.", node, tag_default
                                )
                                if line_item.infrastructure_monthly_cost_json:
                                    node_cost = (
                                        line_item.infrastructure_monthly_cost_json.get(distribution, 0) + tag_default
                                    )
                                monthly_cost = self.generate_monthly_cost_json_object(distribution, node_cost)
                                line_item.infrastructure_monthly_cost_json = monthly_cost
                            elif rate_type == metric_constants.SUPPLEMENTARY_COST_TYPE:
                                LOG.info(
                                    "Node (%s) has a default monthly supplemenarty cost of %s.", node, tag_default
                                )
                                if line_item.supplementary_monthly_cost_json:
                                    node_cost = (
                                        line_item.supplementary_monthly_cost_json.get(distribution, 0) + tag_default
                                    )
                                monthly_cost = self.generate_monthly_cost_json_object(distribution, node_cost)
                                line_item.supplementary_monthly_cost_json = monthly_cost
                            line_item.save()

    def tag_upsert_monthly_default_pvc_cost_line_item(  # noqa: C901
        self, start_date, end_date, cluster_id, cluster_alias, rate_type, rate_dict
    ):
        """
        Update or insert daily summary line item for node cost.
        It checks to see if a line item exists for each node
        that contains the tag key:value pair,
        if it does then the price is added to the monthly cost.
        """
        distribution = metric_constants.PVC_DISTRIBUTION
        unique_pvcs = self.get_distinct_pvcs(start_date, end_date, cluster_id)
        report_period = self.get_usage_period_by_dates_and_cluster(start_date, end_date, cluster_id)
        with schema_context(self.schema):
            for pvc, node, namespace in unique_pvcs:
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
                            namespace=namespace,
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
                                data_source="Storage",
                                namespace=namespace,
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
                                    data_source="Storage",
                                    namespace=namespace,
                                )
                            pvc_cost = tag_default
                            if rate_type == metric_constants.INFRASTRUCTURE_COST_TYPE:
                                LOG.info("PVC (%s) has a default monthly infrastructure cost of %s.", pvc, tag_default)
                                if line_item.infrastructure_monthly_cost_json:
                                    pvc_cost = (
                                        line_item.infrastructure_monthly_cost_json.get(distribution, 0) + tag_default
                                    )
                                monthly_cost = self.generate_monthly_cost_json_object(distribution, pvc_cost)
                                line_item.infrastructure_monthly_cost_json = monthly_cost
                            elif rate_type == metric_constants.SUPPLEMENTARY_COST_TYPE:
                                LOG.info("PVC (%s) has a default monthly supplemenarty cost of %s.", pvc, tag_default)
                                if line_item.supplementary_monthly_cost_json:
                                    pvc_cost = (
                                        line_item.supplementary_monthly_cost_json.get(distribution, 0) + tag_default
                                    )
                                monthly_cost = self.generate_monthly_cost_json_object(distribution, pvc_cost)
                                line_item.supplementary_monthly_cost_json = monthly_cost
                            line_item.save()

    def get_cluster_to_node_distribution(self, start_date, end_date, cluster_id, distribution, cluster_cost):
        """Returns a list of dictionaries containing the distributed cost.

        args:
            start_date (datetime, str): The start_date to calculate monthly_cost.
            end_date (datetime, str): The end_date to calculate monthly_cost.
            cluster_id (str): The id of the cluster
            cluster_cost (dec): The flat cost of the cluster
            distribution: Choice of monthly distribution ex. (memory or cpu)

        Memory Distribution:
            - (node memory capacity/cluster memory capacity) x cluster_cost
        CPU Distribution:
            - (node cpu capacity/cluster cpu capacity) x cluster_cost

        Return list of dictionaries: ex [{"node":"aws_compute2", "distributed_cost": 285.71}]

        """
        node_column = "node_capacity_cpu_core_hours"
        cluster_column = "cluster_capacity_cpu_core_hours"
        if "memory" in distribution:
            node_column = "node_capacity_memory_gigabyte_hours"
            cluster_column = "cluster_capacity_memory_gigabyte_hours"

        with schema_context(self.schema):
            distributed_node_list = (
                OCPUsageLineItemDailySummary.objects.filter(
                    usage_start__gte=start_date, usage_start__lt=end_date, cluster_id=cluster_id
                )
                .values("node")
                .annotate(distributed_cost=Sum(node_column) / Sum(cluster_column) * cluster_cost)
            )
        # TIP: For debugging add these to the annotation
        # node_hours=Sum(node_column),
        # cluster_hours=Sum(cluster_column),
        # node_to_cluster_ratio=Sum(node_column)/Sum(cluster_column)
        return distributed_node_list

    def get_cluster_to_project_distribution(self, start_date, end_date, cluster_id, distribution, cluster_cost):
        """Returns a list of dictionaries containing the distributed cost.

        args:
            start_date (datetime, str): The start_date to calculate monthly_cost.
            end_date (datetime, str): The end_date to calculate monthly_cost.
            cluster_id (str): The id of the cluster
            cluster_cost (dec): The flat cost of the cluster
            distribution: Choice of monthly distribution ex. (memory or cpu)

        Project Distribution:
            - Project distribution is a rolling window estimate of month to date.
            - (project_usage / cluster_usage) x cluster_cost

        Return list of dictionaries:
        - ex [{'namespace': 'openshift', 'distributed_cost': Decimal('71.84')}

        """
        usage_column = "pod_usage_cpu_core_hours"
        if "memory" in distribution:
            usage_column = "pod_usage_memory_gigabyte_hours"

        with schema_context(self.schema):
            cluster_hours = (
                OCPUsageLineItemDailySummary.objects.filter(
                    usage_start__gte=start_date, usage_start__lt=end_date, cluster_id=cluster_id
                ).aggregate(cluster_hours=Sum(usage_column))
            ).get("cluster_hours")
            distributed_project_list = (
                OCPUsageLineItemDailySummary.objects.filter(
                    usage_start__gte=start_date, usage_start__lt=end_date, cluster_id=cluster_id
                )
                .filter(namespace__isnull=False)
                .values("namespace")
                .annotate(distributed_cost=Sum(usage_column) / cluster_hours * cluster_cost)
            )
        return distributed_project_list

    def upsert_monthly_cluster_cost_line_item(
        self, start_date, end_date, cluster_id, cluster_alias, rate_type, cluster_cost, distribution
    ):
        """
        Update or insert a daily summary line item for cluster cost.

        args:
            start_date (datetime, str): The start_date to calculate monthly_cost.
            end_date (datetime, str): The end_date to calculate monthly_cost.
            cluster_id (str): The id of the cluster
            cluster_alias: The name of the cluster
            cost_type (str): Contains the type of monthly cost. ex: "Node"
            rate_type (str): Contains the metric name. ex: "node_cost_per_month"
            cluster_cost (dec): The flat cost of the cluster
            distribution: Choice of monthly distribution ex. (memory or cpu)
        """
        report_period = self.get_usage_period_by_dates_and_cluster(start_date, end_date, cluster_id)
        distribution_list = self.get_cluster_to_node_distribution(
            start_date, end_date, cluster_id, distribution, cluster_cost
        )
        if report_period:
            with schema_context(self.schema):
                # NOTE: I implemented a logic change here, now instead of one entry per cluster cost
                # We now have multiple cluster cost entries for each node.
                LOG.debug("Cluster (%s) has a monthly cost of %s.", cluster_id, cluster_cost)
                LOG.debug("Distributing the cluster cost to nodes using %s distribution.", distribution)
                for node_dikt in distribution_list:
                    node = node_dikt.get("node")
                    distributed_cost = node_dikt.get("distributed_cost", Decimal(0))
                    line_item = OCPUsageLineItemDailySummary.objects.filter(
                        usage_start=start_date,
                        usage_end=start_date,
                        report_period=report_period,
                        cluster_id=cluster_id,
                        cluster_alias=cluster_alias,
                        monthly_cost_type="Cluster",
                        node=node,
                        data_source="Pod",
                        namespace__isnull=True,
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
                            node=node,
                            data_source="Pod",
                        )
                    monthly_cost = self.generate_monthly_cost_json_object(distribution, distributed_cost)
                    log_statement = (
                        f"Distributing Cluster Cost to Nodes:\n"
                        f" cluster ({cluster_id}) cost: {cluster_cost} \n"
                        f" node ({node}) distributed cost: {distributed_cost}\n"
                        f" distribution type: {distribution}\n"
                    )
                    if rate_type == metric_constants.INFRASTRUCTURE_COST_TYPE:
                        line_item.infrastructure_monthly_cost_json = monthly_cost
                    elif rate_type == metric_constants.SUPPLEMENTARY_COST_TYPE:
                        line_item.supplementary_monthly_cost_json = monthly_cost
                    LOG.debug(log_statement)
                    line_item.save()
            # Project Distribution
            project_distribution_list = self.get_cluster_to_project_distribution(
                start_date, end_date, cluster_id, distribution, cluster_cost
            )
            with schema_context(self.schema):
                for project_dikt in project_distribution_list:
                    namespace = project_dikt.get("namespace")
                    distributed_cost = project_dikt.get("distributed_cost", Decimal(0))
                    project_line_item = OCPUsageLineItemDailySummary.objects.filter(
                        usage_start=start_date,
                        usage_end=start_date,
                        report_period=report_period,
                        cluster_id=cluster_id,
                        cluster_alias=cluster_alias,
                        monthly_cost_type="Cluster",
                        namespace=namespace,
                        data_source="Pod",
                    ).first()
                    if not project_line_item:
                        project_line_item = OCPUsageLineItemDailySummary(
                            uuid=uuid.uuid4(),
                            usage_start=start_date,
                            usage_end=start_date,
                            report_period=report_period,
                            cluster_id=cluster_id,
                            cluster_alias=cluster_alias,
                            monthly_cost_type="Cluster",
                            namespace=namespace,
                            data_source="Pod",
                        )
                    monthly_cost = self.generate_monthly_cost_json_object(distribution, distributed_cost)
                    log_statement = (
                        f"Distributing Cluster Cost to Project:\n"
                        f" cluster ({cluster_id}) cost: {cluster_cost} \n"
                        f" project ({namespace}) distributed cost: {distributed_cost}\n"
                        f" distribution type: {distribution}\n"
                    )
                    if rate_type == metric_constants.INFRASTRUCTURE_COST_TYPE:
                        project_line_item.infrastructure_project_monthly_cost = monthly_cost
                    elif rate_type == metric_constants.SUPPLEMENTARY_COST_TYPE:
                        project_line_item.supplementary_project_monthly_cost = monthly_cost
                    project_line_item.save()
                    LOG.debug(log_statement)

    def tag_upsert_monthly_pvc_cost_line_item(  # noqa: C901
        self, start_date, end_date, cluster_id, cluster_alias, rate_type, rate_dict
    ):
        """
        Update or insert daily summary line item for PVC cost.

        It checks to see if a line item exists for each PVC
        that contains the tag key:value pair,
        if it does then the price is added to the monthly cost.
        """
        distribution = metric_constants.PVC_DISTRIBUTION
        unique_pvcs = self.get_distinct_pvcs(start_date, end_date, cluster_id)
        report_period = self.get_usage_period_by_dates_and_cluster(start_date, end_date, cluster_id)
        with schema_context(self.schema):
            for pvc, node, namespace in unique_pvcs:
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
                                namespace=namespace,
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
                                    data_source="Storage",
                                    namespace=namespace,
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
                                        data_source="Storage",
                                        namespace=namespace,
                                    )
                                pvc_cost = rate_value
                                if rate_type == metric_constants.INFRASTRUCTURE_COST_TYPE:
                                    LOG.debug("PVC (%s) has a monthly infrastructure cost of %s.", pvc, rate_value)
                                    if line_item.infrastructure_monthly_cost_json:
                                        pvc_cost = (
                                            line_item.infrastructure_monthly_cost_json.get(distribution, 0)
                                            + rate_value
                                        )
                                    monthly_cost = self.generate_monthly_cost_json_object(distribution, pvc_cost)
                                    line_item.infrastructure_monthly_cost_json = monthly_cost
                                elif rate_type == metric_constants.SUPPLEMENTARY_COST_TYPE:
                                    LOG.debug("PVC (%s) has a monthly supplemenarty cost of %s.", pvc, rate_value)
                                    if line_item.supplementary_monthly_cost_json:
                                        pvc_cost = (
                                            line_item.supplementary_monthly_cost_json.get(distribution, 0) + rate_value
                                        )
                                    monthly_cost = self.generate_monthly_cost_json_object(distribution, pvc_cost)
                                    line_item.supplementary_monthly_cost_json = monthly_cost
                                line_item.save()

    def upsert_monthly_pvc_cost_line_item(self, start_date, end_date, cluster_id, cluster_alias, rate_type, pvc_cost):
        """Update or insert daily summary line item for pvc cost."""
        unique_pvcs = self.get_distinct_pvcs(start_date, end_date, cluster_id)
        report_period = self.get_usage_period_by_dates_and_cluster(start_date, end_date, cluster_id)
        with schema_context(self.schema):
            for pvc, node, namespace in unique_pvcs:
                line_item = OCPUsageLineItemDailySummary.objects.filter(
                    usage_start=start_date,
                    usage_end=start_date,
                    report_period=report_period,
                    cluster_id=cluster_id,
                    cluster_alias=cluster_alias,
                    monthly_cost_type="PVC",
                    persistentvolumeclaim=pvc,
                    node=node,
                    data_source="Storage",
                    namespace=namespace,
                    infrastructure_project_monthly_cost__isnull=True,
                    supplementary_project_monthly_cost__isnull=True,
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
                        data_source="Storage",
                        namespace=namespace,
                    )
                monthly_cost = self.generate_monthly_cost_json_object(metric_constants.PVC_DISTRIBUTION, pvc_cost)
                if rate_type == metric_constants.INFRASTRUCTURE_COST_TYPE:
                    LOG.debug("PVC (%s) has a monthly infrastructure cost of %s.", pvc, pvc_cost)
                    line_item.infrastructure_monthly_cost_json = monthly_cost
                elif rate_type == metric_constants.SUPPLEMENTARY_COST_TYPE:
                    LOG.debug("PVC (%s) has a monthly supplemenarty cost of %s.", pvc, pvc_cost)
                    line_item.supplementary_monthly_cost_json = monthly_cost
                line_item.save()
                # PVC to project Distribution
                project_line_item = OCPUsageLineItemDailySummary.objects.filter(
                    usage_start=start_date,
                    usage_end=start_date,
                    report_period=report_period,
                    cluster_id=cluster_id,
                    cluster_alias=cluster_alias,
                    monthly_cost_type="PVC",
                    persistentvolumeclaim=pvc,
                    node=node,
                    namespace=namespace,
                    data_source="Storage",
                    infrastructure_monthly_cost_json__isnull=True,
                    supplementary_monthly_cost_json__isnull=True,
                ).first()
                if not project_line_item:
                    project_line_item = OCPUsageLineItemDailySummary(
                        uuid=uuid.uuid4(),
                        usage_start=start_date,
                        usage_end=start_date,
                        report_period=report_period,
                        cluster_id=cluster_id,
                        cluster_alias=cluster_alias,
                        monthly_cost_type="PVC",
                        persistentvolumeclaim=pvc,
                        node=node,
                        namespace=namespace,
                        data_source="Storage",
                    )
                monthly_cost = self.generate_monthly_cost_json_object(metric_constants.PVC_DISTRIBUTION, pvc_cost)
                if rate_type == metric_constants.INFRASTRUCTURE_COST_TYPE:
                    LOG.debug("PVC (%s) has a monthly project infrastructure cost of %s.", pvc, pvc_cost)
                    project_line_item.infrastructure_project_monthly_cost = monthly_cost
                elif rate_type == metric_constants.SUPPLEMENTARY_COST_TYPE:
                    LOG.debug("PVC (%s) has a monthly project supplemenarty cost of %s.", pvc, pvc_cost)
                    project_line_item.supplementary_project_monthly_cost = monthly_cost
                project_line_item.save()

    def tag_upsert_monthly_cluster_cost_line_item(  # noqa: C901
        self, start_date, end_date, cluster_id, cluster_alias, rate_type, rate_dict, distribution
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
                                    data_source="Pod",
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
                                        data_source="Pod",
                                    )
                                cluster_cost = rate_value
                                if rate_type == metric_constants.INFRASTRUCTURE_COST_TYPE:
                                    LOG.debug(
                                        "Cluster (%s) has a monthly infrastructure cost of %s from tag rates.",
                                        cluster_id,
                                        rate_value,
                                    )
                                    if line_item.infrastructure_monthly_cost_json:
                                        cluster_cost = (
                                            line_item.infrastructure_monthly_cost_json.get(distribution, 0)
                                            + rate_value
                                        )
                                    monthly_cost = self.generate_monthly_cost_json_object(distribution, cluster_cost)
                                    line_item.infrastructure_monthly_cost_json = monthly_cost
                                elif rate_type == metric_constants.SUPPLEMENTARY_COST_TYPE:
                                    LOG.debug(
                                        "Cluster (%s) has a monthly supplemenarty cost of %s from tag rates.",
                                        cluster_id,
                                        rate_value,
                                    )
                                    if line_item.supplementary_monthly_cost_json:
                                        cluster_cost = (
                                            line_item.supplementary_monthly_cost_json.get(distribution, 0) + rate_value
                                        )
                                    monthly_cost = self.generate_monthly_cost_json_object(distribution, cluster_cost)
                                    line_item.supplementary_monthly_cost_json = monthly_cost
                                line_item.save()

    def tag_upsert_monthly_default_cluster_cost_line_item(  # noqa: C901
        self, start_date, end_date, cluster_id, cluster_alias, rate_type, rate_dict, distribution
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
                            data_source="Pod",
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
                                data_source="Pod",
                            )
                        cluster_cost = tag_default
                        if rate_type == metric_constants.INFRASTRUCTURE_COST_TYPE:
                            LOG.debug(
                                "Cluster (%s) has a default monthly infrastructure cost of %s.",
                                cluster_id,
                                tag_default,
                            )
                            if line_item.infrastructure_monthly_cost_json:
                                cluster_cost = (
                                    line_item.infrastructure_monthly_cost_json.get(distribution, 0) + tag_default
                                )
                            monthly_cost = self.generate_monthly_cost_json_object(distribution, cluster_cost)
                            line_item.infrastructure_monthly_cost_json = monthly_cost
                        elif rate_type == metric_constants.SUPPLEMENTARY_COST_TYPE:
                            LOG.debug(
                                "Cluster (%s) has a default monthly supplemenarty cost of %s.", cluster_id, tag_default
                            )
                            if line_item.supplementary_monthly_cost_json:
                                cluster_cost = (
                                    line_item.supplementary_monthly_cost_json.get(distribution, 0) + tag_default
                                )
                            monthly_cost = self.generate_monthly_cost_json_object(distribution, cluster_cost)
                            line_item.supplementary_monthly_cost_json = monthly_cost
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
            cost_filters = [
                f"{rate_type.lower()}_monthly_cost__isnull",
                f"{rate_type.lower()}_monthly_cost_json__isnull",
                f"{rate_type.lower()}_project_monthly_cost__isnull",
            ]
            for cost_filter in cost_filters:
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
        table_name = self._table_map["node_label_line_item_daily"]

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
                table_name = self._table_map["line_item_daily_summary"]
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
                table_name = self._table_map["line_item_daily_summary"]
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

    def populate_openshift_cluster_information_tables(self, provider, cluster_id, cluster_alias, start_date, end_date):
        """Populate the cluster, node, PVC, and project tables for the cluster."""
        cluster = self.populate_cluster_table(provider, cluster_id, cluster_alias)

        nodes = self.get_nodes_presto(str(provider.uuid), start_date, end_date)
        pvcs = self.get_pvcs_presto(str(provider.uuid), start_date, end_date)
        projects = self.get_projects_presto(str(provider.uuid), start_date, end_date)

        # pvcs = self.match_node_to_pvc(pvcs, projects)

        self.populate_node_table(cluster, nodes)
        self.populate_pvc_table(cluster, pvcs)
        self.populate_project_table(cluster, projects)

    def populate_cluster_table(self, provider, cluster_id, cluster_alias):
        """Get or create an entry in the OCP cluster table."""
        with schema_context(self.schema):
            cluster, created = OCPCluster.objects.get_or_create(
                cluster_id=cluster_id, cluster_alias=cluster_id, provider=provider
            )

        if created:
            msg = f"Add entry in reporting_ocp_clusters for {cluster_id}/{cluster_alias}"
            LOG.info(msg)

        return cluster

    def populate_node_table(self, cluster, nodes):
        """Get or create an entry in the OCP cluster table."""
        LOG.info("Populating reporting_ocp_nodes table.")
        with schema_context(self.schema):
            for node in nodes:
                OCPNode.objects.get_or_create(
                    node=node[0], resource_id=node[1], node_capacity_cpu_cores=node[2], cluster=cluster
                )

    def populate_pvc_table(self, cluster, pvcs):
        """Get or create an entry in the OCP cluster table."""
        LOG.info("Populating reporting_ocp_pvcs table.")
        with schema_context(self.schema):
            for pvc in pvcs:
                OCPPVC.objects.get_or_create(persistent_volume=pvc[0], persistent_volume_claim=pvc[1], cluster=cluster)

    def populate_project_table(self, cluster, projects):
        """Get or create an entry in the OCP cluster table."""
        LOG.info("Populating reporting_ocp_projects table.")
        with schema_context(self.schema):
            for project in projects:
                OCPProject.objects.get_or_create(project=project, cluster=cluster)

    def get_nodes_presto(self, source_uuid, start_date, end_date):
        """Get the nodes from an OpenShift cluster."""
        sql = f"""
            SELECT node,
                resource_id,
                max(node_capacity_cpu_cores) as node_capacity_cpu_cores
            FROM hive.{self.schema}.openshift_pod_usage_line_items_daily as ocp
            WHERE ocp.source = '{source_uuid}'
                AND ocp.year = '{start_date.strftime("%Y")}'
                AND ocp.month = '{start_date.strftime("%m")}'
                AND ocp.interval_start >= TIMESTAMP '{start_date}'
                AND ocp.interval_start < date_add('day', 1, TIMESTAMP '{end_date}')
            GROUP BY node,
                resource_id
        """

        nodes = self._execute_presto_raw_sql_query(self.schema, sql)

        return nodes

    def get_pvcs_presto(self, source_uuid, start_date, end_date):
        """Get the nodes from an OpenShift cluster."""
        sql = f"""
            SELECT distinct persistentvolume,
                persistentvolumeclaim
            FROM hive.{self.schema}.openshift_storage_usage_line_items_daily as ocp
            WHERE ocp.source = '{source_uuid}'
                AND ocp.year = '{start_date.strftime("%Y")}'
                AND ocp.month = '{start_date.strftime("%m")}'
                AND ocp.interval_start >= TIMESTAMP '{start_date}'
                AND ocp.interval_start < date_add('day', 1, TIMESTAMP '{end_date}')
        """

        pvcs = self._execute_presto_raw_sql_query(self.schema, sql)

        return pvcs

    def get_projects_presto(self, source_uuid, start_date, end_date):
        """Get the nodes from an OpenShift cluster."""
        sql = f"""
            SELECT distinct namespace
            FROM hive.{self.schema}.openshift_pod_usage_line_items_daily as ocp
            WHERE ocp.source = '{source_uuid}'
                AND ocp.year = '{start_date.strftime("%Y")}'
                AND ocp.month = '{start_date.strftime("%m")}'
                AND ocp.interval_start >= TIMESTAMP '{start_date}'
                AND ocp.interval_start < date_add('day', 1, TIMESTAMP '{end_date}')
        """

        projects = self._execute_presto_raw_sql_query(self.schema, sql)

        return [project[0] for project in projects]

    def get_cluster_for_provider(self, provider_uuid):
        """Return the cluster entry for a provider UUID."""
        with schema_context(self.schema):
            cluster = OCPCluster.objects.filter(provider_id=provider_uuid).first()
        return cluster

    def get_nodes_for_cluster(self, cluster_id):
        """Get all nodes for an OCP cluster."""
        with schema_context(self.schema):
            nodes = OCPNode.objects.filter(cluster_id=cluster_id).values_list("node", "resource_id")
            nodes = [(node[0], node[1]) for node in nodes]
        return nodes

    def get_pvcs_for_cluster(self, cluster_id):
        """Get all nodes for an OCP cluster."""
        with schema_context(self.schema):
            pvcs = OCPPVC.objects.filter(cluster_id=cluster_id).values_list(
                "persistent_volume", "persistent_volume_claim"
            )
            pvcs = [(pvc[0], pvc[1]) for pvc in pvcs]
        return pvcs

    def get_projects_for_cluster(self, cluster_id):
        """Get all nodes for an OCP cluster."""
        with schema_context(self.schema):
            projects = OCPProject.objects.filter(cluster_id=cluster_id).values_list("project")
            projects = [project[0] for project in projects]
        return projects

    def get_openshift_topology_for_provider(self, provider_uuid):
        """Return a dictionary with Cluster topology."""
        cluster = self.get_cluster_for_provider(provider_uuid)
        topology = {"cluster_id": cluster.cluster_id, "cluster_alias": cluster.cluster_alias}
        node_tuples = self.get_nodes_for_cluster(cluster.uuid)
        pvc_tuples = self.get_pvcs_for_cluster(cluster.uuid)
        topology["nodes"] = [node[0] for node in node_tuples]
        topology["resource_ids"] = [node[1] for node in node_tuples]
        topology["persistent_volumes"] = [pvc[0] for pvc in pvc_tuples]
        topology["persistent_volume_claims"] = [pvc[1] for pvc in pvc_tuples]
        topology["projects"] = self.get_projects_for_cluster(cluster.uuid)

        return topology

    def delete_infrastructure_raw_cost_from_daily_summary(self, provider_uuid, report_period_id, start_date, end_date):
        table_name = OCP_REPORT_TABLE_MAP["line_item_daily_summary"]
        msg = f"Removing infrastructure_raw_cost for {provider_uuid} from {start_date} to {end_date}."
        LOG.info(msg)
        sql = f"""
            DELETE FROM {self.schema}.reporting_ocpusagelineitem_daily_summary
            WHERE usage_start >= '{start_date}'::date
                AND usage_start <= '{end_date}'::date
                AND report_period_id = {report_period_id}
                AND infrastructure_raw_cost IS NOT NULL
                AND infrastructure_raw_cost != 0
        """

        self._execute_raw_sql_query(table_name, sql, start_date, end_date)

    def populate_ocp_on_all_project_daily_summary(self, platform, sql_params):
        LOG.info(f"Populating {platform.upper()} records for ocpallcostlineitem_project_daily_summary")
        script_file_path = f"sql/reporting_ocpallcostlineitem_project_daily_summary_{platform.lower()}.sql"
        self._execute_processing_script("masu.database", script_file_path, sql_params)

    def populate_ocp_on_all_daily_summary(self, platform, sql_params):
        LOG.info(f"Populating {platform.upper()} records for ocpallcostlineitem_daily_summary")
        script_file_path = f"sql/reporting_ocpallcostlineitem_daily_summary_{platform.lower()}.sql"
        self._execute_processing_script("masu.database", script_file_path, sql_params)

    def get_max_min_timestamp_from_parquet(self, source_uuid, start_date, end_date):
        """Get the max and min timestamps for parquet data given a date range"""
        sql = f"""
            SELECT min(interval_start) as min_timestamp,
                max(interval_start) as max_timestamp
            FROM hive.{self.schema}.openshift_pod_usage_line_items_daily as ocp
            WHERE ocp.source = '{source_uuid}'
                AND ocp.year = '{start_date.strftime("%Y")}'
                AND ocp.month = '{start_date.strftime("%m")}'
                AND ocp.interval_start >= TIMESTAMP '{start_date}'
                AND ocp.interval_start < date_add('day', 1, TIMESTAMP '{end_date}')
        """

        timestamps = self._execute_presto_raw_sql_query(self.schema, sql)
        max, min = timestamps[0]
        return parse(max), parse(min)
