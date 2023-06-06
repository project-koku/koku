#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Database accessor for OCP report data."""
import datetime
import json
import logging
import os
import pkgutil
import uuid

from dateutil.parser import parse
from django.conf import settings
from django.db import connection
from django.db.models import DecimalField
from django.db.models import F
from django.db.models import Value
from django.db.models.functions import Coalesce
from django_tenants.utils import schema_context
from jinjasql import JinjaSql
from trino.exceptions import TrinoExternalError

from api.common import log_json
from api.metrics.constants import DEFAULT_DISTRIBUTION_TYPE
from api.provider.models import Provider
from api.utils import DateHelper
from koku.database import SQLScriptAtomicExecutorMixin
from masu.config import Config
from masu.database import AWS_CUR_TABLE_MAP
from masu.database import OCP_REPORT_TABLE_MAP
from masu.database.report_db_accessor_base import ReportDBAccessorBase
from masu.util.common import filter_dictionary
from masu.util.common import trino_table_exists
from masu.util.gcp.common import check_resource_level
from reporting.models import OCP_ON_ALL_PERSPECTIVES
from reporting.provider.aws.models import TRINO_LINE_ITEM_DAILY_TABLE as AWS_TRINO_LINE_ITEM_DAILY_TABLE
from reporting.provider.azure.models import TRINO_LINE_ITEM_DAILY_TABLE as AZURE_TRINO_LINE_ITEM_DAILY_TABLE
from reporting.provider.gcp.models import TRINO_LINE_ITEM_DAILY_TABLE as GCP_TRINO_LINE_ITEM_DAILY_TABLE
from reporting.provider.ocp.models import OCPCluster
from reporting.provider.ocp.models import OCPNode
from reporting.provider.ocp.models import OCPProject
from reporting.provider.ocp.models import OCPPVC
from reporting.provider.ocp.models import OCPUsageLineItemDailySummary
from reporting.provider.ocp.models import OCPUsageReportPeriod
from reporting.provider.ocp.models import TRINO_LINE_ITEM_TABLE_DAILY_MAP
from reporting.provider.ocp.models import UI_SUMMARY_TABLES

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

    #  Empty string will put a path seperator on the end
    OCP_ON_ALL_SQL_PATH = os.path.join("sql", "openshift", "all", "")

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

    def get_current_usage_period(self, provider_uuid):
        """Get the most recent usage report period object."""
        with schema_context(self.schema):
            return (
                OCPUsageReportPeriod.objects.filter(provider_id=provider_uuid).order_by("-report_period_start").first()
            )

    def get_usage_period_by_dates_and_cluster(self, start_date, end_date, cluster_id):
        """Return all report period entries for the specified start date."""
        table_name = self._table_map["report_period"]
        with schema_context(self.schema):
            return (
                self._get_db_obj_query(table_name)
                .filter(report_period_start=start_date, report_period_end=end_date, cluster_id=cluster_id)
                .first()
            )

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

    def populate_ui_summary_tables(self, start_date, end_date, source_uuid, tables=UI_SUMMARY_TABLES):
        """Populate our UI summary tables (formerly materialized views)."""
        for table_name in tables:
            summary_sql = pkgutil.get_data("masu.database", f"sql/openshift/{table_name}.sql")
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

    def get_ocp_infrastructure_map_trino(self, start_date, end_date, **kwargs):  # noqa: C901
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
        provider_type = kwargs.get("provider_type")

        check_aws = False
        check_azure = False
        check_gcp = False
        resource_level = False

        if not self.table_exists_trino(TRINO_LINE_ITEM_TABLE_DAILY_MAP.get("pod_usage")):
            return {}
        if aws_provider_uuid or ocp_provider_uuid:
            check_aws = self.table_exists_trino(AWS_TRINO_LINE_ITEM_DAILY_TABLE)
            if aws_provider_uuid and not check_aws:
                return {}
        if azure_provider_uuid or ocp_provider_uuid:
            check_azure = self.table_exists_trino(AZURE_TRINO_LINE_ITEM_DAILY_TABLE)
            if azure_provider_uuid and not check_azure:
                return {}
        if gcp_provider_uuid or ocp_provider_uuid:
            check_gcp = self.table_exists_trino(GCP_TRINO_LINE_ITEM_DAILY_TABLE)
            # Check for GCP resource level data
            if gcp_provider_uuid:
                resource_level = check_resource_level(gcp_provider_uuid)
                if not check_gcp:
                    return {}
        if not any([check_aws, check_azure, check_gcp]):
            return {}

        check_flags = {
            Provider.PROVIDER_AWS.lower(): check_aws,
            Provider.PROVIDER_AZURE.lower(): check_azure,
            Provider.PROVIDER_GCP.lower(): check_gcp,
        }

        if isinstance(start_date, str):
            start_date = datetime.datetime.strptime(start_date, "%Y-%m-%d").date()
            end_date = datetime.datetime.strptime(end_date, "%Y-%m-%d").date()
        for source_type, check_flag in check_flags.items():
            db_results = {}
            if check_flag:
                infra_sql = pkgutil.get_data(
                    "masu.database", f"trino_sql/{source_type}/reporting_ocpinfrastructure_provider_map.sql"
                )
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
                    "provider_type": provider_type,
                    "resource_level": resource_level,
                }

                results = self._execute_trino_raw_sql_query(
                    infra_sql,
                    sql_params=infra_sql_params,
                    log_ref="reporting_ocpinfrastructure_provider_map.sql",
                )
                for entry in results:
                    # This dictionary is keyed on an OpenShift provider UUID
                    # and the tuple contains
                    # (Infrastructure Provider UUID, Infrastructure Provider Type)
                    db_results[entry[0]] = (entry[1], entry[2])
                if db_results:
                    # An OCP cluster can only run on a single source, so stop here if we found a match
                    return db_results
        return db_results

    def delete_ocp_hive_partition_by_day(self, days, source, year, month):
        """Deletes partitions individually for each day in days list."""
        table = "reporting_ocpusagelineitem_daily_summary"
        retries = settings.HIVE_PARTITION_DELETE_RETRIES
        if self.schema_exists_trino() and self.table_exists_trino(table):
            LOG.info(
                "Deleting Hive partitions for the following: \n\tSchema: %s "
                "\n\tOCP Source: %s \n\tTable: %s \n\tYear-Month: %s-%s \n\tDays: %s",
                self.schema,
                source,
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
                        WHERE source = '{source}'
                        AND year = '{year}'
                        AND (month = replace(ltrim(replace('{month}', '0', ' ')),' ', '0') OR month = '{month}')
                        AND day = '{day}'
                        """
                        self._execute_trino_raw_sql_query(
                            sql,
                            log_ref=f"delete_ocp_hive_partition_by_day for {year}-{month}-{day}",
                            attempts_left=(retries - 1) - i,
                        )
                        break
                    except TrinoExternalError as err:
                        if err.error_name == "HIVE_METASTORE_ERROR" and i < (retries - 1):
                            continue
                        else:
                            raise err

    def delete_hive_partitions_by_source(self, table, partition_column, provider_uuid):
        """Deletes partitions individually for each day in days list."""
        retries = settings.HIVE_PARTITION_DELETE_RETRIES
        if self.schema_exists_trino() and self.table_exists_trino(table):
            LOG.info(
                "Deleting Hive partitions for the following: \n\tSchema: %s " "\n\tOCP Source: %s \n\tTable: %s",
                self.schema,
                provider_uuid,
                table,
            )
            for i in range(retries):
                try:
                    sql = f"""
                    DELETE FROM hive.{self.schema}.{table}
                    WHERE {partition_column} = '{provider_uuid}'
                    """
                    self._execute_trino_raw_sql_query(
                        sql,
                        log_ref=f"delete_hive_partitions_by_source for {provider_uuid}",
                        attempts_left=(retries - 1) - i,
                    )
                    break
                except TrinoExternalError as err:
                    if err.error_name == "HIVE_METASTORE_ERROR" and i < (retries - 1):
                        continue
                    else:
                        raise err
            LOG.info(
                "Successfully deleted Hive partitions for the following: \n\tSchema: %s "
                "\n\tOCP Source: %s \n\tTable: %s",
                self.schema,
                provider_uuid,
                table,
            )
            return True
        return False

    def populate_line_item_daily_summary_table_trino(
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

        storage_exists = trino_table_exists(self.schema, "openshift_storage_usage_line_items_daily")

        year = start_date.strftime("%Y")
        month = start_date.strftime("%m")
        days = self.date_helper.list_days(start_date, end_date)
        days_tup = tuple(str(day.day) for day in days)
        self.delete_ocp_hive_partition_by_day(days_tup, source, year, month)

        summary_sql = pkgutil.get_data("masu.database", "trino_sql/reporting_ocpusagelineitem_daily_summary.sql")
        summary_sql = summary_sql.decode("utf-8")
        summary_sql_params = {
            "uuid": source,
            "start_date": start_date,
            "end_date": end_date,
            "report_period_id": report_period_id,
            "cluster_id": cluster_id,
            "cluster_alias": cluster_alias,
            "schema": self.schema,
            "source": str(source),
            "year": year,
            "month": month,
            "days": days_tup,
            "storage_exists": storage_exists,
        }

        self._execute_trino_multipart_sql_query(summary_sql, bind_params=summary_sql_params)

    def populate_pod_label_summary_table(self, report_period_ids, start_date, end_date):
        """Populate the line item aggregated totals data table."""
        table_name = self._table_map["pod_label_summary"]

        agg_sql_params = {
            "uuid": str(uuid.uuid4()).replace("-", "_"),
            "schema": self.schema,
            "report_period_ids": report_period_ids,
            "start_date": start_date,
            "end_date": end_date,
        }
        if start_date and end_date:
            msg = f"Updating {table_name} from {start_date} to {end_date}"
        else:
            msg = f"Updating {table_name}"
        LOG.info(msg)
        self._execute_processing_script("masu.database", "sql/reporting_ocpusagepodlabel_summary.sql", agg_sql_params)
        LOG.info(f"Finished updating {table_name}")

    def populate_volume_label_summary_table(self, report_period_ids, start_date, end_date):
        """Populate the OCP volume label summary table."""
        table_name = self._table_map["volume_label_summary"]

        agg_sql_params = {
            "uuid": str(uuid.uuid4()).replace("-", "_"),
            "schema": self.schema,
            "report_period_ids": report_period_ids,
            "start_date": start_date,
            "end_date": end_date,
        }
        if start_date and end_date:
            msg = f"Updating {table_name} from {start_date} to {end_date}"
        else:
            msg = f"Updating {table_name}"
        LOG.info(msg)
        self._execute_processing_script(
            "masu.database", "sql/reporting_ocpstoragevolumelabel_summary.sql", agg_sql_params
        )
        LOG.info(f"Finished updating {table_name}")

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

    def populate_platform_and_worker_distributed_cost_sql(
        self, start_date, end_date, provider_uuid, distribution_info
    ):
        """
        Populate the platform cost distribution of a customer.

        args:
            start_date (datetime, str): The start_date to calculate monthly_cost.
            end_date (datetime, str): The end_date to calculate monthly_cost.
            distribution: Choice of monthly distribution ex. memory
            provider_uuid (str): The str of the provider UUID
        """
        distribute_mapping = {}
        distribution = distribution_info.get("distribution_type", DEFAULT_DISTRIBUTION_TYPE)
        table_name = self._table_map["line_item_daily_summary"]
        report_period = self.report_periods_for_provider_uuid(provider_uuid, start_date)
        if not report_period:
            msg = "no report period for OCP provider, skipping platform_and_worker_distributed_cost_sql update"
            context = {"schema": self.schema, "provider_uuid": provider_uuid, "start_date": start_date}
            # TODO: Figure out a way to pass the tracing id down here
            # in a separate PR. For now I am just going to use the
            # provider_uuid
            LOG.info(log_json(provider_uuid, msg=msg, context=context))
            return
        with schema_context(self.schema):
            report_period_id = report_period.id

        distribute_mapping = {
            "platform_cost": {
                "sql_file": "distribute_platform_cost.sql",
                "log_msg": {
                    True: "Distributing platform cost.",
                    False: "Removing platform_distributed cost model rate type.",
                },
            },
            "worker_cost": {
                "sql_file": "distribute_worker_cost.sql",
                "log_msg": {
                    True: "Distributing worker unallocated cost.",
                    False: "Removing worker_distributed cost model rate type.",
                },
            },
        }

        for cost_model_key, metadata in distribute_mapping.items():
            populate = distribution_info.get(cost_model_key, False)
            # if populate is false we only execute the delete sql.
            sql_params = {
                "start_date": start_date,
                "end_date": end_date,
                "schema": self.schema,
                "report_period_id": report_period_id,
                "distribution": distribution,
                "source_uuid": provider_uuid,
                "populate": populate,
            }

            templated_sql = pkgutil.get_data("masu.database", f"sql/openshift/cost_model/{metadata['sql_file']}")
            templated_sql = templated_sql.decode("utf-8")
            templated_sql, templated_sql_params = self.jinja_sql.prepare_query(templated_sql, sql_params)
            LOG.info(log_json(provider_uuid, msg=metadata["log_msg"][populate], context=sql_params))
            self._execute_raw_sql_query(
                table_name,
                templated_sql,
                start_date,
                end_date,
                bind_params=list(templated_sql_params),
                operation="INSERT",
            )

    def populate_monthly_cost_sql(self, cost_type, rate_type, rate, start_date, end_date, distribution, provider_uuid):
        """
        Populate the monthly cost of a customer.

        There are three types of monthly rates Node, Cluster & PVC.

        args:
            cost_type (str): Contains the type of monthly cost. ex: "Node"
            rate_type(str): Contains the metric name. ex: "node_cost_per_month"
            rate (decimal): Contains the rate amount ex: 100.0
            start_date (datetime, str): The start_date to calculate monthly_cost.
            end_date (datetime, str): The end_date to calculate monthly_cost.
            distribution: Choice of monthly distribution ex. memory
            provider_uuid (str): The str of the provider UUID
        """
        table_name = self._table_map["line_item_daily_summary"]
        report_period = self.report_periods_for_provider_uuid(provider_uuid, start_date)
        if not report_period:
            LOG.info(
                f"No report period for OCP provider {provider_uuid} with start date {start_date},"
                " skipping populate_monthly_cost_sql update."
            )
            return
        with schema_context(self.schema):
            report_period_id = report_period.id

        if not rate:
            msg = f"Removing monthly costs for source {provider_uuid} from {start_date} to {end_date}"
            LOG.info(msg)
            self.delete_line_item_daily_summary_entries_for_date_range_raw(
                provider_uuid,
                start_date,
                end_date,
                table=OCPUsageLineItemDailySummary,
                filters={"report_period_id": report_period_id, "monthly_cost_type": cost_type},
                null_filters={"cost_model_rate_type": "IS NOT NULL"},
            )
            # We cleared out existing data, but there is no new to calculate.
            return

        if cost_type in ("Node", "Cluster"):
            summary_sql = pkgutil.get_data(
                "masu.database", "sql/openshift/cost_model/monthly_cost_cluster_and_node.sql"
            )
        elif cost_type == "PVC":
            summary_sql = pkgutil.get_data(
                "masu.database", "sql/openshift/cost_model/monthly_cost_persistentvolumeclaim.sql"
            )

        summary_sql = summary_sql.decode("utf-8")
        summary_sql_params = {
            "start_date": start_date,
            "end_date": end_date,
            "schema": self.schema,
            "source_uuid": provider_uuid,
            "report_period_id": report_period_id,
            "rate": rate,
            "cost_type": cost_type,
            "rate_type": rate_type,
            "distribution": distribution,
        }
        summary_sql, summary_sql_params = self.jinja_sql.prepare_query(summary_sql, summary_sql_params)
        LOG.info("Populating monthly %s %s cost from %s to %s.", rate_type, cost_type, start_date, end_date)
        self._execute_raw_sql_query(
            table_name,
            summary_sql,
            start_date,
            end_date,
            bind_params=list(summary_sql_params),
            operation="INSERT",
        )

    def populate_monthly_tag_cost_sql(  # noqa: C901
        self, cost_type, rate_type, tag_key, case_dict, start_date, end_date, distribution, provider_uuid
    ):
        """
        Update or insert daily summary line item for node cost.
        It checks to see if a line item exists for each node
        that contains the tag key:value pair,
        if it does then the price is added to the monthly cost.
        """
        table_name = self._table_map["line_item_daily_summary"]
        report_period = self.report_periods_for_provider_uuid(provider_uuid, start_date)
        if not report_period:
            LOG.info(
                f"No report period for OCP provider {provider_uuid} with start date {start_date},"
                " skipping populate_monthly_tag_cost_sql update."
            )
            return
        with schema_context(self.schema):
            report_period_id = report_period.id

        cpu_case, memory_case, volume_case = case_dict.get("cost")
        labels = case_dict.get("labels")

        if cost_type == "Node":
            summary_sql = pkgutil.get_data("masu.database", "sql/openshift/cost_model/monthly_cost_node_by_tag.sql")
        elif cost_type == "PVC":
            summary_sql = pkgutil.get_data(
                "masu.database", "sql/openshift/cost_model/monthly_cost_persistentvolumeclaim_by_tag.sql"
            )

        summary_sql = summary_sql.decode("utf-8")
        summary_sql_params = {
            "start_date": start_date,
            "end_date": end_date,
            "schema": self.schema,
            "source_uuid": provider_uuid,
            "report_period_id": report_period_id,
            "cost_model_cpu_cost": cpu_case,
            "cost_model_memory_cost": memory_case,
            "cost_model_volume_cost": volume_case,
            "cost_type": cost_type,
            "rate_type": rate_type,
            "distribution": distribution,
            "tag_key": tag_key,
            "labels": labels,
        }

        if case_dict.get("unallocated"):
            unallocated_cpu_case, unallocated_memory_case, unallocated_volume_case = case_dict.get("unallocated")
            summary_sql_params["unallocated_cost_model_cpu_cost"] = unallocated_cpu_case
            summary_sql_params["unallocated_cost_model_memory_cost"] = unallocated_memory_case
            summary_sql_params["unallocated_cost_model_volume_cost"] = unallocated_volume_case

        summary_sql, summary_sql_params = self.jinja_sql.prepare_query(summary_sql, summary_sql_params)
        LOG.info("Populating monthly %s %s tag cost from %s to %s.", rate_type, cost_type, start_date, end_date)
        self._execute_raw_sql_query(
            table_name,
            summary_sql,
            start_date,
            end_date,
            bind_params=list(summary_sql_params),
            operation="INSERT",
        )

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

    def populate_usage_costs(self, rate_type, rates, start_date, end_date, provider_uuid):
        """Update the reporting_ocpusagelineitem_daily_summary table with usage costs."""
        table_name = self._table_map["line_item_daily_summary"]
        report_period = self.report_periods_for_provider_uuid(provider_uuid, start_date)
        if not report_period:
            LOG.info(
                f"No report period for OCP provider {provider_uuid} with start date {start_date},"
                " skipping populate_usage_costs_new_columns update."
            )
            return
        with schema_context(self.schema):
            report_period_id = report_period.id

        if not rates:
            msg = f"Removing usage costs for source {provider_uuid} from {start_date} to {end_date}"
            LOG.info(msg)
            self.delete_line_item_daily_summary_entries_for_date_range_raw(
                provider_uuid,
                start_date,
                end_date,
                table=OCPUsageLineItemDailySummary,
                filters={"cost_model_rate_type": rate_type, "report_period_id": report_period_id},
                null_filters={"monthly_cost_type": "IS NULL"},
            )
            # We cleared out existing data, but there is no new to calculate.
            return

        cost_model_usage_sql = pkgutil.get_data("masu.database", "sql/openshift/cost_model/usage_costs.sql")

        cost_model_usage_sql = cost_model_usage_sql.decode("utf-8")
        usage_sql_params = {
            "start_date": start_date,
            "end_date": end_date,
            "schema": self.schema,
            "source_uuid": provider_uuid,
            "report_period_id": report_period_id,
            "cpu_usage_rate": rates.get("cpu_core_usage_per_hour", 0),
            "cpu_request_rate": rates.get("cpu_core_request_per_hour", 0),
            "cpu_effective_rate": rates.get("cpu_core_effective_usage_per_hour", 0),
            "memory_usage_rate": rates.get("memory_gb_usage_per_hour", 0),
            "memory_request_rate": rates.get("memory_gb_request_per_hour", 0),
            "memory_effective_rate": rates.get("memory_gb_effective_usage_per_hour", 0),
            "volume_usage_rate": rates.get("storage_gb_usage_per_month", 0),
            "volume_request_rate": rates.get("storage_gb_request_per_month", 0),
            "rate_type": rate_type,
        }
        cost_model_usage_sql, cost_model_usage_sql_params = self.jinja_sql.prepare_query(
            cost_model_usage_sql, usage_sql_params
        )
        LOG.info("Populating %s usage cost from %s to %s.", rate_type, start_date, end_date)
        self._execute_raw_sql_query(
            table_name,
            cost_model_usage_sql,
            start_date,
            end_date,
            bind_params=list(cost_model_usage_sql_params),
            operation="INSERT",
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
            "cpu_core_effective_usage_per_hour": "cpu",
            "memory_gb_usage_per_hour": "memory",
            "memory_gb_request_per_hour": "memory",
            "memory_gb_effective_usage_per_hour": "memory",
            "storage_gb_usage_per_month": "storage",
            "storage_gb_request_per_month": "storage",
        }
        # Remove monthly rates
        infrastructure_rates = filter_dictionary(infrastructure_rates, metric_usage_type_map.keys())
        supplementary_rates = filter_dictionary(supplementary_rates, metric_usage_type_map.keys())
        # define the rates so the loop can operate on both rate types
        rate_types = [
            {"rates": infrastructure_rates, "sql_file": "sql/openshift/cost_model/infrastructure_tag_rates.sql"},
            {"rates": supplementary_rates, "sql_file": "sql/openshift/cost_model/supplementary_tag_rates.sql"},
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
                        sql, sql_params = self.jinja_sql.prepare_query(tag_rates_sql, tag_rates_sql_params)
                        LOG.info(log_json(msg="running populate_tag_usage_costs SQL", **tag_rates_sql_params))
                        self._execute_raw_sql_query(
                            table_name, sql, start_date, end_date, bind_params=list(sql_params)
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
            "cpu_core_effective_usage_per_hour": "cpu",
            "memory_gb_usage_per_hour": "memory",
            "memory_gb_request_per_hour": "memory",
            "memory_gb_effective_usage_per_hour": "memory",
            "storage_gb_usage_per_month": "storage",
            "storage_gb_request_per_month": "storage",
        }
        # Remove monthly rates
        infrastructure_rates = filter_dictionary(infrastructure_rates, metric_usage_type_map.keys())
        supplementary_rates = filter_dictionary(supplementary_rates, metric_usage_type_map.keys())
        # define the rates so the loop can operate on both rate types
        rate_types = [
            {
                "rates": infrastructure_rates,
                "sql_file": "sql/openshift/cost_model/default_infrastructure_tag_rates.sql",
            },
            {"rates": supplementary_rates, "sql_file": "sql/openshift/cost_model/default_supplementary_tag_rates.sql"},
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
                    sql, sql_params = self.jinja_sql.prepare_query(tag_rates_sql, tag_rates_sql_params)
                    LOG.info(log_json(msg="running populate_tag_usage_default_costs SQL", **tag_rates_sql_params))
                    self._execute_raw_sql_query(table_name, sql, start_date, end_date, bind_params=list(sql_params))

    def populate_openshift_cluster_information_tables(self, provider, cluster_id, cluster_alias, start_date, end_date):
        """Populate the cluster, node, PVC, and project tables for the cluster."""
        cluster = self.populate_cluster_table(provider, cluster_id, cluster_alias)

        nodes = self.get_nodes_trino(str(provider.uuid), start_date, end_date)
        pvcs = []
        if trino_table_exists(self.schema, "openshift_storage_usage_line_items_daily"):
            pvcs = self.get_pvcs_trino(str(provider.uuid), start_date, end_date)
        projects = self.get_projects_trino(str(provider.uuid), start_date, end_date)

        # pvcs = self.match_node_to_pvc(pvcs, projects)

        self.populate_node_table(cluster, nodes)
        self.populate_pvc_table(cluster, pvcs)
        self.populate_project_table(cluster, projects)

    def populate_cluster_table(self, provider, cluster_id, cluster_alias):
        """Get or create an entry in the OCP cluster table."""
        with schema_context(self.schema):
            cluster, created = OCPCluster.objects.get_or_create(
                cluster_id=cluster_id, cluster_alias=cluster_alias, provider=provider
            )

        if created:
            msg = f"Add entry in reporting_ocp_clusters for {cluster_id}/{cluster_alias}"
            LOG.info(msg)

        return cluster

    def populate_node_table(self, cluster, nodes):
        """Get or create an entry in the OCP node table."""
        LOG.info("Populating reporting_ocp_nodes table.")
        with schema_context(self.schema):
            for node in nodes:
                tmp_node = OCPNode.objects.filter(
                    node=node[0], resource_id=node[1], node_capacity_cpu_cores=node[2], cluster=cluster
                ).first()
                if not tmp_node:
                    OCPNode.objects.create(
                        node=node[0],
                        resource_id=node[1],
                        node_capacity_cpu_cores=node[2],
                        node_role=node[3],
                        cluster=cluster,
                    )
                # if the node entry already exists but does not have a role assigned, update the node role
                elif not tmp_node.node_role:
                    tmp_node.node_role = node[3]
                    tmp_node.save()

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

    def get_nodes_trino(self, source_uuid, start_date, end_date):
        """Get the nodes from an OpenShift cluster."""
        sql = f"""
            SELECT ocp.node,
                ocp.resource_id,
                max(ocp.node_capacity_cpu_cores) as node_capacity_cpu_cores,
                coalesce(max(ocp.node_role), CASE
                    WHEN contains(array_agg(DISTINCT ocp.namespace), 'openshift-kube-apiserver') THEN 'master'
                    WHEN any_match(array_agg(DISTINCT nl.node_labels), element -> element like  '%"node_role_kubernetes_io": "infra"%') THEN 'infra'
                    ELSE 'worker'
                END) as node_role
            FROM hive.{self.schema}.openshift_pod_usage_line_items_daily as ocp
            LEFT JOIN hive.{self.schema}.openshift_node_labels_line_items_daily as nl
                ON ocp.node = nl.node
            WHERE ocp.source = '{source_uuid}'
                AND ocp.year = '{start_date.strftime("%Y")}'
                AND ocp.month = '{start_date.strftime("%m")}'
                AND ocp.interval_start >= TIMESTAMP '{start_date}'
                AND ocp.interval_start < date_add('day', 1, TIMESTAMP '{end_date}')
                AND nl.source = '{source_uuid}'
                AND nl.year = '{start_date.strftime("%Y")}'
                AND nl.month = '{start_date.strftime("%m")}'
                AND nl.interval_start >= TIMESTAMP '{start_date}'
                AND nl.interval_start < date_add('day', 1, TIMESTAMP '{end_date}')
            GROUP BY ocp.node,
                ocp.resource_id
        """  # noqa: E501

        return self._execute_trino_raw_sql_query(sql, log_ref="get_nodes_trino")

    def get_pvcs_trino(self, source_uuid, start_date, end_date):
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

        return self._execute_trino_raw_sql_query(sql, log_ref="get_pvcs_trino")

    def get_projects_trino(self, source_uuid, start_date, end_date):
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

        projects = self._execute_trino_raw_sql_query(sql, log_ref="get_projects_trino")

        return [project[0] for project in projects]

    def get_cluster_for_provider(self, provider_uuid):
        """Return the cluster entry for a provider UUID."""
        with schema_context(self.schema):
            cluster = OCPCluster.objects.filter(provider_id=provider_uuid).first()
        return cluster

    def get_nodes_for_cluster(self, cluster_id):
        """Get all nodes for an OCP cluster."""
        with schema_context(self.schema):
            nodes = (
                OCPNode.objects.filter(cluster_id=cluster_id)
                .exclude(node__exact="")
                .values_list("node", "resource_id")
            )
            nodes = [(node[0], node[1]) for node in nodes]
        return nodes

    def get_pvcs_for_cluster(self, cluster_id):
        """Get all nodes for an OCP cluster."""
        with schema_context(self.schema):
            pvcs = (
                OCPPVC.objects.filter(cluster_id=cluster_id)
                .exclude(persistent_volume__exact="")
                .values_list("persistent_volume", "persistent_volume_claim")
            )
            pvcs = [(pvc[0], pvc[1]) for pvc in pvcs]
        return pvcs

    def get_projects_for_cluster(self, cluster_id):
        """Get all nodes for an OCP cluster."""
        with schema_context(self.schema):
            projects = OCPProject.objects.filter(cluster_id=cluster_id).values_list("project")
            projects = [project[0] for project in projects]
        return projects

    def get_openshift_topology_for_multiple_providers(self, provider_uuids):
        """Return a dictionary with 1 or more Clusters topology."""
        topology_list = []
        for provider_uuid in provider_uuids:
            cluster = self.get_cluster_for_provider(provider_uuid)
            nodes_tuple = self.get_nodes_for_cluster(cluster.uuid)
            pvc_tuple = self.get_pvcs_for_cluster(cluster.uuid)
            project_tuple = self.get_projects_for_cluster(cluster.uuid)
            topology_list.append(
                {
                    "cluster_id": cluster.cluster_id,
                    "cluster_alias": cluster.cluster_alias,
                    "provider_uuid": provider_uuid,
                    "nodes": [node[0] for node in nodes_tuple],
                    "resource_ids": [node[1] for node in nodes_tuple],
                    "persistent_volumes": [pvc[0] for pvc in pvc_tuple],
                    "persistent_volume_claims": [pvc[1] for pvc in pvc_tuple],
                    "projects": [project for project in project_tuple],
                }
            )

        return topology_list

    def get_filtered_openshift_topology_for_multiple_providers(self, provider_uuids, start_date, end_date):
        """Return a dictionary with 1 or more Clusters topology."""
        topology_list = []
        for provider_uuid in provider_uuids:
            cluster = self.get_cluster_for_provider(provider_uuid)
            nodes_tuple = self.get_nodes_trino(provider_uuid, start_date, end_date)
            pvc_tuple = self.get_pvcs_trino(provider_uuid, start_date, end_date)
            topology_list.append(
                {
                    "cluster_id": cluster.cluster_id,
                    "cluster_alias": cluster.cluster_alias,
                    "provider_uuid": provider_uuid,
                    "nodes": [node[0] for node in nodes_tuple],
                    "resource_ids": [node[1] for node in nodes_tuple],
                    "persistent_volumes": [pvc[0] for pvc in pvc_tuple],
                }
            )

        return topology_list

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

    def delete_all_except_infrastructure_raw_cost_from_daily_summary(
        self, provider_uuid, report_period_id, start_date, end_date
    ):
        table_name = OCP_REPORT_TABLE_MAP["line_item_daily_summary"]
        msg = (
            f"Removing all cost excluding infrastructure_raw_cost for {provider_uuid} from {start_date} to {end_date}."
        )
        LOG.info(msg)
        sql = f"""
            DELETE FROM {self.schema}.reporting_ocpusagelineitem_daily_summary
            WHERE usage_start >= '{start_date}'::date
                AND usage_start <= '{end_date}'::date
                AND report_period_id = {report_period_id}
                AND (infrastructure_raw_cost IS NULL OR infrastructure_raw_cost = 0)
        """

        self._execute_raw_sql_query(table_name, sql, start_date, end_date)

    def populate_ocp_on_all_project_daily_summary(self, platform, sql_params):
        LOG.info(f"Populating {platform.upper()} records for ocpallcostlineitem_project_daily_summary")
        script_file_name = f"reporting_ocpallcostlineitem_project_daily_summary_{platform.lower()}.sql"
        script_file_path = f"{self.OCP_ON_ALL_SQL_PATH}{script_file_name}"
        self._execute_processing_script("masu.database", script_file_path, sql_params)

    def populate_ocp_on_all_daily_summary(self, platform, sql_params):
        LOG.info(f"Populating {platform.upper()} records for ocpallcostlineitem_daily_summary")
        script_file_name = f"reporting_ocpallcostlineitem_daily_summary_{platform.lower()}.sql"
        script_file_path = f"{self.OCP_ON_ALL_SQL_PATH}{script_file_name}"
        self._execute_processing_script("masu.database", script_file_path, sql_params)

    def populate_ocp_on_all_ui_summary_tables(self, sql_params):
        for perspective in OCP_ON_ALL_PERSPECTIVES:
            LOG.info(f"Populating {perspective._meta.db_table} data using {sql_params}")
            script_file_path = f"{self.OCP_ON_ALL_SQL_PATH}{perspective._meta.db_table}.sql"
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

        timestamps = self._execute_trino_raw_sql_query(sql, log_ref="get_max_min_timestamp_from_parquet")
        minim, maxim = timestamps[0]
        minim = parse(str(minim)) if minim else datetime.datetime(start_date.year, start_date.month, start_date.day)
        maxim = parse(str(maxim)) if maxim else datetime.datetime(end_date.year, end_date.month, end_date.day)
        return minim, maxim
