#
# Copyright 2018 Red Hat, Inc.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
"""Test the OCPReportDBAccessor utility object."""
import random
from decimal import Decimal
from unittest.mock import patch

from dateutil.relativedelta import relativedelta
from tenant_schemas.utils import schema_context

from api.utils import DateHelper
from masu.database import OCP_REPORT_TABLE_MAP
from masu.database.ocp_report_db_accessor import OCPReportDBAccessor
from masu.processor.ocp.ocp_cost_model_cost_updater import OCPCostModelCostUpdater
from masu.processor.ocp.ocp_cost_model_cost_updater import OCPCostModelCostUpdaterError
from masu.test import MasuTestCase
from reporting.models import OCPUsageLineItemDailySummary


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

        mock_cost_accessor.return_value.__enter__.return_value.markup = markup

        start_date = self.dh.this_month_start
        end_date = self.dh.this_month_end

        updater = OCPCostModelCostUpdater(schema=self.schema, provider=self.provider)
        updater._update_markup_cost(start_date, end_date)

        with schema_context(self.schema):
            line_items = OCPUsageLineItemDailySummary.objects.filter(
                cluster_id=self.cluster_id, usage_start__gte=start_date, usage_start__lte=end_date
            ).all()
            for line_item in line_items:
                self.assertNotEqual(line_item.infrastructure_markup_cost, 0)
                self.assertNotEqual(line_item.infrastructure_project_markup_cost, 0)
                self.assertAlmostEqual(
                    line_item.infrastructure_markup_cost, line_item.infrastructure_raw_cost * markup_dec, 6
                )
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
                cluster_id=self.cluster_id, usage_start__gte=start_date, usage_start__lte=end_date
            ).all()
            for line_item in line_items:
                self.assertEqual(line_item.infrastructure_markup_cost, 0)
                self.assertEqual(line_item.infrastructure_project_markup_cost, 0)

    @patch("masu.processor.ocp.ocp_cost_model_cost_updater.CostModelDBAccessor")
    def test_update_usage_costs(self, mock_cost_accessor):
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

        start_date = self.dh.this_month_start
        end_date = self.dh.this_month_end

        updater = OCPCostModelCostUpdater(schema=self.schema, provider=self.provider)
        updater._update_usage_costs(start_date, end_date)

        with schema_context(self.schema):
            pod_line_items = OCPUsageLineItemDailySummary.objects.filter(
                report_period__provider_id=self.ocp_provider.uuid, usage_start__gte=start_date, data_source="Pod"
            ).all()
            for line_item in pod_line_items:
                self.assertNotEqual(line_item.infrastructure_usage_cost.get("cpu"), 0)
                self.assertNotEqual(line_item.infrastructure_usage_cost.get("memory"), 0)
                self.assertEqual(line_item.infrastructure_usage_cost.get("storage"), 0)

                self.assertEqual(line_item.supplementary_usage_cost.get("cpu"), 0)
                self.assertEqual(line_item.supplementary_usage_cost.get("memory"), 0)
                self.assertEqual(line_item.supplementary_usage_cost.get("storage"), 0)

            volume_line_items = OCPUsageLineItemDailySummary.objects.filter(
                report_period__provider_id=self.ocp_provider.uuid, usage_start__gte=start_date, data_source="Storage"
            ).all()

            for line_item in volume_line_items:
                self.assertEqual(line_item.infrastructure_usage_cost.get("cpu"), 0)
                self.assertEqual(line_item.infrastructure_usage_cost.get("memory"), 0)
                self.assertEqual(line_item.infrastructure_usage_cost.get("storage"), 0)

                self.assertEqual(line_item.supplementary_usage_cost.get("cpu"), 0)
                self.assertEqual(line_item.supplementary_usage_cost.get("memory"), 0)
                self.assertNotEqual(line_item.supplementary_usage_cost.get("storage"), 0)

    @patch("masu.processor.ocp.ocp_cost_model_cost_updater.CostModelDBAccessor")
    def test_update_monthly_cost_infrastructure(self, mock_cost_accessor):
        """Test OCP charge for monthly costs is updated."""
        node_cost = random.randrange(1, 200)
        infrastructure_rates = {"node_cost_per_month": node_cost}
        mock_cost_accessor.return_value.__enter__.return_value.infrastructure_rates = infrastructure_rates
        mock_cost_accessor.return_value.__enter__.return_value.supplementary_rates = {}

        usage_period = self.accessor.get_current_usage_period()
        start_date = usage_period.report_period_start.date() + relativedelta(days=-1)
        end_date = usage_period.report_period_end.date() + relativedelta(days=+1)
        updater = OCPCostModelCostUpdater(schema=self.schema, provider=self.provider)
        updater._update_monthly_cost(start_date, end_date)
        with schema_context(self.schema):
            monthly_cost_row = OCPUsageLineItemDailySummary.objects.filter(
                infrastructure_monthly_cost__isnull=False
            ).first()
            self.assertGreater(monthly_cost_row.infrastructure_monthly_cost, 0)
            self.assertEquals(monthly_cost_row.infrastructure_monthly_cost, node_cost)

    @patch("masu.processor.ocp.ocp_cost_model_cost_updater.CostModelDBAccessor")
    def test_update_monthly_cost_supplementary(self, mock_cost_accessor):
        """Test OCP charge for monthly costs is updated."""
        node_cost = random.randrange(1, 200)
        supplementary_rates = {"node_cost_per_month": node_cost}
        mock_cost_accessor.return_value.__enter__.return_value.infrastructure_rates = {}
        mock_cost_accessor.return_value.__enter__.return_value.supplementary_rates = supplementary_rates
        usage_period = self.accessor.get_current_usage_period()
        start_date = usage_period.report_period_start.date() + relativedelta(days=-1)
        end_date = usage_period.report_period_end.date() + relativedelta(days=+1)
        updater = OCPCostModelCostUpdater(schema=self.schema, provider=self.provider)
        updater._update_monthly_cost(start_date, end_date)
        with schema_context(self.schema):
            monthly_cost_row = OCPUsageLineItemDailySummary.objects.filter(
                supplementary_monthly_cost__isnull=False
            ).first()
            self.assertGreater(monthly_cost_row.supplementary_monthly_cost, 0)
            self.assertEquals(monthly_cost_row.supplementary_monthly_cost, node_cost)

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
                    report_period__provider_id=self.ocp_provider.uuid, usage_start__gte=start_date
                )
                .values("node")
                .distinct()
                .count()
            )
            monthly_cost_rows = OCPUsageLineItemDailySummary.objects.filter(
                usage_start=start_date, infrastructure_monthly_cost__isnull=False
            ).count()
            self.assertEqual(monthly_cost_rows, expected_count)

            pod_line_item = OCPUsageLineItemDailySummary.objects.filter(
                report_period__provider_id=self.ocp_provider.uuid,
                usage_start__gte=start_date,
                infrastructure_raw_cost__isnull=False,
                data_source="Pod",
            ).first()
            volume_line_item = OCPUsageLineItemDailySummary.objects.filter(
                report_period__provider_id=self.ocp_provider.uuid,
                usage_start__gte=start_date,
                infrastructure_raw_cost__isnull=False,
                data_source="Storage",
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

        usage_period = self.accessor.get_current_usage_period()
        start_date = usage_period.report_period_start.date() + relativedelta(days=-1)
        end_date = usage_period.report_period_end.date() + relativedelta(days=+1)
        updater = OCPCostModelCostUpdater(schema=self.schema, provider=self.provider)
        updater._update_monthly_tag_based_cost(start_date, end_date)

        # assert that the Node call includes relevant information and Cluster call has nothing
        # since there was no Cluster related cost
        mock_update_monthly.assert_any_call(
            "Node", "Infrastructure", "a tag rate", start_date, end_date, self.cluster_id, updater._cluster_alias
        )
        mock_update_monthly.assert_any_call(
            "Cluster", None, None, start_date, end_date, self.cluster_id, updater._cluster_alias
        )
        mock_update_monthly.assert_any_call(
            "PVC", None, None, start_date, end_date, self.cluster_id, updater._cluster_alias
        )
        self.assertEqual(mock_update_monthly.call_count, 3)

    @patch("masu.database.ocp_report_db_accessor.OCPReportDBAccessor.populate_monthly_tag_cost")
    @patch("masu.processor.ocp.ocp_cost_model_cost_updater.CostModelDBAccessor")
    def test_tag_update_monthly_cost_supplementary(self, mock_cost_accessor, mock_update_monthly):
        """Test that _update_monthly_tag_based_cost is called with the correct cost_type and rate."""
        # using a string instead of an actual rate for the purposes of testing that the function is called
        mock_cost_accessor.return_value.__enter__.return_value.tag_infrastructure_rates = {}
        mock_cost_accessor.return_value.__enter__.return_value.tag_supplementary_rates = {
            "cluster_cost_per_month": "a tag rate"
        }

        usage_period = self.accessor.get_current_usage_period()
        start_date = usage_period.report_period_start.date() + relativedelta(days=-1)
        end_date = usage_period.report_period_end.date() + relativedelta(days=+1)
        updater = OCPCostModelCostUpdater(schema=self.schema, provider=self.provider)
        updater._update_monthly_tag_based_cost(start_date, end_date)

        # assert that the Cluster call includes relevant information and Node call has nothing
        # since there was no Node related cost
        mock_update_monthly.assert_any_call(
            "Node", None, None, start_date, end_date, self.cluster_id, updater._cluster_alias
        )
        mock_update_monthly.assert_any_call(
            "Cluster", "Supplementary", "a tag rate", start_date, end_date, self.cluster_id, updater._cluster_alias
        )
        mock_update_monthly.assert_any_call(
            "PVC", None, None, start_date, end_date, self.cluster_id, updater._cluster_alias
        )
        self.assertEqual(mock_update_monthly.call_count, 3)

    @patch("masu.database.ocp_report_db_accessor.OCPReportDBAccessor.populate_tag_usage_costs")
    @patch("masu.processor.ocp.ocp_cost_model_cost_updater.CostModelDBAccessor")
    def test_update_tag_usage_costs(self, mock_cost_accessor, mock_update_usage):
        """Test that populate_tag_usage_cost is called with the correct cost_type and rate."""
        # using a string instead of an actual rate for the purposes of testing that the function is called
        infrastructure_rates = {"cpu_core_usage_per_hour": "another tag rate"}
        supplementary_rates = {"memory_gb_usage_per_hour": "a tag rate"}
        mock_cost_accessor.return_value.__enter__.return_value.tag_infrastructure_rates = infrastructure_rates
        mock_cost_accessor.return_value.__enter__.return_value.tag_supplementary_rates = supplementary_rates

        usage_period = self.accessor.get_current_usage_period()
        start_date = usage_period.report_period_start.date() + relativedelta(days=-1)
        end_date = usage_period.report_period_end.date() + relativedelta(days=+1)
        updater = OCPCostModelCostUpdater(schema=self.schema, provider=self.provider)
        updater._update_tag_usage_costs(start_date, end_date)
        # assert that populate_tag_usage_costs was called with the correct info
        mock_update_usage.assert_called_once_with(
            infrastructure_rates, supplementary_rates, start_date, end_date, self.cluster_id
        )
