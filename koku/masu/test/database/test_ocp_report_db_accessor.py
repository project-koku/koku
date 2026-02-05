#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the OCPReportDBAccessor utility object."""
import logging
import pkgutil
import random
import uuid
from collections import defaultdict
from datetime import datetime
from unittest.mock import call
from unittest.mock import Mock
from unittest.mock import patch

from django.conf import settings
from django.db import IntegrityError
from django.db.models import Q
from django.db.models import Sum
from django_tenants.utils import schema_context
from trino.exceptions import TrinoExternalError
from trino.exceptions import TrinoUserError

from api.metrics import constants as metric_constants
from api.provider.models import Provider
from api.report.test.util.constants import OCP_PVC_LABELS
from koku.trino_database import TrinoHiveMetastoreError
from koku.trino_database import TrinoStatementExecError
from masu.database import OCP_REPORT_TABLE_MAP
from masu.database.ocp_report_db_accessor import OCPReportDBAccessor
from masu.test import MasuTestCase
from masu.util.common import SummaryRangeConfig
from reporting.models import OCPUsageLineItemDailySummary
from reporting.provider.all.models import EnabledTagKeys
from reporting.provider.all.models import TagMapping
from reporting.provider.ocp.models import OCPCluster
from reporting.provider.ocp.models import OCPNode
from reporting.provider.ocp.models import OCPProject
from reporting.provider.ocp.models import OCPPVC
from reporting.provider.ocp.models import OCPUsageReportPeriod

LOG = logging.getLogger(__name__)


class OCPReportDBAccessorTest(MasuTestCase):
    """Test Cases for the OCPReportDBAccessor object."""

    def setUp(self):
        """Set up a test with database objects."""
        super().setUp()

        self.accessor = OCPReportDBAccessor(schema=self.schema)

        self.cluster_id = "testcluster"
        self.ocp_provider_uuid = self.ocp_provider.uuid

    def test_get_usage_period_query_by_provider(self):
        """Test that periods are returned filtered by provider."""
        with self.accessor as acc:
            provider_uuid = self.ocp_provider_uuid
            period_query = acc.get_usage_period_query_by_provider(provider_uuid)
            periods = period_query.all()
            self.assertGreater(len(periods), 0)
            period = periods[0]
            self.assertEqual(period.provider_id, provider_uuid)

    def test_report_periods_for_provider_uuid(self):
        """Test that periods are returned filtered by provider id and start date."""
        with self.accessor as acc:
            provider_uuid = self.ocp_provider_uuid
            reporting_period = OCPUsageReportPeriod.objects.filter(provider=self.ocp_provider_uuid).first()
            start_date = str(reporting_period.report_period_start)
            period = acc.report_periods_for_provider_uuid(provider_uuid, start_date)
            self.assertEqual(period.provider_id, provider_uuid)

    @patch("masu.database.ocp_report_db_accessor.trino_table_exists")
    @patch("masu.database.ocp_report_db_accessor.OCPReportDBAccessor.delete_ocp_hive_partition_by_day")
    @patch("masu.database.ocp_report_db_accessor.OCPReportDBAccessor._execute_trino_multipart_sql_query")
    def test_populate_line_item_daily_summary_table_trino(self, mock_execute, *args):
        """
        Test that OCP trino processing calls executescript
        """
        start_date = self.dh.this_month_start
        end_date = self.dh.next_month_start
        cluster_id = "ocp-cluster"
        cluster_alias = "OCP FTW"
        report_period_id = 1
        source = self.provider_uuid
        with self.accessor as acc:
            acc.populate_line_item_daily_summary_table_trino(
                start_date, end_date, report_period_id, cluster_id, cluster_alias, source
            )
            mock_execute.assert_called()

    @patch("masu.database.ocp_report_db_accessor.trino_table_exists", return_value=True)
    def test_populate_line_item_daily_summary_table_trino_exception_warn(self, mock_table_exists):
        """
        Test that a warning is logged when a TrinoStatementExecError is raised because
        a partion already exists.
        """

        start_date = self.dh.this_month_start
        end_date = self.dh.next_month_start
        cluster_id = "ocp-cluster"
        cluster_alias = "OCP FTW"
        report_period_id = 1
        source = self.provider_uuid
        message = "One or more Partitions Already exist"
        with (
            patch.object(self.accessor, "delete_ocp_hive_partition_by_day"),
            patch.object(self.accessor, "_execute_trino_multipart_sql_query") as mock_sql_query,
            self.accessor as acc,
            self.assertLogs("masu.database.ocp_report_db_accessor", level="WARN") as logger,
        ):
            trino_error = TrinoUserError(
                {
                    "errorType": "USER_ERROR",
                    "errorName": "ALREADY_EXISTS",
                    "message": message,
                }
            )
            mock_sql_query.side_effect = TrinoStatementExecError("SELECT * from table", 1, {}, trino_error)

            acc.populate_line_item_daily_summary_table_trino(
                start_date, end_date, report_period_id, cluster_id, cluster_alias, source
            )

        self.assertIn(
            f"WARNING:masu.database.ocp_report_db_accessor:{{'message': '{message}'",
            logger.output[0],
        )

    @patch("masu.database.ocp_report_db_accessor.trino_table_exists", return_value=True)
    def test_populate_line_item_daily_summary_table_trino_exception(self, mock_table_exists):
        """
        Test that a TrinoStatementExecError is raised for errors that are not partition related.
        """

        start_date = self.dh.this_month_start
        end_date = self.dh.next_month_start
        cluster_id = "ocp-cluster"
        cluster_alias = "OCP FTW"
        report_period_id = 1
        source = self.provider_uuid
        with (
            patch.object(self.accessor, "delete_ocp_hive_partition_by_day"),
            patch.object(self.accessor, "_execute_trino_multipart_sql_query") as mock_sql_query,
            self.accessor as acc,
            self.assertRaisesRegex(TrinoStatementExecError, "Something went wrong"),
        ):
            trino_error = TrinoExternalError(
                {
                    "errorType": "EXTERNAL",
                    "errorName": "SOME_EXTERNAL_PROBLEM",
                    "message": "Something went wrong",
                }
            )
            mock_sql_query.side_effect = TrinoStatementExecError("SELECT * from table", 1, {}, trino_error)

            acc.populate_line_item_daily_summary_table_trino(
                start_date, end_date, report_period_id, cluster_id, cluster_alias, source
            )

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
        start_date = self.dh.this_month_start
        end_date = self.dh.this_month_end
        self.cluster_id = "OCP-on-AWS"
        with self.accessor as acc:
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
                    acc.populate_tag_usage_costs(
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
        start_date = self.dh.this_month_start
        end_date = self.dh.this_month_end
        self.cluster_id = "OCP-on-AWS"
        with self.accessor as acc:
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
                    acc.populate_tag_usage_default_costs(
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

    def test_table_properties(self):
        self.assertEqual(self.accessor.line_item_daily_summary_table, OCPUsageLineItemDailySummary)

    def test_table_map(self):
        self.assertEqual(self.accessor._table_map, OCP_REPORT_TABLE_MAP)

    @patch("masu.database.ocp_report_db_accessor.OCPReportDBAccessor._execute_trino_raw_sql_query")
    def test_get_ocp_infrastructure_map_trino(self, mock_trino):
        """Test that Trino is used to find matched tags."""
        subtests = ["aws", "gcp", "azure"]
        mock_trino.side_effect = [True, True, [["test", "test", "test"]]] * len(subtests)
        for p_type_var_substring in subtests:
            with self.subTest(p_type_var_substring=p_type_var_substring):
                kwargs = {
                    "start_date": self.dh.this_month_start.date(),
                    "end_date": self.dh.this_month_end.date(),
                    f"{p_type_var_substring}_provider_uuid": uuid.uuid4(),
                }
                accessor = OCPReportDBAccessor(schema=self.schema)
                result = accessor.get_ocp_infrastructure_map_trino(**kwargs)
                self.assertEqual(result, {"test": ("test", "test")})

    @patch("masu.database.ocp_report_db_accessor.OCPReportDBAccessor._execute_trino_raw_sql_query")
    def test_get_ocp_infrastructure_map_trino_table_does_not_exist(self, table_exists):
        """Test trino returns empty dict if table does not exit"""
        subtests = ["aws", "gcp", "azure"]
        table_exists.side_effect = [True, False] * len(subtests)
        for p_type_var_substring in subtests:
            with self.subTest(p_type_var_substring=p_type_var_substring):
                kwargs = {
                    "start_date": self.dh.this_month_start.date(),
                    "end_date": self.dh.this_month_end.date(),
                    f"{p_type_var_substring}_provider_uuid": uuid.uuid4(),
                }
                accessor = OCPReportDBAccessor(schema=self.schema)
                result = accessor.get_ocp_infrastructure_map_trino(**kwargs)
                self.assertEqual(result, {})

    @patch("masu.database.ocp_report_db_accessor.trino_table_exists")
    @patch("masu.database.ocp_report_db_accessor.OCPReportDBAccessor.get_projects_trino")
    @patch("masu.database.ocp_report_db_accessor.OCPReportDBAccessor._execute_trino_raw_sql_query")
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
        csi_volume_handles = ["csi1", "csi2"]
        projects = ["project_1", "project_2"]
        roles = ["master", "worker"]
        arches = ["arm64", "amd64"]
        mock_get_nodes.return_value = zip(nodes, resource_ids, capacity, roles, arches)
        mock_get_pvcs.return_value = zip(volumes, pvcs, csi_volume_handles)
        mock_get_projects.return_value = projects
        mock_table.return_value = True
        cluster_id = uuid.uuid4()
        cluster_alias = "test-cluster-1"

        start_date = self.dh.this_month_start.date()
        end_date = self.dh.this_month_end.date()

        with self.accessor as acc:
            cluster = acc.populate_cluster_table(self.aws_provider, cluster_id, cluster_alias)
            OCPPVC.objects.get_or_create(
                persistent_volume_claim=pvcs[0], persistent_volume=volumes[0], cluster=cluster
            )
            acc.populate_openshift_cluster_information_tables(
                self.aws_provider, cluster_id, cluster_alias, start_date, end_date
            )

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

            acc.populate_openshift_cluster_information_tables(
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
        csi_volume_handles = ["csi1", "csi2"]
        projects = ["project_1", "project_2"]
        roles = ["master", "worker"]
        arches = ["arm64", "amd63"]
        mock_get_nodes.return_value = zip(nodes, resource_ids, capacity, roles, arches)
        mock_get_pvcs.return_value = zip(volumes, pvcs, csi_volume_handles)
        mock_get_projects.return_value = projects
        mock_table.return_value = True
        cluster_id = str(uuid.uuid4())
        cluster_alias = "test-cluster-1"

        start_date = self.dh.this_month_start.date()
        end_date = self.dh.this_month_end.date()

        with self.accessor as acc:
            # Using the aws_provider to short cut this test instead of creating a brand
            # new provider. The OCP providers already have data, and can't be used here
            acc.populate_openshift_cluster_information_tables(
                self.aws_provider, cluster_id, cluster_alias, start_date, end_date
            )

            cluster = OCPCluster.objects.filter(cluster_id=cluster_id).first()
            nodes = OCPNode.objects.filter(cluster=cluster).all()
            pvcs = OCPPVC.objects.filter(cluster=cluster).all()
            projects = OCPProject.objects.filter(cluster=cluster).all()
            topology = acc.get_openshift_topology_for_multiple_providers([self.aws_provider_uuid])
            self.assertEqual(len(topology), 1)
            topo = topology[0]
            self.assertEqual(topo.get("cluster_id"), cluster_id)
            self.assertEqual(nodes.count(), len(topo.get("nodes")))
            for node in nodes:
                self.assertIn(node.node, topo.get("nodes"))
            for pvc in pvcs:
                self.assertIn(pvc.persistent_volume_claim, topo.get("persistent_volume_claims"))
                self.assertIn(pvc.persistent_volume, topo.get("persistent_volumes"))
                self.assertIn(pvc.csi_volume_handle, topo.get("csi_volume_handle"))
            for project in projects:
                self.assertIn(project.project, topo.get("projects"))

    @patch("masu.database.ocp_report_db_accessor.trino_table_exists")
    @patch("masu.database.ocp_report_db_accessor.OCPReportDBAccessor.get_pvcs_trino")
    @patch("masu.database.ocp_report_db_accessor.OCPReportDBAccessor.get_nodes_trino")
    def test_get_filtered_openshift_topology_for_multiple_providers(self, mock_get_nodes, mock_get_pvcs, mock_table):
        """Test that OpenShift topology is populated."""
        nodes = ["test_node_1", "test_node_2"]
        resource_ids = ["id_1", "id_2"]
        capacity = [1, 1]
        volumes = ["vol_1", "vol_2"]
        pvcs = ["pvc_1", "pvc_2"]
        roles = ["master", "worker"]
        mock_get_nodes.return_value = zip(nodes, resource_ids, capacity, roles)
        mock_get_pvcs.return_value = zip(volumes, pvcs)
        mock_table.return_value = True
        cluster_id = str(uuid.uuid4())
        cluster_alias = "test-cluster-1"

        start_date = self.dh.this_month_start.date()
        end_date = self.dh.this_month_end.date()

        with self.accessor as acc:
            cluster = OCPCluster(
                cluster_id=cluster_id, cluster_alias=cluster_alias, provider_id=self.gcp_provider_uuid
            )
            cluster.save()
            topology = acc.get_filtered_openshift_topology_for_multiple_providers(
                [self.gcp_provider_uuid], start_date, end_date
            )
            self.assertEqual(len(topology), 1)
            topo = topology[0]
            self.assertEqual(topo.get("cluster_id"), cluster_id)
            self.assertEqual(len(nodes), len(topo.get("nodes")))
            for node in nodes:
                self.assertIn(node, topo.get("nodes"))
            for volume in volumes:
                self.assertIn(volume, topo.get("persistent_volumes"))

    def test_populate_node_table_update_role(self):
        """Test that populating the node table for an entry that previously existed fills the node role correctly."""
        node_info = ["node_role_test_node", "node_role_test_id", 1, "worker", "arm64"]
        cluster_id = str(uuid.uuid4())
        cluster_alias = "node_role_test"
        with self.accessor as acc:
            cluster = acc.populate_cluster_table(self.aws_provider, cluster_id, cluster_alias)
            node = OCPNode.objects.create(
                node=node_info[0], resource_id=node_info[1], node_capacity_cpu_cores=node_info[2], cluster=cluster
            )
            self.assertIsNone(node.node_role)
            acc.populate_node_table(cluster, [node_info])
            node = OCPNode.objects.get(
                node=node_info[0], resource_id=node_info[1], node_capacity_cpu_cores=node_info[2], cluster=cluster
            )
            self.assertEqual(node.node_role, node_info[3])

    def test_populate_node_table_update_arch(self):
        """Test that populating the node table for an entry that previously existed fills the arch correctly."""
        node_info = ["node_role_test_node", "node_role_test_id", 1, "worker", "arm64"]
        cluster_id = str(uuid.uuid4())
        cluster_alias = "node_role_test"
        with self.accessor as acc:
            cluster = acc.populate_cluster_table(self.aws_provider, cluster_id, cluster_alias)
            node = OCPNode.objects.create(
                node=node_info[0],
                resource_id=node_info[1],
                node_capacity_cpu_cores=node_info[2],
                cluster=cluster,
                node_role=node_info[3],
            )
            self.assertEqual(node.node_role, node_info[3])
            self.assertIsNone(node.architecture)
            acc.populate_node_table(cluster, [node_info])
            node = OCPNode.objects.get(
                node=node_info[0], resource_id=node_info[1], node_capacity_cpu_cores=node_info[2], cluster=cluster
            )
            self.assertEqual(node.architecture, node_info[4])

    def test_populate_cluster_table_update_cluster_alias(self):
        """Test updating cluster alias for entry in the cluster table."""
        cluster_id = str(uuid.uuid4())
        cluster_alias = "cluster_alias"
        new_cluster_alias = "new_cluster_alias"
        with self.accessor as acc:
            acc.populate_cluster_table(self.aws_provider, cluster_id, cluster_alias)
            cluster = OCPCluster.objects.filter(cluster_id=cluster_id).first()
            self.assertEqual(cluster.cluster_alias, cluster_alias)
            acc.populate_cluster_table(self.aws_provider, cluster_id, new_cluster_alias)
            cluster = OCPCluster.objects.filter(cluster_id=cluster_id).first()
            self.assertEqual(cluster.cluster_alias, new_cluster_alias)

    def test_populate_cluster_table_delete_duplicates(self):
        """Test updating cluster alias for duplicate entry in the cluster table."""
        cluster_id = str(uuid.uuid4())
        new_cluster_alias = "new_cluster_alias"
        with self.accessor as acc:
            acc.populate_cluster_table(self.aws_provider, cluster_id, "cluster_alias")
            # Forcefully create a second entry
            OCPCluster.objects.get_or_create(
                cluster_id=cluster_id, cluster_alias=self.aws_provider.name, provider_id=self.aws_provider_uuid
            )
            acc.populate_cluster_table(self.aws_provider, cluster_id, new_cluster_alias)
            clusters = OCPCluster.objects.filter(cluster_id=cluster_id)
            self.assertEqual(len(clusters), 1)
            cluster = clusters.first()
            self.assertEqual(cluster.cluster_alias, new_cluster_alias)

    def test_populate_node_table_second_time_no_change(self):
        """Test that populating the node table for an entry a second time does not duplicate entries."""
        node_info = ["node_role_test_node", "node_role_test_id", 1, "worker", "arm64"]
        cluster_id = str(uuid.uuid4())
        cluster_alias = "node_role_test"
        with self.accessor as acc:
            cluster = acc.populate_cluster_table(self.aws_provider, cluster_id, cluster_alias)
            acc.populate_node_table(cluster, [node_info])
            node_count = OCPNode.objects.filter(
                node=node_info[0], resource_id=node_info[1], node_capacity_cpu_cores=node_info[2], cluster=cluster
            ).count()
            self.assertEqual(node_count, 1)
            acc.populate_node_table(cluster, [node_info])
            node_count = OCPNode.objects.filter(
                node=node_info[0], resource_id=node_info[1], node_capacity_cpu_cores=node_info[2], cluster=cluster
            ).count()
            self.assertEqual(node_count, 1)

    @patch("reporting.provider.ocp.models.OCPPVC.objects.create", side_effect=IntegrityError)
    @patch("masu.database.ocp_report_db_accessor.LOG.warning")
    def test_populate_pvc_table_handles_integrity_error(self, mock_log, mock_create):
        """Test that populating OCPPVC table handles IntegrityError exception."""

        pvcs = ["pvc_1", "pvc_2"]
        cluster_id = uuid.uuid4()
        cluster_alias = "test-cluster-1"

        with self.accessor as accessor:
            cluster = accessor.populate_cluster_table(self.ocp_provider, cluster_id, cluster_alias)
            accessor.populate_pvc_table(cluster, pvcs)

            mock_create.assert_called()
            self.assertTrue(
                any("IntegrityError raised when creating pvc" in str(call) for call in mock_log.call_args_list)
            )

    def test_delete_infrastructure_raw_cost_from_daily_summary(self):
        """Test that infra raw cost is deleted."""
        with self.accessor as acc:
            start_date = self.dh.this_month_start.date()
            end_date = self.dh.this_month_end.date()
            report_period = acc.report_periods_for_provider_uuid(self.ocpaws_provider_uuid, start_date)
            report_period_id = report_period.id
            count = OCPUsageLineItemDailySummary.objects.filter(
                report_period_id=report_period_id, usage_start__gte=start_date, infrastructure_raw_cost__gt=0
            ).count()
            self.assertNotEqual(count, 0)
            acc.delete_infrastructure_raw_cost_from_daily_summary(
                self.ocpaws_provider_uuid, report_period_id, start_date, end_date
            )
            count = OCPUsageLineItemDailySummary.objects.filter(
                report_period_id=report_period_id, usage_start__gte=start_date, infrastructure_raw_cost__gt=0
            ).count()
            self.assertEqual(count, 0)

    @patch("masu.database.ocp_report_db_accessor.OCPReportDBAccessor.schema_exists_trino")
    @patch("masu.database.ocp_report_db_accessor.OCPReportDBAccessor.table_exists_trino")
    @patch("masu.database.report_db_accessor_base.trino_db.connect")
    @patch("time.sleep", return_value=None)
    def test_delete_ocp_hive_partition_by_day(self, mock_sleep, mock_connect, mock_table_exists, mock_schema_exists):
        """Test that deletions work with retries."""
        mock_schema_exists.return_value = False
        self.accessor.delete_ocp_hive_partition_by_day([1], self.ocp_provider_uuid, self.ocp_provider_uuid, "2022")
        mock_connect.assert_not_called()

        mock_connect.reset_mock()

        mock_schema_exists.return_value = True
        attrs = {"cursor.side_effect": TrinoExternalError({"errorName": "HIVE_METASTORE_ERROR"})}
        mock_connect.return_value = Mock(**attrs)

        with self.assertRaises(TrinoHiveMetastoreError):
            self.accessor.delete_ocp_hive_partition_by_day([1], self.aws_provider_uuid, self.ocp_provider_uuid, "2022")

        mock_connect.assert_called()
        self.assertEqual(mock_connect.call_count, settings.HIVE_PARTITION_DELETE_RETRIES)

    @patch("masu.database.ocp_report_db_accessor.OCPReportDBAccessor.table_exists_trino")
    @patch("masu.database.ocp_report_db_accessor.OCPReportDBAccessor._execute_trino_raw_sql_query")
    def test_delete_hive_partitions_by_source_success(self, mock_trino, mock_table_exist):
        """Test that deletions work with retries."""
        result = self.accessor.delete_hive_partitions_by_source("table", "partition_column", self.ocp_provider_uuid)
        mock_trino.assert_called()
        self.assertTrue(result)

    @patch("masu.database.ocp_report_db_accessor.OCPReportDBAccessor.table_exists_trino")
    @patch("masu.database.ocp_report_db_accessor.OCPReportDBAccessor._execute_trino_raw_sql_query")
    def test_find_expired_trino_partitions_success(self, mock_trino, mock_table_exist):
        """Test that deletions work with retries."""
        result = self.accessor.find_expired_trino_partitions("table", "source_column", "2024-06-01")
        mock_trino.assert_called()
        self.assertTrue(result)

    @patch("masu.database.ocp_report_db_accessor.OCPReportDBAccessor.schema_exists_trino")
    @patch("masu.database.ocp_report_db_accessor.OCPReportDBAccessor._execute_trino_raw_sql_query")
    def test_find_expired_trino_partitions_no_schema(self, mock_trino, mock_schema):
        """Test that deletions work with retries."""
        mock_schema.return_value = False
        result = self.accessor.find_expired_trino_partitions("table", "source_column", "2024-06-01")
        mock_trino.assert_not_called()
        self.assertFalse(result)

    @patch("masu.database.ocp_report_db_accessor.OCPReportDBAccessor.schema_exists_trino")
    @patch("masu.database.ocp_report_db_accessor.OCPReportDBAccessor.table_exists_trino")
    @patch("masu.database.ocp_report_db_accessor.OCPReportDBAccessor._execute_trino_raw_sql_query")
    def test_find_expired_trino_partitions_no_table(self, mock_trino, mock_table_exist, mock_schema):
        """Test that deletions work with retries."""
        mock_schema.return_value = True
        mock_table_exist.return_value = False
        result = self.accessor.find_expired_trino_partitions("table", "source_column", "2024-06-01")
        mock_trino.assert_not_called()
        self.assertFalse(result)

    @patch("reporting.provider.ocp.self_hosted_models.get_self_hosted_models")
    def test_delete_self_hosted_data_by_source(self, mock_get_models):
        """Test that delete_self_hosted_data_by_source deletes from all self-hosted tables."""
        # Create mock models
        mock_staging_model = Mock()
        mock_staging_model.objects.filter.return_value.delete.return_value = (5, {})
        mock_staging_model._meta.db_table = "staging_table"

        mock_line_item_model = Mock()
        mock_line_item_model.objects.filter.return_value.delete.return_value = (10, {})
        mock_line_item_model._meta.db_table = "line_item_table"

        mock_get_models.return_value = [mock_staging_model, mock_line_item_model]

        with patch(
            "reporting.provider.ocp.self_hosted_models.OCPUsageLineItemDailySummaryStaging",
            mock_staging_model,
        ):
            with self.accessor as acc:
                result = acc.delete_self_hosted_data_by_source(self.ocp_provider_uuid)

                # Verify staging table filtered by source_uuid
                mock_staging_model.objects.filter.assert_called_with(source_uuid=str(self.ocp_provider_uuid))
                # Verify line item table filtered by source
                mock_line_item_model.objects.filter.assert_called_with(source=str(self.ocp_provider_uuid))
                self.assertEqual(result, 15)  # 5 + 10

    @patch("reporting.provider.ocp.self_hosted_models.get_self_hosted_models")
    def test_delete_self_hosted_data_by_source_no_data(self, mock_get_models):
        """Test delete_self_hosted_data_by_source when no data exists."""
        mock_model = Mock()
        mock_model.objects.filter.return_value.delete.return_value = (0, {})
        mock_model._meta.db_table = "test_table"

        mock_get_models.return_value = [mock_model]

        with self.accessor as acc:
            result = acc.delete_self_hosted_data_by_source(uuid.uuid4())
            self.assertEqual(result, 0)

    @patch("masu.database.ocp_report_db_accessor.OCPReportDBAccessor.schema_exists_trino")
    @patch("masu.database.ocp_report_db_accessor.OCPReportDBAccessor.table_exists_trino")
    @patch("masu.database.report_db_accessor_base.trino_db.connect")
    @patch("time.sleep", return_value=None)
    def test_delete_hive_partitions_by_source_failure(
        self, mock_sleep, mock_connect, mock_table_exist, mock_schema_exists
    ):
        """Test that deletions work with retries."""
        mock_schema_exists.return_value = False
        self.accessor.delete_hive_partitions_by_source("table", "partition_column", self.ocp_provider_uuid)
        mock_connect.assert_not_called()
        mock_connect.reset_mock()

        mock_schema_exists.return_value = True

        attrs = {"cursor.side_effect": TrinoExternalError({"errorName": "HIVE_METASTORE_ERROR"})}
        mock_connect.return_value = Mock(**attrs)

        with self.assertRaises(TrinoHiveMetastoreError):
            self.accessor.delete_hive_partitions_by_source("table", "partition_column", self.ocp_provider_uuid)

        mock_connect.assert_called()
        self.assertEqual(mock_connect.call_count, settings.HIVE_PARTITION_DELETE_RETRIES)

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
        with self.accessor as acc:
            start_date = self.dh.this_month_start
            end_date = self.dh.this_month_end

            # First test an OCP on Cloud source to make sure we don't delete that data
            provider_uuid = self.ocp_on_aws_ocp_provider.uuid
            report_period = acc.report_periods_for_provider_uuid(provider_uuid, start_date)

            report_period_id = report_period.id
            initial_non_raw_count = (
                OCPUsageLineItemDailySummary.objects.filter(
                    Q(infrastructure_raw_cost__isnull=True) | Q(infrastructure_raw_cost=0),
                    report_period_id=report_period_id,
                )
                .exclude(cost_model_rate_type="platform_distributed")
                .exclude(data_source="GPU")
                .count()
            )
            # the distributed cost is being added so the initial count is no longer zero.
            initial_raw_count = OCPUsageLineItemDailySummary.objects.filter(
                Q(infrastructure_raw_cost__isnull=False) & ~Q(infrastructure_raw_cost=0),
                report_period_id=report_period_id,
            ).count()

            acc.delete_all_except_infrastructure_raw_cost_from_daily_summary(
                provider_uuid, report_period_id, start_date, end_date
            )

            new_non_raw_count = (
                OCPUsageLineItemDailySummary.objects.filter(
                    Q(infrastructure_raw_cost__isnull=True) | Q(infrastructure_raw_cost=0),
                    report_period_id=report_period_id,
                )
                .exclude(data_source="GPU")
                .count()
            )
            new_raw_count = OCPUsageLineItemDailySummary.objects.filter(
                Q(infrastructure_raw_cost__isnull=False) & ~Q(infrastructure_raw_cost=0),
                report_period_id=report_period_id,
            ).count()

            self.assertEqual(initial_non_raw_count, 0)
            self.assertEqual(new_non_raw_count, 0)
            self.assertEqual(initial_raw_count, new_raw_count)

            # Now test an on prem OCP cluster to make sure we still remove non raw costs
            provider_uuid = self.ocp_provider.uuid
            report_period = acc.report_periods_for_provider_uuid(provider_uuid, start_date)

            report_period_id = report_period.id
            initial_non_raw_count = (
                OCPUsageLineItemDailySummary.objects.filter(
                    Q(infrastructure_raw_cost__isnull=True) | Q(infrastructure_raw_cost=0),
                    report_period_id=report_period_id,
                )
                .exclude(data_source="GPU")
                .count()
            )
            initial_raw_count = OCPUsageLineItemDailySummary.objects.filter(
                Q(infrastructure_raw_cost__isnull=False) & ~Q(infrastructure_raw_cost=0),
                report_period_id=report_period_id,
            ).count()

            acc.delete_all_except_infrastructure_raw_cost_from_daily_summary(
                provider_uuid, report_period_id, start_date, end_date
            )

            new_non_raw_count = (
                OCPUsageLineItemDailySummary.objects.filter(
                    Q(infrastructure_raw_cost__isnull=True) | Q(infrastructure_raw_cost=0),
                    report_period_id=report_period_id,
                )
                .exclude(data_source="GPU")
                .count()
            )
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
        with self.assertLogs("masu.database.ocp_report_db_accessor", level="INFO") as logger:
            with self.accessor as acc:
                acc.populate_monthly_cost_sql("Cluster", "", "", start_date, end_date, "", self.provider_uuid)
                self.assertIn("no report period for OCP provider", logger.output[0])

    def test_populate_monthly_cost_sql_invalid_cost_type(self):
        """Test that updating monthly costs without a matching report period no longer throws an error"""
        with self.assertLogs("masu.database.ocp_report_db_accessor", level="INFO") as logger:
            with self.accessor as acc:
                acc.populate_monthly_cost_sql("Fake", "", "", self.start_date, self.start_date, "", self.provider_uuid)
                self.assertIn("Skipping populate_monthly_cost_sql update", logger.output[0])

    @patch("masu.database.ocp_report_db_accessor.trino_table_exists", return_value=True)
    @patch("masu.database.ocp_report_db_accessor.OCPReportDBAccessor._execute_trino_multipart_sql_query")
    def test_populate_usage_costs_vm_rate(self, mock_trino, mock_trino_exists):
        """Test the populate vm hourly usage costs"""
        with self.accessor as acc:
            acc.populate_vm_usage_costs(
                metric_constants.SUPPLEMENTARY_COST_TYPE,
                {metric_constants.OCP_VM_HOUR: 1, metric_constants.OCP_VM_CORE_HOUR: 2},
                self.dh.this_month_start,
                self.dh.this_month_end,
                self.ocp_provider_uuid,
                1,
            )
            mock_trino.assert_called()

    def test_populate_monthly_cost_tag_sql_no_report_period(self):
        """Test that updating monthly costs without a matching report period no longer throws an error"""
        start_date = "2000-01-01"
        end_date = "2000-02-01"
        with self.assertLogs("masu.database.ocp_report_db_accessor", level="INFO") as logger:
            with self.accessor as acc:
                acc.populate_tag_cost_sql("", "", "", "", start_date, end_date, "", self.provider_uuid)
                self.assertIn("no report period for OCP provider", logger.output[0])

    def test_populate_distributed_cost_sql_no_report_period(self):
        """Test that updating monthly costs without a matching report period no longer throws an error"""
        start_date = "2000-01-01"
        end_date = "2000-02-01"
        summary_range = SummaryRangeConfig(start_date=start_date, end_date=end_date)
        with self.accessor as acc:
            # Should not raise an exception when no report period exists
            acc.populate_distributed_cost_sql(summary_range, self.provider_uuid, {"platform_cost": True})

    def _setup_distributed_cost_sql_mocks(self, start_date, end_date):
        """Helper to set up common mocks for distributed cost SQL tests."""
        masu_database = "masu.database"

        def get_pkgutil_values(file):
            sql = pkgutil.get_data(masu_database, f"sql/openshift/cost_model/{file}")
            return sql.decode("utf-8")

        default_sql_params = {
            "start_date": start_date,
            "end_date": end_date,
            "schema": self.schema,
            "report_period_id": 1,
            "distribution": "cpu",
            "source_uuid": self.ocp_test_provider_uuid,
            "populate": True,
        }
        side_effect = [
            [get_pkgutil_values("delete_monthly_cost_model_rate_type.sql"), default_sql_params],
            [get_pkgutil_values("distribute_platform_cost.sql"), default_sql_params],
            [get_pkgutil_values("delete_monthly_cost_model_rate_type.sql"), default_sql_params],
            [get_pkgutil_values("distribute_worker_cost.sql"), default_sql_params],
            [get_pkgutil_values("delete_monthly_cost_model_rate_type.sql"), default_sql_params],
            [get_pkgutil_values("distribute_unattributed_storage_cost.sql"), default_sql_params],
            [get_pkgutil_values("delete_monthly_cost_model_rate_type.sql"), default_sql_params],
            [get_pkgutil_values("distribute_unattributed_network_cost.sql"), default_sql_params],
            [get_pkgutil_values("delete_monthly_cost_model_rate_type.sql"), default_sql_params],
        ]
        mock_jinja = Mock()
        mock_jinja.side_effect = side_effect
        return masu_database, mock_jinja

    @patch("masu.util.ocp.common.trino_table_exists", return_value=True)
    @patch("masu.database.ocp_report_db_accessor.pkgutil.get_data")
    @patch("masu.database.ocp_report_db_accessor.OCPReportDBAccessor._execute_raw_sql_query")
    @patch("masu.database.ocp_report_db_accessor.OCPReportDBAccessor._execute_trino_multipart_sql_query")
    def test_populate_distributed_cost_sql_called(
        self, mock_trino_execute, mock_sql_execute, mock_data_get, mock_table_exists
    ):
        """Test that platform distribution is called and GPU skipped for current month (not first of month)."""
        start_date = self.dh.this_month_start.date()
        end_date = self.dh.this_month_end.date()
        masu_database, mock_jinja = self._setup_distributed_cost_sql_mocks(start_date, end_date)

        with (
            self.accessor as acc,
            patch("masu.database.ocp_report_db_accessor.DateHelper") as mock_dh_class,
        ):
            mock_dh = Mock()
            mock_dh.parse_to_date.return_value = start_date
            mock_dh.now_utc = self.dh.now.replace(day=15)  # Not the first of the month
            mock_dh_class.return_value = mock_dh

            acc.prepare_query = mock_jinja
            summary_range = SummaryRangeConfig(start_date=start_date, end_date=end_date)
            acc.populate_distributed_cost_sql(
                summary_range,
                self.ocp_test_provider_uuid,
                {"worker_cost": True, "platform_cost": True, "gpu_unallocated": True},
            )
            # GPU should NOT be called since it's not the 1st of the month
            gpu_call = call(
                masu_database,
                "trino_sql/openshift/cost_model/distribute_cost/distribute_unallocated_gpu_cost.sql",
            )
            self.assertNotIn(gpu_call, mock_data_get.call_args_list)
            mock_sql_execute.assert_called()
            mock_trino_execute.assert_not_called()

    @patch("masu.util.ocp.common.trino_table_exists", return_value=True)
    @patch("masu.database.ocp_report_db_accessor.pkgutil.get_data")
    @patch("masu.database.ocp_report_db_accessor.OCPReportDBAccessor._execute_raw_sql_query")
    @patch("masu.database.ocp_report_db_accessor.OCPReportDBAccessor._execute_trino_multipart_sql_query")
    def test_populate_distributed_cost_sql_gpu_runs_prev_month_on_first_of_month(
        self, mock_trino_execute, mock_sql_execute, mock_data_get, mock_table_exists
    ):
        """Test that GPU distribution runs for previous month only on the first of the month."""
        start_date = self.dh.this_month_start.date()
        end_date = self.dh.this_month_end.date()
        masu_database, mock_jinja = self._setup_distributed_cost_sql_mocks(start_date, end_date)

        with (
            self.accessor as acc,
            patch("masu.database.ocp_report_db_accessor.DateHelper") as mock_dh_class,
        ):
            mock_dh = Mock()
            mock_dh.parse_to_date.return_value = start_date
            mock_dh.now_utc = self.dh.now.replace(day=1)  # First of the month
            mock_dh.last_month_start = self.dh.last_month_start
            mock_dh.last_month_end = self.dh.last_month_end
            mock_dh_class.return_value = mock_dh

            acc.prepare_query = mock_jinja
            summary_range = SummaryRangeConfig(start_date=start_date, end_date=end_date)
            acc.populate_distributed_cost_sql(
                summary_range,
                self.ocp_test_provider_uuid,
                {"worker_cost": True, "platform_cost": True, "gpu_unallocated": True},
            )
            gpu_call = call(
                masu_database,
                "trino_sql/openshift/cost_model/distribute_cost/distribute_unallocated_gpu_cost.sql",
            )
            self.assertIn(gpu_call, mock_data_get.call_args_list)
            mock_trino_execute.assert_called()

    @patch("masu.util.ocp.common.trino_table_exists", return_value=True)
    @patch("masu.database.ocp_report_db_accessor.pkgutil.get_data")
    @patch("masu.database.ocp_report_db_accessor.OCPReportDBAccessor._execute_raw_sql_query")
    @patch("masu.database.ocp_report_db_accessor.OCPReportDBAccessor._execute_trino_multipart_sql_query")
    def test_populate_distributed_cost_sql_gpu_runs_for_previous_month(
        self, mock_trino_execute, mock_sql_execute, mock_data_get, mock_table_exists
    ):
        """Test that GPU distribution runs when directly processing a previous month."""
        start_date = self.dh.last_month_start.date()
        end_date = self.dh.last_month_end.date()
        masu_database, mock_jinja = self._setup_distributed_cost_sql_mocks(start_date, end_date)

        with self.accessor as acc:
            acc.prepare_query = mock_jinja
            summary_range = SummaryRangeConfig(start_date=start_date, end_date=end_date)
            acc.populate_distributed_cost_sql(
                summary_range,
                self.ocp_test_provider_uuid,
                {"worker_cost": True, "platform_cost": True, "gpu_unallocated": True},
            )
            gpu_call = call(
                masu_database,
                "trino_sql/openshift/cost_model/distribute_cost/distribute_unallocated_gpu_cost.sql",
            )
            self.assertIn(gpu_call, mock_data_get.call_args_list)
            mock_trino_execute.assert_called()

    @patch("masu.util.ocp.common.trino_table_exists", return_value=True)
    @patch("masu.database.ocp_report_db_accessor.pkgutil.get_data")
    @patch("masu.database.ocp_report_db_accessor.OCPReportDBAccessor._execute_raw_sql_query")
    @patch("masu.database.ocp_report_db_accessor.OCPReportDBAccessor._execute_trino_multipart_sql_query")
    @patch("masu.database.ocp_report_db_accessor.OCPReportDBAccessor.report_periods_for_provider_uuid")
    def test_populate_distributed_cost_sql_gpu_skipped_no_prev_report_period(
        self, mock_report_periods, mock_trino_execute, mock_sql_execute, mock_data_get, mock_table_exists
    ):
        """Test that GPU distribution is skipped when no report period exists for previous month."""
        start_date = self.dh.this_month_start.date()
        end_date = self.dh.this_month_end.date()
        masu_database, mock_jinja = self._setup_distributed_cost_sql_mocks(start_date, end_date)

        # Return current month report period, but None for previous month
        current_report_period = Mock()
        current_report_period.id = 1
        mock_report_periods.side_effect = lambda provider_uuid, date: (
            current_report_period if date == start_date else None
        )

        with (
            self.accessor as acc,
            patch("masu.database.ocp_report_db_accessor.DateHelper") as mock_dh_class,
        ):
            mock_dh = Mock()
            mock_dh.parse_to_date.return_value = start_date
            mock_dh.now_utc = self.dh.now.replace(day=1)  # First of the month
            mock_dh.last_month_start = self.dh.last_month_start
            mock_dh.last_month_end = self.dh.last_month_end
            mock_dh_class.return_value = mock_dh

            acc.prepare_query = mock_jinja
            summary_range = SummaryRangeConfig(start_date=start_date, end_date=end_date)
            acc.populate_distributed_cost_sql(
                summary_range,
                self.ocp_test_provider_uuid,
                {"worker_cost": True, "platform_cost": True, "gpu_unallocated": True},
            )
            # GPU should NOT be called since no report period exists for previous month
            gpu_call = call(
                masu_database,
                "trino_sql/openshift/cost_model/distribute_cost/distribute_unallocated_gpu_cost.sql",
            )
            self.assertNotIn(gpu_call, mock_data_get.call_args_list)
            mock_trino_execute.assert_not_called()

    def test_update_line_item_daily_summary_with_tag_mapping(self):
        """
        This tests the tag mapping feature.
        """
        populated_keys = []
        with schema_context(self.schema):
            enabled_tags = EnabledTagKeys.objects.filter(provider_type=Provider.PROVIDER_OCP, enabled=True)
            for enabled_tag in enabled_tags:
                tag_count = OCPUsageLineItemDailySummary.objects.filter(
                    all_labels__has_key=enabled_tag.key,
                    usage_start__gte=self.dh.this_month_start,
                    usage_start__lte=self.dh.today,
                ).count()
                if tag_count > 0:
                    key_metadata = [enabled_tag.key, enabled_tag, tag_count]
                    populated_keys.append(key_metadata)
            parent_key, parent_obj, parent_count = populated_keys[0]
            child_key, child_obj, child_count = populated_keys[1]
            # Check to see how many of our keys where the parent & child key
            # were present in the data.
            value_precedence_count = OCPUsageLineItemDailySummary.objects.filter(
                Q(all_labels__has_key=parent_key) & Q(all_labels__has_key=child_key),
                usage_start__gte=self.dh.this_month_start,
                usage_start__lte=self.dh.today,
            ).count()
            TagMapping.objects.create(parent=parent_obj, child=child_obj)
            self.accessor.update_line_item_daily_summary_with_tag_mapping(self.dh.this_month_start, self.dh.today)
            expected_parent_count = (parent_count + child_count) - value_precedence_count
            actual_parent_count = OCPUsageLineItemDailySummary.objects.filter(
                all_labels__has_key=parent_key,
                usage_start__gte=self.dh.this_month_start,
                usage_start__lte=self.dh.today,
            )
            self.assertEqual(expected_parent_count, actual_parent_count.count())
            actual_child_count = OCPUsageLineItemDailySummary.objects.filter(
                all_labels__has_key=child_key,
                usage_start__gte=self.dh.this_month_start,
                usage_start__lte=self.dh.today,
            ).count()
            self.assertEqual(0, actual_child_count)

            # Test correct value presedence
            tested = False
            distinct_values = (
                OCPUsageLineItemDailySummary.objects.filter(
                    usage_start__gte=self.dh.this_month_start, usage_start__lte=self.dh.today
                )
                .values_list(f"volume_labels__{parent_key}", flat=True)
                .distinct()
            )
            parent_values = []
            child_values = []
            for dikt in OCP_PVC_LABELS:
                parent_values.append(dikt.get(parent_key))
                child_values.append(dikt.get(child_key))
            for distinct_value in distinct_values:
                if distinct_value is None:
                    continue
                self.assertIn(distinct_value, parent_values)
                self.assertNotIn(distinct_value, child_values)
                tested = True
            self.assertTrue(tested)

    def test_no_report_period_populate_vm_tag_based_costs(self):
        """
        Test that if a valid report period is not found.
        """
        with self.accessor as acc:
            result = acc.populate_tag_based_costs("1970-10-01", "1970-10-31", self.ocp_provider_uuid, {}, {})
            self.assertFalse(result)

    @patch("masu.database.ocp_report_db_accessor.OCPReportDBAccessor._prepare_and_execute_raw_sql_query")
    @patch("masu.database.ocp_report_db_accessor.trino_table_exists", return_value=False)
    def test_monthly_populate_vm_tag_based_costs(self, mock_trino_exists, mock_psql):
        """Test monthly populated of vm count tag based costs."""
        test_mapping = {
            metric_constants.OCP_VM_MONTH: [
                {"rate_type": "Supplementary", "tag_key": "group", "value_rates": {"Engineering": 0.05}}
            ]
        }
        with self.accessor as acc:
            acc.populate_tag_based_costs(
                self.start_date,
                self.dh.this_month_end,
                self.ocp_provider_uuid,
                test_mapping,
                {"cluster_id": "test", "cluster_alias": "test"},
            )
            mock_psql.assert_called()

    @patch("masu.database.ocp_report_db_accessor.OCPReportDBAccessor._execute_trino_multipart_sql_query")
    @patch("masu.database.ocp_report_db_accessor.trino_table_exists", return_value=False)
    def test_hourly_populate_vm_tag_based_costs(self, mock_trino_exists, mock_trino):
        """Test hourly populated of vm count tag based costs."""
        cluster_params = {"cluster_id": "test", "cluster_alias": "test"}
        test_mapping = {
            metric_constants.OCP_VM_HOUR: [
                {"rate_type": "Supplementary", "tag_key": "group", "value_rates": {"Engineering": 0.05}}
            ]
        }
        with self.accessor as acc:
            acc.populate_tag_based_costs(
                self.start_date, self.dh.this_month_end, self.ocp_provider_uuid, test_mapping, cluster_params
            )
            mock_trino.assert_called()

    @patch("masu.database.ocp_report_db_accessor.OCPReportDBAccessor._prepare_and_execute_raw_sql_query")
    def test_no_tag_rates(self, mock_psql):
        """Test monthly populated of vm count tag based costs."""
        with self.accessor as acc:
            acc.populate_tag_based_costs(
                self.start_date,
                self.dh.this_month_end,
                self.ocp_provider_uuid,
                {},
                {"cluster_id": "test", "cluster_alias": "test"},
            )
            mock_psql.assert_not_called()

    @patch("masu.database.ocp_report_db_accessor.OCPReportDBAccessor.schema_exists_trino", return_value=False)
    @patch("masu.database.ocp_report_db_accessor.OCPReportDBAccessor._prepare_and_execute_raw_sql_query")
    def test__populate_virtualization_ui_summary_table_no_trino_schema(self, mock_psql, mock_schema_exists):
        """Test that sql is not run when the trino schema does not exist."""
        with self.accessor as acc:
            acc._populate_virtualization_ui_summary_table({})
            mock_psql.assert_not_called()

    @patch("masu.database.ocp_report_db_accessor.trino_table_exists", return_value=[True, False])
    @patch("masu.database.ocp_report_db_accessor.OCPReportDBAccessor.schema_exists_trino", return_value=True)
    @patch("masu.database.ocp_report_db_accessor.OCPReportDBAccessor._prepare_and_execute_raw_sql_query")
    def test__populate_virtualization_ui_summary_table_no_trino_table(self, mock_psql, *args):
        """Test that sql is not run when the trino table does not exist."""
        with self.accessor as acc:
            acc._populate_virtualization_ui_summary_table({})
            mock_psql.assert_not_called()

    @patch("masu.database.ocp_report_db_accessor.trino_table_exists", return_value=[True, True])
    @patch("masu.database.ocp_report_db_accessor.OCPReportDBAccessor.schema_exists_trino", return_value=True)
    @patch("masu.database.ocp_report_db_accessor.OCPReportDBAccessor._prepare_and_execute_raw_sql_query")
    def test__populate_virtualization_ui_summary_table_no_sql_param(self, mock_psql, *args):
        """Test that sql is not run when sql params are not provided."""
        with self.accessor as acc:
            acc._populate_virtualization_ui_summary_table({})
            mock_psql.assert_not_called()

    @patch("masu.database.ocp_report_db_accessor.trino_table_exists", return_value=[True, True])
    @patch("masu.database.ocp_report_db_accessor.OCPReportDBAccessor.schema_exists_trino", return_value=True)
    @patch(
        "masu.database.ocp_report_db_accessor.OCPReportDBAccessor._prepare_and_execute_raw_sql_query",
        side_effect=Exception,
    )
    def test__populate_virtualization_ui_summary_table_all_true_raise_error(self, mock_psql, *args):
        """Test that sql is run when all requirements are met. Test uses an exception to show that sql would be run."""
        with self.accessor as acc:
            with self.assertRaises(Exception):
                acc._populate_virtualization_ui_summary_table({"start_date": "1970-01-01"})
            mock_psql.assert_called()

    @patch("masu.database.ocp_report_db_accessor.trino_table_exists", return_value=True)
    @patch("masu.database.ocp_report_db_accessor.OCPReportDBAccessor._execute_trino_multipart_sql_query")
    def test_monthly_populate_gpu_tag_based_costs(self, mock_trino_exec, mock_trino_exists):
        """Test monthly population of GPU tag based costs."""
        # Tag key is the GPU vendor, value_rates contains model-specific rates
        test_mapping = {
            metric_constants.OCP_GPU_MONTH: [
                {
                    "rate_type": "Infrastructure",
                    "tag_key": "nvidia",
                    "value_rates": {"Tesla T4": 1000, "A100": 2500, "H100": 5000},
                    "default_rate": 5000,
                },
            ]
        }
        with self.accessor as acc:
            acc.populate_tag_based_costs(
                self.start_date,
                self.dh.this_month_end,
                self.ocp_provider_uuid,
                test_mapping,
                {"cluster_id": "test", "cluster_alias": "test"},
            )
            mock_trino_exec.assert_called()

    @patch("masu.database.ocp_report_db_accessor.is_feature_flag_enabled_by_account", return_value=False)
    @patch("masu.database.ocp_report_db_accessor.trino_table_exists", return_value=True)
    @patch("masu.database.ocp_report_db_accessor.OCPReportDBAccessor._execute_trino_multipart_sql_query")
    def test_gpu_cost_model_disabled_by_unleash(self, mock_trino_exec, mock_trino_exists, mock_feature_flag):
        """Test that GPU cost model is skipped when Unleash flag is disabled."""
        # Tag key is the GPU vendor, value_rates contains model-specific rates
        test_mapping = {
            metric_constants.OCP_GPU_MONTH: [
                {
                    "rate_type": "Infrastructure",
                    "tag_key": "nvidia",
                    "value_rates": {"Tesla T4": 1000},
                    "default_rate": 1000,
                }
            ]
        }
        with self.accessor as acc:
            acc.populate_tag_based_costs(
                self.start_date,
                self.dh.this_month_end,
                self.ocp_provider_uuid,
                test_mapping,
                {"cluster_id": "test", "cluster_alias": "test"},
            )
            # Should not call SQL execution when flag is disabled
            mock_trino_exec.assert_not_called()


class OCPReportDBAccessorGPUUITest(MasuTestCase):
    """Test Cases for GPU UI summary table population."""

    def setUp(self):
        """Set up test fixtures."""
        super().setUp()
        self.accessor = OCPReportDBAccessor(schema=self.schema)
        self.sql_params = {
            "start_date": self.dh.this_month_start.date(),
            "end_date": self.dh.this_month_end.date(),
            "source_uuid": self.ocp_provider.uuid,
            "year": "2026",
            "month": "01",
        }

    @patch("masu.database.ocp_report_db_accessor.get_cluster_id_from_provider")
    @patch("masu.database.ocp_report_db_accessor.CostModelDBAccessor")
    @patch("masu.database.ocp_report_db_accessor.trino_table_exists")
    @patch("masu.database.ocp_report_db_accessor.OCPReportDBAccessor._execute_trino_raw_sql_query")
    def test_populate_gpu_ui_summary_table_with_usage_only_no_cluster_id(
        self,
        mock_trino_raw_sql,
        mock_trino_table_exists,
        mock_cost_model_accessor,
        mock_get_cluster_id,
    ):
        """Test that GPU UI table is not populated when source has no cluster ID."""
        mock_get_cluster_id.return_value = None
        mock_trino_table_exists.return_value = True
        mock_trino_raw_sql.return_value = [[1]]  # Source has GPU data
        mock_cost_model_instance = Mock()
        mock_cost_model_instance.metric_to_tag_params_map = {}
        mock_cost_model_accessor.return_value = mock_cost_model_instance
        with (
            patch.object(self.accessor, "_execute_trino_multipart_sql_query") as mock_trino_exec,
            self.accessor as acc,
        ):
            acc._populate_gpu_ui_summary_table_with_usage_only(self.sql_params)
            mock_trino_exec.assert_not_called()
            mock_get_cluster_id.assert_called_once_with(self.ocp_provider.uuid)

    @patch("masu.database.ocp_report_db_accessor.trino_table_exists")
    @patch("masu.database.ocp_report_db_accessor.OCPReportDBAccessor._execute_trino_raw_sql_query")
    def test_populate_gpu_ui_summary_table_with_usage_only_no_gpu_data(
        self, mock_trino_raw_sql, mock_trino_table_exists
    ):
        """Test that GPU UI table is not populated when source has no GPU data in Trino."""
        mock_trino_table_exists.return_value = True
        mock_trino_raw_sql.return_value = [[0]]  # No GPU data (count is 0)
        with (
            patch.object(self.accessor, "_execute_trino_multipart_sql_query") as mock_trino_exec,
            self.accessor as acc,
        ):
            acc._populate_gpu_ui_summary_table_with_usage_only(self.sql_params)
            mock_trino_exec.assert_not_called()

    @patch("masu.database.ocp_report_db_accessor.CostModelDBAccessor")
    @patch("masu.database.ocp_report_db_accessor.trino_table_exists")
    @patch("masu.database.ocp_report_db_accessor.OCPReportDBAccessor._execute_trino_raw_sql_query")
    def test_populate_gpu_ui_summary_table_with_usage_only_has_cost_model(
        self, mock_trino_raw_sql, mock_trino_table_exists, mock_cost_model_accessor
    ):
        """Test that GPU UI table is not populated when source has GPU cost model configured."""
        mock_trino_table_exists.return_value = True
        mock_trino_raw_sql.return_value = [[5]]  # Source has GPU data (5 partitions)
        mock_cost_model_instance = Mock()
        mock_cost_model_instance.metric_to_tag_params_map = {
            metric_constants.OCP_GPU_MONTH: [{"rate_type": "Infrastructure", "tag_key": "nvidia"}]
        }
        mock_cost_model_accessor.return_value.__enter__ = Mock(return_value=mock_cost_model_instance)
        mock_cost_model_accessor.return_value.__exit__ = Mock(return_value=False)
        with (
            patch.object(self.accessor, "_execute_trino_multipart_sql_query") as mock_trino_exec,
            self.accessor as acc,
        ):
            acc._populate_gpu_ui_summary_table_with_usage_only(self.sql_params)
            mock_trino_exec.assert_not_called()

    @patch("masu.database.ocp_report_db_accessor.get_cluster_alias_from_cluster_id")
    @patch("masu.database.ocp_report_db_accessor.get_cluster_id_from_provider")
    @patch("masu.database.ocp_report_db_accessor.CostModelDBAccessor")
    @patch("masu.database.ocp_report_db_accessor.trino_table_exists")
    @patch("masu.database.ocp_report_db_accessor.OCPReportDBAccessor._execute_trino_raw_sql_query")
    def test_populate_gpu_ui_summary_table_with_usage_only_no_cost_model(
        self,
        mock_trino_raw_sql,
        mock_trino_table_exists,
        mock_cost_model_accessor,
        mock_get_cluster_id,
        mock_get_cluster_alias,
    ):
        """Test that GPU UI table is populated when source has GPU data but no cost model."""
        mock_trino_table_exists.return_value = True
        mock_trino_raw_sql.return_value = [[3]]  # Source has GPU data (3 partitions)
        mock_cost_model_instance = Mock()
        mock_cost_model_instance.metric_to_tag_params_map = {}  # No GPU cost model
        mock_cost_model_accessor.return_value = mock_cost_model_instance
        mock_get_cluster_id.return_value = "test-cluster-id"
        mock_get_cluster_alias.return_value = "test-cluster-alias"
        with (
            patch.object(self.accessor, "_execute_trino_multipart_sql_query") as mock_trino_exec,
            self.accessor as acc,
        ):
            acc._populate_gpu_ui_summary_table_with_usage_only(self.sql_params)
            mock_trino_exec.assert_called_once()

    @patch("masu.database.ocp_report_db_accessor.trino_table_exists")
    @patch("masu.database.ocp_report_db_accessor.OCPReportDBAccessor._execute_trino_raw_sql_query")
    def test_populate_gpu_ui_summary_table_with_usage_only_source_in_trino_returns_zero(
        self, mock_trino_raw_sql, mock_trino_table_exists
    ):
        """Test that GPU UI table is not populated when source check returns zero count."""
        mock_trino_table_exists.return_value = True
        mock_trino_raw_sql.return_value = [[0]]  # Source has no GPU data (count is 0)
        with (
            patch.object(self.accessor, "_execute_trino_multipart_sql_query") as mock_trino_exec,
            self.accessor as acc,
        ):
            acc._populate_gpu_ui_summary_table_with_usage_only(self.sql_params)
            # With the fix, 0 is now falsy and function returns early
            mock_trino_exec.assert_not_called()

    @patch("masu.database.ocp_report_db_accessor.trino_table_exists")
    @patch("masu.database.ocp_report_db_accessor.OCPReportDBAccessor.schema_exists_trino", return_value=True)
    @patch("masu.database.ocp_report_db_accessor.OCPReportDBAccessor._prepare_and_execute_raw_sql_query")
    @patch("masu.database.ocp_report_db_accessor.OCPReportDBAccessor._execute_trino_raw_sql_query")
    def test_populate_virtualization_ui_summary_table_uses_source_in_trino_table(
        self, mock_trino_sql, mock_psql, mock_schema_exists, mock_trino_table_exists
    ):
        """Test that _populate_virtualization_ui_summary_table uses _execute_trino_raw_sql_query."""
        mock_trino_table_exists.return_value = True
        mock_trino_sql.return_value = [[1]]  # Source found in VM table (count is 1)
        with (
            patch.object(self.accessor, "_execute_trino_multipart_sql_query"),
            self.accessor as acc,
        ):
            acc._populate_virtualization_ui_summary_table(self.sql_params)
            # Verify _execute_trino_raw_sql_query was called for VM usage table
            mock_trino_sql.assert_called()

    @patch("masu.database.ocp_report_db_accessor.trino_table_exists")
    @patch("masu.database.ocp_report_db_accessor.OCPReportDBAccessor.schema_exists_trino", return_value=True)
    @patch("masu.database.ocp_report_db_accessor.OCPReportDBAccessor._prepare_and_execute_raw_sql_query")
    @patch("masu.database.ocp_report_db_accessor.OCPReportDBAccessor._execute_trino_raw_sql_query")
    def test_populate_virtualization_ui_summary_table_vm_table_not_in_source(
        self, mock_trino_sql, mock_psql, mock_schema_exists, mock_trino_table_exists
    ):
        """Test that _populate_virtualization_ui_summary_table uses fallback when VM table has no source data."""
        mock_trino_table_exists.return_value = True
        mock_trino_sql.return_value = [[0]]  # Source NOT found in VM table (count is 0)
        with (
            patch.object(self.accessor, "_execute_trino_multipart_sql_query"),
            patch("masu.database.ocp_report_db_accessor.pkgutil.get_data") as mock_get_data,
            self.accessor as acc,
        ):
            mock_get_data.return_value = b"SELECT 1"
            acc._populate_virtualization_ui_summary_table(self.sql_params)
            # Verify that the fallback SQL file is used when source is not in VM table
            calls = mock_get_data.call_args_list
            # Should use populate_vm_tmp_table.sql (fallback) instead of populate_vm_tmp_table_with_vm_report.sql
            sql_files_used = [str(call) for call in calls]
            self.assertTrue(any("populate_vm_tmp_table.sql" in s for s in sql_files_used))
