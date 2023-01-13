#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the OCPReportDBAccessor utility object."""
import logging
import random
from decimal import Decimal
from unittest import skip
from unittest.mock import patch

from dateutil.relativedelta import relativedelta
from django.db.models import Sum
from tenant_schemas.utils import schema_context

from api.metrics import constants as metric_constants
from api.utils import DateHelper
from masu.database import OCP_REPORT_TABLE_MAP
from masu.database.ocp_report_db_accessor import OCPReportDBAccessor
from masu.processor.ocp.ocp_cost_model_cost_updater import OCPCostModelCostUpdater
from masu.processor.ocp.ocp_cost_model_cost_updater import OCPCostModelCostUpdaterError
from masu.test import MasuTestCase
from masu.util.ocp.common import get_amortized_monthly_cost_model_rate
from reporting.models import OCPUsageLineItemDailySummary

LOG = logging.getLogger(__name__)


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

    def test_normalize_tier(self):
        """Test the tier helper function to normalize rate tier."""
        rate_json = [
            {"usage": {"usage_start": "20", "usage_end": "30"}, "value": "0.30", "unit": "USD"},
            {"usage": {"usage_start": None, "usage_end": "10"}, "value": "0.10", "unit": "USD"},
            {"usage": {"usage_start": "10", "usage_end": "20"}, "value": "0.20", "unit": "USD"},
            {"usage": {"usage_start": "30", "usage_end": None}, "value": "0.40", "unit": "USD"},
        ]
        normalized_tier = self.updater._normalize_tier(rate_json)
        self.assertEqual(len(normalized_tier), len(rate_json))
        self.assertIsNone(normalized_tier[0].get("usage").get("usage_start"))
        self.assertGreater(
            normalized_tier[1].get("usage").get("usage_end"), normalized_tier[0].get("usage").get("usage_end")
        )
        self.assertGreater(
            normalized_tier[2].get("usage").get("usage_end"), normalized_tier[1].get("usage").get("usage_end")
        )
        self.assertIsNone(normalized_tier[3].get("usage").get("usage_end"))

    def test_normalize_tier_no_start_end_provided(self):
        """Test the tier helper function to normalize rate tier when end points are not provided."""
        rate_json = [
            {"usage": {"usage_start": "20", "usage_end": "30"}, "value": "0.30", "unit": "USD"},
            {"usage": {"usage_end": "10", "value": "0.10"}, "unit": "USD"},
            {"usage": {"usage_start": "10", "usage_end": "20"}, "value": "0.20", "unit": "USD"},
            {"usage": {"usage_start": "30"}, "value": "0.40", "unit": "USD"},
        ]
        normalized_tier = self.updater._normalize_tier(rate_json)
        self.assertEqual(len(normalized_tier), len(rate_json))
        self.assertIsNone(normalized_tier[0].get("usage").get("usage_start"))
        self.assertGreater(
            normalized_tier[1].get("usage").get("usage_end"), normalized_tier[0].get("usage").get("usage_end")
        )
        self.assertGreater(
            normalized_tier[2].get("usage").get("usage_end"), normalized_tier[1].get("usage").get("usage_end")
        )
        self.assertIsNone(normalized_tier[3].get("usage").get("usage_end"))

    def test_normalize_tier_missing_first(self):
        """Test the tier helper function when first tier is missing."""
        rate_json = [
            {"usage": {"usage_start": None, "usage_end": "10"}, "value": "0.10", "unit": "USD"},
            {"usage": {"usage_start": "20", "usage_end": "30"}, "value": "0.30", "unit": "USD"},
            {"usage": {"usage_start": "10", "usage_end": "20"}, "value": "0.20", "unit": "USD"},
            {"usage": {"usage_start": "30", "usage_end": "40"}, "value": "0.40", "unit": "USD"},
        ]
        with self.assertRaises(OCPCostModelCostUpdaterError) as error:
            self.updater._normalize_tier(rate_json)
            self.assertIn("Missing first tier", error)

    def test_normalize_tier_two_starts(self):
        """Test the tier helper function when two starting tiers are provided."""
        rate_json = [
            {"usage": {"usage_start": None, "usage_end": "10"}, "value": "0.10", "unit": "USD"},
            {"usage": {"usage_start": None, "usage_end": "30"}, "value": "0.30", "unit": "USD"},
            {"usage": {"usage_start": "10", "usage_end": "20"}, "value": "0.20", "unit": "USD"},
            {"usage": {"usage_start": "30"}, "value": "0.40", "unit": "USD"},
        ]
        with self.assertRaises(OCPCostModelCostUpdaterError) as error:
            self.updater._normalize_tier(rate_json)
            self.assertIn("Two starting tiers", error)

    def test_normalize_tier_two_final(self):
        """Test the tier helper function when two final tiers are provided."""
        rate_json = [
            {"usage": {"usage_start": None, "usage_end": "10"}, "value": "0.10", "unit": "USD"},
            {"usage": {"usage_start": "20", "usage_end": "30"}, "value": "0.30", "unit": "USD"},
            {"usage": {"usage_start": "10", "usage_end": None}, "value": "0.20", "unit": "USD"},
            {"usage": {"usage_start": "30"}, "value": "0.40", "unit": "USD"},
        ]
        with self.assertRaises(OCPCostModelCostUpdaterError) as error:
            self.updater._normalize_tier(rate_json)
            self.assertIn("Two final tiers", error)

    def test_normalize_tier_missing_last(self):
        """Test the tier helper function when last tier is missing."""
        rate_json = [
            {"usage": {"usage_start": "20", "usage_end": "30"}, "value": "0.30", "unit": "USD"},
            {"usage": {"usage_start": "10", "usage_end": "20"}, "value": "0.20", "unit": "USD"},
            {"usage": {"usage_start": "30", "usage_end": None}, "value": "0.40", "unit": "USD"},
        ]
        with self.assertRaises(OCPCostModelCostUpdaterError) as error:
            self.updater._normalize_tier(rate_json)
            self.assertIn("Missing final tier", error)

    def test_bucket_applied(self):
        """Test the tier helper function."""
        lower_limit = 0
        upper_limit = 10
        test_matrix = [
            {"usage": -10, "expected_usage_applied": 0},
            {"usage": 5, "expected_usage_applied": 5},
            {"usage": 10, "expected_usage_applied": 10},
            {"usage": 15, "expected_usage_applied": 10},
        ]
        for test in test_matrix:
            usage_applied = self.updater._bucket_applied(test.get("usage"), lower_limit, upper_limit)
            self.assertEqual(usage_applied, test.get("expected_usage_applied"))

    def test_calculate_variable_charge(self):
        """Test the helper function to calculate charge."""
        rate_json = {
            "tiered_rates": [
                {"usage": {"usage_start": None, "usage_end": "10"}, "value": "0.10", "unit": "USD"},
                {"usage": {"usage_start": "10", "usage_end": "20"}, "value": "0.20", "unit": "USD"},
                {"usage": {"usage_start": "20", "usage_end": "30"}, "value": "0.30", "unit": "USD"},
                {"usage": {"usage_start": "30", "usage_end": None}, "value": "0.40", "unit": "USD"},
            ]
        }
        usage_dictionary = {1: Decimal(5), 2: Decimal(15), 3: Decimal(25), 4: Decimal(50), 5: Decimal(0)}
        expected_results = {
            1: Decimal(0.5),  # usage: 5,  charge: 0.5 = 5 * 0.1
            2: Decimal(2.0),  # usage: 15, charge: 2.0 = (10 * 0.1) + (5 * 0.2)
            3: Decimal(4.5),  # usage: 25, charge: 4.5 = (10 * 0.1) + (10 * 0.2) + (5 * 0.3)
            4: Decimal(14.0),  # usage: 50, charge: 14.0 = (10 * 0.1) + (10 * 0.2) + (10 * 0.3) + (20 * 0.4)
            5: Decimal(0.0),
        }  # usage: 0, charge: 0
        for key, usage in usage_dictionary.items():
            tier_charge = self.updater._calculate_variable_charge(usage, rate_json)
            self.assertEqual(tier_charge, expected_results.get(key))

    def test_calculate_variable_charge_floating_ends(self):
        """Test the helper function to calculate charge with floating endpoints."""
        rate_json = {
            "tiered_rates": [
                {"usage": {"usage_start": None, "usage_end": "10.3"}, "value": "0.10", "unit": "USD"},
                {"usage": {"usage_start": "10.3", "usage_end": "19.8"}, "value": "0.20", "unit": "USD"},
                {"usage": {"usage_start": "19.8", "usage_end": "22.6"}, "value": "0.30", "unit": "USD"},
                {"usage": {"usage_start": "22.6", "usage_end": None}, "value": "0.40", "unit": "USD"},
            ]
        }
        usage_dictionary = {1: Decimal(5), 2: Decimal(15), 3: Decimal(25), 4: Decimal(50), 5: Decimal(0)}
        expected_results = {
            1: Decimal("0.5"),  # usage: 5,  charge: 0.5 = 5 * 0.1
            2: Decimal("1.97"),  # usage: 15, charge: 1.97 = (10.3 * 0.1) + (4.7 * 0.2)
            3: Decimal("4.730"),  # usage: 25, charge: 4.730 = (10.3 * 0.1)
            #  + (9.5 * 0.2) + (2.8 * 0.3) + (2.4 * 0.4)
            4: Decimal("14.730"),  # usage: 50, charge: 14.73 = (10.3 * 0.1)
            # + (9.5 * 0.2) + (2.8 * 0.3) + (27.4 * 0.4)
            5: Decimal("0.0"),
        }  # usage: 0, charge: 0
        for key, usage in usage_dictionary.items():
            tier_charge = self.updater._calculate_variable_charge(usage, rate_json)
            self.assertEqual(tier_charge, expected_results.get(key))

    def test_calculate_variable_charge_ends_missing(self):
        """Test the helper function to calculate charge when end limits are missing."""
        rate_json = {
            "tiered_rates": [
                {"usage": {"usage_end": "10"}, "value": "0.10", "unit": "USD"},
                {"usage": {"usage_start": "10", "usage_end": "20"}, "value": "0.20", "unit": "USD"},
                {"usage": {"usage_start": "20", "usage_end": "30"}, "value": "0.30", "unit": "USD"},
                {"usage": {"usage_start": "30"}, "value": "0.40", "unit": "USD"},
            ]
        }
        usage_dictionary = {1: Decimal(5), 2: Decimal(15), 3: Decimal(25), 4: Decimal(50), 5: Decimal(0)}
        expected_results = {1: Decimal(0.5), 2: Decimal(2.0), 3: Decimal(4.5), 4: Decimal(14.0), 5: Decimal(0.0)}
        for key, usage in usage_dictionary.items():
            tier_charge = self.updater._calculate_variable_charge(usage, rate_json)
            self.assertEqual(tier_charge, expected_results.get(key))

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

    @patch("masu.processor.ocp.ocp_cost_model_cost_updater.CostModelDBAccessor")
    def test_update_markup_cost_no_markup(self, mock_cost_accessor):
        """Test that markup is calculated."""
        markup = {}

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
                self.assertEqual(line_item.infrastructure_markup_cost, 0)
                self.assertEqual(line_item.infrastructure_project_markup_cost, 0)

    @patch("masu.processor.ocp.ocp_cost_model_cost_updater.enable_ocp_amortized_monthly_cost")
    @patch("masu.processor.ocp.ocp_cost_model_cost_updater.CostModelDBAccessor")
    def test_update_usage_costs(self, mock_cost_accessor, mock_amortized):
        """Test that usage costs are updated for infrastructure and supplementary."""
        mock_amortized.return_value = False
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

        start_date = self.dh.this_month_start
        end_date = self.dh.this_month_end

        updater = OCPCostModelCostUpdater(schema=self.schema, provider=self.provider)
        updater._update_usage_costs(start_date, end_date)

        with schema_context(self.schema):
            pod_line_items = OCPUsageLineItemDailySummary.objects.filter(
                usage_start__gte=start_date,
                data_source="Pod",
                cluster_id=self.cluster_id,
                infrastructure_raw_cost__isnull=True,
                cost_model_rate_type__isnull=True,
            ).all()
            for line_item in pod_line_items:
                self.assertNotEqual(line_item.infrastructure_usage_cost.get("cpu", 0), 0)
                self.assertNotEqual(line_item.infrastructure_usage_cost.get("memory", 0), 0)
                self.assertEqual(line_item.infrastructure_usage_cost.get("storage"), 0)

                self.assertEqual(line_item.supplementary_usage_cost.get("cpu"), 0)
                self.assertEqual(line_item.supplementary_usage_cost.get("memory"), 0)
                self.assertEqual(line_item.supplementary_usage_cost.get("storage"), 0)

            volume_line_items = OCPUsageLineItemDailySummary.objects.filter(
                usage_start__gte=start_date,
                data_source="Storage",
                cluster_id=self.cluster_id,
                infrastructure_raw_cost__isnull=True,
                cost_model_rate_type__isnull=True,
            ).all()

            for line_item in volume_line_items:
                self.assertEqual(line_item.infrastructure_usage_cost.get("cpu"), 0)
                self.assertEqual(line_item.infrastructure_usage_cost.get("memory"), 0)
                self.assertEqual(line_item.infrastructure_usage_cost.get("storage"), 0)

                self.assertEqual(line_item.supplementary_usage_cost.get("cpu"), 0)
                self.assertEqual(line_item.supplementary_usage_cost.get("memory"), 0)
                self.assertNotEqual(line_item.supplementary_usage_cost.get("storage", 0), 0)

    @patch("masu.processor.ocp.ocp_cost_model_cost_updater.enable_ocp_amortized_monthly_cost")
    @patch("masu.processor.ocp.ocp_cost_model_cost_updater.CostModelDBAccessor")
    def test_update_usage_costs_new_columns(self, mock_cost_accessor, mock_amortized):
        """Test that usage costs are updated for infrastructure and supplementary."""
        mock_amortized.return_value = True
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

    @patch("masu.processor.ocp.ocp_cost_model_cost_updater.enable_ocp_amortized_monthly_cost")
    @patch("masu.processor.ocp.ocp_cost_model_cost_updater.CostModelDBAccessor")
    def test_update_monthly_cost_infrastructure(self, mock_cost_accessor, mock_amortized):
        """Test OCP charge for monthly costs is updated."""
        mock_amortized.return_value = False
        node_cost = random.randrange(1, 200)
        infrastructure_rates = {"node_cost_per_month": node_cost}
        mock_cost_accessor.return_value.__enter__.return_value.infrastructure_rates = infrastructure_rates
        mock_cost_accessor.return_value.__enter__.return_value.supplementary_rates = {}
        mock_cost_accessor.return_value.__enter__.return_value.distribution = ""

        usage_period = self.accessor.get_current_usage_period(self.provider_uuid)
        start_date = usage_period.report_period_start.date() + relativedelta(days=-1)
        end_date = usage_period.report_period_end.date() + relativedelta(days=+1)
        updater = OCPCostModelCostUpdater(schema=self.schema, provider=self.provider)
        updater._update_monthly_cost(start_date, end_date)
        with schema_context(self.schema):
            monthly_cost_row = OCPUsageLineItemDailySummary.objects.filter(
                cluster_id=self.cluster_id, infrastructure_monthly_cost_json__isnull=False
            ).first()
            self.assertEqual(monthly_cost_row.infrastructure_monthly_cost_json.get("cpu"), 0)
            self.assertEqual(monthly_cost_row.infrastructure_monthly_cost_json.get("memory"), 0)
            self.assertEqual(monthly_cost_row.infrastructure_monthly_cost_json.get("pvc"), 0)

    @patch("masu.processor.ocp.ocp_cost_model_cost_updater.enable_ocp_amortized_monthly_cost")
    @patch("masu.processor.ocp.ocp_cost_model_cost_updater.CostModelDBAccessor")
    def test_update_monthly_cost_infrastructure_new_columns(self, mock_cost_accessor, mock_amortized):
        """Test OCP charge for monthly costs is updated."""
        mock_amortized.return_value = True
        node_cost = random.randrange(1, 200)
        infrastructure_rates = {"node_cost_per_month": node_cost}
        mock_cost_accessor.return_value.__enter__.return_value.infrastructure_rates = infrastructure_rates
        mock_cost_accessor.return_value.__enter__.return_value.supplementary_rates = {}
        mock_cost_accessor.return_value.__enter__.return_value.distribution = "cpu"
        usage_period = self.accessor.get_current_usage_period(self.provider_uuid)
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

    @patch("masu.processor.ocp.ocp_cost_model_cost_updater.CostModelDBAccessor")
    def test_update_monthly_cost_infrastructure_cluster_distribution(self, mock_cost_accessor):
        """Test OCP charge for monthly costs is updated."""
        cluster_cost = 1000
        infrastructure_rates = {"cluster_cost_per_month": cluster_cost}
        mock_cost_accessor.return_value.__enter__.return_value.infrastructure_rates = infrastructure_rates
        mock_cost_accessor.return_value.__enter__.return_value.supplementary_rates = {}
        mock_cost_accessor.return_value.__enter__.return_value.distribution = "cpu"

        start_date = self.dh.this_month_start
        end_date = self.dh.this_month_end
        updater = OCPCostModelCostUpdater(schema=self.schema, provider=self.provider)
        updater._update_monthly_cost(start_date, end_date)
        with OCPReportDBAccessor(self.schema) as accessor:
            report_period = accessor.get_usage_period_by_dates_and_cluster(start_date, end_date, self.cluster_id)
        with schema_context(self.schema):
            nodes = (
                OCPUsageLineItemDailySummary.objects.filter(cluster_id=self.cluster_id)
                .values("node")
                .annotate(
                    **{
                        "node_capacity_cpu_core_hours": Sum("node_capacity_cpu_core_hours"),
                        "cluster_capacity_cpu_core_hours": Sum("cluster_capacity_cpu_core_hours"),
                    }
                )
                .values_list("node", "node_capacity_cpu_core_hours", "cluster_capacity_cpu_core_hours")
                .filter(report_period_id=report_period)
            )
            for node in nodes:
                if node[1] is None:
                    continue
                monthly_cost_row = OCPUsageLineItemDailySummary.objects.filter(
                    usage_start__gte=start_date,
                    node=node[0],
                    monthly_cost_type="Cluster",
                    infrastructure_monthly_cost_json__isnull=False,
                    cluster_id=self.cluster_id,
                    report_period_id=report_period,
                ).first()
                expected_cost = float((node[1] / node[2]) * cluster_cost)
                self.assertAlmostEqual(monthly_cost_row.infrastructure_monthly_cost_json.get("cpu"), expected_cost)
                self.assertEqual(monthly_cost_row.infrastructure_monthly_cost_json.get("memory"), 0)
                self.assertEqual(monthly_cost_row.infrastructure_monthly_cost_json.get("pvc"), 0)

    @patch("masu.processor.ocp.ocp_cost_model_cost_updater.enable_ocp_amortized_monthly_cost")
    @patch("masu.processor.ocp.ocp_cost_model_cost_updater.CostModelDBAccessor")
    def test_update_monthly_cost_supplementary(self, mock_cost_accessor, mock_amortized):
        """Test OCP charge for monthly costs is updated."""
        mock_amortized.return_value = False
        node_cost = random.randrange(1, 200)
        supplementary_rates = {"node_cost_per_month": node_cost}
        mock_cost_accessor.return_value.__enter__.return_value.infrastructure_rates = {}
        mock_cost_accessor.return_value.__enter__.return_value.supplementary_rates = supplementary_rates
        mock_cost_accessor.return_value.__enter__.return_value.distribution = ""
        usage_period = self.accessor.get_current_usage_period(self.provider_uuid)
        start_date = usage_period.report_period_start.date() + relativedelta(days=-1)
        end_date = usage_period.report_period_end.date() + relativedelta(days=+1)
        updater = OCPCostModelCostUpdater(schema=self.schema, provider=self.provider)
        updater._update_monthly_cost(start_date, end_date)
        with schema_context(self.schema):
            monthly_cost_row = OCPUsageLineItemDailySummary.objects.filter(
                supplementary_monthly_cost_json__isnull=False,
                cluster_id=self.cluster_id,
            ).first()

            self.assertEqual(monthly_cost_row.supplementary_monthly_cost_json.get("cpu"), 0)
            self.assertEqual(monthly_cost_row.supplementary_monthly_cost_json.get("memory"), 0)
            self.assertEqual(monthly_cost_row.supplementary_monthly_cost_json.get("pvc"), 0)

    @patch("masu.processor.ocp.ocp_cost_model_cost_updater.enable_ocp_amortized_monthly_cost")
    @patch("masu.processor.ocp.ocp_cost_model_cost_updater.CostModelDBAccessor")
    def test_update_monthly_cost_supplementary_new_columns(self, mock_cost_accessor, mock_amortized):
        """Test OCP charge for monthly costs is updated."""
        mock_amortized.return_value = True
        node_cost = random.randrange(1, 200)
        supplementary_rates = {"node_cost_per_month": node_cost}
        mock_cost_accessor.return_value.__enter__.return_value.infrastructure_rates = {}
        mock_cost_accessor.return_value.__enter__.return_value.supplementary_rates = supplementary_rates
        mock_cost_accessor.return_value.__enter__.return_value.distribution = ""
        usage_period = self.accessor.get_current_usage_period(self.provider_uuid)
        start_date = usage_period.report_period_start.date() + relativedelta(days=-1)
        end_date = usage_period.report_period_end.date() + relativedelta(days=+1)
        updater = OCPCostModelCostUpdater(schema=self.schema, provider=self.provider)
        updater._update_monthly_cost(start_date, end_date)
        with schema_context(self.schema):
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
        updater.update_summary_cost_model_costs(start_date, end_date)

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

    @patch("masu.database.ocp_report_db_accessor.OCPReportDBAccessor.populate_monthly_tag_cost")
    @patch("masu.processor.ocp.ocp_cost_model_cost_updater.CostModelDBAccessor")
    def test_tag_update_monthly_cost_infrastructure(self, mock_cost_accessor, mock_update_monthly):
        """Test that populate_monthly_tag_cost is called with the correct cost_type and rate."""
        # using a string instead of an actual rate for the purposes of testing that the function is called
        mock_cost_accessor.return_value.__enter__.return_value.tag_infrastructure_rates = {
            "node_cost_per_month": "a tag rate"
        }
        mock_cost_accessor.return_value.__enter__.return_value.tag_supplementary_rates = {}
        mock_cost_accessor.return_value.__enter__.return_value.distribution = "cpu"

        usage_period = self.accessor.get_current_usage_period(self.provider_uuid)
        start_date = usage_period.report_period_start.date() + relativedelta(days=-1)
        end_date = usage_period.report_period_end.date() + relativedelta(days=+1)
        updater = OCPCostModelCostUpdater(schema=self.schema, provider=self.provider)
        updater._update_monthly_tag_based_cost(start_date, end_date)

        # assert that the Node call includes relevant information and the call for cluster and pvc
        # do not happen since they did not have a rate included
        mock_update_monthly.assert_called_once_with(
            "Node",
            "Infrastructure",
            "a tag rate",
            start_date,
            end_date,
            self.cluster_id,
            updater._cluster_alias,
            "cpu",
            str(self.provider_uuid),
        )

    @patch("masu.database.ocp_report_db_accessor.OCPReportDBAccessor.populate_monthly_tag_cost")
    @patch("masu.processor.ocp.ocp_cost_model_cost_updater.CostModelDBAccessor")
    def test_tag_update_monthly_cost_both(self, mock_cost_accessor, mock_update_monthly):
        """
        Test that populate_monthly_tag_cost is called with the
        correct cost_type and rate when you pass in both cost types.
        """
        distribution = "cpu"
        # using a string instead of an actual rate for the purposes of testing that the function is called
        mock_cost_accessor.return_value.__enter__.return_value.tag_infrastructure_rates = {
            "node_cost_per_month": "a tag rate"
        }
        mock_cost_accessor.return_value.__enter__.return_value.tag_supplementary_rates = {
            "node_cost_per_month": "a second tag rate"
        }
        mock_cost_accessor.return_value.__enter__.return_value.distribution = distribution

        usage_period = self.accessor.get_current_usage_period(self.provider_uuid)
        start_date = usage_period.report_period_start.date() + relativedelta(days=-1)
        end_date = usage_period.report_period_end.date() + relativedelta(days=+1)
        updater = OCPCostModelCostUpdater(schema=self.schema, provider=self.provider)
        updater._update_monthly_tag_based_cost(start_date, end_date)

        # assert that the Node call includes relevant information and was called for both cost types
        # and the call for cluster and pvc do not happen since they did not have a rate included
        mock_update_monthly.assert_any_call(
            "Node",
            "Infrastructure",
            "a tag rate",
            start_date,
            end_date,
            self.cluster_id,
            updater._cluster_alias,
            distribution,
            str(self.provider_uuid),
        )
        mock_update_monthly.assert_any_call(
            "Node",
            "Supplementary",
            "a second tag rate",
            start_date,
            end_date,
            self.cluster_id,
            updater._cluster_alias,
            distribution,
            str(self.provider_uuid),
        )

        self.assertEqual(mock_update_monthly.call_count, 2)

    @patch("masu.database.ocp_report_db_accessor.OCPReportDBAccessor.populate_monthly_tag_cost")
    @patch("masu.processor.ocp.ocp_cost_model_cost_updater.CostModelDBAccessor")
    def test_tag_update_monthly_cost_supplementary(self, mock_cost_accessor, mock_update_monthly):
        """Test that _update_monthly_tag_based_cost is called with the correct cost_type and rate."""
        # using a string instead of an actual rate for the purposes of testing that the function is called
        distribution = "cpu"
        mock_cost_accessor.return_value.__enter__.return_value.tag_infrastructure_rates = {}
        mock_cost_accessor.return_value.__enter__.return_value.tag_supplementary_rates = {
            "cluster_cost_per_month": "a tag rate"
        }
        mock_cost_accessor.return_value.__enter__.return_value.distribution = distribution

        usage_period = self.accessor.get_current_usage_period(self.provider_uuid)
        start_date = usage_period.report_period_start.date() + relativedelta(days=-1)
        end_date = usage_period.report_period_end.date() + relativedelta(days=+1)
        updater = OCPCostModelCostUpdater(schema=self.schema, provider=self.provider)
        updater._update_monthly_tag_based_cost(start_date, end_date)

        # assert that the Cluster call includes relevant information and the call for node and pvc
        # do not happen since they did not have a rate included
        mock_update_monthly.assert_called_once_with(
            "Cluster",
            "Supplementary",
            "a tag rate",
            start_date,
            end_date,
            self.cluster_id,
            updater._cluster_alias,
            distribution,
            str(self.provider_uuid),
        )

    @patch("masu.database.ocp_report_db_accessor.OCPReportDBAccessor.populate_tag_usage_costs")
    @patch("masu.processor.ocp.ocp_cost_model_cost_updater.CostModelDBAccessor")
    def test_update_tag_usage_costs(self, mock_cost_accessor, mock_update_usage):
        """Test that populate_tag_usage_cost is called with the correct cost_type and rate."""
        # using a string instead of an actual rate for the purposes of testing that the function is called
        infrastructure_rates = {"cpu_core_usage_per_hour": "another tag rate"}
        supplementary_rates = {"memory_gb_usage_per_hour": "a tag rate"}
        mock_cost_accessor.return_value.__enter__.return_value.tag_infrastructure_rates = infrastructure_rates
        mock_cost_accessor.return_value.__enter__.return_value.tag_supplementary_rates = supplementary_rates

        usage_period = self.accessor.get_current_usage_period(self.provider_uuid)
        start_date = usage_period.report_period_start.date() + relativedelta(days=-1)
        end_date = usage_period.report_period_end.date() + relativedelta(days=+1)
        updater = OCPCostModelCostUpdater(schema=self.schema, provider=self.provider)
        updater._update_tag_usage_costs(start_date, end_date)
        # assert that populate_tag_usage_costs was called with the correct info
        mock_update_usage.assert_called_once_with(
            infrastructure_rates, supplementary_rates, start_date, end_date, self.cluster_id
        )

    @patch("masu.database.ocp_report_db_accessor.OCPReportDBAccessor.populate_monthly_tag_default_cost")
    @patch("masu.processor.ocp.ocp_cost_model_cost_updater.CostModelDBAccessor")
    def test_tag_update_monthly_cost_supplementary_no_match(self, mock_cost_accessor, mock_update_monthly):
        """Test that _update_monthly_tag_based_default_cost is not called when there is no rate for the metric"""
        # using a string instead of an actual rate for the purposes of testing that the function is called
        mock_cost_accessor.return_value.__enter__.return_value.tag_default_infrastructure_rates = {}
        mock_cost_accessor.return_value.__enter__.return_value.tag_default_supplementary_rates = {
            "node_cost_per_month": "a node cost"
        }

        start_date = "2020-10-01"
        end_date = "2020-11-01"
        updater = OCPCostModelCostUpdater(schema=self.schema, provider=self.provider)
        updater._update_monthly_tag_based_default_cost(start_date, end_date)

        # assert that the Cluster call includes relevant information and the call for node and pvc
        # do not happen since they did not have a rate included
        mock_update_monthly.assert_called_once()

    def test_delete_tag_usage_costs_no_report_period(self):
        """Test that a delete without a matching report period no longer throws an error"""
        start_date = "2000-01-01"
        end_date = "2000-02-01"
        updater = OCPCostModelCostUpdater(schema=self.schema, provider=self.provider)
        updater._delete_tag_usage_costs(start_date, end_date, "")
        self.assertLogs("masu.processor.ocp", level="WARNING")

    def test_build_node_tag_rate_case_statement_str(self):
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
            f"""
            CASE
            WHEN pod_labels->>'app'='cost' AND 'cpu' = 'cpu'
                THEN sum(pod_effective_usage_cpu_core_hours)
                    / max(node_capacity_cpu_core_hours)
                    * {cost_rate_amor}::decimal
            WHEN pod_labels->>'app'='management' AND 'cpu' = 'cpu'
                THEN sum(pod_effective_usage_cpu_core_hours)
                    / max(node_capacity_cpu_core_hours)
                    * {management_rate_amor}::decimal
            ELSE sum(pod_effective_usage_cpu_core_hours)
                / max(node_capacity_cpu_core_hours)
                * {default_rate_amor}::decimal
            END as cost_model_cpu_cost
            """,
            f"""
            CASE
            WHEN pod_labels->>'app'='cost' AND 'cpu' = 'memory'
                THEN sum(pod_effective_usage_memory_gigabyte_hours)
                    / max(node_capacity_memory_gigabyte_hours)
                    * {cost_rate_amor}::decimal
            WHEN pod_labels->>'app'='management' AND 'cpu' = 'memory'
                THEN sum(pod_effective_usage_memory_gigabyte_hours)
                    / max(node_capacity_memory_gigabyte_hours)
                    * {management_rate_amor}::decimal
            ELSE sum(pod_effective_usage_memory_gigabyte_hours)
                / max(node_capacity_memory_gigabyte_hours)
                * {default_rate_amor}::decimal
            END as cost_model_memory_cost
        """,
            "NULL as cost_model_volume_cost",
        )

        case_dict = self.updater._build_node_tag_rate_case_statement_str(
            tag_rate_dict, start_date, default_rate_dict=default_rate_dict
        )

        for actual, expected in zip(case_dict.get(tag_key), expected_case_strs):
            self.assertEqual(actual.replace("\n", "").replace(" ", ""), expected.replace("\n", "").replace(" ", ""))

    def test_build_volume_tag_rate_case_statement_str(self):
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
            "NULL as cost_model_cpu_cost",
            "NULL as cost_model_memory_cost",
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

        case_dict = self.updater._build_volume_tag_rate_case_statement_str(
            tag_rate_dict, start_date, default_rate_dict=default_rate_dict
        )

        for actual, expected in zip(case_dict.get(tag_key), expected_case_strs):
            self.assertEqual(actual.replace("\n", "").replace(" ", ""), expected.replace("\n", "").replace(" ", ""))

    def test_update_monthly_tag_based_cost_amortized(self):
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
            {"metric": metric_constants.CPU_DISTRIBUTION, "column": "cost_model_cpu_cost"},
            {"metric": metric_constants.MEMORY_DISTRIBUTION, "column": "cost_model_memory_cost"},
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

                updater._update_monthly_tag_based_cost_amortized(start_date, end_date)

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
