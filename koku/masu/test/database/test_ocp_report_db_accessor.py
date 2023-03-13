#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the OCPReportDBAccessor utility object."""
import random
import string
import uuid
from collections import defaultdict
from datetime import datetime
from unittest.mock import Mock
from unittest.mock import patch

from dateutil import relativedelta
from django.conf import settings
from django.db.models import Max
from django.db.models import Min
from django.db.models import Q
from django.db.models import Sum
from django.db.models.query import QuerySet
from tenant_schemas.utils import schema_context
from trino.exceptions import TrinoExternalError

from api.iam.test.iam_test_case import FakeTrinoConn
from api.utils import DateHelper
from koku import trino_database as trino_db
from masu.database import AWS_CUR_TABLE_MAP
from masu.database import OCP_REPORT_TABLE_MAP
from masu.database.ocp_report_db_accessor import OCPReportDBAccessor
from masu.database.provider_db_accessor import ProviderDBAccessor
from masu.external.date_accessor import DateAccessor
from masu.test import MasuTestCase
from masu.test.database.helpers import ReportObjectCreator
from reporting.models import OCPEnabledTagKeys
from reporting.models import OCPStorageVolumeLabelSummary
from reporting.models import OCPUsageLineItemDailySummary
from reporting.models import OCPUsagePodLabelSummary
from reporting.provider.ocp.models import OCPCluster
from reporting.provider.ocp.models import OCPNode
from reporting.provider.ocp.models import OCPProject
from reporting.provider.ocp.models import OCPPVC
from reporting_common import REPORT_COLUMN_MAP


class OCPReportDBAccessorTest(MasuTestCase):
    """Test Cases for the OCPReportDBAccessor object."""

    @classmethod
    def setUpClass(cls):
        """Set up the test class with required objects."""
        super().setUpClass()

        cls.accessor = OCPReportDBAccessor(schema=cls.schema)
        cls.report_schema = cls.accessor.report_schema
        cls.creator = ReportObjectCreator(cls.schema)
        cls.all_tables = list(OCP_REPORT_TABLE_MAP.values())

    def setUp(self):
        """Set up a test with database objects."""
        super().setUp()

        self.cluster_id = "testcluster"
        with ProviderDBAccessor(provider_uuid=self.ocp_test_provider_uuid) as provider_accessor:
            self.ocp_provider_uuid = provider_accessor.get_provider().uuid

        self.reporting_period = self.creator.create_ocp_report_period(
            provider_uuid=self.ocp_provider_uuid, cluster_id=self.cluster_id
        )
        self.report = self.creator.create_ocp_report(self.reporting_period)
        pod = "".join(random.choice(string.ascii_lowercase) for _ in range(10))
        namespace = "".join(random.choice(string.ascii_lowercase) for _ in range(10))
        node = "".join(random.choice(string.ascii_lowercase) for _ in range(10))
        self.creator.create_ocp_usage_line_item(self.reporting_period, self.report, pod=pod, namespace=namespace)
        self.creator.create_ocp_storage_line_item(self.reporting_period, self.report, pod=pod, namespace=namespace)
        self.creator.create_ocp_node_label_line_item(self.reporting_period, self.report, node=node)

    def test_initializer(self):
        """Test initializer."""
        self.assertIsNotNone(self.report_schema)

    def test_get_db_obj_query_default(self):
        """Test that a query is returned."""
        table_name = random.choice(self.all_tables)

        query = self.accessor._get_db_obj_query(table_name)

        self.assertIsInstance(query, QuerySet)

    def test_get_db_obj_query_with_columns(self):
        """Test that a query is returned with limited columns."""
        table_name = OCP_REPORT_TABLE_MAP["line_item"]
        columns = list(REPORT_COLUMN_MAP[table_name].values())

        selected_columns = [random.choice(columns) for _ in range(2)]
        missing_columns = set(columns).difference(selected_columns)

        query = self.accessor._get_db_obj_query(table_name, columns=selected_columns)
        self.assertIsInstance(query, QuerySet)
        with schema_context(self.schema):
            result = query.first()

            for column in selected_columns:
                self.assertTrue(column in result)

            for column in missing_columns:
                self.assertFalse(column in result)

    def test_get_current_usage_period(self):
        """Test that the most recent usage period is returned."""
        current_report_period = self.accessor.get_current_usage_period(self.ocp_provider_uuid)
        self.assertIsNotNone(current_report_period.report_period_start)
        self.assertIsNotNone(current_report_period.report_period_end)

    def test_get_usage_period_by_dates_and_cluster(self):
        """Test that report periods are returned by dates & cluster filter."""
        period_start = DateAccessor().today_with_timezone("UTC").replace(day=1)
        period_end = period_start + relativedelta.relativedelta(months=1)
        prev_period_start = period_start - relativedelta.relativedelta(months=1)
        prev_period_end = prev_period_start + relativedelta.relativedelta(months=1)
        reporting_period = self.creator.create_ocp_report_period(
            self.ocp_provider_uuid, period_date=period_start, cluster_id="0001"
        )
        prev_reporting_period = self.creator.create_ocp_report_period(
            self.ocp_provider_uuid, period_date=prev_period_start, cluster_id="0002"
        )
        with schema_context(self.schema):
            periods = self.accessor.get_usage_period_by_dates_and_cluster(
                period_start.date(), period_end.date(), "0001"
            )
            self.assertEqual(reporting_period, periods)
            periods = self.accessor.get_usage_period_by_dates_and_cluster(
                prev_period_start.date(), prev_period_end.date(), "0002"
            )
            self.assertEqual(prev_reporting_period, periods)

    def test_get_usage_period_query_by_provider(self):
        """Test that periods are returned filtered by provider."""
        provider_uuid = self.ocp_provider_uuid

        period_query = self.accessor.get_usage_period_query_by_provider(provider_uuid)
        with schema_context(self.schema):
            periods = period_query.all()

            self.assertGreater(len(periods), 0)

            period = periods[0]

            self.assertEqual(period.provider_id, provider_uuid)

    def test_report_periods_for_provider_uuid(self):
        """Test that periods are returned filtered by provider id and start date."""
        provider_uuid = self.ocp_provider_uuid
        start_date = str(self.reporting_period.report_period_start)

        period = self.accessor.report_periods_for_provider_uuid(provider_uuid, start_date)
        with schema_context(self.schema):
            self.assertEqual(period.provider_id, provider_uuid)

    @patch("masu.database.ocp_report_db_accessor.trino_table_exists")
    @patch("masu.database.ocp_report_db_accessor.trino_db.executescript")
    @patch("masu.database.ocp_report_db_accessor.trino_db.connect")
    def test_populate_line_item_daily_summary_table_trino(self, mock_connect, mock_executescript, mock_table_exists):
        """
        Test that OCP trino processing calls executescript
        """
        trino_conn = FakeTrinoConn()
        mock_table_exists.return_value = True
        mock_connect.return_value = trino_conn
        mock_executescript.return_value = []
        dh = DateHelper()
        start_date = dh.this_month_start
        end_date = dh.next_month_start
        cluster_id = "ocp-cluster"
        cluster_alias = "OCP FTW"
        report_period_id = 1
        source = self.provider_uuid
        self.accessor.populate_line_item_daily_summary_table_trino(
            start_date, end_date, report_period_id, cluster_id, cluster_alias, source
        )
        mock_connect.assert_called()
        mock_executescript.assert_called()

    # @patch("masu.util.common.trino_table_exists")
    @patch("masu.database.ocp_report_db_accessor.trino_table_exists")
    @patch("masu.database.ocp_report_db_accessor.pkgutil.get_data")
    @patch("masu.database.ocp_report_db_accessor.trino_db.connect")
    def test_populate_line_item_daily_summary_table_trino_preprocess_exception(
        self, mock_connect, mock_get_data, mock_table_exists
    ):
        """
        Test that OCP trino processing converts datetime to date for start, end dates
        """
        trino_conn = FakeTrinoConn()
        mock_table_exists.return_value = True
        mock_connect.return_value = trino_conn
        mock_get_data.return_value = b"""
select * from eek where val1 in {{report_period_id}} ;
"""
        start_date = "2020-01-01"
        end_date = "2020-02-01"
        report_period_id = (1, 2)  # This should generate a preprocessor error
        cluster_id = "ocp-cluster"
        cluster_alias = "OCP FTW"
        source = self.provider_uuid
        with self.assertRaises(trino_db.PreprocessStatementError):
            self.accessor.populate_line_item_daily_summary_table_trino(
                start_date, end_date, report_period_id, cluster_id, cluster_alias, source
            )

    def test_populate_node_label_line_item_daily_table(self):
        """Test that the node label line item daily table populates."""
        report_table_name = OCP_REPORT_TABLE_MAP["report"]
        daily_table_name = OCP_REPORT_TABLE_MAP["node_label_line_item_daily"]

        report_table = getattr(self.accessor.report_schema, report_table_name)
        daily_table = getattr(self.accessor.report_schema, daily_table_name)

        for _ in range(5):
            self.creator.create_ocp_node_label_line_item(self.reporting_period, self.report)

        with schema_context(self.schema):
            report_entry = report_table.objects.all().aggregate(Min("interval_start"), Max("interval_start"))
            start_date = report_entry["interval_start__min"]
            end_date = report_entry["interval_start__max"]

        start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = end_date.replace(hour=0, minute=0, second=0, microsecond=0)

        query = self.accessor._get_db_obj_query(daily_table_name)
        with schema_context(self.schema):
            initial_count = query.count()

        self.accessor.populate_node_label_line_item_daily_table(start_date, end_date, self.cluster_id)

        self.assertNotEqual(query.count(), initial_count)

        with schema_context(self.schema):
            daily_entry = daily_table.objects.all().aggregate(Min("usage_start"), Max("usage_start"))
            result_start_date = daily_entry["usage_start__min"]
            result_end_date = daily_entry["usage_start__max"]

        self.assertEqual(result_start_date, start_date.date())
        self.assertEqual(result_end_date, end_date.date())

        with schema_context(self.schema):
            entry = query.first()

            summary_columns = ["cluster_id", "node", "node_labels", "total_seconds", "usage_end", "usage_start"]

            for column in summary_columns:
                self.assertIsNotNone(getattr(entry, column))

    def test_populate_tag_based_usage_costs(self):  # noqa: C901
        """
        Test that the usage costs are updated when tag values are passed in.
        This test runs for both Infrastructure and Supplementary cost types
        as well as all 6 metrics that apply to this update
        and uses subtests that will identify the metric, the tag value, the line item id, and the cost type if it fails.
        """
        # set up the key value pairs to test and the map for cost type and the fields it needs
        key_value_pairs = {"app": ["banking", "mobile", "weather"]}
        cost_type = {
            "cpu_core_usage_per_hour": ["cpu", "pod_usage_cpu_core_hours"],
            "cpu_core_request_per_hour": ["cpu", "pod_request_cpu_core_hours"],
            "memory_gb_usage_per_hour": ["memory", "pod_usage_memory_gigabyte_hours"],
            "memory_gb_request_per_hour": ["memory", "pod_request_memory_gigabyte_hours"],
            "storage_gb_usage_per_month": ["storage", "persistentvolumeclaim_usage_gigabyte_months"],
            "storage_gb_request_per_month": ["storage", "volume_request_storage_gigabyte_months"],
        }

        dh = DateHelper()
        start_date = dh.this_month_start
        end_date = dh.this_month_end
        self.cluster_id = "OCP-on-AWS"
        with schema_context(self.schema):
            # define the two usage types to test
            usage_types = ("Infrastructure", "Supplementary")
            for usage_type in usage_types:
                # create dictionaries for rates
                for cost, usage_fields in cost_type.items():
                    if usage_fields[0] == "cpu":
                        cost_term = "cost_model_cpu_cost"
                    elif usage_fields[0] == "memory":
                        cost_term = "cost_model_memory_cost"
                    elif usage_fields[0] == "storage":
                        cost_term = "cost_model_volume_cost"
                    rate_costs = {}
                    # go through and populate values for the key value pairs for this usage and cost type
                    node_tag_rates = {}
                    for key, values in key_value_pairs.items():
                        values_dict = {}
                        for value in values:
                            node_rate = random.randrange(1, 100)
                            values_dict[value] = node_rate
                        node_tag_rates[key] = values_dict
                    rate_costs[cost] = node_tag_rates
                    # define the arguments for the function based on what usage type needs to be tested
                    if usage_type == "Infrastructure":
                        infrastructure_rates = rate_costs
                        supplementary_rates = {}
                    else:
                        infrastructure_rates = {}
                        supplementary_rates = rate_costs
                    # get the three querysets to be evaluated based on the pod_labels
                    banking_qset = (
                        OCPUsageLineItemDailySummary.objects.filter(
                            cluster_id=self.cluster_id, pod_labels__contains={"app": "banking"}
                        )
                        .values("usage_start")
                        .annotate(
                            cost=Sum(cost_term),
                            usage=Sum(usage_fields[1]),
                        )
                    )
                    mobile_qset = (
                        OCPUsageLineItemDailySummary.objects.filter(
                            cluster_id=self.cluster_id, pod_labels__contains={"app": "mobile"}
                        )
                        .values("usage_start")
                        .annotate(
                            cost=Sum(cost_term),
                            usage=Sum(usage_fields[1]),
                        )
                    )
                    weather_qset = (
                        OCPUsageLineItemDailySummary.objects.filter(
                            cluster_id=self.cluster_id, pod_labels__contains={"app": "weather"}
                        )
                        .values("usage_start")
                        .annotate(
                            cost=Sum(cost_term),
                            usage=Sum(usage_fields[1]),
                        )
                    )

                    # populate a results dictionary for each item in the querysets using the cost before the update
                    initial_results_dict = defaultdict(dict)
                    mapper = {
                        "banking": (banking_qset, {"app": "banking"}),
                        "mobile": (mobile_qset, {"app": "mobile"}),
                        "weather": (weather_qset, {"app": "weather"}),
                    }
                    for word, qset_tuple in mapper.items():
                        qset = qset_tuple[0]
                        for entry in qset:
                            # For each label, by date store the usage, cost
                            initial_results_dict[word][entry.get("usage_start")] = (
                                entry.get("usage") or 0,
                                entry.get("cost") or 0,
                            )

                    # call populate monthly tag_cost with the rates defined above
                    self.accessor.populate_tag_usage_costs(
                        infrastructure_rates, supplementary_rates, start_date, end_date, self.cluster_id
                    )

                    # get the three querysets to be evaluated based on the pod_labels after the update
                    banking_qset = (
                        OCPUsageLineItemDailySummary.objects.filter(
                            cluster_id=self.cluster_id,
                            pod_labels__contains={"app": "banking"},
                            monthly_cost_type="Tag",
                        )
                        .values("usage_start")
                        .annotate(
                            cost=Sum(cost_term),
                            usage=Sum(usage_fields[1]),
                        )
                    )
                    mobile_qset = (
                        OCPUsageLineItemDailySummary.objects.filter(
                            cluster_id=self.cluster_id, pod_labels__contains={"app": "mobile"}, monthly_cost_type="Tag"
                        )
                        .values("usage_start")
                        .annotate(
                            cost=Sum(cost_term),
                            usage=Sum(usage_fields[1]),
                        )
                    )
                    weather_qset = (
                        OCPUsageLineItemDailySummary.objects.filter(
                            cluster_id=self.cluster_id,
                            pod_labels__contains={"app": "weather"},
                            monthly_cost_type="Tag",
                        )
                        .values("usage_start")
                        .annotate(
                            cost=Sum(cost_term),
                            usage=Sum(usage_fields[1]),
                        )
                    )

                    # update the querysets stored in mapper
                    mapper = {"banking": banking_qset, "mobile": mobile_qset, "weather": weather_qset}
                    # get the values from after the call and store them in the dictionary
                    post_results_dict = defaultdict(dict)
                    for word, qset in mapper.items():
                        for entry in qset:
                            post_results_dict[word][entry.get("usage_start")] = (
                                entry.get("usage") or 0,
                                entry.get("cost") or 0,
                            )

                    # assert that after the update, the appropriate values were added to each usage_cost
                    # the date check ensures that only entries after start date were updated and the ones
                    # outside the start and end date are not updated
                    for value, rate in rate_costs.get(cost).get("app").items():
                        for day, vals in initial_results_dict.get(value).items():

                            with self.subTest(
                                msg=f"Metric: {cost}, Value: {value}, usage_type: {usage_type}, id: {day}"
                            ):
                                if day >= start_date.date():
                                    expected_diff = float(vals[0] * rate)
                                else:
                                    expected_diff = 0
                                post_record = post_results_dict.get(value, {}).get(day, {})
                                actual_diff = 0
                                if post_record:
                                    actual_diff = float(post_record[1] - vals[1])
                                self.assertAlmostEqual(actual_diff, expected_diff)

    def test_populate_tag_based_default_usage_costs(self):  # noqa: C901
        """Test that the usage costs are updated correctly when default tag values are passed in."""
        # set up the key value pairs to test and the map for cost type and the fields it needs
        cost_type = {
            "cpu_core_usage_per_hour": ["cpu", "pod_usage_cpu_core_hours"],
            "cpu_core_request_per_hour": ["cpu", "pod_request_cpu_core_hours"],
            "memory_gb_usage_per_hour": ["memory", "pod_usage_memory_gigabyte_hours"],
            "memory_gb_request_per_hour": ["memory", "pod_request_memory_gigabyte_hours"],
            "storage_gb_usage_per_month": ["storage", "persistentvolumeclaim_usage_gigabyte_months"],
            "storage_gb_request_per_month": ["storage", "volume_request_storage_gigabyte_months"],
        }

        dh = DateHelper()
        start_date = dh.this_month_start
        end_date = dh.this_month_end
        self.cluster_id = "OCP-on-AWS"
        with schema_context(self.schema):
            # define the two usage types to test
            usage_types = ("Infrastructure", "Supplementary")
            for usage_type in usage_types:
                # create dictionaries for rates
                for cost, usage_fields in cost_type.items():
                    if usage_fields[0] == "cpu":
                        cost_term = "cost_model_cpu_cost"
                    elif usage_fields[0] == "memory":
                        cost_term = "cost_model_memory_cost"
                    elif usage_fields[0] == "storage":
                        cost_term = "cost_model_volume_cost"
                    rate_costs = {}
                    """
                    {
                        'cpu_core_usage_per_hour': {
                            'app': {
                                'default_value': '100.0000000000', 'defined_keys': ['far', 'manager', 'walk']
                        }
                    }
                    """

                    rate_costs[cost] = {
                        "app": {"default_value": random.randrange(1, 100), "defined_keys": ["mobile", "banking"]}
                    }
                    # define the arguments for the function based on what usage type needs to be tested
                    if usage_type == "Infrastructure":
                        infrastructure_rates = rate_costs
                        supplementary_rates = {}
                    else:
                        infrastructure_rates = {}
                        supplementary_rates = rate_costs
                    # get the three querysets to be evaluated based on the pod_labels
                    banking_qset = (
                        OCPUsageLineItemDailySummary.objects.filter(
                            cluster_id=self.cluster_id, pod_labels__contains={"app": "banking"}
                        )
                        .values("usage_start")
                        .annotate(
                            cost=Sum(cost_term),
                            usage=Sum(usage_fields[1]),
                        )
                    )
                    mobile_qset = (
                        OCPUsageLineItemDailySummary.objects.filter(
                            cluster_id=self.cluster_id, pod_labels__contains={"app": "mobile"}
                        )
                        .values("usage_start")
                        .annotate(
                            usage=Sum(usage_fields[1]),
                            cost=Sum(cost_term),
                        )
                    )
                    weather_qset = (
                        OCPUsageLineItemDailySummary.objects.filter(
                            cluster_id=self.cluster_id, pod_labels__contains={"app": "weather"}
                        )
                        .values("usage_start")
                        .annotate(
                            usage=Sum(usage_fields[1]),
                            cost=Sum(cost_term),
                        )
                    )

                    # populate a results dictionary for each item in the querysets using the cost before the update
                    initial_results_dict = defaultdict(dict)
                    mapper = {"banking": banking_qset, "mobile": mobile_qset, "weather": weather_qset}
                    for word, qset in mapper.items():
                        for entry in qset:
                            # For each label, by date store the usage, cost
                            initial_results_dict[word][entry.get("usage_start")] = (
                                entry.get("usage") or 0,
                                entry.get("cost") or 0,
                            )

                    # call populate monthly tag_cost with the rates defined above
                    self.accessor.populate_tag_usage_default_costs(
                        infrastructure_rates, supplementary_rates, start_date, end_date, self.cluster_id
                    )

                    # get the three querysets to be evaluated based on the pod_labels after the update
                    banking_qset = (
                        OCPUsageLineItemDailySummary.objects.filter(
                            cluster_id=self.cluster_id,
                            pod_labels__contains={"app": "banking"},
                            monthly_cost_type="Tag",
                        )
                        .values("usage_start")
                        .annotate(
                            cost=Sum(cost_term),
                            usage=Sum(usage_fields[1]),
                        )
                    )
                    mobile_qset = (
                        OCPUsageLineItemDailySummary.objects.filter(
                            cluster_id=self.cluster_id, pod_labels__contains={"app": "mobile"}, monthly_cost_type="Tag"
                        )
                        .values("usage_start")
                        .annotate(
                            cost=Sum(cost_term),
                            usage=Sum(usage_fields[1]),
                        )
                    )
                    weather_qset = (
                        OCPUsageLineItemDailySummary.objects.filter(
                            cluster_id=self.cluster_id,
                            pod_labels__contains={"app": "weather"},
                            monthly_cost_type="Tag",
                        )
                        .values("usage_start")
                        .annotate(
                            cost=Sum(cost_term),
                            usage=Sum(usage_fields[1]),
                        )
                    )

                    # update the querysets stored in mapper
                    mapper = {"banking": banking_qset, "mobile": mobile_qset, "weather": weather_qset}
                    # get the values from after the call and store them in the dictionary
                    post_results_dict = defaultdict(dict)
                    for word, qset in mapper.items():
                        for entry in qset:
                            post_results_dict[word][entry.get("usage_start")] = (
                                entry.get("usage") or 0,
                                entry.get("cost") or 0,
                            )

                    # assert that after the update, the appropriate values were added to each usage_cost
                    # the date check ensures that only entries after start date were updated and the ones
                    # outside the start and end date are not updated
                    for value in mapper:
                        for day, vals in initial_results_dict.get(value).items():
                            with self.subTest(
                                msg=f"Metric: {cost}, Value: {value}, usage_type: {usage_type}, day: {day}"
                            ):
                                if value == "banking" or value == "mobile":
                                    expected_diff = 0
                                else:
                                    if day >= start_date.date():
                                        rate = rate_costs.get(cost).get("app").get("default_value")
                                        expected_diff = float(vals[0] * rate)
                                    else:
                                        expected_diff = 0
                                post_record = post_results_dict.get(value, {}).get(day, {})
                                actual_diff = 0
                                if post_record:
                                    actual_diff = float(post_record[1] - vals[1])
                                self.assertAlmostEqual(actual_diff, expected_diff)

    def test_update_line_item_daily_summary_with_enabled_tags(self):
        """Test that we filter the daily summary table's tags with only enabled tags."""
        dh = DateHelper()
        start_date = dh.this_month_start.date()
        end_date = dh.this_month_end.date()

        report_period = self.accessor.report_periods_for_provider_uuid(self.ocp_provider_uuid, start_date)

        with schema_context(self.schema):
            OCPUsagePodLabelSummary.objects.all().delete()
            OCPStorageVolumeLabelSummary.objects.all().delete()
            key_to_keep = OCPEnabledTagKeys.objects.filter(key="app").first()
            OCPEnabledTagKeys.objects.all().update(enabled=False)
            OCPEnabledTagKeys.objects.filter(key="app").update(enabled=True)
            report_period_ids = [report_period.id]
            self.accessor.update_line_item_daily_summary_with_enabled_tags(start_date, end_date, report_period_ids)
            tags = (
                OCPUsageLineItemDailySummary.objects.filter(
                    usage_start__gte=start_date, report_period_id__in=report_period_ids
                )
                .values_list("pod_labels")
                .distinct()
            )

            for tag in tags:
                tag_dict = tag[0] if tag[0] is not None else {}  # Account for possible null
                tag_keys = list(tag_dict.keys())
                if tag_keys:
                    self.assertEqual([key_to_keep.key], tag_keys)
                else:
                    self.assertEqual([], tag_keys)

            tags = (
                OCPUsageLineItemDailySummary.objects.filter(
                    usage_start__gte=start_date, report_period_id__in=report_period_ids
                )
                .values_list("volume_labels")
                .distinct()
            )

            for tag in tags:
                tag_dict = tag[0] if tag[0] is not None else {}  # Account for possible null
                tag_keys = list(tag_dict.keys())
                if tag_keys:
                    self.assertEqual([key_to_keep.key], tag_keys)
                else:
                    self.assertEqual([], tag_keys)

    def test_delete_line_item_daily_summary_entries_for_date_range(self):
        """Test that daily summary rows are deleted."""
        with schema_context(self.schema):
            start_date = OCPUsageLineItemDailySummary.objects.aggregate(Max("usage_start")).get("usage_start__max")
            end_date = start_date

        table_query = OCPUsageLineItemDailySummary.objects.filter(
            source_uuid=self.ocp_provider_uuid, usage_start__gte=start_date, usage_start__lte=end_date
        )
        with schema_context(self.schema):
            self.assertNotEqual(table_query.count(), 0)

        self.accessor.delete_line_item_daily_summary_entries_for_date_range(
            self.ocp_provider_uuid, start_date, end_date
        )

        with schema_context(self.schema):
            self.assertEqual(table_query.count(), 0)

    def test_table_properties(self):
        self.assertEqual(self.accessor.line_item_daily_summary_table, OCPUsageLineItemDailySummary)

    def test_table_map(self):
        self.assertEqual(self.accessor._table_map, OCP_REPORT_TABLE_MAP)
        self.assertEqual(self.accessor._aws_table_map, AWS_CUR_TABLE_MAP)

    @patch("masu.database.ocp_report_db_accessor.OCPReportDBAccessor._execute_trino_raw_sql_query")
    def test_get_ocp_infrastructure_map_trino(self, mock_trino):
        """Test that Trino is used to find matched tags."""
        dh = DateHelper()
        start_date = dh.this_month_start.date()
        end_date = dh.this_month_end.date()

        self.accessor.get_ocp_infrastructure_map_trino(start_date, end_date)
        mock_trino.assert_called()

    @patch("masu.database.ocp_report_db_accessor.OCPReportDBAccessor._execute_trino_raw_sql_query")
    def test_get_ocp_infrastructure_map_trino_gcp_resource(self, mock_trino):
        """Test that Trino is used to find matched resource names."""
        dh = DateHelper()
        start_date = dh.this_month_start.date()
        end_date = dh.this_month_end.date()
        expected_log = "INFO:masu.util.gcp.common:OCP GCP matching set to resource level"
        with patch(
            "masu.util.gcp.common.ProviderDBAccessor.get_data_source",
            Mock(return_value={"table_id": "resource"}),
        ):
            with self.assertLogs("masu.util.gcp.common", level="INFO") as logger:
                self.accessor.get_ocp_infrastructure_map_trino(
                    start_date, end_date, gcp_provider_uuid=self.gcp_provider_uuid
                )
                mock_trino.assert_called()
                self.assertIn(expected_log, logger.output)

    @patch("masu.database.ocp_report_db_accessor.OCPReportDBAccessor._execute_trino_raw_sql_query")
    def test_get_ocp_infrastructure_map_trino_gcp_with_disabled_resource_matching(self, mock_trino):
        """Test that Trino is used to find matched resource names."""
        dh = DateHelper()
        start_date = dh.this_month_start.date()
        end_date = dh.this_month_end.date()
        expected_log = f"INFO:masu.util.gcp.common:GCP resource matching disabled for {self.schema}"
        with patch("masu.util.gcp.common.disable_gcp_resource_matching", return_value=True):
            with self.assertLogs("masu", level="INFO") as logger:
                self.accessor.get_ocp_infrastructure_map_trino(
                    start_date, end_date, gcp_provider_uuid=self.gcp_provider_uuid
                )
                mock_trino.assert_called()
                self.assertIn(expected_log, logger.output)

    @patch("masu.database.ocp_report_db_accessor.trino_table_exists")
    @patch("masu.database.ocp_report_db_accessor.OCPReportDBAccessor.get_projects_trino")
    @patch("masu.database.ocp_report_db_accessor.OCPReportDBAccessor.get_pvcs_trino")
    @patch("masu.database.ocp_report_db_accessor.OCPReportDBAccessor.get_nodes_trino")
    def test_populate_openshift_cluster_information_tables(
        self, mock_get_nodes, mock_get_pvcs, mock_get_projects, mock_table
    ):
        """Test that we populate cluster info."""
        nodes = ["test_node_1", "test_node_2"]
        resource_ids = ["id_1", "id_2"]
        capacity = [1, 1]
        volumes = ["vol_1", "vol_2"]
        pvcs = ["pvc_1", "pvc_2"]
        projects = ["project_1", "project_2"]
        roles = ["master", "worker"]
        mock_get_nodes.return_value = zip(nodes, resource_ids, capacity, roles)
        mock_get_pvcs.return_value = zip(volumes, pvcs)
        mock_get_projects.return_value = projects
        mock_table.return_value = True
        cluster_id = uuid.uuid4()
        cluster_alias = "test-cluster-1"
        dh = DateHelper()
        start_date = dh.this_month_start.date()
        end_date = dh.this_month_end.date()

        self.accessor.populate_openshift_cluster_information_tables(
            self.ocp_provider, cluster_id, cluster_alias, start_date, end_date
        )

        with schema_context(self.schema):
            self.assertIsNotNone(OCPCluster.objects.filter(cluster_id=cluster_id).first())
            for node in nodes:
                db_node = OCPNode.objects.filter(node=node).first()
                self.assertIsNotNone(db_node)
                self.assertIsNotNone(db_node.node)
                self.assertIsNotNone(db_node.resource_id)
                self.assertIsNotNone(db_node.node_capacity_cpu_cores)
                self.assertIsNotNone(db_node.cluster_id)
                self.assertIsNotNone(db_node.node_role)
            for pvc in pvcs:
                self.assertIsNotNone(OCPPVC.objects.filter(persistent_volume_claim=pvc).first())
            for project in projects:
                self.assertIsNotNone(OCPProject.objects.filter(project=project).first())

        mock_table.reset_mock()
        mock_get_pvcs.reset_mock()
        mock_table.return_value = False

        self.accessor.populate_openshift_cluster_information_tables(
            self.ocp_provider, cluster_id, cluster_alias, start_date, end_date
        )
        mock_get_pvcs.assert_not_called()

    @patch("masu.database.ocp_report_db_accessor.trino_table_exists")
    @patch("masu.database.ocp_report_db_accessor.OCPReportDBAccessor.get_projects_trino")
    @patch("masu.database.ocp_report_db_accessor.OCPReportDBAccessor.get_pvcs_trino")
    @patch("masu.database.ocp_report_db_accessor.OCPReportDBAccessor.get_nodes_trino")
    def test_get_openshift_topology_for_multiple_providers(
        self, mock_get_nodes, mock_get_pvcs, mock_get_projects, mock_table
    ):
        """Test that OpenShift topology is populated."""
        nodes = ["test_node_1", "test_node_2"]
        resource_ids = ["id_1", "id_2"]
        capacity = [1, 1]
        volumes = ["vol_1", "vol_2"]
        pvcs = ["pvc_1", "pvc_2"]
        projects = ["project_1", "project_2"]
        roles = ["master", "worker"]
        mock_get_nodes.return_value = zip(nodes, resource_ids, capacity, roles)
        mock_get_pvcs.return_value = zip(volumes, pvcs)
        mock_get_projects.return_value = projects
        mock_table.return_value = True
        cluster_id = str(uuid.uuid4())
        cluster_alias = "test-cluster-1"
        dh = DateHelper()
        start_date = dh.this_month_start.date()
        end_date = dh.this_month_end.date()

        # Using the aws_provider to short cut this test instead of creating a brand
        # new provider. The OCP providers already have data, and can't be used here
        self.accessor.populate_openshift_cluster_information_tables(
            self.aws_provider, cluster_id, cluster_alias, start_date, end_date
        )

        with schema_context(self.schema):
            cluster = OCPCluster.objects.filter(cluster_id=cluster_id).first()
            nodes = OCPNode.objects.filter(cluster=cluster).all()
            pvcs = OCPPVC.objects.filter(cluster=cluster).all()
            projects = OCPProject.objects.filter(cluster=cluster).all()
            topology = self.accessor.get_openshift_topology_for_multiple_providers([self.aws_provider])
            self.assertEqual(len(topology), 1)
            topo = topology[0]
            self.assertEqual(topo.get("cluster_id"), cluster_id)
            self.assertEqual(nodes.count(), len(topo.get("nodes")))
            for node in nodes:
                self.assertIn(node.node, topo.get("nodes"))
            for pvc in pvcs:
                self.assertIn(pvc.persistent_volume_claim, topo.get("persistent_volume_claims"))
                self.assertIn(pvc.persistent_volume, topo.get("persistent_volumes"))
            for project in projects:
                self.assertIn(project.project, topo.get("projects"))

    def test_populate_node_table_update_role(self):
        """Test that populating the node table for an entry that previously existed fills the node role correctly."""
        node_info = ["node_role_test_node", "node_role_test_id", 1, "worker"]
        cluster_id = str(uuid.uuid4())
        cluster_alias = "node_role_test"
        cluster = self.accessor.populate_cluster_table(self.aws_provider, cluster_id, cluster_alias)
        with schema_context(self.schema):
            node = OCPNode.objects.create(
                node=node_info[0], resource_id=node_info[1], node_capacity_cpu_cores=node_info[2], cluster=cluster
            )
            self.assertIsNone(node.node_role)
            self.accessor.populate_node_table(cluster, [node_info])
            node = OCPNode.objects.get(
                node=node_info[0], resource_id=node_info[1], node_capacity_cpu_cores=node_info[2], cluster=cluster
            )
            self.assertEqual(node.node_role, node_info[3])

    def test_populate_node_table_second_time_no_change(self):
        """Test that populating the node table for an entry a second time does not duplicate entries."""
        node_info = ["node_role_test_node", "node_role_test_id", 1, "worker"]
        cluster_id = str(uuid.uuid4())
        cluster_alias = "node_role_test"
        cluster = self.accessor.populate_cluster_table(self.aws_provider, cluster_id, cluster_alias)
        with schema_context(self.schema):
            self.accessor.populate_node_table(cluster, [node_info])
            node_count = OCPNode.objects.filter(
                node=node_info[0], resource_id=node_info[1], node_capacity_cpu_cores=node_info[2], cluster=cluster
            ).count()
            self.assertEqual(node_count, 1)
            self.accessor.populate_node_table(cluster, [node_info])
            node_count = OCPNode.objects.filter(
                node=node_info[0], resource_id=node_info[1], node_capacity_cpu_cores=node_info[2], cluster=cluster
            ).count()
            self.assertEqual(node_count, 1)

    def test_delete_infrastructure_raw_cost_from_daily_summary(self):
        """Test that infra raw cost is deleted."""
        dh = DateHelper()
        start_date = dh.this_month_start.date()
        end_date = dh.this_month_end.date()
        report_period = self.accessor.report_periods_for_provider_uuid(self.ocpaws_provider_uuid, start_date)
        with schema_context(self.schema):
            report_period_id = report_period.id
            count = OCPUsageLineItemDailySummary.objects.filter(
                report_period_id=report_period_id, usage_start__gte=start_date, infrastructure_raw_cost__gt=0
            ).count()
        self.assertNotEqual(count, 0)

        self.accessor.delete_infrastructure_raw_cost_from_daily_summary(
            self.ocpaws_provider_uuid, report_period_id, start_date, end_date
        )

        with schema_context(self.schema):
            count = OCPUsageLineItemDailySummary.objects.filter(
                report_period_id=report_period_id, usage_start__gte=start_date, infrastructure_raw_cost__gt=0
            ).count()
        self.assertEqual(count, 0)

    @patch("masu.database.ocp_report_db_accessor.OCPReportDBAccessor.table_exists_trino")
    @patch("masu.database.ocp_report_db_accessor.OCPReportDBAccessor._execute_trino_raw_sql_query")
    def test_delete_ocp_hive_partition_by_day(self, mock_trino, mock_table_exist):
        """Test that deletions work with retries."""
        error = {"errorName": "HIVE_METASTORE_ERROR"}
        mock_trino.side_effect = TrinoExternalError(error)
        with self.assertRaises(TrinoExternalError):
            self.accessor.delete_ocp_hive_partition_by_day([1], self.ocp_provider_uuid, "2022", "01")
        mock_trino.assert_called()
        # Confirms that the error log would be logged on last attempt
        self.assertEqual(mock_trino.call_args_list[-1].kwargs.get("attempts_left"), 0)
        self.assertEqual(mock_trino.call_count, settings.HIVE_PARTITION_DELETE_RETRIES)

    @patch("masu.database.ocp_report_db_accessor.OCPReportDBAccessor.table_exists_trino")
    @patch("masu.database.ocp_report_db_accessor.OCPReportDBAccessor._execute_trino_raw_sql_query")
    def test_delete_hive_partitions_by_source_success(self, mock_trino, mock_table_exist):
        """Test that deletions work with retries."""
        result = self.accessor.delete_hive_partitions_by_source("table", "partition_column", self.ocp_provider_uuid)
        mock_trino.assert_called()
        self.assertTrue(result)

    @patch("masu.database.ocp_report_db_accessor.OCPReportDBAccessor.table_exists_trino")
    @patch("masu.database.ocp_report_db_accessor.OCPReportDBAccessor._execute_trino_raw_sql_query")
    def test_delete_hive_partitions_by_source_failure(self, mock_trino, mock_table_exist):
        """Test that deletions work with retries."""
        error = {"errorName": "HIVE_METASTORE_ERROR"}
        mock_trino.side_effect = TrinoExternalError(error)
        with self.assertRaises(TrinoExternalError):
            result = self.accessor.delete_hive_partitions_by_source(
                "table", "partition_column", self.ocp_provider_uuid
            )
            self.assertFalse(result)
        mock_trino.assert_called()
        # Confirms that the error log would be logged on last attempt
        self.assertEqual(mock_trino.call_args_list[-1].kwargs.get("attempts_left"), 0)
        self.assertEqual(mock_trino.call_count, settings.HIVE_PARTITION_DELETE_RETRIES)

    @patch("masu.database.ocp_report_db_accessor.OCPReportDBAccessor._execute_trino_raw_sql_query")
    def test_get_max_min_timestamp_from_parquet(self, mock_query):
        """Get the max and min timestamps for parquet data given a date range"""
        start_date, end_date = datetime(2022, 3, 1), datetime(2022, 3, 30)
        table = [
            {
                "name": "valid-dates",
                "return": ["2022-04-01", "2022-04-30"],
                "expected": (datetime(2022, 4, 1), datetime(2022, 4, 30)),
            },
            {"name": "none-dates", "return": [None, None], "expected": (start_date, end_date)},
            {
                "name": "none-start-date",
                "return": [None, "2022-04-30"],
                "expected": (start_date, datetime(2022, 4, 30)),
            },
            {"name": "none-end-date", "return": ["2022-04-01", None], "expected": (datetime(2022, 4, 1), end_date)},
        ]

        for test in table:
            with self.subTest(test=test["name"]):
                mock_query.return_value = [test["return"]]  # returned value is a list of a list
                result = self.accessor.get_max_min_timestamp_from_parquet(uuid.uuid4(), start_date, end_date)
                self.assertEqual(result, test["expected"])
                self.assertTrue(hasattr(result[0], "date"))
                self.assertTrue(hasattr(result[1], "date"))

    def test_delete_all_except_infrastructure_raw_cost_from_daily_summary(self):
        """Test that deleting saves OCP on Cloud data."""
        dh = DateHelper()
        start_date = dh.this_month_start
        end_date = dh.this_month_end

        # First test an OCP on Cloud source to make sure we don't delete that data
        provider_uuid = self.ocp_on_aws_ocp_provider.uuid
        report_period = self.accessor.report_periods_for_provider_uuid(provider_uuid, start_date)

        with schema_context(self.schema):
            report_period_id = report_period.id
            initial_non_raw_count = (
                OCPUsageLineItemDailySummary.objects.filter(
                    Q(infrastructure_raw_cost__isnull=True) | Q(infrastructure_raw_cost=0),
                    report_period_id=report_period_id,
                )
                .exclude(cost_model_rate_type="platform_distributed")
                .count()
            )
            # the distributed cost is being added so the initial count is no longer zero.
            initial_raw_count = OCPUsageLineItemDailySummary.objects.filter(
                Q(infrastructure_raw_cost__isnull=False) & ~Q(infrastructure_raw_cost=0),
                report_period_id=report_period_id,
            ).count()

        self.accessor.delete_all_except_infrastructure_raw_cost_from_daily_summary(
            provider_uuid, report_period_id, start_date, end_date
        )

        with schema_context(self.schema):
            new_non_raw_count = OCPUsageLineItemDailySummary.objects.filter(
                Q(infrastructure_raw_cost__isnull=True) | Q(infrastructure_raw_cost=0),
                report_period_id=report_period_id,
            ).count()
            new_raw_count = OCPUsageLineItemDailySummary.objects.filter(
                Q(infrastructure_raw_cost__isnull=False) & ~Q(infrastructure_raw_cost=0),
                report_period_id=report_period_id,
            ).count()

        self.assertEqual(initial_non_raw_count, 0)
        self.assertEqual(new_non_raw_count, 0)
        self.assertEqual(initial_raw_count, new_raw_count)

        # Now test an on prem OCP cluster to make sure we still remove non raw costs
        provider_uuid = self.ocp_provider.uuid
        report_period = self.accessor.report_periods_for_provider_uuid(provider_uuid, start_date)

        with schema_context(self.schema):
            report_period_id = report_period.id
            initial_non_raw_count = OCPUsageLineItemDailySummary.objects.filter(
                Q(infrastructure_raw_cost__isnull=True) | Q(infrastructure_raw_cost=0),
                report_period_id=report_period_id,
            ).count()
            initial_raw_count = OCPUsageLineItemDailySummary.objects.filter(
                Q(infrastructure_raw_cost__isnull=False) & ~Q(infrastructure_raw_cost=0),
                report_period_id=report_period_id,
            ).count()

        self.accessor.delete_all_except_infrastructure_raw_cost_from_daily_summary(
            provider_uuid, report_period_id, start_date, end_date
        )

        with schema_context(self.schema):
            new_non_raw_count = OCPUsageLineItemDailySummary.objects.filter(
                Q(infrastructure_raw_cost__isnull=True) | Q(infrastructure_raw_cost=0),
                report_period_id=report_period_id,
            ).count()
            new_raw_count = OCPUsageLineItemDailySummary.objects.filter(
                Q(infrastructure_raw_cost__isnull=False) & ~Q(infrastructure_raw_cost=0),
                report_period_id=report_period_id,
            ).count()

        self.assertNotEqual(initial_non_raw_count, new_non_raw_count)
        self.assertEqual(initial_raw_count, 0)
        self.assertEqual(new_raw_count, 0)

    def test_populate_monthly_cost_sql_no_report_period(self):
        """Test that updating monthly costs without a matching report period no longer throws an error"""
        start_date = "2000-01-01"
        end_date = "2000-02-01"
        expected = (
            "INFO:masu.database.ocp_report_db_accessor:No report period for OCP provider"
            f" {self.provider_uuid} with start date {start_date}, skipping populate_monthly_cost_sql update."
        )
        with self.assertLogs("masu.database.ocp_report_db_accessor", level="INFO") as logger:
            self.accessor.populate_monthly_cost_sql("", "", "", start_date, end_date, "", self.provider_uuid)
            self.assertIn(expected, logger.output)

    def test_populate_monthly_cost_tag_sql_no_report_period(self):
        """Test that updating monthly costs without a matching report period no longer throws an error"""
        start_date = "2000-01-01"
        end_date = "2000-02-01"
        expected = (
            "INFO:masu.database.ocp_report_db_accessor:No report period for OCP provider"
            f" {self.provider_uuid} with start date {start_date}, skipping populate_monthly_tag_cost_sql update."
        )
        with self.assertLogs("masu.database.ocp_report_db_accessor", level="INFO") as logger:
            self.accessor.populate_monthly_tag_cost_sql("", "", "", "", start_date, end_date, "", self.provider_uuid)
            self.assertIn(expected, logger.output)

    def test_populate_usage_costs_new_columns_no_report_period(self):
        """Test that updating new column usage costs without a matching report period no longer throws an error"""
        start_date = "2000-01-01"
        end_date = "2000-02-01"
        expected = (
            "INFO:masu.database.ocp_report_db_accessor:No report period for OCP provider"
            f" {self.provider_uuid} with start date {start_date}, skipping populate_usage_costs_new_columns update."
        )
        with self.assertLogs("masu.database.ocp_report_db_accessor", level="INFO") as logger:
            self.accessor.populate_usage_costs("", "", start_date, end_date, self.provider_uuid)
            self.assertIn(expected, logger.output)
