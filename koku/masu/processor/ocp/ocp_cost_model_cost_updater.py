#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Updates report summary tables in the database with charge information."""
import logging
from decimal import Decimal

from dateutil.parser import parse
from tenant_schemas.utils import schema_context

from api.metrics import constants as metric_constants
from masu.database.cost_model_db_accessor import CostModelDBAccessor
from masu.database.ocp_report_db_accessor import OCPReportDBAccessor
from masu.external.date_accessor import DateAccessor
from masu.processor.ocp.ocp_cloud_updater_base import OCPCloudUpdaterBase
from masu.util.common import filter_dictionary
from masu.util.ocp.common import get_amortized_monthly_cost_model_rate
from masu.util.ocp.common import get_cluster_alias_from_cluster_id
from masu.util.ocp.common import get_cluster_id_from_provider
from reporting.provider.ocp.models import OCPUsageLineItemDailySummary

LOG = logging.getLogger(__name__)


class OCPCostModelCostUpdaterError(Exception):
    """OCPCostModelCostUpdater error."""


class OCPCostModelCostUpdater(OCPCloudUpdaterBase):
    """Class to update OCP report summary data with charge information."""

    def __init__(self, schema, provider):
        """Establish the database connection.

        Args:
            schema (str): The customer schema to associate with

        """
        super().__init__(schema, provider, None)
        self._cluster_id = get_cluster_id_from_provider(self._provider_uuid)
        self._cluster_alias = get_cluster_alias_from_cluster_id(self._cluster_id)
        with CostModelDBAccessor(self._schema, self._provider_uuid) as cost_model_accessor:
            self._infra_rates = cost_model_accessor.infrastructure_rates
            self._tag_infra_rates = cost_model_accessor.tag_infrastructure_rates
            self._tag_default_infra_rates = cost_model_accessor.tag_default_infrastructure_rates
            self._supplementary_rates = cost_model_accessor.supplementary_rates
            self._tag_supplementary_rates = cost_model_accessor.tag_supplementary_rates
            self._tag_default_supplementary_rates = cost_model_accessor.tag_default_supplementary_rates
            self._distribution = cost_model_accessor.distribution

    def _build_node_tag_cost_case_statements(self, rate_dict, start_date, default_rate_dict={}, unallocated=False):
        """Given a tag key, value, and rate return a CASE SQL statement for tag based monthly SQL."""
        case_dict = {}
        cpu_distribution_term = """
            sum(pod_effective_usage_cpu_core_hours)
                / max(node_capacity_cpu_core_hours)
        """
        memory_distribution_term = """
            sum(pod_effective_usage_memory_gigabyte_hours)
                / max(node_capacity_memory_gigabyte_hours)
        """

        if unallocated is True:
            cpu_distribution_term = """
                (max(node_capacity_cpu_core_hours) - sum(pod_effective_usage_cpu_core_hours))
                    / max(node_capacity_cpu_core_hours)
            """
            memory_distribution_term = """
                (max(node_capacity_memory_gigabyte_hours) - sum(pod_effective_usage_memory_gigabyte_hours))
                    / max(node_capacity_memory_gigabyte_hours)
            """

        for tag_key, tag_value_rates in rate_dict.items():
            cpu_statement_list = ["CASE"]
            memory_statement_list = ["CASE"]
            for tag_value, rate_value in tag_value_rates.items():
                label_condition = f"pod_labels->>'{tag_key}'='{tag_value}'"
                if unallocated is True:
                    label_condition = f'pod_labels = \'{{"{tag_key}": "{tag_value}"}}\''
                rate = get_amortized_monthly_cost_model_rate(rate_value, start_date)
                cpu_statement_list.append(
                    f"""
                        WHEN {label_condition}
                            THEN {cpu_distribution_term}
                                * {rate}::decimal
                    """
                )
                memory_statement_list.append(
                    f"""
                        WHEN {label_condition}
                            THEN {memory_distribution_term}
                                * {rate}::decimal
                    """
                )
            if default_rate_dict:
                rate_value = default_rate_dict.get(tag_key, {}).get("default_value", 0)
                rate = get_amortized_monthly_cost_model_rate(rate_value, start_date)
                # The SQL file already filters results that have the tag key
                cpu_statement_list.append(
                    f"""
                        ELSE {cpu_distribution_term}
                            * {rate}::decimal
                    """
                )
                memory_statement_list.append(
                    f"""
                        ELSE {memory_distribution_term}
                            * {rate}::decimal
                    """
                )
            cpu_statement_list.append("END as cost_model_cpu_cost")
            memory_statement_list.append("END as cost_model_memory_cost")
            if self._distribution == metric_constants.CPU_DISTRIBUTION:
                case_dict[tag_key] = (
                    "\n".join(cpu_statement_list),
                    "0::decimal as cost_model_memory_cost",
                    "0::decimal as cost_model_volume_cost",
                )
            elif self._distribution == metric_constants.MEMORY_DISTRIBUTION:
                case_dict[tag_key] = (
                    "0::decimal as cost_model_cpu_cost",
                    "\n".join(memory_statement_list),
                    "0::decimal as cost_model_volume_cost",
                )
        return case_dict

    def _build_labels_case_statement(self, rate_dict, label_type, default_rate=None):
        """Build a CASE statement to set pod or volume labels for tag base monthly SQL."""
        case_dict = {}
        for tag_key, tag_value_rates in rate_dict.items():
            statement_list = ["CASE"]
            for tag_value in tag_value_rates:
                statement_list.append(
                    f"""
                        WHEN {label_type}->>'{tag_key}'='{tag_value}'
                            THEN '{{"{tag_key}": "{tag_value}"}}'
                    """
                )
            if default_rate:
                statement_list.append(
                    f"""
                    ELSE '{{"{tag_key}": "' || cast({label_type}->>'{tag_key}' as text) || '"}}'
                    """
                )
            statement_list.append(f"END as {label_type}")
            case_dict[tag_key] = "\n".join(statement_list)
        return case_dict

    def _build_volume_tag_cost_case_statements(self, rate_dict, start_date, default_rate_dict={}):
        """Given a tag key, value, and rate return a CASE SQL statement."""
        case_dict = {}
        for tag_key, tag_value_rates in rate_dict.items():
            volume_statement_list = ["CASE"]
            for tag_value, rate_value in tag_value_rates.items():
                rate = get_amortized_monthly_cost_model_rate(rate_value, start_date)
                volume_statement_list.append(
                    f"""
                        WHEN volume_labels->>'{tag_key}'='{tag_value}'
                            THEN {rate}::decimal / vc.pvc_count
                    """
                )
            if default_rate_dict:
                rate_value = default_rate_dict.get(tag_key, {}).get("default_value", 0)
                rate = get_amortized_monthly_cost_model_rate(rate_value, start_date)
                volume_statement_list.append(f"ELSE {rate}::decimal / vc.pvc_count")
            volume_statement_list.append("END as cost_model_volume_cost")
            case_dict[tag_key] = (
                "0::decimal as cost_model_cpu_cost",
                "0::decimal as cost_model_memory_cost",
                "\n".join(volume_statement_list),
            )
        return case_dict

    def _get_all_monthly_tag_based_case_statements(self, openshift_resource_type, rates, default_rates, start_date):
        """Call and organize cost, unallocated, and label case statements."""
        cost_case_statements = {}
        combined_case_statements = {}
        if openshift_resource_type == "Node":
            cost_case_statements = self._build_node_tag_cost_case_statements(rates, start_date, default_rates)
            unallocated_cost_case_statements = self._build_node_tag_cost_case_statements(
                rates, start_date, default_rates, unallocated=True
            )
            labels_case_statement = self._build_labels_case_statement(rates, "pod_labels", default_rate=default_rates)
        elif openshift_resource_type == "PVC":
            cost_case_statements = self._build_volume_tag_cost_case_statements(rates, start_date, default_rates)
            # No unallocated cost for volumes
            unallocated_cost_case_statements = {}
            labels_case_statement = self._build_labels_case_statement(
                rates, "volume_labels", default_rate=default_rates
            )

        for tag_key in cost_case_statements:
            combined_case_statements[tag_key] = {
                "cost": cost_case_statements.get(tag_key, {}),
                "unallocated": unallocated_cost_case_statements.get(tag_key, {}),
                "labels": labels_case_statement.get(tag_key, {}),
            }
        return combined_case_statements

    def _update_monthly_cost(self, start_date, end_date):
        """Update the monthly cost for a period of time."""
        try:
            with OCPReportDBAccessor(self._schema) as report_accessor:
                # Ex. cost_type == "Node", rate_term == "node_cost_per_month", rate == 1000
                for cost_type, rate_term in OCPUsageLineItemDailySummary.MONTHLY_COST_RATE_MAP.items():
                    rate_type = None
                    rate = None
                    if self._infra_rates.get(rate_term):
                        rate_type = metric_constants.INFRASTRUCTURE_COST_TYPE
                        rate = self._infra_rates.get(rate_term)
                    elif self._supplementary_rates.get(rate_term):
                        rate_type = metric_constants.SUPPLEMENTARY_COST_TYPE
                        rate = self._supplementary_rates.get(rate_term)

                    log_msg = "Updating"
                    if rate is None:
                        log_msg = "Removing"

                    LOG.info(
                        log_msg + " monthly %s cost for" "\n\tSchema: %s \n\t%s Provider: %s (%s) \n\tDates: %s - %s",
                        cost_type,
                        self._schema,
                        self._provider.type,
                        self._provider.name,
                        self._provider_uuid,
                        start_date,
                        end_date,
                    )

                    amortized_rate = get_amortized_monthly_cost_model_rate(rate, start_date)
                    report_accessor.populate_monthly_cost_sql(
                        cost_type,
                        rate_type,
                        amortized_rate,
                        start_date,
                        end_date,
                        self._distribution,
                        self._provider_uuid,
                    )
        except OCPCostModelCostUpdaterError as error:
            LOG.error("Unable to update monthly costs. Error: %s", str(error))

    def _update_monthly_tag_based_cost(self, start_date, end_date):  # noqa: C901
        """Update the monthly cost for a period of time based on tag rates."""
        try:
            with OCPReportDBAccessor(self._schema) as report_accessor:
                for (
                    openshift_resource_type,
                    monthly_cost_metric,
                ) in OCPUsageLineItemDailySummary.MONTHLY_COST_RATE_MAP.items():
                    # openshift_resource_type i.e. Cluster, Node, PVC
                    # monthly_cost_metric i.e. node_cost_per_month, cluster_cost_per_month, pvc_cost_per_month
                    if monthly_cost_metric == metric_constants.OCP_CLUSTER_MONTH:
                        # Cluster monthly rates do not support tag based rating
                        continue

                    for cost_model_cost_type in (
                        metric_constants.INFRASTRUCTURE_COST_TYPE,
                        metric_constants.SUPPLEMENTARY_COST_TYPE,
                    ):
                        if cost_model_cost_type == metric_constants.INFRASTRUCTURE_COST_TYPE:
                            rates = self._tag_infra_rates.get(monthly_cost_metric, {})
                            default_rates = self._tag_default_infra_rates.get(monthly_cost_metric, {})
                        elif cost_model_cost_type == metric_constants.SUPPLEMENTARY_COST_TYPE:
                            rates = self._tag_supplementary_rates.get(monthly_cost_metric, {})
                            default_rates = self._tag_default_supplementary_rates.get(monthly_cost_metric, {})

                        if not rates:
                            # The cost model has no rates for this metric
                            continue

                        LOG.info(
                            "Updating tag based monthly %s cost for"
                            "\n\tSchema: %s \n\t%s Provider: %s (%s) \n\tDates: %s - %s",
                            openshift_resource_type,
                            self._schema,
                            self._provider.type,
                            self._provider.name,
                            self._provider_uuid,
                            start_date,
                            end_date,
                        )

                        per_tag_key_case_statements = self._get_all_monthly_tag_based_case_statements(
                            openshift_resource_type, rates, default_rates, start_date
                        )

                        for tag_key, case_statements in per_tag_key_case_statements.items():
                            report_accessor.populate_monthly_tag_cost_sql(
                                openshift_resource_type,
                                cost_model_cost_type,
                                tag_key,
                                case_statements,
                                start_date,
                                end_date,
                                self._distribution,
                                self._provider_uuid,
                            )

        except OCPCostModelCostUpdaterError as error:
            LOG.error("Unable to update monthly costs. Error: %s", str(error))

    def _update_usage_costs(self, start_date, end_date):
        """Update infrastructure and supplementary usage costs."""
        with OCPReportDBAccessor(self._schema) as report_accessor:
            report_accessor.populate_usage_costs(
                metric_constants.INFRASTRUCTURE_COST_TYPE,
                filter_dictionary(self._infra_rates, metric_constants.COST_MODEL_USAGE_RATES),
                start_date,
                end_date,
                self._provider.uuid,
            )
            report_accessor.populate_usage_costs(
                metric_constants.SUPPLEMENTARY_COST_TYPE,
                filter_dictionary(self._supplementary_rates, metric_constants.COST_MODEL_USAGE_RATES),
                start_date,
                end_date,
                self._provider.uuid,
            )

    def _update_markup_cost(self, start_date, end_date):
        """Populate markup costs for OpenShift.

        Args:
            start_date (str) The date to start populating the table.
            end_date   (str) The date to end on.

        Returns
            None

        """
        with CostModelDBAccessor(self._schema, self._provider_uuid) as cost_model_accessor:
            markup = cost_model_accessor.markup
            markup = Decimal(markup.get("value", 0)) / 100
        with OCPReportDBAccessor(self._schema) as accessor:
            LOG.info(
                "Updating markup for" "\n\tSchema: %s \n\t%s Provider: %s (%s) \n\tDates: %s - %s",
                self._schema,
                self._provider.type,
                self._provider.name,
                self._provider_uuid,
                start_date,
                end_date,
            )
            accessor.populate_markup_cost(markup, start_date, end_date, self._cluster_id)
        LOG.info("Finished updating markup.")

    def _update_tag_usage_costs(self, start_date, end_date):
        """Update infrastructure and supplementary tag based usage costs."""
        with OCPReportDBAccessor(self._schema) as report_accessor:
            report_accessor.populate_tag_usage_costs(
                self._tag_infra_rates, self._tag_supplementary_rates, start_date, end_date, self._cluster_id
            )

    def _update_tag_usage_default_costs(self, start_date, end_date):
        """Update infrastructure and supplementary tag based usage costs based on default values."""
        with OCPReportDBAccessor(self._schema) as report_accessor:
            report_accessor.populate_tag_usage_default_costs(
                self._tag_default_infra_rates,
                self._tag_default_supplementary_rates,
                start_date,
                end_date,
                self._cluster_id,
            )

    def _delete_tag_usage_costs(self, start_date, end_date, source_uuid):
        """Delete existing tag based rated entries"""
        # Delete existing records
        with OCPReportDBAccessor(self._schema) as report_accessor:
            with schema_context(self._schema):
                report_period = report_accessor.report_periods_for_provider_uuid(self._provider.uuid, start_date)
                if not report_period:
                    LOG.warning(f"No report period for {self._provider.uuid} with start date {start_date}")
                    return
                report_period_id = report_period.id
            report_accessor.delete_line_item_daily_summary_entries_for_date_range_raw(
                source_uuid,
                start_date,
                end_date,
                table=OCPUsageLineItemDailySummary,
                filters={"monthly_cost_type": "Tag", "report_period_id": report_period_id},
            )

    def update_summary_cost_model_costs(self, start_date, end_date):
        """Update the OCP summary table with the charge information.

        Args:
            start_date (str, Optional) - Start date of range to update derived cost.
            end_date (str, Optional) - End date of range to update derived cost.

        Returns
            None

        """
        if isinstance(start_date, str):
            start_date = parse(start_date)
        if isinstance(end_date, str):
            end_date = parse(end_date)

        LOG.info(
            "Updating cost model costs for \n%s provider: %s (%s). \nCluster ID: %s.",
            self._provider.type,
            self._provider.name,
            self._provider_uuid,
            self._cluster_id,
        )
        self._update_usage_costs(start_date, end_date)
        self._update_markup_cost(start_date, end_date)
        self._update_monthly_cost(start_date, end_date)
        # only update based on tag rates if there are tag rates
        # this also lets costs get removed if there is no tiered rate and then add to them if there is a tag_rate
        if self._tag_infra_rates != {} or self._tag_supplementary_rates != {}:
            self._delete_tag_usage_costs(start_date, end_date, self._provider.uuid)
            self._update_tag_usage_costs(start_date, end_date)
            self._update_tag_usage_default_costs(start_date, end_date)
            self._update_monthly_tag_based_cost(start_date, end_date)
        if not (self._tag_infra_rates or self._tag_supplementary_rates):
            self._delete_tag_usage_costs(start_date, end_date, self._provider.uuid)

        with OCPReportDBAccessor(self._schema) as accessor:
            accessor.populate_ui_summary_tables(start_date, end_date, self._provider.uuid)
            report_period = accessor.report_periods_for_provider_uuid(self._provider_uuid, start_date)
            if report_period:
                with schema_context(self._schema):
                    report_period.derived_cost_datetime = DateAccessor().today_with_timezone("UTC")
                    report_period.save()
