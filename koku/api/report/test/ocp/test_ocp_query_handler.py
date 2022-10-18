#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the Report Queries."""
import logging
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch
from unittest.mock import PropertyMock

from dateutil.relativedelta import relativedelta
from django.db.models import Max
from django.db.models import Sum
from django.db.models.expressions import OrderBy
from rest_framework.exceptions import ValidationError
from tenant_schemas.utils import tenant_context

from api.iam.test.iam_test_case import IamTestCase
from api.query_filter import QueryFilterCollection
from api.report.ocp.query_handler import OCPReportQueryHandler
from api.report.ocp.serializers import ExcludeSerializer
from api.report.ocp.view import OCPCostView
from api.report.ocp.view import OCPCpuView
from api.report.ocp.view import OCPMemoryView
from api.report.ocp.view import OCPVolumeView
from api.tags.ocp.queries import OCPTagQueryHandler
from api.tags.ocp.view import OCPTagView
from api.utils import DateHelper
from api.utils import materialized_view_month_start
from reporting.models import OCPCostSummaryByProjectP
from reporting.models import OCPUsageLineItemDailySummary
from reporting.provider.ocp.models import OCPUsageReportPeriod

LOG = logging.getLogger(__name__)


def _calculate_subtotals(data, cost, infra, sup):
    """Returns list of subtotals given data."""
    for _, value in data.items():
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    if "values" in item.keys():
                        value = item["values"][0]
                        cost.append(value["cost"]["total"]["value"])
                        infra.append(value["infrastructure"]["total"]["value"])
                        sup.append(value["supplementary"]["total"]["value"])
                    else:
                        cost, infra, sup = _calculate_subtotals(item, cost, infra, sup)
            return (cost, infra, sup)


class OCPReportQueryHandlerTest(IamTestCase):
    """Tests for the OCP report query handler."""

    def setUp(self):
        """Set up the customer view tests."""
        super().setUp()
        self.dh = DateHelper()

        self.this_month_filter = {"usage_start__gte": self.dh.this_month_start}
        self.ten_day_filter = {"usage_start__gte": self.dh.n_days_ago(self.dh.today, 9)}
        self.thirty_day_filter = {"usage_start__gte": self.dh.n_days_ago(self.dh.today, 29)}
        self.last_month_filter = {
            "usage_start__gte": self.dh.last_month_start,
            "usage_end__lte": self.dh.last_month_end,
        }
        with tenant_context(self.tenant):
            self.namespaces = OCPUsageLineItemDailySummary.objects.values("namespace").distinct()
            self.namespaces = [entry.get("namespace") for entry in self.namespaces]

    def get_totals(self, handler, filters=None):
        aggregates = handler._mapper.report_type_map.get("aggregates")
        with tenant_context(self.tenant):
            return (
                OCPUsageLineItemDailySummary.objects.filter(**filters)
                .annotate(**handler.annotations)
                .aggregate(**aggregates)
            )

    def get_totals_by_time_scope(self, handler, filters=None):
        """Return the total aggregates for a time period."""
        if filters is None:
            filters = self.ten_day_filter
        return self.get_totals(handler, filters)

    def get_totals_costs_by_time_scope(self, handler, filters=None):
        """Return the total costs aggregates for a time period."""
        if filters is None:
            filters = self.this_month_filter
        return self.get_totals(handler, filters)

    def test_execute_sum_query(self):
        """Test that the sum query runs properly."""
        url = "?"
        query_params = self.mocked_query_params(url, OCPCpuView)
        handler = OCPReportQueryHandler(query_params)
        current_totals = self.get_totals_by_time_scope(handler)
        query_output = handler.execute_query()
        self.assertIsNotNone(query_output.get("data"))
        self.assertIsNotNone(query_output.get("total"))
        total = query_output.get("total")

        self.assertEqual(total.get("usage", {}).get("value"), current_totals.get("usage"))
        self.assertEqual(total.get("request", {}).get("value"), current_totals.get("request"))
        self.assertEqual(total.get("cost", {}).get("value"), current_totals.get("cost"))
        self.assertEqual(total.get("limit", {}).get("value"), current_totals.get("limit"))

    def test_execute_sum_query_costs(self):
        """Test that the sum query runs properly for the costs endpoint."""
        url = "?"
        query_params = self.mocked_query_params(url, OCPCostView)
        handler = OCPReportQueryHandler(query_params)
        current_totals = self.get_totals_costs_by_time_scope(handler, self.ten_day_filter)
        expected_cost_total = current_totals.get("cost_total")
        self.assertIsNotNone(expected_cost_total)
        query_output = handler.execute_query()
        self.assertIsNotNone(query_output.get("data"))
        self.assertIsNotNone(query_output.get("total"))
        total = query_output.get("total")
        result_cost_total = total.get("cost", {}).get("total", {}).get("value")
        self.assertIsNotNone(result_cost_total)
        self.assertEqual(result_cost_total, expected_cost_total)

    def test_get_cluster_capacity_monthly_resolution(self):
        """Test that cluster capacity returns a full month's capacity."""
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly"
        query_params = self.mocked_query_params(url, OCPCpuView)
        handler = OCPReportQueryHandler(query_params)
        query_data = [{"row": 1}]
        query_data, total_capacity = handler.get_cluster_capacity(query_data)
        self.assertTrue("capacity" in total_capacity)
        self.assertTrue(isinstance(total_capacity["capacity"], Decimal))
        self.assertTrue("capacity" in query_data[0])
        self.assertIsNotNone(query_data[0].get("capacity"))
        self.assertIsNotNone(total_capacity.get("capacity"))
        self.assertEqual(query_data[0].get("capacity"), total_capacity.get("capacity"))

    def test_get_cluster_capacity_monthly_resolution_group_by_cluster(self):
        """Test that cluster capacity returns capacity by cluster."""
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&group_by[cluster]=*"  # noqa: E501
        query_params = self.mocked_query_params(url, OCPCpuView)
        handler = OCPReportQueryHandler(query_params)
        query_data = handler.execute_query()

        capacity_by_cluster = defaultdict(Decimal)
        total_capacity = Decimal(0)
        query_filter = handler.query_filter
        query_group_by = ["usage_start", "cluster_id"]
        annotations = {"capacity": Max("cluster_capacity_cpu_core_hours")}
        cap_key = list(annotations.keys())[0]

        q_table = handler._mapper.provider_map.get("tables").get("query")
        query = q_table.objects.filter(query_filter)

        with tenant_context(self.tenant):
            cap_data = query.values(*query_group_by).annotate(**annotations)
            for entry in cap_data:
                cluster_id = entry.get("cluster_id", "")
                capacity_by_cluster[cluster_id] += entry.get(cap_key, 0)
                total_capacity += entry.get(cap_key, 0)

        for entry in query_data.get("data", []):
            for cluster in entry.get("clusters", []):
                cluster_name = cluster.get("cluster", "")
                capacity = cluster.get("values")[0].get("capacity", {}).get("value")
                self.assertEqual(capacity, capacity_by_cluster[cluster_name])

        self.assertEqual(query_data.get("total", {}).get("capacity", {}).get("value"), total_capacity)

    def test_get_cluster_capacity_monthly_resolution_start_end_date(self):
        """Test that cluster capacity returns capacity by month."""
        start_date = self.dh.last_month_end.date()
        end_date = self.dh.today.date()
        url = f"?start_date={start_date}&end_date={end_date}&filter[resolution]=monthly"
        query_params = self.mocked_query_params(url, OCPCpuView)
        handler = OCPReportQueryHandler(query_params)
        query_data = handler.execute_query()

        with tenant_context(self.tenant):
            total_capacity = (
                OCPUsageLineItemDailySummary.objects.filter(
                    usage_start__gte=start_date, usage_start__lte=end_date, data_source="Pod"
                )
                .values("usage_start", "cluster_id")
                .annotate(capacity=Max("cluster_capacity_cpu_core_hours"))
                .aggregate(total=Sum("capacity"))
            )
        self.assertAlmostEqual(
            query_data.get("total", {}).get("capacity", {}).get("value"), total_capacity.get("total"), 6
        )

    def test_get_cluster_capacity_monthly_resolution_start_end_date_group_by_cluster(self):
        """Test that cluster capacity returns capacity by cluster."""
        url = (
            f"?start_date={self.dh.last_month_end.date()}&end_date={self.dh.today.date()}"
            f"&filter[resolution]=monthly&group_by[cluster]=*"
        )
        query_params = self.mocked_query_params(url, OCPCpuView)
        handler = OCPReportQueryHandler(query_params)
        query_data = handler.execute_query()

        capacity_by_month_cluster = defaultdict(lambda: defaultdict(Decimal))
        total_capacity = Decimal(0)
        query_filter = handler.query_filter
        query_group_by = ["usage_start", "cluster_id"]
        annotations = {"capacity": Max("cluster_capacity_cpu_core_hours")}
        cap_key = list(annotations.keys())[0]

        q_table = handler._mapper.provider_map.get("tables").get("query")
        query = q_table.objects.filter(query_filter)

        with tenant_context(self.tenant):
            cap_data = query.values(*query_group_by).annotate(**annotations)
            for entry in cap_data:
                cluster_id = entry.get("cluster_id", "")
                month = entry.get("usage_start", "").month
                capacity_by_month_cluster[month][cluster_id] += entry.get(cap_key, 0)
                total_capacity += entry.get(cap_key, 0)

        for entry in query_data.get("data", []):
            month = int(entry.get("date").split("-")[1])
            for cluster in entry.get("clusters", []):
                cluster_name = cluster.get("cluster", "")
                capacity = cluster.get("values")[0].get("capacity", {}).get("value")
                self.assertEqual(capacity, capacity_by_month_cluster[month][cluster_name])

        self.assertEqual(query_data.get("total", {}).get("capacity", {}).get("value"), total_capacity)

    def test_get_cluster_capacity_daily_resolution(self):
        """Test that total capacity is returned daily resolution."""
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=daily"
        query_params = self.mocked_query_params(url, OCPCpuView)
        handler = OCPReportQueryHandler(query_params)
        query_data = handler.execute_query()

        daily_capacity = defaultdict(Decimal)
        total_capacity = Decimal(0)
        query_filter = handler.query_filter
        query_group_by = ["usage_start", "cluster_id"]
        annotations = {"capacity": Max("cluster_capacity_cpu_core_hours")}
        cap_key = list(annotations.keys())[0]

        q_table = handler._mapper.provider_map.get("tables").get("query")
        query = q_table.objects.filter(query_filter)

        with tenant_context(self.tenant):
            cap_data = query.values(*query_group_by).annotate(**annotations)
            for entry in cap_data:
                date = handler.date_to_string(entry.get("usage_start"))
                daily_capacity[date] += entry.get(cap_key, 0)
            cap_data = query.values(*query_group_by).annotate(**annotations)
            for entry in cap_data:
                total_capacity += entry.get(cap_key, 0)

        self.assertEqual(query_data.get("total", {}).get("capacity", {}).get("value"), total_capacity)
        for entry in query_data.get("data", []):
            date = entry.get("date")
            values = entry.get("values")
            if values:
                capacity = values[0].get("capacity", {}).get("value")
                self.assertEqual(capacity, daily_capacity[date])

    def test_get_cluster_capacity_daily_resolution_group_by_clusters(self):
        """Test that cluster capacity returns daily capacity by cluster."""
        url = (
            "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=daily&group_by[cluster]=*"
        )
        query_params = self.mocked_query_params(url, OCPCpuView)
        handler = OCPReportQueryHandler(query_params)
        query_data = handler.execute_query()

        daily_capacity_by_cluster = defaultdict(dict)
        total_capacity = Decimal(0)
        query_filter = handler.query_filter
        query_group_by = ["usage_start", "cluster_id"]
        annotations = {"capacity": Max("cluster_capacity_cpu_core_hours")}
        cap_key = list(annotations.keys())[0]

        q_table = handler._mapper.query_table
        query = q_table.objects.filter(query_filter)

        with tenant_context(self.tenant):
            cap_data = query.values(*query_group_by).annotate(**annotations)
            for entry in cap_data:
                date = handler.date_to_string(entry.get("usage_start"))
                cluster_id = entry.get("cluster_id", "")
                if cluster_id in daily_capacity_by_cluster[date]:
                    daily_capacity_by_cluster[date][cluster_id] += entry.get(cap_key, 0)
                else:
                    daily_capacity_by_cluster[date][cluster_id] = entry.get(cap_key, 0)
                total_capacity += entry.get(cap_key, 0)

        for entry in query_data.get("data", []):
            date = entry.get("date")
            for cluster in entry.get("clusters", []):
                cluster_name = cluster.get("cluster", "")
                capacity = cluster.get("values")[0].get("capacity", {}).get("value")
                self.assertEqual(capacity, daily_capacity_by_cluster[date][cluster_name])

        self.assertEqual(query_data.get("total", {}).get("capacity", {}).get("value"), total_capacity)

    @patch("api.report.ocp.query_handler.ReportQueryHandler.add_deltas")
    @patch("api.report.ocp.query_handler.OCPReportQueryHandler.add_current_month_deltas")
    def test_add_deltas_current_month(self, mock_current_deltas, mock_deltas):
        """Test that the current month method is called for deltas."""
        url = "?"
        query_params = self.mocked_query_params(url, OCPCpuView)
        handler = OCPReportQueryHandler(query_params)
        handler._delta = "usage__request"
        handler.add_deltas([], [])
        mock_current_deltas.assert_called()
        mock_deltas.assert_not_called()

    @patch("api.report.ocp.query_handler.ReportQueryHandler.add_deltas")
    @patch("api.report.ocp.query_handler.OCPReportQueryHandler.add_current_month_deltas")
    def test_add_deltas_super_delta(self, mock_current_deltas, mock_deltas):
        """Test that the super delta method is called for deltas."""
        url = "?"
        query_params = self.mocked_query_params(url, OCPCpuView)
        handler = OCPReportQueryHandler(query_params)
        handler._delta = "usage"

        handler.add_deltas([], [])

        mock_current_deltas.assert_not_called()
        mock_deltas.assert_called()

    def test_add_current_month_deltas(self):
        """Test that current month deltas are calculated."""
        url = "?"
        query_params = self.mocked_query_params(url, OCPCpuView)
        handler = OCPReportQueryHandler(query_params)
        handler._delta = "usage__request"

        q_table = handler._mapper.provider_map.get("tables").get("query")
        with tenant_context(self.tenant):
            query = q_table.objects.filter(handler.query_filter)
            query = query.annotate(**handler.annotations)
            group_by_value = handler._get_group_by()
            query_group_by = ["date"] + group_by_value
            query_order_by = ("-date",)
            query_order_by += (handler.order,)

            annotations = handler.report_annotations
            query_data = query.values(*query_group_by).annotate(**annotations)

            aggregates = handler._mapper.report_type_map.get("aggregates")
            metric_sum = query.aggregate(**aggregates)
            query_sum = {key: metric_sum.get(key) for key in aggregates}

            result = handler.add_current_month_deltas(query_data, query_sum)

            delta_field_one, delta_field_two = handler._delta.split("__")
            field_one_total = Decimal(0)
            field_two_total = Decimal(0)
            for entry in result:
                field_one_total += entry.get(delta_field_one, 0)
                field_two_total += entry.get(delta_field_two, 0)
                delta_percent = entry.get("delta_percent")
                expected = (
                    (entry.get(delta_field_one, 0) / entry.get(delta_field_two, 0) * 100)
                    if entry.get(delta_field_two)
                    else 0
                )
                self.assertEqual(delta_percent, expected)

            expected_total = field_one_total / field_two_total * 100 if field_two_total != 0 else 0

            self.assertEqual(handler.query_delta.get("percent"), expected_total)

    def test_add_current_month_deltas_no_previous_data_w_query_data(self):
        """Test that current month deltas are calculated with no previous data for field two."""
        url = "?filter[time_scope_value]=-1&filter[resolution]=monthly"
        query_params = self.mocked_query_params(
            url, OCPCpuView, path="/api/cost-management/v1/reports/openshift/compute/"
        )
        handler = OCPReportQueryHandler(query_params)
        handler._delta = "usage__foo"

        q_table = handler._mapper.provider_map.get("tables").get("query")
        with tenant_context(self.tenant):
            query = q_table.objects.filter(handler.query_filter)
            query = query.annotate(**handler.annotations)
            group_by_value = handler._get_group_by()
            query_group_by = ["date"] + group_by_value
            query_order_by = ("-date",)
            query_order_by += (handler.order,)

            annotations = annotations = handler.report_annotations
            query_data = query.values(*query_group_by).annotate(**annotations)

            aggregates = handler._mapper.report_type_map.get("aggregates")
            metric_sum = query.aggregate(**aggregates)
            query_sum = {key: metric_sum.get(key) if metric_sum.get(key) else Decimal(0) for key in aggregates}

            result = handler.add_current_month_deltas(query_data, query_sum)

            self.assertEqual(result, query_data)
            self.assertIsNotNone(handler.query_delta["value"])
            self.assertIsNone(handler.query_delta["percent"])

    def test_get_tag_filter_keys(self):
        """Test that filter params with tag keys are returned."""
        url = "?"
        query_params = self.mocked_query_params(url, OCPTagView)
        handler = OCPTagQueryHandler(query_params)
        tag_keys = handler.get_tag_keys(filters=False)

        url = f"?filter[tag:{tag_keys[0]}]=*"
        query_params = self.mocked_query_params(url, OCPCpuView)
        handler = OCPReportQueryHandler(query_params)
        results = handler.get_tag_filter_keys()
        self.assertEqual(results, ["tag:" + tag_keys[0]])

    def test_get_tag_group_by_keys(self):
        """Test that group_by params with tag keys are returned."""
        url = "?"
        query_params = self.mocked_query_params(url, OCPTagView)
        handler = OCPTagQueryHandler(query_params)
        tag_keys = handler.get_tag_keys(filters=False)
        group_by_key = tag_keys[0]

        url = f"?group_by[tag:{group_by_key}]=*"
        query_params = self.mocked_query_params(url, OCPCpuView)
        handler = OCPReportQueryHandler(query_params)
        results = handler.get_tag_group_by_keys()
        self.assertEqual(results, ["tag:" + group_by_key])

    def test_set_tag_filters(self):
        """Test that tag filters are created properly."""
        filters = QueryFilterCollection()

        url = "?"
        query_params = self.mocked_query_params(url, OCPTagView)
        handler = OCPTagQueryHandler(query_params)
        tag_keys = handler.get_tag_keys(filters=False)

        filter_key = tag_keys[0]

        filter_value = "filter"
        group_by_key = tag_keys[1]

        group_by_value = "group_By"

        url = f"?filter[tag:{filter_key}]={filter_value}&group_by[tag:{group_by_key}]={group_by_value}"
        query_params = self.mocked_query_params(url, OCPCpuView)
        handler = OCPReportQueryHandler(query_params)
        filters = handler._set_tag_filters(filters)

        expected = f"""<class 'api.query_filter.QueryFilterCollection'>: (AND: ('pod_labels__{filter_key}__icontains', '{filter_value}')), (AND: ('pod_labels__{group_by_key}__icontains', '{group_by_value}')), """  # noqa: E501

        self.assertEqual(repr(filters), expected)

    def test_get_tag_group_by(self):
        """Test that tag based group bys work."""
        url = "?"
        query_params = self.mocked_query_params(url, OCPTagView)
        handler = OCPTagQueryHandler(query_params)
        tag_keys = handler.get_tag_keys(filters=False)

        group_by_key = tag_keys[0]
        group_by_value = "group_by"
        url = f"?group_by[tag:{group_by_key}]={group_by_value}"
        query_params = self.mocked_query_params(url, OCPCpuView)
        handler = OCPReportQueryHandler(query_params)
        group_by = handler._get_tag_group_by()
        group = group_by[0]
        expected = "pod_labels__" + group_by_key
        self.assertEqual(len(group_by), 1)
        self.assertEqual(group[0], expected)

    def test_get_tag_order_by(self):
        """Verify that a propery order by is returned."""
        tag = "pod_labels__key"
        expected_param = (tag.split("__")[1],)

        url = "?"
        query_params = self.mocked_query_params(url, OCPCpuView)
        handler = OCPReportQueryHandler(query_params)
        result = handler.get_tag_order_by(tag)
        expression = result.expression

        self.assertIsInstance(result, OrderBy)
        self.assertEqual(expression.sql, "pod_labels -> %s")
        self.assertEqual(expression.params, expected_param)

    def test_filter_by_infrastructure_ocp_on_aws(self):
        """Test that filter by infrastructure for ocp on aws."""
        url = "?filter[resolution]=monthly&filter[time_scope_value]=-1&filter[time_scope_units]=month&filter[infrastructures]=aws"  # noqa: E501
        query_params = self.mocked_query_params(url, OCPCpuView)
        handler = OCPReportQueryHandler(query_params)
        query_data = handler.execute_query()

        self.assertTrue(query_data.get("data"))  # check that returned list is not empty
        for entry in query_data.get("data"):
            self.assertTrue(entry.get("values"))
            for value in entry.get("values"):
                self.assertIsNotNone(value.get("usage").get("value"))
                self.assertIsNotNone(value.get("request").get("value"))

    def test_filter_by_infrastructure_ocp_on_azure(self):
        """Test that filter by infrastructure for ocp on azure."""
        url = "?filter[resolution]=monthly&filter[time_scope_value]=-1&filter[time_scope_units]=month&filter[infrastructures]=azure"  # noqa: E501
        query_params = self.mocked_query_params(url, OCPCpuView)
        handler = OCPReportQueryHandler(query_params)
        query_data = handler.execute_query()

        self.assertTrue(query_data.get("data"))  # check that returned list is not empty
        for entry in query_data.get("data"):
            self.assertTrue(entry.get("values"))
            for value in entry.get("values"):
                self.assertIsNotNone(value.get("usage").get("value"))
                self.assertIsNotNone(value.get("request").get("value"))

    def test_filter_by_infrastructure_ocp(self):
        """Test that filter by infrastructure for ocp not on aws."""

        url = "?filter[resolution]=monthly&filter[time_scope_value]=-1&filter[time_scope_units]=month&filter[cluster]=OCP-On-Azure&filter[infrastructures]=aws"  # noqa: E501
        query_params = self.mocked_query_params(url, OCPCpuView)
        handler = OCPReportQueryHandler(query_params)
        query_data = handler.execute_query()

        self.assertTrue(query_data.get("data"))  # check that returned list is not empty
        for entry in query_data.get("data"):
            for value in entry.get("values"):
                self.assertEqual(value.get("usage").get("value"), 0)
                self.assertEqual(value.get("request").get("value"), 0)

    def test_order_by_null_values(self):
        """Test that order_by returns properly sorted data with null data."""
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly"  # noqa: E501
        query_params = self.mocked_query_params(url, OCPCpuView)
        handler = OCPReportQueryHandler(query_params)

        unordered_data = [
            {"node": None, "cluster": "cluster-1"},
            {"node": "alpha", "cluster": "cluster-2"},
            {"node": "bravo", "cluster": "cluster-3"},
            {"node": "oscar", "cluster": "cluster-4"},
        ]

        order_fields = ["node"]
        expected = [
            {"node": "alpha", "cluster": "cluster-2"},
            {"node": "bravo", "cluster": "cluster-3"},
            {"node": "no-node", "cluster": "cluster-1"},
            {"node": "oscar", "cluster": "cluster-4"},
        ]
        ordered_data = handler.order_by(unordered_data, order_fields)
        self.assertEqual(ordered_data, expected)

    def test_ocp_cpu_query_group_by_cluster(self):
        """Test that group by cluster includes cluster and cluster_alias."""
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&filter[limit]=3&group_by[cluster]=*"  # noqa: E501
        query_params = self.mocked_query_params(url, OCPCpuView)
        handler = OCPReportQueryHandler(query_params)

        query_data = handler.execute_query()
        for data in query_data.get("data"):
            self.assertIn("clusters", data)
            for cluster_data in data.get("clusters"):
                self.assertIn("cluster", cluster_data)
                self.assertIn("values", cluster_data)
                for cluster_value in cluster_data.get("values"):
                    # cluster_value is a dictionary
                    self.assertIn("cluster", cluster_value.keys())
                    self.assertIn("clusters", cluster_value.keys())
                    self.assertIsNotNone(cluster_value["cluster"])
                    self.assertIsNotNone(cluster_value["clusters"])

    @patch("api.report.queries.ReportQueryHandler.is_openshift", new_callable=PropertyMock)
    def test_other_clusters(self, mock_is_openshift):
        """Test that group by cluster includes cluster and cluster_alias."""
        mock_is_openshift.return_value = True
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&filter[limit]=1&group_by[cluster]=*"  # noqa: E501
        query_params = self.mocked_query_params(url, OCPCpuView)
        handler = OCPReportQueryHandler(query_params)

        query_data = handler.execute_query()
        for data in query_data.get("data"):
            for cluster_data in data.get("clusters"):
                cluster_name = cluster_data.get("cluster", "")
                if cluster_name == "Other":
                    for cluster_value in cluster_data.get("values"):
                        self.assertTrue(len(cluster_value.get("clusters", [])) == 1)
                        self.assertTrue(len(cluster_value.get("source_uuid", [])) == 1)
                elif cluster_name == "Others":
                    for cluster_value in cluster_data.get("values"):
                        self.assertTrue(len(cluster_value.get("clusters", [])) > 1)
                        self.assertTrue(len(cluster_value.get("source_uuid", [])) > 1)

    @patch("api.report.queries.ReportQueryHandler.is_openshift", new_callable=PropertyMock)
    def test_subtotals_add_up_to_total(self, mock_is_openshift):
        """Test the apply_group_by handles different grouping scenerios."""
        mock_is_openshift.return_value = True
        group_by_list = [
            ("project", "cluster", "node"),
            ("project", "node", "cluster"),
            ("cluster", "project", "node"),
            ("cluster", "node", "project"),
            ("node", "cluster", "project"),
            ("node", "project", "cluster"),
        ]
        base_url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&filter[limit]=3"  # noqa: E501
        tolerance = 1
        for group_by in group_by_list:
            sub_url = "&group_by[%s]=*&group_by[%s]=*&group_by[%s]=*" % group_by
            url = base_url + sub_url
            query_params = self.mocked_query_params(url, OCPCpuView)
            handler = OCPReportQueryHandler(query_params)
            query_data = handler.execute_query()
            the_sum = handler.query_sum
            data = query_data["data"][0]
            result_cost, result_infra, result_sup = _calculate_subtotals(data, [], [], [])
            test_dict = {
                "cost": {
                    "expected": the_sum.get("cost", {}).get("total", {}).get("value"),
                    "result": sum(result_cost),
                },
                "infra": {
                    "expected": the_sum.get("infrastructure", {}).get("total", {}).get("value"),
                    "result": sum(result_infra),
                },
                "sup": {
                    "expected": the_sum.get("supplementary", {}).get("total", {}).get("value"),
                    "result": sum(result_sup),
                },
            }
            for _, data in test_dict.items():
                expected = data["expected"]
                result = data["result"]
                self.assertIsNotNone(expected)
                self.assertIsNotNone(result)
                self.assertLessEqual(abs(expected - result), tolerance)

    def test_source_uuid_mapping(self):  # noqa: C901
        """Test source_uuid is mapped to the correct source."""
        endpoints = [OCPCostView, OCPCpuView, OCPVolumeView, OCPMemoryView]
        with tenant_context(self.tenant):
            expected_source_uuids = list(OCPUsageReportPeriod.objects.all().values_list("provider_id", flat=True))
        source_uuid_list = []
        for endpoint in endpoints:
            urls = ["?", "?group_by[project]=*"]
            if endpoint == OCPCostView:
                urls.append("?group_by[node]=*")
            for url in urls:
                query_params = self.mocked_query_params(url, endpoint)
                handler = OCPReportQueryHandler(query_params)
                query_output = handler.execute_query()
                for dictionary in query_output.get("data"):
                    for _, value in dictionary.items():
                        if isinstance(value, list):
                            for item in value:
                                if isinstance(item, dict):
                                    if "values" in item.keys():
                                        self.assertEqual(len(item["values"]), 1)
                                        value = item["values"][0]
                                        source_uuid_list.extend(value.get("source_uuid"))
        self.assertNotEqual(source_uuid_list, [])
        for source_uuid in source_uuid_list:
            self.assertIn(source_uuid, expected_source_uuids)

    def test_group_by_project_w_limit(self):
        """COST-1252: Test that grouping by project with limit works as expected."""
        url = "?group_by[project]=*&order_by[project]=asc&filter[limit]=2"  # noqa: E501
        query_params = self.mocked_query_params(url, OCPCostView)
        handler = OCPReportQueryHandler(query_params)
        current_totals = self.get_totals_costs_by_time_scope(handler, self.ten_day_filter)
        expected_cost_total = current_totals.get("cost_total")
        self.assertIsNotNone(expected_cost_total)
        query_output = handler.execute_query()
        self.assertIsNotNone(query_output.get("data"))
        self.assertIsNotNone(query_output.get("total"))
        total = query_output.get("total")
        result_cost_total = total.get("cost", {}).get("total", {}).get("value")
        self.assertIsNotNone(result_cost_total)
        self.assertEqual(result_cost_total, expected_cost_total)

    def test_ocp_date_order_by_cost_desc(self):
        """Test that order of every other date matches the order of the `order_by` date."""
        tested = False
        yesterday = self.dh.yesterday.date()
        url = f"?order_by[cost]=desc&order_by[date]={yesterday}&group_by[project]=*"
        query_params = self.mocked_query_params(url, OCPCostView)
        handler = OCPReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")

        proj_annotations = handler.annotations.get("project")
        exch_annotations = handler.annotations.get("exchange_rate")
        infra_exch_annotations = handler.annotations.get("infra_exchange_rate")
        cost_annotations = handler.report_annotations.get("cost_total")
        with tenant_context(self.tenant):
            expected = list(
                OCPCostSummaryByProjectP.objects.filter(usage_start=str(yesterday))
                .annotate(
                    project=proj_annotations,
                    exchange_rate=exch_annotations,
                    infra_exchange_rate=infra_exch_annotations,
                )
                .values("project", "exchange_rate")
                .annotate(cost=cost_annotations)
                .order_by("-cost")
            )
        ranking_map = {}
        count = 1
        for project in expected:
            ranking_map[project.get("project")] = count
            count += 1
        for element in data:
            previous = 0
            for project in element.get("projects"):
                project_name = project.get("project")
                # This if is cause some days may not have same projects.
                # however we want the projects that do match to be in the
                # same order
                if project_name in ranking_map.keys():
                    self.assertGreaterEqual(ranking_map[project_name], previous)
                    previous = ranking_map[project_name]
                    tested = True
        self.assertTrue(tested)

    def test_ocp_date_incorrect_date(self):
        wrong_date = "200BC"
        url = f"?order_by[cost]=desc&order_by[date]={wrong_date}&group_by[project]=*"
        with self.assertRaises(ValidationError):
            self.mocked_query_params(url, OCPCostView)

    def test_ocp_out_of_range_under_date(self):
        wrong_date = materialized_view_month_start() - timedelta(days=1)
        url = f"?order_by[cost]=desc&order_by[date]={wrong_date}&group_by[project]=*"
        with self.assertRaises(ValidationError):
            self.mocked_query_params(url, OCPCostView)

    def test_ocp_out_of_range_over_date(self):
        wrong_date = DateHelper().today.date() + timedelta(days=1)
        url = f"?order_by[cost]=desc&order_by[date]={wrong_date}&group_by[project]=*"
        with self.assertRaises(ValidationError):
            self.mocked_query_params(url, OCPCostView)

    def test_ocp_date_with_no_data(self):
        # This test will group by a date that is out of range for data generated.
        # The data will still return data because other dates will still generate data.
        yesterday = DateHelper().today.date()
        yesterday_month = yesterday - relativedelta(months=2)
        url = f"?group_by[project]=*&order_by[cost]=desc&order_by[date]={yesterday_month}&end_date={yesterday}&start_date={yesterday_month}"  # noqa: E501
        query_params = self.mocked_query_params(url, OCPCostView)
        handler = OCPReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")
        self.assertIsNotNone(data)

    @patch("api.query_params.enable_negative_filtering", return_value=True)
    def test_exclude_functionality(self, _):
        """Test that the exclude feature works for all options."""
        exclude_opts = list(ExcludeSerializer._opfields)
        exclude_opts.remove("infrastructures")  # Tested separately
        for exclude_opt in exclude_opts:
            for view in [OCPCostView, OCPCpuView, OCPMemoryView, OCPVolumeView]:
                with self.subTest(exclude_opt):
                    overall_url = f"?group_by[{exclude_opt}]=*"
                    query_params = self.mocked_query_params(overall_url, view)
                    handler = OCPReportQueryHandler(query_params)
                    overall_output = handler.execute_query()
                    overall_total = handler.query_sum.get("cost", {}).get("total", {}).get("value")
                    opt_dict = overall_output.get("data", [{}])[0]
                    opt_dict = opt_dict.get(f"{exclude_opt}s")[0]
                    opt_value = opt_dict.get(exclude_opt)
                    # Grab filtered value
                    filtered_url = f"?group_by[{exclude_opt}]=*&filter[{exclude_opt}]={opt_value}"
                    query_params = self.mocked_query_params(filtered_url, view)
                    handler = OCPReportQueryHandler(query_params)
                    handler.execute_query()
                    filtered_total = handler.query_sum.get("cost", {}).get("total", {}).get("value")
                    expected_total = overall_total - filtered_total
                    # Test exclude
                    exclude_url = f"?group_by[{exclude_opt}]=*&exclude[{exclude_opt}]={opt_value}"
                    query_params = self.mocked_query_params(exclude_url, view)
                    handler = OCPReportQueryHandler(query_params)
                    self.assertIsNotNone(handler.query_exclusions)
                    excluded_output = handler.execute_query()
                    excluded_total = handler.query_sum.get("cost", {}).get("total", {}).get("value")
                    excluded_data = excluded_output.get("data")
                    # Check to make sure the value is not in the return
                    for date_dict in excluded_data:
                        grouping_list = date_dict.get(f"{exclude_opt}s", [])
                        self.assertIsNotNone(grouping_list)
                        for group_dict in grouping_list:
                            self.assertNotEqual(opt_value, group_dict.get(exclude_opt))
                    self.assertAlmostEqual(expected_total, excluded_total, 6)
                    self.assertNotEqual(overall_total, excluded_total)

    @patch("api.query_params.enable_negative_filtering", return_value=True)
    def test_exclude_infastructures(self, _):
        """Test that the exclude feature works for all options."""
        # It works on cost endpoint, but not the other views:
        for view in [OCPVolumeView, OCPCostView, OCPCpuView, OCPMemoryView]:
            with self.subTest(view=view):
                # Grab overall value
                overall_url = "?"
                query_params = self.mocked_query_params(overall_url, view)
                handler = OCPReportQueryHandler(query_params)
                handler.execute_query()
                ocp_total = handler.query_sum.get("cost", {}).get("total", {}).get("value")
                ocp_raw = handler.query_sum.get("cost").get("raw", {}).get("value")
                # Grab azure filtered value
                azure_url = "?filter[infrastructures]=azure"
                query_params = self.mocked_query_params(azure_url, view)
                handler = OCPReportQueryHandler(query_params)
                handler.execute_query()
                azure_filtered_total = handler.query_sum.get("cost", {}).get("total", {}).get("value")
                # Grab gcp filtered value
                gcp_url = "?filter[infrastructures]=gcp"
                query_params = self.mocked_query_params(gcp_url, view)
                handler = OCPReportQueryHandler(query_params)
                handler.execute_query()
                gcp_filtered_total = handler.query_sum.get("cost", {}).get("total", {}).get("value")
                # Test exclude
                # we subtract the ocp_raw cost here because we only want cost associated to
                # an infrastructure here, or atleas tthat is my understanding.
                expected_total = (ocp_total + azure_filtered_total + gcp_filtered_total) - ocp_raw
                exclude_url = "?exclude[infrastructures]=aws"
                query_params = self.mocked_query_params(exclude_url, view)
                handler = OCPReportQueryHandler(query_params)
                self.assertIsNotNone(handler.query_exclusions)
                handler.execute_query()
                excluded_result = handler.query_sum.get("cost", {}).get("total", {}).get("value")
                self.assertAlmostEqual(expected_total, excluded_result, 6)

    @patch("api.query_params.enable_negative_filtering", return_value=True)
    def test_exclude_tags(self, _):
        """Test that the exclude works for our tags."""
        url = "?"
        query_params = self.mocked_query_params(url, OCPTagView)
        handler = OCPTagQueryHandler(query_params)
        tags = handler.get_tags()
        tag = tags[0]
        tag_key = tag.get("key")
        base_url = f"?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=daily&group_by[tag:{tag_key}]=*"  # noqa: E501
        query_params = self.mocked_query_params(base_url, OCPCostView)
        handler = OCPReportQueryHandler(query_params)
        data = handler.execute_query().get("data")
        exclude_one = None
        exclude_two = None
        for date_dict in data:
            if exclude_one and exclude_two:
                continue
            grouping_list = date_dict.get(f"{tag_key}s", [])
            for group_dict in grouping_list:
                if not exclude_one:
                    exclude_one = group_dict.get(tag_key)
                elif not exclude_two:
                    exclude_two = group_dict.get(tag_key)
        overall_total = handler.query_sum.get("cost", {}).get("total", {}).get("value")
        # single_tag_exclude
        single_exclude = base_url + f"&exclude[tag:{tag_key}]={exclude_one}"
        query_params = self.mocked_query_params(single_exclude, OCPCostView)
        handler = OCPReportQueryHandler(query_params)
        handler.execute_query()
        exclude_total1 = handler.query_sum.get("cost", {}).get("total", {}).get("value")
        self.assertLess(exclude_total1, overall_total)
        double_exclude = single_exclude + f"&exclude[tag:{tag_key}]={exclude_two}"
        query_params = self.mocked_query_params(double_exclude, OCPCostView)
        handler = OCPReportQueryHandler(query_params)
        handler.execute_query()
        exclude_total = handler.query_sum.get("cost", {}).get("total", {}).get("value")
        self.assertLess(exclude_total, exclude_total1)

    @patch("api.query_params.enable_negative_filtering", return_value=True)
    def test_multi_exclude_functionality(self, _):
        """Test that the exclude feature works for all options."""
        exclude_opts = list(ExcludeSerializer._opfields)
        exclude_opts.remove("infrastructures")
        for ex_opt in exclude_opts:
            base_url = f"?group_by[{ex_opt}]=*&filter[time_scope_units]=month&filter[resolution]=monthly&filter[time_scope_value]=-1"  # noqa: E501
            for view in [OCPVolumeView, OCPCostView, OCPCpuView, OCPMemoryView]:
                query_params = self.mocked_query_params(base_url, view)
                handler = OCPReportQueryHandler(query_params)
                overall_output = handler.execute_query()
                opt_dict = overall_output.get("data", [{}])[0]
                opt_list = opt_dict.get(f"{ex_opt}s")
                exclude_one = None
                exclude_two = None
                for exclude_option in opt_list:
                    if "no-" not in exclude_option.get(ex_opt):
                        if not exclude_one:
                            exclude_one = exclude_option.get(ex_opt)
                        elif not exclude_two:
                            exclude_two = exclude_option.get(ex_opt)
                        else:
                            continue
                if not exclude_one or not exclude_two:
                    continue
                url = base_url + f"&exclude[or:{ex_opt}]={exclude_one}&exclude[or:{ex_opt}]={exclude_two}"
                with self.subTest(url=url, view=view, ex_opt=ex_opt):
                    query_params = self.mocked_query_params(url, view)
                    handler = OCPReportQueryHandler(query_params)
                    self.assertIsNotNone(handler.query_exclusions)
                    excluded_output = handler.execute_query()
                    excluded_data = excluded_output.get("data")
                    self.assertIsNotNone(excluded_data)
                    for date_dict in excluded_data:
                        grouping_list = date_dict.get(f"{ex_opt}s", [])
                        self.assertIsNotNone(grouping_list)
                        for group_dict in grouping_list:
                            self.assertNotIn(group_dict.get(ex_opt), [exclude_one, exclude_two])
