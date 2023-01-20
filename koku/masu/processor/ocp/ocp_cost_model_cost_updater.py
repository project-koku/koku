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
from masu.processor import enable_ocp_amortized_monthly_cost
from masu.processor.ocp.ocp_cloud_updater_base import OCPCloudUpdaterBase
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
        self._is_amortized = enable_ocp_amortized_monthly_cost(self._schema)
        with CostModelDBAccessor(self._schema, self._provider_uuid) as cost_model_accessor:
            self._infra_rates = cost_model_accessor.infrastructure_rates
            self._tag_infra_rates = cost_model_accessor.tag_infrastructure_rates
            self._tag_default_infra_rates = cost_model_accessor.tag_default_infrastructure_rates
            self._supplementary_rates = cost_model_accessor.supplementary_rates
            self._tag_supplementary_rates = cost_model_accessor.tag_supplementary_rates
            self._tag_default_supplementary_rates = cost_model_accessor.tag_default_supplementary_rates
            self._distribution = cost_model_accessor.distribution

    @staticmethod
    def _normalize_tier(input_tier):
        """Normalize a tier for tiered rate calculations.

        NOTE: Tiered rates are not currently supported.
        """
        # Pull out the parts for beginning, middle, and end for validation and ordering correction.
        first_tier = [t for t in input_tier if not t.get("usage", {}).get("usage_start")]
        last_tier = [t for t in input_tier if not t.get("usage", {}).get("usage_end")]
        middle_tiers = [
            t for t in input_tier if t.get("usage", {}).get("usage_start") and t.get("usage", {}).get("usage_end")
        ]

        # Ensure that there is only 1 starting tier. (i.e. 1 'usage_start': None, if provided)
        if not first_tier:
            LOG.error("Failed Tier: %s", str(input_tier))
            raise OCPCostModelCostUpdaterError("Missing first tier.")

        if len(first_tier) != 1:
            LOG.error("Failed Tier: %s", str(input_tier))
            raise OCPCostModelCostUpdaterError("Two starting tiers.")

        # Ensure that there is only 1 final tier. (i.e. 1 'usage_end': None, if provided)
        if not last_tier:
            LOG.error("Failed Tier: %s", str(input_tier))
            raise OCPCostModelCostUpdaterError("Missing last tier.")

        if len(last_tier) != 1:
            LOG.error("Failed Tier: %s", str(input_tier))
            raise OCPCostModelCostUpdaterError("Two final tiers.")

        # Remove last 'usage_end' for consistency to avoid 'usage_end: 0' situations.
        last_tier[0].pop("usage_end", None)

        # Build final tier that is sorted in asending order.
        newlist = first_tier
        newlist += sorted(middle_tiers, key=lambda k: k["usage"]["usage_end"])
        newlist += last_tier

        return newlist

    @staticmethod
    def _bucket_applied(usage, lower_limit, upper_limit):
        """Return how much usage remains after a tier.

        NOTE: Tiered rates are not currently supported.
        """
        usage_applied = 0

        if usage >= upper_limit:
            usage_applied = upper_limit
        elif usage > lower_limit:
            usage_applied = usage - lower_limit

        return usage_applied

    def _calculate_variable_charge(self, usage, rates):
        """Calculate cost based on tiers.

        NOTE: Tiered rates are not currently supported.
        """
        charge = Decimal(0)
        balance = usage
        tier = []
        if rates:
            tier = self._normalize_tier(rates.get("tiered_rates", []))

        for bucket in tier:
            usage_end = (
                Decimal(bucket.get("usage", {}).get("usage_end")) if bucket.get("usage", {}).get("usage_end") else None
            )
            usage_start = (
                Decimal(bucket.get("usage", {}).get("usage_start"))
                if bucket.get("usage", {}).get("usage_start")
                else 0
            )
            bucket_size = (usage_end - usage_start) if usage_end else None

            lower_limit = 0
            upper_limit = bucket_size
            rate = Decimal(bucket.get("value"))

            usage_applied = 0
            if upper_limit is not None:
                usage_applied = self._bucket_applied(balance, lower_limit, upper_limit)
            else:
                usage_applied = balance

            charge += usage_applied * rate
            balance -= usage_applied

        return Decimal(charge)

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

    def _build_node_tag_rate_case_statement_str(self, rate_dict, start_date, default_rate_dict={}, unallocated=False):
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
                    label_condition_list = ["pod_labels = '{", f'"{tag_key}": "{tag_value}"', "}'"]
                    label_condition = "".join(label_condition_list)
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
                    "NULL::decimal as cost_model_memory_cost",
                    "NULL::decimal as cost_model_volume_cost",
                )
            elif self._distribution == metric_constants.MEMORY_DISTRIBUTION:
                case_dict[tag_key] = (
                    "NULL::decimal as cost_model_cpu_cost",
                    "\n".join(memory_statement_list),
                    "NULL::decimal as cost_model_volume_cost",
                )
        return case_dict

    def _build_labels_case_statement_str(self, rate_dict, label_type, default_rate=None):
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

    def _build_volume_tag_rate_case_statement_str(self, rate_dict, start_date, default_rate_dict={}):
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
                "NULL as cost_model_cpu_cost",
                "NULL as cost_model_memory_cost",
                "\n".join(volume_statement_list),
            )
        return case_dict

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

                    if self._is_amortized:
                        if rate:
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
                    else:
                        report_accessor.populate_monthly_cost(
                            cost_type,
                            rate_type,
                            rate,
                            start_date,
                            end_date,
                            self._cluster_id,
                            self._cluster_alias,
                            self._distribution,
                            self._provider_uuid,
                        )

        except OCPCostModelCostUpdaterError as error:
            LOG.error("Unable to update monthly costs. Error: %s", str(error))

    def _update_monthly_tag_based_cost(self, start_date, end_date):
        """Update the monthly cost for a period of time based on tag rates."""
        try:
            with OCPReportDBAccessor(self._schema) as report_accessor:
                for cost_type, rate_term in OCPUsageLineItemDailySummary.MONTHLY_COST_RATE_MAP.items():
                    for rate_type in [
                        metric_constants.INFRASTRUCTURE_COST_TYPE,
                        metric_constants.SUPPLEMENTARY_COST_TYPE,
                    ]:
                        if rate_type == metric_constants.INFRASTRUCTURE_COST_TYPE:
                            if not self._tag_infra_rates.get(rate_term, {}):
                                continue
                            rate_dict = self._tag_infra_rates.get(rate_term)
                        else:
                            if not self._tag_supplementary_rates.get(rate_term, {}):
                                continue
                            rate_dict = self._tag_supplementary_rates.get(rate_term)

                        log_msg = "Updating"
                        if rate_dict is None:
                            log_msg = "Removing"

                        LOG.info(
                            log_msg + " tag based monthly %s cost for"
                            "\n\tSchema: %s \n\t%s Provider: %s (%s) \n\tDates: %s - %s",
                            cost_type,
                            self._schema,
                            self._provider.type,
                            self._provider.name,
                            self._provider_uuid,
                            start_date,
                            end_date,
                        )

                        report_accessor.populate_monthly_tag_cost(
                            cost_type,
                            rate_type,
                            rate_dict,
                            start_date,
                            end_date,
                            self._cluster_id,
                            self._cluster_alias,
                            self._distribution,
                            self._provider_uuid,
                        )

        except OCPCostModelCostUpdaterError as error:
            LOG.error("Unable to update monthly costs. Error: %s", str(error))

    def _update_monthly_tag_based_cost_amortized(self, start_date, end_date):  # noqa: C901
        """Update the monthly cost for a period of time based on tag rates."""
        try:
            with OCPReportDBAccessor(self._schema) as report_accessor:
                for cost_type, rate_term in OCPUsageLineItemDailySummary.MONTHLY_COST_RATE_MAP.items():
                    for rate_type in [
                        metric_constants.INFRASTRUCTURE_COST_TYPE,
                        metric_constants.SUPPLEMENTARY_COST_TYPE,
                    ]:
                        if rate_type == metric_constants.INFRASTRUCTURE_COST_TYPE:
                            if not self._tag_infra_rates.get(rate_term, {}):
                                continue
                            rate_dict = self._tag_infra_rates.get(rate_term)
                            default_rate_dict = None
                            if self._tag_default_infra_rates.get(rate_term):
                                default_rate_dict = self._tag_default_infra_rates.get(rate_term)
                        else:
                            if not self._tag_supplementary_rates.get(rate_term, {}):
                                continue
                            rate_dict = self._tag_supplementary_rates.get(rate_term)
                            default_rate_dict = None
                            if self._tag_default_supplementary_rates.get(rate_term):
                                default_rate_dict = self._tag_default_supplementary_rates.get(rate_term)

                        LOG.info(
                            "Updating tag based monthly %s cost for"
                            "\n\tSchema: %s \n\t%s Provider: %s (%s) \n\tDates: %s - %s",
                            cost_type,
                            self._schema,
                            self._provider.type,
                            self._provider.name,
                            self._provider_uuid,
                            start_date,
                            end_date,
                        )

                        if cost_type == "Node":
                            key_rate_dict = self._build_node_tag_rate_case_statement_str(
                                rate_dict, start_date, default_rate_dict
                            )
                            unallocated_key_rate_dict = self._build_node_tag_rate_case_statement_str(
                                rate_dict, start_date, default_rate_dict, unallocated=True
                            )
                            labels = self._build_labels_case_statement_str(
                                rate_dict, "pod_labels", default_rate=default_rate_dict
                            )
                        elif cost_type == "PVC":
                            key_rate_dict = self._build_volume_tag_rate_case_statement_str(
                                rate_dict, start_date, default_rate_dict
                            )
                            labels = self._build_labels_case_statement_str(
                                rate_dict, "volume_labels", default_rate=default_rate_dict
                            )

                        for tag_key, case_statements in key_rate_dict.items():
                            unallocated_case_statements = unallocated_key_rate_dict.get(tag_key, {})
                            label_case_statements = labels.get(tag_key)
                            case_dict = {
                                "allocated": case_statements,
                                "unallocated": unallocated_case_statements,
                                "labels": label_case_statements,
                            }
                            report_accessor.populate_monthly_tag_cost_sql(
                                cost_type,
                                rate_type,
                                tag_key,
                                case_dict,
                                start_date,
                                end_date,
                                self._distribution,
                                self._provider_uuid,
                            )

        except OCPCostModelCostUpdaterError as error:
            LOG.error("Unable to update monthly costs. Error: %s", str(error))

    def _update_monthly_tag_based_default_cost(self, start_date, end_date):
        """Update the monthly cost for a period of time based on tag rates."""
        try:
            with OCPReportDBAccessor(self._schema) as report_accessor:
                for cost_type, rate_term in OCPUsageLineItemDailySummary.MONTHLY_COST_RATE_MAP.items():
                    for rate_type in [
                        metric_constants.INFRASTRUCTURE_COST_TYPE,
                        metric_constants.SUPPLEMENTARY_COST_TYPE,
                    ]:
                        if rate_type == metric_constants.INFRASTRUCTURE_COST_TYPE:
                            if not self._tag_default_infra_rates.get(rate_term, {}):
                                continue
                            rate = self._tag_default_infra_rates.get(rate_term)
                        else:
                            if not self._tag_default_supplementary_rates.get(rate_term, {}):
                                continue
                            rate = self._tag_default_supplementary_rates.get(rate_term)

                        log_msg = "Updating"
                        if rate is None:
                            log_msg = "Removing"

                        LOG.info(
                            log_msg + " tag based monthly %s cost for"
                            "\n\tSchema: %s \n\t%s Provider: %s (%s) \n\tDates: %s - %s",
                            cost_type,
                            self._schema,
                            self._provider.type,
                            self._provider.name,
                            self._provider_uuid,
                            start_date,
                            end_date,
                        )

                        report_accessor.populate_monthly_tag_default_cost(
                            cost_type,
                            rate_type,
                            rate,
                            start_date,
                            end_date,
                            self._cluster_id,
                            self._cluster_alias,
                            self._distribution,
                            self._provider_uuid,
                        )

        except OCPCostModelCostUpdaterError as error:
            LOG.error("Unable to update monthly costs. Error: %s", str(error))

    def _update_usage_costs(self, start_date, end_date):
        """Update infrastructure and supplementary usage costs."""
        with OCPReportDBAccessor(self._schema) as report_accessor:
            if self._is_amortized:
                report_accessor.populate_usage_costs_new_columns(
                    metric_constants.INFRASTRUCTURE_COST_TYPE,
                    self._infra_rates,
                    start_date,
                    end_date,
                    self._cluster_id,
                    self._provider.uuid,
                )
                report_accessor.populate_usage_costs_new_columns(
                    metric_constants.SUPPLEMENTARY_COST_TYPE,
                    self._supplementary_rates,
                    start_date,
                    end_date,
                    self._cluster_id,
                    self._provider.uuid,
                )
            else:
                report_accessor.populate_usage_costs(
                    self._infra_rates, self._supplementary_rates, start_date, end_date, self._cluster_id
                )

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
            if self._is_amortized:
                self._update_monthly_tag_based_cost_amortized(start_date, end_date)
            else:
                self._update_monthly_tag_based_cost(start_date, end_date)
                self._update_monthly_tag_based_default_cost(start_date, end_date)

        with OCPReportDBAccessor(self._schema) as accessor:
            accessor.populate_ui_summary_tables(start_date, end_date, self._provider.uuid)
            report_period = accessor.report_periods_for_provider_uuid(self._provider_uuid, start_date)
            if report_period:
                with schema_context(self._schema):
                    report_period.derived_cost_datetime = DateAccessor().today_with_timezone("UTC")
                    report_period.save()
