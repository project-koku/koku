#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Database accessor for OCP report data."""
import copy
import datetime
import json
import logging
import os
import pkgutil
import uuid
from uuid import uuid4

from dateutil.parser import parse
from django.db import IntegrityError
from django.db.models import DecimalField
from django.db.models import F
from django.db.models import Value
from django.db.models.functions import Coalesce
from django_tenants.utils import schema_context

from api.common import log_json
from api.metrics import constants as metric_constants
from api.metrics.constants import DEFAULT_DISTRIBUTION_TYPE
from api.provider.models import Provider
from api.utils import DateHelper
from cost_models.sql_parameters import BaseCostModelParams
from koku.database import SQLScriptAtomicExecutorMixin
from koku.trino_database import TrinoStatementExecError
from masu.database import OCP_REPORT_TABLE_MAP
from masu.database.cost_model_db_accessor import CostModelDBAccessor
from masu.database.report_db_accessor_base import ReportDBAccessorBase
from masu.processor import is_feature_flag_enabled_by_account
from masu.processor import OCP_GPU_COST_MODEL_UNLEASH_FLAG
from masu.util.common import filter_dictionary
from masu.util.common import source_in_trino_table
from masu.util.common import trino_table_exists
from masu.util.ocp.common import DistributionConfig
from masu.util.ocp.common import get_cluster_alias_from_cluster_id
from masu.util.ocp.common import get_cluster_id_from_provider
from reporting.models import OCP_ON_ALL_PERSPECTIVES
from reporting.provider.all.models import TagMapping
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
from reporting.provider.ocp.models import VM_UI_SUMMARY_TABLE

LOG = logging.getLogger(__name__)


class OCPReportDBAccessor(SQLScriptAtomicExecutorMixin, ReportDBAccessorBase):
    """Class to interact with customer reporting tables."""

    #  Empty string will put a path seperator on the end
    OCP_ON_ALL_SQL_PATH = os.path.join("sql", "openshift", "all", "ui_summary", "")

    def __init__(self, schema):
        """Establish the database connection.

        Args:
            schema (str): The customer schema to associate with
        """
        super().__init__(schema)
        self._table_map = OCP_REPORT_TABLE_MAP

    @property
    def line_item_daily_summary_table(self):
        return OCPUsageLineItemDailySummary

    def get_usage_period_query_by_provider(self, provider_uuid):
        """Return all report periods for the specified provider."""
        return OCPUsageReportPeriod.objects.filter(provider_id=provider_uuid)

    def report_periods_for_provider_uuid(self, provider_uuid, start_date=None):
        """Return all report periods for provider_uuid on date."""
        report_periods = self.get_usage_period_query_by_provider(provider_uuid)
        if start_date:
            if isinstance(start_date, str):
                start_date = parse(start_date)
            report_date = start_date.replace(day=1)
            report_periods = report_periods.filter(report_period_start=report_date).first()
        return report_periods

    def get_report_periods_before_date(self, date):
        """Get the report periods with report period before provided date."""
        return OCPUsageReportPeriod.objects.filter(report_period_start__lte=date)

    def populate_ui_summary_tables(self, start_date, end_date, source_uuid, tables=UI_SUMMARY_TABLES):
        """Populate our UI summary tables (formerly materialized views)."""
        sql_params = {
            "start_date": start_date,
            "end_date": end_date,
            "schema": self.schema,
            "source_uuid": source_uuid,
        }
        for table_name in tables:
            sql = pkgutil.get_data("masu.database", f"sql/openshift/ui_summary/{table_name}.sql")
            sql = sql.decode("utf-8")
            self._prepare_and_execute_raw_sql_query(table_name, sql, sql_params, operation="DELETE/INSERT")

        # Trino Queries:
        start_date = DateHelper().parse_to_date(sql_params["start_date"])
        sql_params["year"] = start_date.strftime("%Y")
        sql_params["month"] = start_date.strftime("%m")

        self._populate_gpu_ui_summary_table_with_usage_only(sql_params)
        self._populate_virtualization_ui_summary_table(sql_params)

    def _populate_gpu_ui_summary_table_with_usage_only(self, params):
        """
        Populates the gpu only table with just basic gpu information whenever
        GPU information exists, but the customer has not set up a cost model.
        """
        sql_params = copy.deepcopy(params)
        if not source_in_trino_table(
            self.schema, sql_params.get("source_uuid"), TRINO_LINE_ITEM_TABLE_DAILY_MAP["gpu_usage"]
        ):
            return
        # Don't use context manager here - its __exit__ resets schema to public,
        # which would break subsequent ORM operations in the calling code
        cost_model_accessor = CostModelDBAccessor(self.schema, sql_params.get("source_uuid"))
        # Check to see if the cost model is set up to give cost
        if cost_model_accessor.metric_to_tag_params_map.get(metric_constants.OCP_GPU_MONTH):
            return
        cluster_id = get_cluster_id_from_provider(sql_params.get("source_uuid"))
        sql_params["cluster_id"] = cluster_id
        sql_params["cluster_alias"] = get_cluster_alias_from_cluster_id(cluster_id)
        sql_params["source_uuid"] = str(sql_params["source_uuid"])
        populate_gpu_usage_info = pkgutil.get_data(
            "masu.database", "trino_sql/openshift/ui_summary/reporting_ocp_gpu_summary_p_usage_only.sql"
        )
        populate_gpu_usage_info = populate_gpu_usage_info.decode("utf-8")
        self._execute_trino_multipart_sql_query(populate_gpu_usage_info, bind_params=sql_params)

    def _populate_virtualization_ui_summary_table(self, params):
        """
        Populates the virtualization ui table.
        """
        sql_params = copy.deepcopy(params)
        if not self.schema_exists_trino():
            return
        trino_query_requirements = [
            trino_table_exists(self.schema, "openshift_storage_usage_line_items_daily"),
            trino_table_exists(self.schema, "openshift_pod_usage_line_items_daily"),
            sql_params.get("start_date"),
        ]
        if not all(trino_query_requirements):
            return
        # create the temp table
        sql_params["uuid"] = str(uuid4().hex)
        create_temp_table_sql = pkgutil.get_data("masu.database", "sql/openshift/create_virtualization_tmp_table.sql")
        create_temp_table_sql = create_temp_table_sql.decode("utf-8")
        self._prepare_and_execute_raw_sql_query(
            "create temp virtualization table", create_temp_table_sql, sql_params, operation="CREATE"
        )
        # This pathway won't be needed if/when we require users to utilize 4.0.0 operator
        population_temp_table_file = "populate_vm_tmp_table.sql"
        if source_in_trino_table(
            self.schema, sql_params.get("source_uuid"), TRINO_LINE_ITEM_TABLE_DAILY_MAP["vm_usage"]
        ):
            population_temp_table_file = "populate_vm_tmp_table_with_vm_report.sql"
        populate_temp_table_sql = pkgutil.get_data(
            "masu.database", f"trino_sql/openshift/{population_temp_table_file}"
        )
        populate_temp_table_sql = populate_temp_table_sql.decode("utf8")
        self._execute_trino_multipart_sql_query(populate_temp_table_sql, bind_params=sql_params)
        # populate vm UI table
        sql = pkgutil.get_data("masu.database", f"sql/openshift/ui_summary/{VM_UI_SUMMARY_TABLE}.sql")
        sql = sql.decode("utf-8")
        self._prepare_and_execute_raw_sql_query(VM_UI_SUMMARY_TABLE, sql, sql_params, operation="DELETE/INSERT")

    def update_line_item_daily_summary_with_tag_mapping(self, start_date, end_date, report_period_ids=None):
        """Maps child keys to parent key.
        Args:
            start_date (datetime.date) The date to start mapping keys
            end_date (datetime.date) The date to end on.
            bill_ids (list) A list of bill IDs.
        Returns
            (None)
        """
        with schema_context(self.schema):
            # Early return check to see if they have any tag mappings set.
            if not TagMapping.objects.filter(child__provider_type=Provider.PROVIDER_OCP).exists():
                LOG.debug("No tag mappings for OCP.")
                return
        table_name = self._table_map["line_item_daily_summary"]
        sql = pkgutil.get_data("masu.database", "sql/openshift/ocp_tag_mapping_update_daily_summary.sql")
        sql = sql.decode("utf-8")
        sql_params = {
            "start_date": start_date,
            "end_date": end_date,
            "report_period_ids": report_period_ids,
            "schema": self.schema,
        }
        self._prepare_and_execute_raw_sql_query(table_name, sql, sql_params)

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

        check_aws = False
        check_azure = False
        check_gcp = False

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
            if gcp_provider_uuid and not check_gcp:
                return {}
        if not any([check_aws, check_azure, check_gcp]):
            return {}

        check_flags = {
            Provider.PROVIDER_AWS: check_aws,
            Provider.PROVIDER_AZURE: check_azure,
            Provider.PROVIDER_GCP: check_gcp,
        }

        if isinstance(start_date, str):
            start_date = datetime.datetime.strptime(start_date, "%Y-%m-%d").date()
            end_date = datetime.datetime.strptime(end_date, "%Y-%m-%d").date()
        for source_type, check_flag in check_flags.items():
            db_results = {}
            if check_flag:
                sql = pkgutil.get_data(
                    "masu.database", f"trino_sql/{source_type.lower()}/reporting_ocpinfrastructure_provider_map.sql"
                )
                sql = sql.decode("utf-8")

                sql_params = {
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

                results = self._execute_trino_raw_sql_query(
                    sql,
                    sql_params=sql_params,
                    log_ref="reporting_ocpinfrastructure_provider_map.sql",
                )
                for entry in results:
                    # This dictionary is keyed on an OpenShift provider UUID
                    # and the tuple contains
                    # (Infra Provider UUID, Infra Provider Type)
                    db_results[entry[0]] = (entry[1], entry[2])
                if db_results:
                    # An OCP cluster can only run on a single source, so stop here if we found a match
                    return db_results
        return db_results

    def delete_ocp_hive_partition_by_day(self, days, source, year, month):
        """Deletes partitions individually for each day in days list."""
        table = "reporting_ocpusagelineitem_daily_summary"
        if self.schema_exists_trino() and self.table_exists_trino(table):
            LOG.info(
                log_json(
                    msg="deleting Hive partitions by day",
                    schema=self.schema,
                    ocp_source=source,
                    table=table,
                    year=year,
                    month=month,
                    days=days,
                )
            )
            for day in days:
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
                )

    def delete_hive_partitions_by_source(self, table, partition_column, provider_uuid):
        """Deletes partitions individually for each day in days list."""
        if not self.schema_exists_trino() or not self.table_exists_trino(table):
            return False
        ctx = {
            "schema": self.schema,
            "provider_uuid": provider_uuid,
            "table": table,
        }
        LOG.info(log_json(msg="deleting Hive partitions by source", context=ctx))
        sql = f"""
        DELETE FROM hive.{self.schema}.{table}
        WHERE {partition_column} = '{provider_uuid}'
        """
        self._execute_trino_raw_sql_query(
            sql,
            log_ref=f"delete_hive_partitions_by_source for {provider_uuid}",
        )
        return True

    def find_expired_trino_partitions(self, table, source_column, date_str):
        """Queries Trino for partitions less than the parition date."""
        if not self.schema_exists_trino():
            LOG.info("Schema does not exist.")
            return False
        if not self.table_exists_trino(table):
            LOG.info("Could not find table.")
            return False
        sql = f"""
            SELECT partitions.year, partitions.month, partitions.source
            FROM (
                SELECT year as year,
                    month as month,
                    day as day,
                    cast(date_parse(concat(year, '-', month, '-', day), '%Y-%m-%d') as date) as partition_date,
                    {source_column} as source
                FROM  "{table}$partitions"
            ) as partitions
            WHERE partitions.partition_date < DATE '{date_str}'
            GROUP BY partitions.year, partitions.month, partitions.source
        """
        return self._execute_trino_raw_sql_query(sql, log_ref="finding expired partitions")

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
        start_date = DateHelper().parse_to_date(start_date)
        end_date = DateHelper().parse_to_date(end_date)

        storage_exists = trino_table_exists(self.schema, "openshift_storage_usage_line_items_daily")

        year = start_date.strftime("%Y")
        month = start_date.strftime("%m")
        days = self.date_helper.list_days(start_date, end_date)
        days_tup = tuple(str(day.day) for day in days)
        self.delete_ocp_hive_partition_by_day(days_tup, source, year, month)

        sql = pkgutil.get_data("masu.database", "trino_sql/openshift/reporting_ocpusagelineitem_daily_summary.sql")
        sql = sql.decode("utf-8")
        sql_params = {
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

        try:
            self._execute_trino_multipart_sql_query(sql, bind_params=sql_params)
        except TrinoStatementExecError as trino_exc:
            if trino_exc.error_name == "ALREADY_EXISTS":
                LOG.warning(
                    log_json(
                        ctx=self.extract_context_from_sql_params(sql_params),
                        msg=trino_exc.message,
                        error_type=trino_exc.error_type,
                        error_name=trino_exc.error_name,
                        query_id=trino_exc.query_id,
                    )
                )
            else:
                raise

    def populate_pod_label_summary_table(self, report_period_ids, start_date, end_date):
        """Populate the line item aggregated totals data table."""
        table_name = self._table_map["pod_label_summary"]

        sql_params = {
            "uuid": str(uuid.uuid4()).replace("-", "_"),
            "schema": self.schema,
            "report_period_ids": report_period_ids,
            "start_date": start_date,
            "end_date": end_date,
        }
        ctx = self.extract_context_from_sql_params(sql_params)
        LOG.info(log_json(msg=f"updating {table_name}", context=ctx))
        self._execute_processing_script(
            "masu.database", "sql/openshift/reporting_ocpusagepodlabel_summary.sql", sql_params
        )
        LOG.info(log_json(msg=f"finished updating {table_name}", context=ctx))

    def populate_volume_label_summary_table(self, report_period_ids, start_date, end_date):
        """Populate the OCP volume label summary table."""
        table_name = self._table_map["volume_label_summary"]

        sql_params = {
            "uuid": str(uuid.uuid4()).replace("-", "_"),
            "schema": self.schema,
            "report_period_ids": report_period_ids,
            "start_date": start_date,
            "end_date": end_date,
        }
        ctx = self.extract_context_from_sql_params(sql_params)
        LOG.info(log_json(msg=f"updating {table_name}", context=ctx))
        self._execute_processing_script(
            "masu.database", "sql/openshift/reporting_ocpstoragevolumelabel_summary.sql", sql_params
        )
        LOG.info(log_json(msg=f"finished updating {table_name}", context=ctx))

    def populate_markup_cost(self, markup, start_date, end_date, cluster_id):
        """Set markup cost for OCP including infrastructure cost markup."""
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

    def populate_distributed_cost_sql(self, start_date, end_date, provider_uuid, distribution_info):
        """
        Populate the distribution cost model options.

        args:
            start_date (datetime, str): The start_date to calculate monthly_cost.
            end_date (datetime, str): The end_date to calculate monthly_cost.
            distribution: Choice of monthly distribution ex. memory
            provider_uuid (str): The str of the provider UUID
        """

        distribution_configs = {
            metric_constants.PLATFORM_COST: DistributionConfig(
                sql_file="distribute_platform_cost.sql",
                cost_model_rate_type="platform_distributed",
            ),
            metric_constants.WORKER_UNALLOCATED: DistributionConfig(
                sql_file="distribute_worker_cost.sql",
                cost_model_rate_type="worker_distributed",
            ),
            metric_constants.STORAGE_UNATTRIBUTED: DistributionConfig(
                sql_file="distribute_unattributed_storage_cost.sql",
                cost_model_rate_type="unattributed_storage",
                distribute_by_default=True,  # Distributed without cost model
            ),
            metric_constants.NETWORK_UNATTRIBUTED: DistributionConfig(
                sql_file="distribute_unattributed_network_cost.sql",
                cost_model_rate_type="unattributed_network",
                distribute_by_default=True,  # Distributed without cost model
            ),
            metric_constants.GPU_UNALLOCATED: DistributionConfig(
                sql_file="distribute_unallocated_gpu_cost.sql",
                cost_model_rate_type="gpu_distributed",
                query_type="trino",
                required_table="openshift_gpu_usage_line_items_daily",
                requires_full_month=True,
            ),
        }

        table_name = self._table_map["line_item_daily_summary"]
        dh = DateHelper()
        for cost_model_key, config in distribution_configs.items():
            sql_params = {
                "start_date": start_date,
                "end_date": end_date,
                "schema": self.schema,
                "source_uuid": provider_uuid,
                "cost_model_rate_type": config.cost_model_rate_type,
            }
            # Handle distributions that require full month data
            if config.requires_full_month:
                start_date_parsed = dh.parse_to_date(start_date)
                is_current_month = (
                    start_date_parsed.year == dh.now_utc.year and start_date_parsed.month == dh.now_utc.month
                )
                sql_params["start_date"] = dh.month_start(start_date)
                if is_current_month:
                    # Trigger distribution for previous month during a window of the current
                    # month
                    if dh.now_utc.day in [1, 2, 3]:
                        sql_params["start_date"] = dh.last_month_start.date()
                        sql_params["end_date"] = dh.last_month_end.date()
                    else:
                        msg = f"Skipping {cost_model_key} distribution requires full month"
                        LOG.info(log_json(msg=msg, context={"schema": self.schema, "cost_model_key": cost_model_key}))
                        continue

            report_period = self.report_periods_for_provider_uuid(provider_uuid, sql_params["start_date"])
            if not report_period:
                msg = f"no report period for OCP provider, skipping {cost_model_key} distribution update"
                context = {
                    "schema": self.schema,
                    "provider_uuid": provider_uuid,
                    "start_date": sql_params["start_date"],
                }
                LOG.info(log_json(msg=msg, context=context))
                continue
            sql_params["report_period_id"] = report_period.id

            self._delete_monthly_cost_model_rate_type_data(sql_params, cost_model_key)
            populate = distribution_info.get(cost_model_key, config.distribute_by_default)
            if not populate:
                continue
            sql_params["distribution"] = distribution_info.get("distribution_type", DEFAULT_DISTRIBUTION_TYPE)
            sql = pkgutil.get_data("masu.database", config.get_full_path())
            sql = sql.decode("utf-8")
            log_msg = f"distributing {cost_model_key}"
            LOG.info(log_json(msg=log_msg, context=sql_params))

            # Execute using appropriate query engine
            if config.is_trino:
                # Check if required table exists before executing Trino query
                if config.has_table_requirement and not config.table_exists(self.schema):
                    msg = (
                        f"Skipping {cost_model_key} distribution - "
                        f"required table '{config.required_table}' does not exist"
                    )
                    LOG.info(log_json(msg=msg, context={"schema": self.schema, "cost_model_key": cost_model_key}))
                    continue
                start_date_parsed = DateHelper().parse_to_date(sql_params["start_date"])
                sql_params["year"] = start_date_parsed.strftime("%Y")
                sql_params["month"] = start_date_parsed.strftime("%m")
                self._execute_trino_multipart_sql_query(sql, bind_params=sql_params)
            else:
                self._prepare_and_execute_raw_sql_query(table_name, sql, sql_params, operation=f"INSERT: {log_msg}")

    def _delete_monthly_cost_model_rate_type_data(self, sql_params, cost_model_key):
        delete_sql = pkgutil.get_data(
            "masu.database", "sql/openshift/cost_model/delete_monthly_cost_model_rate_type.sql"
        )
        delete_sql = delete_sql.decode("utf-8")
        LOG.info(log_json(msg=f"removing {cost_model_key} distribution", context=sql_params))
        self._prepare_and_execute_raw_sql_query(
            self._table_map["line_item_daily_summary"], delete_sql, sql_params, operation="DELETE"
        )

    def _delete_monthly_cost_model_data(self, sql_params, ctx):
        delete_sql = pkgutil.get_data("masu.database", "sql/openshift/cost_model/delete_monthly_cost.sql")
        delete_sql = delete_sql.decode("utf-8")
        if sql_params.get("rate_type"):
            LOG.info(log_json(msg="removing monthly costs", context=ctx))
        else:
            LOG.info(log_json(msg="removing stale monthly costs", context=ctx))
        self._prepare_and_execute_raw_sql_query(
            self._table_map["line_item_daily_summary"], delete_sql, sql_params, operation="DELETE"
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
        if cost_type == "OCP_VM_CORE" and not trino_table_exists(self.schema, "openshift_vm_usage_line_items"):
            return
        cost_type_file_mapping = {
            "Node": "sql/openshift/cost_model/monthly_cost_cluster_and_node.sql",
            "Node_Core_Month": "sql/openshift/cost_model/monthly_cost_cluster_and_node.sql",
            "Cluster": "sql/openshift/cost_model/monthly_cost_cluster_and_node.sql",
            "PVC": "sql/openshift/cost_model/monthly_cost_persistentvolumeclaim.sql",
            "OCP_VM": "sql/openshift/cost_model/monthly_cost_virtual_machine.sql",
            "OCP_VM_CORE": "trino_sql/openshift/cost_model/monthly_vm_core.sql",
        }
        cost_type_file = cost_type_file_mapping.get(cost_type)
        if not cost_type_file:
            LOG.warning(f"Invalid cost_type: {cost_type} for OCP provider. Skipping populate_monthly_cost_sql update")
            return

        table_name = self._table_map["line_item_daily_summary"]
        report_period = self.report_periods_for_provider_uuid(provider_uuid, start_date)
        ctx = {
            "schema": self.schema,
            "provider_uuid": provider_uuid,
            "start_date": start_date,
            "end_date": end_date,
            "report_period": report_period,
            "cost_type": cost_type,
        }
        if not report_period:
            LOG.info(
                log_json(
                    msg="no report period for OCP provider, skipping populate_monthly_cost_sql update",
                    context=ctx,
                )
            )
            return

        # always delete existing cost-type data
        self._delete_monthly_cost_model_data(
            {
                "schema": self.schema,
                "report_period_id": report_period.id,
                "start_date": start_date,
                "end_date": end_date,
                "cost_type": cost_type,
            },
            ctx,
        )
        if not rate:
            # since we don't have a rate, we have no new costs to calculate.
            return

        # Insert
        sql_params = {
            "start_date": start_date,
            "end_date": end_date,
            "schema": self.schema,
            "source_uuid": provider_uuid,
            "report_period_id": report_period.id,
            "rate": rate,
            "cost_type": cost_type,
            "rate_type": rate_type,
            "distribution": distribution,
        }
        insert_sql = pkgutil.get_data("masu.database", cost_type_file)
        insert_sql = insert_sql.decode("utf-8")
        LOG.info(log_json(msg="populating monthly costs", context=ctx))
        if "trino_sql/" in cost_type_file:
            start_date = DateHelper().parse_to_date(sql_params["start_date"])
            sql_params["year"] = start_date.strftime("%Y")
            sql_params["month"] = start_date.strftime("%m")
            self._execute_trino_multipart_sql_query(insert_sql, bind_params=sql_params)
        else:
            self._prepare_and_execute_raw_sql_query(table_name, insert_sql, sql_params, operation="INSERT")

    def populate_tag_cost_sql(
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
        ctx = {
            "schema": self.schema,
            "provider_uuid": provider_uuid,
            "start_date": start_date,
            "end_date": end_date,
            "report_period": report_period,
        }
        if not report_period:
            LOG.info(
                log_json(
                    msg="no report period for OCP provider, skipping populate_monthly_tag_cost_sql update",
                    context=ctx,
                )
            )
            return
        report_period_id = report_period.id

        cpu_case, memory_case, volume_case = case_dict.get("cost")
        labels = case_dict.get("labels")

        if "Node" in cost_type:
            sql = pkgutil.get_data("masu.database", "sql/openshift/cost_model/node_cost_by_tag.sql")
        elif cost_type == "PVC":
            sql = pkgutil.get_data(
                "masu.database", "sql/openshift/cost_model/monthly_cost_persistentvolumeclaim_by_tag.sql"
            )

        sql = sql.decode("utf-8")
        sql_params = {
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
            sql_params["unallocated_cost_model_cpu_cost"] = unallocated_cpu_case
            sql_params["unallocated_cost_model_memory_cost"] = unallocated_memory_case
            sql_params["unallocated_cost_model_volume_cost"] = unallocated_volume_case

        LOG.info(log_json(msg="populating tag costs", context=ctx))
        self._prepare_and_execute_raw_sql_query(table_name, sql, sql_params, operation="INSERT")

    def populate_vm_usage_costs(
        self, rate_type, vm_usage_rates, start_date, end_date, provider_uuid, report_period_id
    ):
        if not vm_usage_rates:
            return
        vm_table_exists = trino_table_exists(self.schema, "openshift_vm_usage_line_items")
        vm_usage_metadata = {
            metric_constants.OCP_VM_HOUR: {
                "file_path": "trino_sql/openshift/cost_model/hourly_cost_virtual_machine.sql",
                "log_msg": "populating virtual machine hourly costs",
                "metric_params": {"use_fractional_hours": vm_table_exists},
            },
            metric_constants.OCP_VM_CORE_HOUR: {
                "file_path": "trino_sql/openshift/cost_model/hourly_vm_core.sql",
                "log_msg": "populating virtual machine core hourly costs",
            },
        }
        for metric_name, hourly_rate in vm_usage_rates.items():
            metadata = vm_usage_metadata.get(metric_name)
            if metric_name == metric_constants.OCP_VM_CORE_HOUR and not vm_table_exists:
                continue
            param_builder = BaseCostModelParams(
                schema_name=self.schema,
                start_date=start_date,
                end_date=end_date,
                source_uuid=provider_uuid,
                report_period_id=report_period_id,
            )
            context_params = {"rate_type": rate_type, "hourly_rate": hourly_rate}
            if metric_params := metadata.get("metric_params"):
                context_params.update(metric_params)
            sql_params = param_builder.build_parameters(context_params=context_params)
            sql = pkgutil.get_data("masu.database", metadata["file_path"]).decode("utf-8")
            LOG.info(log_json(msg=metadata["log_msg"], context=sql_params))
            self._execute_trino_multipart_sql_query(sql, bind_params=sql_params)

    def populate_usage_costs(
        self, rate_type, rates, distribution, start_date, end_date, provider_uuid, report_period_id
    ):
        """Update the reporting_ocpusagelineitem_daily_summary table with usage costs."""
        table_name = self._table_map["line_item_daily_summary"]

        ctx = {
            "schema": self.schema,
            "provider_uuid": provider_uuid,
            "start_date": start_date,
            "end_date": end_date,
            "report_period": report_period_id,
        }
        if not rates:
            LOG.info(log_json(msg="removing usage costs", context=ctx))
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

        sql = pkgutil.get_data("masu.database", "sql/openshift/cost_model/usage_costs.sql")

        sql = sql.decode("utf-8")
        sql_params = {
            "start_date": start_date,
            "end_date": end_date,
            "schema": self.schema,
            "source_uuid": provider_uuid,
            "report_period_id": report_period_id,
            "rate_type": rate_type,
            "distribution": distribution,
        }
        for metric in metric_constants.COST_MODEL_USAGE_RATES:
            sql_params[metric] = rates.get(metric, 0)

        LOG.info(log_json(msg=f"populating {rate_type} usage costs", context=ctx))
        self._prepare_and_execute_raw_sql_query(table_name, sql, sql_params, operation="INSERT")

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
        # Remove monthly rates
        infrastructure_rates = filter_dictionary(infrastructure_rates, metric_constants.USAGE_METRIC_MAP.keys())
        supplementary_rates = filter_dictionary(supplementary_rates, metric_constants.USAGE_METRIC_MAP.keys())
        # define the rates so the loop can operate on both rate types
        rate_types = [
            {"rates": infrastructure_rates, "sql_file": "sql/openshift/cost_model/infrastructure_tag_rates.sql"},
            {"rates": supplementary_rates, "sql_file": "sql/openshift/cost_model/supplementary_tag_rates.sql"},
        ]
        # Cast start_date and end_date to date object, if they aren't already
        start_date = DateHelper().parse_to_date(start_date)
        end_date = DateHelper().parse_to_date(end_date)
        # updates costs from tags
        for rate_type in rate_types:
            rate = rate_type.get("rates")
            sql_file = rate_type.get("sql_file")
            for metric in rate:
                tags = rate.get(metric, {})
                usage_type = metric_constants.USAGE_METRIC_MAP.get(metric)
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
                        sql = pkgutil.get_data("masu.database", sql_file)
                        sql = sql.decode("utf-8")
                        sql_params = {
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
                        ctx = self.extract_context_from_sql_params(sql_params)
                        LOG.info(log_json(msg="running populate_tag_usage_costs SQL", context=ctx))
                        self._prepare_and_execute_raw_sql_query(table_name, sql, sql_params)

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
        # Remove monthly rates
        infrastructure_rates = filter_dictionary(infrastructure_rates, metric_constants.USAGE_METRIC_MAP.keys())
        supplementary_rates = filter_dictionary(supplementary_rates, metric_constants.USAGE_METRIC_MAP.keys())
        # define the rates so the loop can operate on both rate types
        rate_types = [
            {
                "rates": infrastructure_rates,
                "sql_file": "sql/openshift/cost_model/default_infrastructure_tag_rates.sql",
            },
            {"rates": supplementary_rates, "sql_file": "sql/openshift/cost_model/default_supplementary_tag_rates.sql"},
        ]
        # Cast start_date and end_date to date object, if they aren't already
        start_date = DateHelper().parse_to_date(start_date)
        end_date = DateHelper().parse_to_date(end_date)

        # updates costs from tags
        for rate_type in rate_types:
            rate = rate_type.get("rates")
            sql_file = rate_type.get("sql_file")
            for metric in rate:
                tags = rate.get(metric, {})
                usage_type = metric_constants.USAGE_METRIC_MAP.get(metric)
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
                    sql = pkgutil.get_data("masu.database", sql_file)
                    sql = sql.decode("utf-8")
                    sql_params = {
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
                    ctx = self.extract_context_from_sql_params(sql_params)
                    LOG.info(log_json(msg="running populate_tag_usage_default_costs SQL", context=ctx))
                    self._prepare_and_execute_raw_sql_query(table_name, sql, sql_params)

    def populate_openshift_cluster_information_tables(self, provider, cluster_id, cluster_alias, start_date, end_date):
        """Populate the cluster, node, PVC, and project tables for the cluster."""
        cluster_table = self.populate_cluster_table(provider, cluster_id, cluster_alias)

        nodes = self.get_nodes_trino(str(provider.uuid), start_date, end_date)
        pvcs = self.get_pvcs_trino(str(provider.uuid), start_date, end_date)
        projects = self.get_projects_trino(str(provider.uuid), start_date, end_date)

        self.populate_node_table(cluster_table, nodes)
        self.populate_pvc_table(cluster_table, pvcs)
        self.populate_project_table(cluster_table, projects)

    def populate_cluster_table(self, provider, cluster_id, cluster_alias):
        """Get or create an entry in the OCP cluster table."""
        LOG.info(log_json(msg="fetching entry in reporting_ocp_cluster", provider_uuid=provider.uuid))
        clusters = OCPCluster.objects.filter(provider_id=provider.uuid)
        if clusters.count() > 1:
            clusters_to_delete = clusters.exclude(cluster_alias=cluster_alias)
            LOG.info(
                log_json(
                    msg="attempting to delete duplicate entries in reporting_ocp_cluster",
                    provider_uuid=provider.uuid,
                )
            )
            clusters_to_delete.delete()
        cluster = clusters.first()
        msg = "fetched entry in reporting_ocp_cluster"
        if not cluster:
            cluster, created = OCPCluster.objects.get_or_create(
                cluster_id=cluster_id, cluster_alias=cluster_alias, provider_id=provider.uuid
            )
            msg = f"created entry in reporting_ocp_clusters: {created}"

        # if the cluster entry already exists and cluster alias does not match, update the cluster alias
        elif cluster.cluster_alias != cluster_alias:
            cluster.cluster_alias = cluster_alias
            cluster.save()
            msg = "updated cluster entry with new cluster alias in reporting_ocp_clusters"

        LOG.info(
            log_json(
                msg=msg,
                cluster_id=cluster_id,
                cluster_alias=cluster_alias,
                provider_uuid=provider.uuid,
            )
        )
        return cluster

    def populate_node_table(self, cluster_table, nodes):
        """Get or create an entry in the OCP node table."""

        LOG.info(
            log_json(
                msg="populating reporting_ocp_nodes table",
                schema=self.schema,
                cluster_id=cluster_table.cluster_id,
                cluster_alias=cluster_table.cluster_alias,
            )
        )

        for node in nodes:
            tmp_node = OCPNode.objects.filter(
                node=node[0], resource_id=node[1], node_capacity_cpu_cores=node[2], cluster=cluster_table
            ).first()
            if not tmp_node:
                OCPNode.objects.create(
                    node=node[0],
                    resource_id=node[1],
                    node_capacity_cpu_cores=node[2],
                    node_role=node[3],
                    architecture=node[4],
                    cluster=cluster_table,
                )
                continue

            if not tmp_node.node_role or not tmp_node.architecture:
                tmp_node.node_role = node[3]
                tmp_node.architecture = node[4]
                tmp_node.save(update_fields=["node_role", "architecture"])

    def populate_pvc_table(self, cluster_table, pvcs):
        """Get or create an entry in the OCP cluster table."""

        LOG.info(
            log_json(
                msg="populating reporting_ocp_pvcs table",
                schema=self.schema,
                cluster_id=cluster_table.cluster_id,
                cluster_alias=cluster_table.cluster_alias,
            )
        )

        for pvc in pvcs:
            ocppvc = OCPPVC.objects.filter(
                persistent_volume=pvc[0], persistent_volume_claim=pvc[1], cluster=cluster_table
            ).first()
            if ocppvc:
                if not ocppvc.csi_volume_handle:
                    # Update the existing record's csi_volume_handle
                    ocppvc.csi_volume_handle = pvc[2]
                    ocppvc.save(update_fields=["csi_volume_handle"])
            else:
                # If the record does not exist, try creating a new one
                try:
                    OCPPVC.objects.create(
                        persistent_volume=pvc[0],
                        persistent_volume_claim=pvc[1],
                        csi_volume_handle=pvc[2],
                        cluster=cluster_table,
                    )

                except IntegrityError as e:
                    LOG.warning(log_json(msg="IntegrityError raised when creating pvc", pvc=pvc), exc_info=e)

    def populate_project_table(self, cluster_table, projects):
        """Get or create an entry in the OCP cluster table."""

        LOG.info(
            log_json(
                msg="populating reporting_ocp_projects table",
                schema=self.schema,
                cluster_id=cluster_table.cluster_id,
                cluster_alias=cluster_table.cluster_alias,
            )
        )

        for project in projects:
            OCPProject.objects.get_or_create(project=project, cluster=cluster_table)

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
                END) as node_role,
                lower(json_extract_scalar(max(node_labels), '$.kubernetes_io_arch')) as arch
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
        context = {"schema": self.schema, "start": start_date, "end": end_date, "provider_uuid": source_uuid}
        return self._execute_trino_raw_sql_query(sql, context=context, log_ref="get_nodes_trino")

    def get_pvcs_trino(self, source_uuid, start_date, end_date):
        """Get the nodes from an OpenShift cluster."""
        if not trino_table_exists(self.schema, "openshift_storage_usage_line_items_daily"):
            return []
        sql = f"""
            SELECT distinct persistentvolume,
                persistentvolumeclaim,
                csi_volume_handle
            FROM hive.{self.schema}.openshift_storage_usage_line_items_daily as ocp
            WHERE ocp.source = '{source_uuid}'
                AND ocp.year = '{start_date.strftime("%Y")}'
                AND ocp.month = '{start_date.strftime("%m")}'
                AND ocp.interval_start >= TIMESTAMP '{start_date}'
                AND ocp.interval_start < date_add('day', 1, TIMESTAMP '{end_date}')
        """
        context = {"schema": self.schema, "start": start_date, "end": end_date, "provider_uuid": source_uuid}
        return self._execute_trino_raw_sql_query(sql, context=context, log_ref="get_pvcs_trino")

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
        context = {"schema": self.schema, "start": start_date, "end": end_date, "provider_uuid": source_uuid}
        projects = self._execute_trino_raw_sql_query(sql, context=context, log_ref="get_projects_trino")

        return [project[0] for project in projects]

    def get_cluster_for_provider(self, provider_uuid):
        """Return the cluster entry for a provider UUID."""
        return OCPCluster.objects.filter(provider_id=provider_uuid).first()

    def get_nodes_for_cluster(self, cluster_pk):
        """Get all nodes for an OCP cluster."""
        nodes = (
            OCPNode.objects.filter(cluster_id=cluster_pk).exclude(node__exact="").values_list("node", "resource_id")
        )
        nodes = [(node[0], node[1]) for node in nodes]
        return nodes

    def get_pvcs_for_cluster(self, cluster_pk):
        """Get all nodes for an OCP cluster."""
        pvcs = (
            OCPPVC.objects.filter(cluster_id=cluster_pk)
            .exclude(persistent_volume__exact="")
            .values_list("persistent_volume", "persistent_volume_claim", "csi_volume_handle")
        )
        pvcs = [(pvc[0], pvc[1], pvc[2]) for pvc in pvcs]
        return pvcs

    def get_projects_for_cluster(self, cluster_pk):
        """Get all nodes for an OCP cluster."""
        projects = OCPProject.objects.filter(cluster_id=cluster_pk).values_list("project")
        projects = [project[0] for project in projects]
        return projects

    def get_openshift_topology_for_multiple_providers(self, provider_uuids):
        """Return a dictionary with 1 or more Clusters topology."""
        topology_list = []
        for provider_uuid in provider_uuids:
            cluster_table = self.get_cluster_for_provider(provider_uuid)
            nodes_tuple = self.get_nodes_for_cluster(cluster_table.uuid)
            pvc_tuple = self.get_pvcs_for_cluster(cluster_table.uuid)
            project_tuple = self.get_projects_for_cluster(cluster_table.uuid)
            topology_list.append(
                {
                    "cluster_id": cluster_table.cluster_id,
                    "cluster_alias": cluster_table.cluster_alias,
                    "provider_uuid": provider_uuid,
                    "nodes": [node[0] for node in nodes_tuple],
                    "resource_ids": [node[1] for node in nodes_tuple],
                    "persistent_volumes": [pvc[0] for pvc in pvc_tuple],
                    "persistent_volume_claims": [pvc[1] for pvc in pvc_tuple],
                    "csi_volume_handle": [pvc[2] for pvc in pvc_tuple if pvc[2] is not None],
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
        ctx = {
            "schema": self.schema,
            "provider_uuid": provider_uuid,
            "start_date": start_date,
            "end_date": end_date,
            "table_name": table_name,
            "report_period_id": report_period_id,
        }
        LOG.info(log_json(msg="removing infrastructure raw cast from daily summary", context=ctx))
        sql = f"""
            DELETE FROM {self.schema}.reporting_ocpusagelineitem_daily_summary
            WHERE usage_start >= '{start_date}'::date
                AND usage_start <= '{end_date}'::date
                AND report_period_id = {report_period_id}
                AND infrastructure_raw_cost IS NOT NULL
                AND infrastructure_raw_cost != 0
        """

        self._prepare_and_execute_raw_sql_query(table_name, sql)

    def delete_all_except_infrastructure_raw_cost_from_daily_summary(
        self, provider_uuid, report_period_id, start_date, end_date
    ):
        table_name = OCP_REPORT_TABLE_MAP["line_item_daily_summary"]
        ctx = {
            "schema": self.schema,
            "provider_uuid": provider_uuid,
            "start_date": start_date,
            "end_date": end_date,
            "table_name": table_name,
            "report_period_id": report_period_id,
        }
        LOG.info(log_json(msg="removing all cost excluding infrastructure_raw_cost from daily summary", context=ctx))
        sql = f"""
            DELETE FROM {self.schema}.reporting_ocpusagelineitem_daily_summary
            WHERE usage_start >= '{start_date}'::date
                AND usage_start <= '{end_date}'::date
                AND report_period_id = {report_period_id}
                AND (infrastructure_raw_cost IS NULL OR infrastructure_raw_cost = 0)
        """

        self._prepare_and_execute_raw_sql_query(table_name, sql)

    def populate_ocp_on_all_project_daily_summary(self, platform, sql_params):
        LOG.info(
            log_json(
                msg=f"populating {platform.upper()} records for ocpallcostlineitem_project_daily_summary", **sql_params
            )
        )
        script_file_name = f"reporting_ocpallcostlineitem_project_daily_summary_{platform.lower()}.sql"
        script_file_path = f"{self.OCP_ON_ALL_SQL_PATH}{script_file_name}"
        self._execute_processing_script("masu.database", script_file_path, sql_params)

    def populate_ocp_on_all_daily_summary(self, platform, sql_params):
        LOG.info(
            log_json(msg=f"populating {platform.upper()} records for ocpallcostlineitem_daily_summary", **sql_params)
        )
        script_file_name = f"reporting_ocpallcostlineitem_daily_summary_{platform.lower()}.sql"
        script_file_path = f"{self.OCP_ON_ALL_SQL_PATH}{script_file_name}"
        self._execute_processing_script("masu.database", script_file_path, sql_params)

    def populate_ocp_on_all_ui_summary_tables(self, sql_params):
        for perspective in OCP_ON_ALL_PERSPECTIVES:
            LOG.info(log_json(msg=f"populating {perspective._meta.db_table}", **sql_params))
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
        context = {"schema": self.schema, "start": start_date, "end": end_date, "provider_uuid": source_uuid}
        timestamps = self._execute_trino_raw_sql_query(
            sql, context=context, log_ref="get_max_min_timestamp_from_parquet"
        )
        minim, maxim = timestamps[0]
        minim = parse(str(minim)) if minim else datetime.datetime(start_date.year, start_date.month, start_date.day)
        maxim = parse(str(maxim)) if maxim else datetime.datetime(end_date.year, end_date.month, end_date.day)
        return minim, maxim

    def populate_tag_based_costs(  # noqa: C901
        self, start_date, end_date, provider_uuid, metric_to_tag_params_map, cluster_params
    ):
        """Populate the tag based costs.

        This method populates the daily summary table with tag-based costs for
        the metrics highlighted in the metadata section.
        """
        report_period = self.report_periods_for_provider_uuid(provider_uuid, start_date)
        if not report_period or not metric_to_tag_params_map:
            return

        monthly_params = {"amortized_denominator": DateHelper().days_in_month(start_date), "cost_type": "Tag"}
        vm_table_exists = trino_table_exists(self.schema, "openshift_vm_usage_line_items")
        gpu_table_exists = trino_table_exists(self.schema, "openshift_gpu_usage_line_items_daily")
        requires_vm_table = [metric_constants.OCP_VM_CORE_HOUR, metric_constants.OCP_VM_CORE_MONTH]
        requires_gpu_table = [metric_constants.OCP_GPU_MONTH]

        metric_metadata = {
            metric_constants.OCP_VM_HOUR: {
                "log_msg": "populating hourly VM tag based costs",
                "file_path": "trino_sql/openshift/cost_model/hourly_cost_vm_tag_based.sql",
                "metric_params": {"use_fractional_hours": vm_table_exists},
            },
            metric_constants.OCP_VM_MONTH: {
                "log_msg": "populating monthly VM tag based costs",
                "file_path": "sql/openshift/cost_model/monthly_cost_virtual_machine.sql",
                "metric_params": monthly_params,
            },
            metric_constants.OCP_VM_CORE_MONTH: {
                "log_msg": "populating monthly VM Core based costs",
                "file_path": "trino_sql/openshift/cost_model/monthly_vm_core_tag_based.sql",
                "metric_params": monthly_params,
            },
            metric_constants.OCP_VM_CORE_HOUR: {
                "log_msg": "populating hourly VM Core based costs",
                "file_path": "trino_sql/openshift/cost_model/hourly_vm_core_tag_based.sql",
            },
            metric_constants.OCP_GPU_MONTH: {
                "log_msg": "populating monthly GPU tag based costs",
                "file_path": "trino_sql/openshift/cost_model/monthly_cost_gpu.sql",
                "metric_params": {**monthly_params, **cluster_params},
            },
            metric_constants.OCP_PROJECT_MONTH: {
                "log_msg": "populating monthly project tag costs",
                "file_path": "trino_sql/openshift/cost_model/monthly_project_tag_based.sql",
                "metric_params": {**monthly_params, **cluster_params},
            },
        }

        param_builder = BaseCostModelParams(
            schema_name=self.schema,
            start_date=start_date,
            end_date=end_date,
            source_uuid=provider_uuid,
            report_period_id=report_period.id,
        )

        for name, metadata in metric_metadata.items():
            if name in requires_vm_table and not vm_table_exists:
                continue

            if name in requires_gpu_table and not gpu_table_exists:
                continue

            # Check Unleash flag for GPU cost model
            if name == metric_constants.OCP_GPU_MONTH:
                if not is_feature_flag_enabled_by_account(
                    self.schema, OCP_GPU_COST_MODEL_UNLEASH_FLAG, dev_fallback=True
                ):
                    continue

            param_list = metric_to_tag_params_map.get(name)
            if not param_list:
                continue
            for tag_params in param_list:
                if metric_params := metadata.get("metric_params"):
                    context_params = tag_params | metric_params
                else:
                    context_params = tag_params.copy()
                final_sql_params = param_builder.build_parameters(context_params=context_params)
                sql = pkgutil.get_data("masu.database", metadata["file_path"]).decode("utf-8")
                LOG.info(log_json(msg=metadata["log_msg"], context=context_params))
                if "trino_sql/" in metadata["file_path"]:
                    self._execute_trino_multipart_sql_query(sql, bind_params=final_sql_params)
                else:
                    self._prepare_and_execute_raw_sql_query(
                        self._table_map["line_item_daily_summary"],
                        sql,
                        final_sql_params,
                        operation="INSERT",
                    )
