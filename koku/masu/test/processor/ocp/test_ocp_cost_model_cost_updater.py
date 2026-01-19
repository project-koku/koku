#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the OCPReportDBAccessor utility object."""
import random
from decimal import Decimal
from unittest import skip
from unittest.mock import patch

from dateutil.relativedelta import relativedelta
from django.db.models import Sum
from django_tenants.utils import schema_context

from api.metrics import constants as metric_constants
from api.utils import DateHelper
from masu.database import OCP_REPORT_TABLE_MAP
from masu.database.ocp_report_db_accessor import OCPReportDBAccessor
from masu.processor.ocp.ocp_cost_model_cost_updater import OCPCostModelCostUpdater
from masu.test import MasuTestCase
from masu.util.common import SummaryRangeConfig
from masu.util.ocp.common import get_amortized_monthly_cost_model_rate
from reporting.models import OCPUsageLineItemDailySummary
from reporting.provider.ocp.models import OCPUsageReportPeriod


class OCPCostModelCostUpdaterTest(MasuTestCase):
    """Test Cases for the OCPCostModelCostUpdater object."""

    @classmethod
    def setUpClass(cls):
        """Set up the test class with required objects."""
        super().setUpClass()
        cls.accessor = OCPReportDBAccessor(schema=cls.schema)
        cls.all_tables = list(OCP_REPORT_TABLE_MAP.values())
        cls.dh = DateHelper()

    def setUp(self):
        """Set up a test with database objects."""
        super().setUp()
        self.provider = self.ocp_provider
        self.cluster_id = self.ocp_cluster_id
        self.provider_uuid = self.ocp_provider_uuid
        self.updater = OCPCostModelCostUpdater(schema=self.schema, provider=self.provider)
        self.distribution_info = {"distribution_type": "cpu", "platform_cost": False, "worker_cost": False}

    @patch("masu.processor.ocp.ocp_cost_model_cost_updater.CostModelDBAccessor")
    def test_update_markup_cost(self, mock_cost_accessor):
        """Test that markup is calculated."""
        markup = {"value": 10, "unit": "percent"}
        markup_dec = Decimal(markup.get("value") / 100)
        dec_zero = Decimal("0")

        mock_cost_accessor.return_value.__enter__.return_value.markup = markup

        start_date = self.dh.this_month_start
        end_date = self.dh.this_month_end

        updater = OCPCostModelCostUpdater(schema=self.schema, provider=self.provider)
        updater._update_markup_cost(start_date, end_date)

        with schema_context(self.schema):
            line_items = OCPUsageLineItemDailySummary.objects.filter(
                usage_start__gte=start_date, usage_start__lte=end_date, cluster_id=self.cluster_id
            ).all()
            for line_item in line_items:
                if line_item.infrastructure_raw_cost is not None:
                    li_infra_raw_cost = line_item.infrastructure_raw_cost
                else:
                    li_infra_raw_cost = dec_zero
                # If raw cost is zero, then markup will also be zero
                if li_infra_raw_cost != dec_zero:
                    self.assertNotEqual(line_item.infrastructure_markup_cost, dec_zero)
                    self.assertAlmostEqual(
                        line_item.infrastructure_markup_cost, line_item.infrastructure_raw_cost * markup_dec, 6
                    )
                if line_item.infrastructure_project_raw_cost is not None:
                    li_infra_proj_cost = line_item.infrastructure_project_raw_cost
                else:
                    li_infra_proj_cost = dec_zero
                # If raw cost is zero, then markup will also be zero
                if li_infra_proj_cost != dec_zero:
                    self.assertNotEqual(line_item.infrastructure_project_markup_cost, dec_zero)
                    self.assertAlmostEqual(
                        line_item.infrastructure_project_markup_cost,
                        line_item.infrastructure_project_raw_cost * markup_dec,
                        6,
                    )

    @patch("masu.database.ocp_report_db_accessor.OCPReportDBAccessor.populate_markup_cost")
    @patch("masu.processor.ocp.ocp_cost_model_cost_updater.CostModelDBAccessor")
    def test_update_markup_cost_no_markup(self, mock_cost_accessor, mock_markup):
        """Test that markup is calculated."""
        markup = {}

        mock_cost_accessor.return_value.__enter__.return_value.markup = markup

        start_date = self.dh.this_month_start
        end_date = self.dh.this_month_end

        updater = OCPCostModelCostUpdater(schema=self.schema, provider=self.provider)
        updater._update_markup_cost(start_date, end_date)

        mock_markup.assert_not_called()

    @patch("masu.processor.ocp.ocp_cost_model_cost_updater.CostModelDBAccessor")
    @patch("masu.database.ocp_report_db_accessor.trino_table_exists", return_value=False)
    def test_update_usage_costs_no_report_period(self, mock_trino_exists, mock_cost_accessor):
        """Test that usage costs are updated for infrastructure and supplementary."""
        updater = OCPCostModelCostUpdater(schema=self.schema, provider=self.provider)
        result = updater._update_usage_costs(self.dh.parse_to_date("1993-10-01"), self.dh.parse_to_date("1993-10-02"))
        self.assertFalse(result)

    @patch("masu.processor.ocp.ocp_cost_model_cost_updater.CostModelDBAccessor")
    @patch("masu.database.ocp_report_db_accessor.trino_table_exists", return_value=False)
    def test_update_usage_costs(self, mock_trino_exists, mock_cost_accessor):
        """Test that usage costs are updated for infrastructure and supplementary."""
        infrastructure_rates = {
            "cpu_core_usage_per_hour": 0.0070000000,
            "cpu_core_request_per_hour": 0.2000000000,
            "memory_gb_usage_per_hour": 0.0090000000,
            "memory_gb_request_per_hour": 0.0500000000,
        }
        supplementary_rates = {
            "storage_gb_usage_per_month": 0.0100000000,
            "storage_gb_request_per_month": 0.0100000000,
        }

        mock_cost_accessor.return_value.__enter__.return_value.infrastructure_rates = infrastructure_rates
        mock_cost_accessor.return_value.__enter__.return_value.supplementary_rates = supplementary_rates
        mock_cost_accessor.return_value.__enter__.return_value.distribution_info = {}

        start_date = self.dh.this_month_start
        end_date = self.dh.this_month_end

        updater = OCPCostModelCostUpdater(schema=self.schema, provider=self.provider)
        updater._update_usage_costs(start_date, end_date)

        with schema_context(self.schema):
            pod_line_items = OCPUsageLineItemDailySummary.objects.filter(
                usage_start__gte=start_date,
                data_source="Pod",
                cluster_id=self.cluster_id,
                cost_model_rate_type="Infrastructure",
                monthly_cost_type__isnull=True,
                distributed_cost__gt=0,
            ).all()
            for line_item in pod_line_items:
                self.assertNotEqual(line_item.cost_model_cpu_cost, 0)
                self.assertNotEqual(line_item.cost_model_memory_cost, 0)
                self.assertEqual(line_item.cost_model_volume_cost, 0)

            volume_line_items = OCPUsageLineItemDailySummary.objects.filter(
                usage_start__gte=start_date,
                data_source="Storage",
                cluster_id=self.cluster_id,
                cost_model_rate_type="Supplementary",
                monthly_cost_type__isnull=True,
            ).all()

            for line_item in volume_line_items:
                self.assertEqual(line_item.cost_model_cpu_cost, 0)
                self.assertEqual(line_item.cost_model_memory_cost, 0)
                self.assertNotEqual(line_item.cost_model_volume_cost, 0)

    @patch("masu.database.ocp_report_db_accessor.trino_table_exists", return_value=False)
    @patch("masu.processor.ocp.ocp_cost_model_cost_updater.CostModelDBAccessor")
    def test_update_monthly_cost_infrastructure(self, mock_cost_accessor, _):
        """Test OCP charge for monthly costs is updated."""
        node_cost = random.randrange(1, 200)
        infrastructure_rates = {"node_cost_per_month": node_cost}
        mock_cost_accessor.return_value.__enter__.return_value.infrastructure_rates = infrastructure_rates
        mock_cost_accessor.return_value.__enter__.return_value.supplementary_rates = {}
        mock_cost_accessor.return_value.__enter__.return_value.distribution_info = self.distribution_info
        with schema_context(self.schema):
            usage_period = (
                OCPUsageReportPeriod.objects.filter(provider_id=self.provider_uuid)
                .order_by("-report_period_start")
                .first()
            )

        start_date = usage_period.report_period_start.date()
        end_date = usage_period.report_period_end.date() - relativedelta(days=1)
        updater = OCPCostModelCostUpdater(schema=self.schema, provider=self.provider)
        updater._update_monthly_cost(start_date, end_date)
        with schema_context(self.schema):
            monthly_costs = (
                OCPUsageLineItemDailySummary.objects.filter(
                    cost_model_rate_type="Infrastructure",
                    monthly_cost_type="Node",
                    cluster_id=self.cluster_id,
                    usage_start=start_date,
                )
                .values("node")
                .annotate(
                    **{
                        "cpu_cost": Sum("cost_model_cpu_cost"),
                        "memory_cost": Sum("cost_model_memory_cost"),
                        "volume_cost": Sum("cost_model_volume_cost"),
                    }
                )
            )

            for row in monthly_costs:
                self.assertNotEqual(row.get("cpu_cost"), 0)
                self.assertEqual(row.get("memory_cost"), 0)
                self.assertEqual(row.get("volume_cost"), 0)

    @patch("masu.database.ocp_report_db_accessor.trino_table_exists", return_value=True)
    @patch("masu.database.ocp_report_db_accessor.OCPReportDBAccessor._execute_trino_multipart_sql_query")
    @patch("masu.processor.ocp.ocp_cost_model_cost_updater.CostModelDBAccessor")
    def test_update_monthly_cost_infrastructure_trino_connector(self, mock_cost_accessor, mock_db_accessor, _):
        """Test OCP charge for monthly costs is updated thru trino connector."""
        node_cost = random.randrange(1, 200)
        infrastructure_rates = {"vm_core_cost_per_month": node_cost}
        mock_cost_accessor.return_value.__enter__.return_value.infrastructure_rates = infrastructure_rates
        mock_cost_accessor.return_value.__enter__.return_value.supplementary_rates = {}
        mock_cost_accessor.return_value.__enter__.return_value.distribution_info = self.distribution_info
        with schema_context(self.schema):
            usage_period = (
                OCPUsageReportPeriod.objects.filter(provider_id=self.provider_uuid)
                .order_by("-report_period_start")
                .first()
            )

        start_date = usage_period.report_period_start.date()
        end_date = usage_period.report_period_end.date() - relativedelta(days=1)
        updater = OCPCostModelCostUpdater(schema=self.schema, provider=self.provider)
        updater._update_monthly_cost(start_date, end_date)
        mock_db_accessor.assert_called_once()

    @patch("masu.database.ocp_report_db_accessor.trino_table_exists", return_value=False)
    @patch("masu.processor.ocp.ocp_cost_model_cost_updater.CostModelDBAccessor")
    def test_update_monthly_cost_supplementary(self, mock_cost_accessor, _):
        """Test OCP charge for monthly costs is updated."""
        node_cost = random.randrange(1, 200)
        supplementary_rates = {"node_cost_per_month": node_cost}
        mock_cost_accessor.return_value.__enter__.return_value.infrastructure_rates = {}
        mock_cost_accessor.return_value.__enter__.return_value.supplementary_rates = supplementary_rates
        mock_cost_accessor.return_value.__enter__.return_value.distribution_info = {
            "distribution_type": "",
            "platform_cost": False,
            "worker_cost": False,
        }
        with self.accessor:
            usage_period = (
                OCPUsageReportPeriod.objects.filter(provider_id=self.provider_uuid)
                .order_by("-report_period_start")
                .first()
            )
            start_date = usage_period.report_period_start.date() + relativedelta(days=-1)
            end_date = usage_period.report_period_end.date() + relativedelta(days=+1)
        updater = OCPCostModelCostUpdater(schema=self.schema, provider=self.provider)
        updater._update_monthly_cost(start_date, end_date)
        with self.accessor:
            monthly_cost_row = OCPUsageLineItemDailySummary.objects.filter(
                cost_model_rate_type="Supplementary",
                monthly_cost_type__isnull=False,
                cluster_id=self.cluster_id,
            ).first()

            self.assertEqual(monthly_cost_row.cost_model_cpu_cost, 0)
            self.assertEqual(monthly_cost_row.cost_model_memory_cost, 0)
            self.assertEqual(monthly_cost_row.cost_model_volume_cost, 0)

    @skip("flaky test")
    @patch("masu.processor.ocp.ocp_cost_model_cost_updater.CostModelDBAccessor")
    def test_update_summary_cost_model_costs(self, mock_cost_accessor):
        """Test that all cost model cost types are updated."""
        infrastructure_rates = {"node_cost_per_month": 1000.0000000000}
        supplementary_rates = {
            "cpu_core_usage_per_hour": 0.0070000000,
            "cpu_core_request_per_hour": 0.2000000000,
            "memory_gb_usage_per_hour": 0.0090000000,
            "memory_gb_request_per_hour": 0.0500000000,
            "storage_gb_usage_per_month": 0.0100000000,
            "storage_gb_request_per_month": 0.0100000000,
        }
        markup = {"value": 10, "unit": "percent"}
        markup_dec = Decimal(markup.get("value") / 100)

        mock_cost_accessor.return_value.__enter__.return_value.infrastructure_rates = infrastructure_rates
        mock_cost_accessor.return_value.__enter__.return_value.supplementary_rates = supplementary_rates
        mock_cost_accessor.return_value.__enter__.return_value.markup = markup

        start_date = self.dh.this_month_start
        end_date = self.dh.this_month_end

        updater = OCPCostModelCostUpdater(schema=self.schema, provider=self.provider)
        summary_range = SummaryRangeConfig(start_date=start_date, end_date=end_date)
        updater.update_summary_cost_model_costs(summary_range)

        with schema_context(self.schema):
            # Monthly cost
            expected_count = (
                OCPUsageLineItemDailySummary.objects.filter(
                    usage_start__gte=start_date,
                    cluster_id=self.cluster_id,
                )
                .values("node")
                .distinct()
                .count()
            )
            monthly_cost_rows = OCPUsageLineItemDailySummary.objects.filter(
                usage_start=start_date, cluster_id=self.cluster_id, infrastructure_monthly_cost_json__isnull=False
            ).count()
            self.assertEqual(monthly_cost_rows, expected_count)

            pod_line_item = OCPUsageLineItemDailySummary.objects.filter(
                usage_start__gte=start_date,
                data_source="Pod",
                cluster_id=self.cluster_id,
                infrastructure_raw_cost__isnull=False,
            ).first()
            volume_line_item = OCPUsageLineItemDailySummary.objects.filter(
                usage_start__gte=start_date,
                data_source="Storage",
                cluster_id=self.cluster_id,
                infrastructure_raw_cost__isnull=False,
            ).first()

            # Markup
            self.assertAlmostEqual(
                pod_line_item.infrastructure_markup_cost, pod_line_item.infrastructure_raw_cost * markup_dec, 6
            )
            self.assertAlmostEqual(
                pod_line_item.infrastructure_project_markup_cost,
                pod_line_item.infrastructure_project_raw_cost * markup_dec,
                6,
            )

            # Now we want non-cloud infra line item to check usage cost on
            pod_line_item = OCPUsageLineItemDailySummary.objects.filter(
                usage_start__gte=start_date,
                data_source="Pod",
                cluster_id=self.cluster_id,
                infrastructure_raw_cost__isnull=True,
            ).first()
            volume_line_item = OCPUsageLineItemDailySummary.objects.filter(
                usage_start__gte=start_date,
                data_source="Storage",
                cluster_id=self.cluster_id,
                infrastructure_raw_cost__isnull=True,
            ).first()

            # Usage cost
            self.assertNotEqual(pod_line_item.supplementary_usage_cost.get("cpu"), 0)
            self.assertNotEqual(volume_line_item.supplementary_usage_cost.get("storage"), 0)

    @patch("masu.database.ocp_report_db_accessor.OCPReportDBAccessor.populate_tag_usage_costs")
    @patch("masu.processor.ocp.ocp_cost_model_cost_updater.CostModelDBAccessor")
    def test_update_tag_usage_costs(self, mock_cost_accessor, mock_update_usage):
        """Test that populate_tag_usage_cost is called with the correct cost_type and rate."""
        # using a string instead of an actual rate for the purposes of testing that the function is called
        infrastructure_rates = {"cpu_core_usage_per_hour": "another tag rate"}
        supplementary_rates = {"memory_gb_usage_per_hour": "a tag rate"}
        mock_cost_accessor.return_value.__enter__.return_value.tag_infrastructure_rates = infrastructure_rates
        mock_cost_accessor.return_value.__enter__.return_value.tag_supplementary_rates = supplementary_rates

        with schema_context(self.schema):
            usage_period = (
                OCPUsageReportPeriod.objects.filter(provider_id=self.provider_uuid)
                .order_by("-report_period_start")
                .first()
            )
        start_date = usage_period.report_period_start.date() + relativedelta(days=-1)
        end_date = usage_period.report_period_end.date() + relativedelta(days=+1)
        updater = OCPCostModelCostUpdater(schema=self.schema, provider=self.provider)
        updater._update_tag_usage_costs(start_date, end_date)
        # assert that populate_tag_usage_costs was called with the correct info
        mock_update_usage.assert_called_once_with(
            infrastructure_rates, supplementary_rates, start_date, end_date, self.cluster_id
        )

    def test_delete_tag_usage_costs_no_report_period(self):
        """Test that a delete without a matching report period no longer throws an error"""
        start_date = "2000-01-01"
        end_date = "2000-02-01"
        updater = OCPCostModelCostUpdater(schema=self.schema, provider=self.provider)
        updater._delete_tag_usage_costs(start_date, end_date, "")
        self.assertLogs("masu.processor.ocp", level="WARNING")

    def test_build_node_tag_cost_case_statements(self):
        """Make sure a correct SQL CASE statement is generated."""
        tag_key = "app"
        dh = DateHelper()
        start_date = dh.this_month_start
        cost_rate = dh.days_in_month(start_date)
        management_rate = cost_rate * 2
        default_rate = cost_rate * 3
        tag_rate_dict = {tag_key: {"cost": cost_rate, "management": management_rate}}
        default_rate_dict = {tag_key: {"default_value": default_rate}}

        cost_rate_amor = get_amortized_monthly_cost_model_rate(cost_rate, start_date)
        management_rate_amor = get_amortized_monthly_cost_model_rate(management_rate, start_date)
        default_rate_amor = get_amortized_monthly_cost_model_rate(default_rate, start_date)

        cpu_case_str = f"""
            CASE
            WHEN pod_labels->>'app'='cost'
                THEN sum(pod_effective_usage_cpu_core_hours)
                    / max(node_capacity_cpu_core_hours)
                    * {cost_rate_amor}::decimal
            WHEN pod_labels->>'app'='management'
                THEN sum(pod_effective_usage_cpu_core_hours)
                    / max(node_capacity_cpu_core_hours)
                    * {management_rate_amor}::decimal
            ELSE sum(pod_effective_usage_cpu_core_hours)
                / max(node_capacity_cpu_core_hours)
                * {default_rate_amor}::decimal
            END as cost_model_cpu_cost
        """
        memory_case_str = f"""
            CASE
            WHEN pod_labels->>'app'='cost'
                THEN sum(pod_effective_usage_memory_gigabyte_hours)
                    / max(node_capacity_memory_gigabyte_hours)
                    * {cost_rate_amor}::decimal
            WHEN pod_labels->>'app'='management'
                THEN sum(pod_effective_usage_memory_gigabyte_hours)
                    / max(node_capacity_memory_gigabyte_hours)
                    * {management_rate_amor}::decimal
            ELSE sum(pod_effective_usage_memory_gigabyte_hours)
                / max(node_capacity_memory_gigabyte_hours)
                * {default_rate_amor}::decimal
            END as cost_model_memory_cost
        """
        expected_case_strs = (
            cpu_case_str,
            "0::decimal as cost_model_memory_cost",
            "0::decimal as cost_model_volume_cost",
        )

        case_dict = self.updater._build_node_tag_cost_case_statements(
            tag_rate_dict, start_date, default_rate_dict=default_rate_dict
        )

        for actual, expected in zip(case_dict.get(tag_key), expected_case_strs):
            self.assertEqual(actual.replace("\n", "").replace(" ", ""), expected.replace("\n", "").replace(" ", ""))

        expected_case_strs = (
            "0::decimal as cost_model_cpu_cost",
            memory_case_str,
            "0::decimal as cost_model_volume_cost",
        )

        self.updater._distribution = metric_constants.MEM
        case_dict = self.updater._build_node_tag_cost_case_statements(
            tag_rate_dict, start_date, default_rate_dict=default_rate_dict
        )

        for actual, expected in zip(case_dict.get(tag_key), expected_case_strs):
            self.assertEqual(actual.replace("\n", "").replace(" ", ""), expected.replace("\n", "").replace(" ", ""))

    def test_build_volume_tag_cost_case_statements(self):
        """Make sure a correct SQL CASE statement is generated."""
        tag_key = "app"
        dh = DateHelper()
        start_date = dh.this_month_start
        cost_rate = dh.days_in_month(start_date)
        management_rate = cost_rate * 2
        default_rate = cost_rate * 3
        tag_rate_dict = {tag_key: {"cost": cost_rate, "management": management_rate}}
        default_rate_dict = {tag_key: {"default_value": default_rate}}

        cost_rate_amor = get_amortized_monthly_cost_model_rate(cost_rate, start_date)
        management_rate_amor = get_amortized_monthly_cost_model_rate(management_rate, start_date)
        default_rate_amor = get_amortized_monthly_cost_model_rate(default_rate, start_date)

        expected_case_strs = (
            "0::decimal as cost_model_cpu_cost",
            "0::decimal as cost_model_memory_cost",
            f"""
            CASE
            WHEN volume_labels->>'app'='cost'
                THEN {cost_rate_amor}::decimal / vc.pvc_count
            WHEN volume_labels->>'app'='management'
                THEN {management_rate_amor}::decimal / vc.pvc_count
            ELSE {default_rate_amor}::decimal / vc.pvc_count
            END as cost_model_volume_cost
            """,
        )

        case_dict = self.updater._build_volume_tag_cost_case_statements(
            tag_rate_dict, start_date, default_rate_dict=default_rate_dict
        )

        for actual, expected in zip(case_dict.get(tag_key), expected_case_strs):
            self.assertEqual(actual.replace("\n", "").replace(" ", ""), expected.replace("\n", "").replace(" ", ""))

    def test_update_monthly_tag_based_cost(self):
        """Test that monthly tag costs are amortized."""
        node_tag_key = "app"
        pvc_tag_key = "storageclass"
        dh = DateHelper()
        start_date = dh.this_month_start
        end_date = dh.this_month_end

        rate_one = dh.days_in_month(start_date)
        rate_two = rate_one * 2
        node_tag_rate_dict = {node_tag_key: {"banking": rate_one, "weather": rate_two}}
        pvc_tag_rate_dict = {pvc_tag_key: {"Pearl": rate_one, "Diamond": rate_two}}

        updater = OCPCostModelCostUpdater(schema=self.schema, provider=self.provider)
        updater.is_amortized = True
        updater._tag_supplementary_rates = {"node_cost_per_month": node_tag_rate_dict}
        updater._tag_infra_rates = {"pvc_cost_per_month": pvc_tag_rate_dict}

        distribution_choices = (
            {"metric": metric_constants.CPU, "column": "cost_model_cpu_cost"},
            {"metric": metric_constants.MEM, "column": "cost_model_memory_cost"},
        )
        for distribution_choice in distribution_choices:
            distribution = distribution_choice.get("metric")
            column = distribution_choice.get("column")
            with self.subTest(distribution=distribution, column=column):
                updater._distribution = distribution
                with schema_context(self.schema):
                    OCPUsageLineItemDailySummary.objects.filter(monthly_cost_type__isnull=False).delete()
                    node_line_item_count = OCPUsageLineItemDailySummary.objects.filter(
                        usage_start__gte=start_date, usage_start__lte=end_date, monthly_cost_type="Node"
                    ).count()

                    self.assertEqual(node_line_item_count, 0)

                    pvc_line_items = OCPUsageLineItemDailySummary.objects.filter(
                        usage_start__gte=start_date, usage_start__lte=end_date, monthly_cost_type="PVC"
                    ).count()

                    self.assertEqual(pvc_line_items, 0)

                updater._update_monthly_tag_based_cost(start_date, end_date)

                with schema_context(self.schema):
                    node_line_items = OCPUsageLineItemDailySummary.objects.filter(
                        usage_start__gte=start_date, usage_start__lte=end_date, monthly_cost_type="Node"
                    ).all()

                    self.assertNotEqual(len(node_line_items), 0)

                    for item in node_line_items:
                        self.assertNotEqual(getattr(item, column), 0)

                    pvc_line_items = OCPUsageLineItemDailySummary.objects.filter(
                        usage_start__gte=start_date, usage_start__lte=end_date, monthly_cost_type="PVC"
                    ).all()

                    self.assertNotEqual(len(pvc_line_items), 0)

                    for item in pvc_line_items:
                        self.assertNotEqual(item.cost_model_volume_cost, 0)

    def test_update_node_hour_tag_based_cost(self):
        """Test that node hour tag costs are applied."""
        node_tag_key = "app"
        dh = DateHelper()
        start_date = dh.this_month_start
        end_date = dh.this_month_end

        rate_one = dh.days_in_month(start_date)
        rate_two = rate_one * 2
        node_tag_rate_dict = {node_tag_key: {"banking": rate_one, "weather": rate_two}}

        updater = OCPCostModelCostUpdater(schema=self.schema, provider=self.provider)
        updater._tag_supplementary_rates = {metric_constants.OCP_NODE_CORE_HOUR: node_tag_rate_dict}

        distribution_choices = (
            {"metric": metric_constants.CPU, "column": "cost_model_cpu_cost"},
            {"metric": metric_constants.MEM, "column": "cost_model_memory_cost"},
        )
        for distribution_choice in distribution_choices:
            distribution = distribution_choice.get("metric")
            column = distribution_choice.get("column")
            with self.subTest(distribution=distribution, column=column):
                updater._distribution = distribution
                with schema_context(self.schema):
                    OCPUsageLineItemDailySummary.objects.filter(monthly_cost_type__isnull=False).delete()
                    node_line_item_count = OCPUsageLineItemDailySummary.objects.filter(
                        usage_start__gte=start_date, usage_start__lte=end_date, monthly_cost_type="Node_Core_Hour"
                    ).count()

                    self.assertEqual(node_line_item_count, 0)

                updater._update_node_hour_tag_based_cost(start_date, end_date)

                with schema_context(self.schema):
                    node_line_items = OCPUsageLineItemDailySummary.objects.filter(
                        usage_start__gte=start_date, usage_start__lte=end_date, monthly_cost_type="Node_Core_Hour"
                    ).all()

                    self.assertNotEqual(len(node_line_items), 0)

                    for item in node_line_items:
                        self.assertNotEqual(getattr(item, column), 0)
