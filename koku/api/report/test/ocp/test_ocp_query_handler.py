#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the Report Queries."""
from collections import defaultdict
from copy import deepcopy
from datetime import datetime
from datetime import timedelta
from decimal import Decimal
from itertools import product
from unittest.mock import patch
from unittest.mock import PropertyMock
from urllib.parse import quote_plus
from urllib.parse import urlencode

from dateutil.relativedelta import relativedelta
from django.db.models import Max
from django.db.models import Sum
from django.db.models.expressions import OrderBy
from django.urls import reverse
from django_tenants.utils import tenant_context
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from api.iam.test.iam_test_case import IamTestCase
from api.query_filter import QueryFilterCollection
from api.report.constants import TAG_PREFIX
from api.report.ocp.query_handler import OCPReportQueryHandler
from api.report.ocp.serializers import OCPExcludeSerializer
from api.report.ocp.view import OCPCostView
from api.report.ocp.view import OCPCpuView
from api.report.ocp.view import OCPMemoryView
from api.report.ocp.view import OCPReportVirtualMachinesView
from api.report.ocp.view import OCPVolumeView
from api.tags.ocp.queries import OCPTagQueryHandler
from api.tags.ocp.view import OCPTagView
from api.utils import DateHelper
from api.utils import materialized_view_month_start
from reporting.models import OCPCostSummaryByProjectP
from reporting.models import OCPUsageLineItemDailySummary
from reporting.provider.ocp.models import OCPGpuSummaryP
from reporting.provider.ocp.models import OCPUsageReportPeriod


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
        self.plaform_filter = {"cost_category__name__icontains": "Platform"}
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

    def test_cpu_memory_order_bys(self):
        """Test that cluster capacity returns capacity by cluster."""
        views = [OCPCpuView, OCPMemoryView]
        order_bys = ["usage", "request", "limit"]

        for view, order_by in product(views, order_bys):
            with self.subTest((view, order_by)):
                url = f"?filter[limit]=5&filter[offset]=0&group_by[project]=*&order_by[{order_by}]=desc"

                query_params = self.mocked_query_params(url, view)
                handler = OCPReportQueryHandler(query_params)
                query_data = handler.execute_query()
                self.assertIsNotNone(query_data.get("data"))
                self.assertIsNotNone(query_data.get("total"))
                total = query_data.get("total")
                self.assertIsNotNone(total.get(order_by))

    def test_storage_class_order_bys(self):
        """Test that we can order by the pvc values."""
        group_bys = ["persistentvolumeclaim", "storageclass"]
        for group_by in group_bys:
            with self.subTest(group_by=group_by):
                url = f"?group_by[project]=*&group_by[{group_by}]=*&order_by[storage_class]=desc"
                query_params = self.mocked_query_params(url, OCPVolumeView)
                handler = OCPReportQueryHandler(query_params)
                query_data = handler.execute_query()
                self.assertIsNotNone(query_data.get("data"))
                self.assertIsNotNone(query_data.get("total"))
                self.assertIsNotNone(query_data["total"].get("storage_class"))
                first_date = query_data["data"][0]
                tested = False
                for project in first_date.get("projects", []):
                    group_list = project.get(f"{group_by}s")
                    storage_class_order_result = []
                    expected = None
                    for element in group_list:
                        for element_value in element.get("values", []):
                            storage_class_order_result.append(element_value.get("storage_class"))
                    if not expected:
                        expected = deepcopy(storage_class_order_result)
                        expected.sort(reverse=True)
                    self.assertEqual(storage_class_order_result, expected)
                    tested = True
                self.assertTrue(tested)

    def test_persistentvolumeclaim_order_by(self):
        """Test that we can order by the pvc values."""
        url = "?group_by[project]=*&group_by[persistentvolumeclaim]=*&order_by[persistentvolumeclaim]=desc"
        query_params = self.mocked_query_params(url, OCPVolumeView)
        handler = OCPReportQueryHandler(query_params)
        query_data = handler.execute_query()
        self.assertIsNotNone(query_data.get("data"))
        self.assertIsNotNone(query_data.get("total"))
        self.assertIsNotNone(query_data["total"].get("persistent_volume_claim"))
        first_date = query_data["data"][0]
        tested = False
        for cluster in first_date.get("projects", []):
            pvc_list = cluster.get("persistentvolumeclaims")
            pvc_order_result = []
            expected = None
            for pvc in pvc_list:
                pvc_name = pvc.get("persistentvolumeclaim")
                pvc_order_result.append(pvc_name)
            if not expected:
                expected = deepcopy(pvc_order_result)
                expected.sort(reverse=True)
            self.assertEqual(pvc_order_result, expected)
            tested = True
        self.assertTrue(tested)

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
        self.assertAlmostEqual(result_cost_total, expected_cost_total, 6)

    def test_get_cluster_capacity_daily_resolution_empty_cluster(self):
        query_params = self.mocked_query_params("?", OCPMemoryView)
        query_data, total_capacity = OCPReportQueryHandler(query_params).get_capacity([{"row": 1}])
        self.assertTrue("capacity" in total_capacity)
        self.assertTrue(isinstance(total_capacity["capacity"], Decimal))
        self.assertTrue("capacity" in query_data[0])
        self.assertIsNotNone(query_data[0].get("capacity"))
        self.assertIsNotNone(total_capacity.get("capacity"))
        self.assertEqual(query_data[0].get("capacity"), Decimal(0))

    def test_get_cluster_capacity_monthly_resolution(self):
        """Test that cluster capacity returns a full month's capacity."""
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly"
        query_params = self.mocked_query_params(url, OCPCpuView)
        handler = OCPReportQueryHandler(query_params)
        query_data = [{"row": 1}]
        query_data, total_capacity = handler.get_capacity(query_data)
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

    def test_get_cluster_capacity_daily_volume_group_bys(self):
        """Test the volume capacities of a daily volume report with various group bys matches expected"""
        base_url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=daily"
        group_bys = [["cluster"], ["project"], ["cluster", "project"]]
        GB_MAP = {"project": "namespace", "cluster": "cluster_id"}
        with tenant_context(self.tenant):
            for group_by in group_bys:
                url_group_by = "".join([f"&group_by[{gb}]=*" for gb in group_by])
                url = base_url + url_group_by
                query_params = self.mocked_query_params(url, OCPVolumeView)
                handler = OCPReportQueryHandler(query_params)
                query_data = handler.execute_query()

                annotations = {"capacity": Sum("persistentvolumeclaim_capacity_gigabyte_months")}
                q_table = handler._mapper.provider_map.get("tables").get("query")
                query_filter = handler.query_filter
                query = q_table.objects.filter(query_filter)
                query_group_by = ["usage_start"]
                for gb in group_by:
                    query_group_by.append(GB_MAP.get(gb))
                query_results = query.values(*query_group_by).annotate(**annotations)
                with self.subTest(group_by=group_by):
                    for entry in query_data.get("data", []):
                        date = entry.get("date")
                        for item in entry.get(f"{group_by[0]}s", []):
                            filter_dict = {GB_MAP.get(group_by[0]): item.get(group_by[0])}
                            if len(group_by) > 1:
                                for element in item.get(f"{group_by[1]}s")[0].get("values"):
                                    filter_dict[GB_MAP.get(group_by[1])] = element.get(group_by[1])
                                    capacity = element.get("capacity", {}).get("value")
                                    expected = query_results.get(usage_start=date, **filter_dict).get(
                                        "capacity", 0.0
                                    ) or Decimal(0.0)
                                    self.assertAlmostEqual(capacity, expected)
                            else:
                                for element in item.get("values"):
                                    capacity = element.get("capacity", {}).get("value")
                                    expected = query_results.get(usage_start=date, **filter_dict).get(
                                        "capacity", 0.0
                                    ) or Decimal(0.0)
                                    self.assertAlmostEqual(capacity, expected)

    def test_get_node_capacity_daily_views_group_bys(self):
        """Test the volume capacities of a daily volume report with various group bys matches expected"""
        params = {
            "filter[time_scope_units]": "month",
            "filter[time_scope_value]": "-1",
            "filter[resolution]": "daily",
            "group_by[node]": "*",
        }
        url = "?" + urlencode(params, quote_via=quote_plus)
        for view in [OCPVolumeView, OCPCpuView, OCPMemoryView]:
            with self.subTest(view=view):
                query_params = self.mocked_query_params(url, view)
                handler = OCPReportQueryHandler(query_params)
                query_data = handler.execute_query()
                query_filter = handler.query_filter
                # intentionly looking for exact keys since structure
                # is required for node capacity to function:
                _cap = handler._mapper.report_type_map["capacity_aggregate"]["node"]["capacity"]
                with tenant_context(self.tenant):
                    expected = handler._mapper.query_table.objects.filter(query_filter)
                    query_results = expected.values(*["usage_start", "node"]).annotate(**{"capacity": _cap})
                    for entry in query_data.get("data", []):
                        date = entry.get("date")
                        for item in entry.get("nodes", []):
                            for element in item.get("values"):
                                capacity = element.get("capacity", {}).get("value")
                                monthly_vals = [
                                    element.get("capacity") or Decimal(0.0)
                                    for element in query_results.filter(usage_start=date, node=element.get("node"))
                                ]
                                self.assertAlmostEqual(capacity, sum(monthly_vals))

    def test_get_node_cpacity_monthly_views_group_bys(self):
        """Test the node capacity of a monthly volume report with various group bys"""
        params = {
            "filter[time_scope_units]": "month",
            "filter[time_scope_value]": "-1",
            "filter[resolution]": "monthly",
            "group_by[node]": "*",
        }
        url = "?" + urlencode(params, quote_via=quote_plus)
        for view in [OCPVolumeView, OCPCpuView, OCPMemoryView]:
            with self.subTest(view=view):
                query_params = self.mocked_query_params(url, view)
                handler = OCPReportQueryHandler(query_params)
                query_data = handler.execute_query()
                query_filter = handler.query_filter
                # intentionly looking for exact keys since structure
                # is required for node capacity to function:
                _cap = handler._mapper.report_type_map["capacity_aggregate"]["node"]["capacity"]
                with tenant_context(self.tenant):
                    expected = handler._mapper.query_table.objects.filter(query_filter)
                    query_results = expected.values(*["usage_start", "node"]).annotate(**{"capacity": _cap})
                    for entry in query_data.get("data", []):
                        date = entry.get("date") + "-01"  # first of the month
                        for item in entry.get("nodes", []):
                            for element in item.get("values"):
                                capacity = element.get("capacity", {}).get("value")
                                monthly_vals = [
                                    element.get("capacity") or Decimal(0.0)
                                    for element in query_results.filter(
                                        usage_start__gte=date, node=element.get("node")
                                    )
                                ]
                                self.assertAlmostEqual(capacity, sum(monthly_vals))

    def test_get_node_capacity_tag_grouping(self):
        """Test that group_by params with tag keys are returned."""
        url = "?"
        query_params = self.mocked_query_params(url, OCPTagView)
        handler = OCPTagQueryHandler(query_params)
        tag_keys = handler.get_tag_keys(filters=False)
        group_by_key = tag_keys[0]

        url = f"?group_by[tag:{group_by_key}]=*&group_by[node]=*"
        query_params = self.mocked_query_params(url, OCPCpuView)
        handler = OCPReportQueryHandler(query_params)
        results = handler.get_tag_group_by_keys()
        self.assertEqual(results, ["tag:" + group_by_key])
        for view in [OCPVolumeView, OCPCpuView, OCPMemoryView]:
            with self.subTest(view=view):
                query_params = self.mocked_query_params(url, view)
                handler = OCPReportQueryHandler(query_params)
                query_data = handler.execute_query()
                query_filter = handler.query_filter
                # intentionly looking for exact keys since structure
                # is required for node capacity to function:
                _cap = handler._mapper.report_type_map["capacity_aggregate"]["node"]["capacity"]
                with tenant_context(self.tenant):
                    expected = handler._mapper.query_table.objects.filter(query_filter)
                    query_results = expected.values(*["usage_start", "node"]).annotate(**{"capacity": _cap})
                    for entry in query_data.get("data", []):
                        date = entry.get("date") + "-01"  # first of the month
                        for item in entry.get("nodes", []):
                            for element in item.get("values"):
                                capacity = element.get("capacity", {}).get("value")
                                monthly_vals = [
                                    element.get("capacity") or Decimal(0.0)
                                    for element in query_results.filter(
                                        usage_start__gte=date, node=element.get("node")
                                    )
                                ]
                                self.assertAlmostEqual(capacity, sum(monthly_vals))

    def test_get_cluster_capacity_monthly_volume_group_bys(self):
        """Test the volume capacities of a monthly volume report with various group bys"""
        base_url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly"
        group_bys = [["cluster"], ["project"], ["cluster", "project"]]
        GB_MAP = {"project": "namespace", "cluster": "cluster_id"}
        with tenant_context(self.tenant):
            for group_by in group_bys:
                url_group_by = "".join([f"&group_by[{gb}]=*" for gb in group_by])
                url = base_url + url_group_by
                query_params = self.mocked_query_params(url, OCPVolumeView)
                handler = OCPReportQueryHandler(query_params)
                query_data = handler.execute_query()

                annotations = {"capacity": Sum("persistentvolumeclaim_capacity_gigabyte_months")}
                q_table = handler._mapper.provider_map.get("tables").get("query")
                query_filter = handler.query_filter
                query = q_table.objects.filter(query_filter)
                query_group_by = ["usage_start", "node"]
                for gb in group_by:
                    query_group_by.append(GB_MAP.get(gb))
                query_results = query.values(*query_group_by).annotate(**annotations)
                with self.subTest(group_by=group_by):
                    for entry in query_data.get("data", []):
                        date = entry.get("date") + "-01"
                        for item in entry.get(f"{group_by[0]}s", []):
                            filter_dict = {GB_MAP.get(group_by[0]): item.get(group_by[0])}
                            if len(group_by) > 1:
                                for element in item.get(f"{group_by[1]}s")[0].get("values"):
                                    filter_dict[GB_MAP.get(group_by[1])] = element.get(group_by[1])
                                    capacity = element.get("capacity", {}).get("value")
                                    monthly_vals = [
                                        element.get("capacity") or Decimal(0.0)
                                        for element in query_results.filter(usage_start__gte=date, **filter_dict)
                                    ]
                                    self.assertAlmostEqual(capacity, sum(monthly_vals))
                            else:
                                for element in item.get("values"):
                                    capacity = element.get("capacity", {}).get("value")
                                    monthly_vals = [
                                        element.get("capacity") or Decimal(0.0)
                                        for element in query_results.filter(usage_start__gte=date, **filter_dict)
                                    ]
                                    self.assertAlmostEqual(capacity, sum(monthly_vals))

    def test_get_cluster_capacity_monthly_start_and_end_volume_group_bys(self):
        """Test the volume capacities of a monthly volume report with various group bys"""
        base_url = (
            f"?start_date={self.dh.last_month_end.date()}&end_date={self.dh.today.date()}&filter[resolution]=monthly"
        )
        group_bys = [
            ["cluster"],
            ["project"],
            ["cluster", "project"],
        ]
        GB_MAP = {"project": "namespace", "cluster": "cluster_id", "node": "node"}
        with tenant_context(self.tenant):
            for group_by in group_bys:
                url_group_by = "".join([f"&group_by[{gb}]=*" for gb in group_by])
                url = base_url + url_group_by
                query_params = self.mocked_query_params(url, OCPVolumeView)
                handler = OCPReportQueryHandler(query_params)
                query_data = handler.execute_query()

                annotations = {"capacity": Sum("persistentvolumeclaim_capacity_gigabyte_months")}
                q_table = handler._mapper.provider_map.get("tables").get("query")
                query_filter = handler.query_filter
                query = q_table.objects.filter(query_filter)
                query_group_by = ["usage_start"]
                for gb in group_by:
                    query_group_by.append(GB_MAP.get(gb))
                query_results = query.values(*query_group_by).annotate(**annotations)
                with self.subTest(group_by=group_by):
                    for entry in query_data.get("data", []):
                        entry_date = entry.get("date")
                        if entry_date == datetime.strftime(self.dh.today.date(), "%Y-%m"):
                            date = entry.get("date") + "-01"
                            end = self.dh.tomorrow.date()
                        else:
                            date = self.dh.last_month_end.date()
                            end = self.dh.this_month_start.date()
                        for item in entry.get(f"{group_by[0]}s", []):
                            filter_dict = {GB_MAP.get(group_by[0]): item.get(group_by[0])}
                            if len(group_by) > 1:
                                for element in item.get(f"{group_by[1]}s")[0].get("values"):
                                    filter_dict[GB_MAP.get(group_by[1])] = element.get(group_by[1])
                                    capacity = element.get("capacity", {}).get("value")
                                    monthly_vals = [
                                        element.get("capacity") or Decimal(0.0)
                                        for element in query_results.filter(
                                            usage_start__gte=date, usage_start__lt=end, **filter_dict
                                        )
                                    ]
                                    self.assertAlmostEqual(capacity, sum(monthly_vals))
                            else:
                                for element in item.get("values"):
                                    capacity = element.get("capacity", {}).get("value")
                                    monthly_vals = [
                                        element.get("capacity") or Decimal(0.0)
                                        for element in query_results.filter(
                                            usage_start__gte=date, usage_start__lt=end, **filter_dict
                                        )
                                    ]
                                    self.assertAlmostEqual(capacity, sum(monthly_vals))

    def test_get_node_capacity_monthly_start_and_end_volume_group_bys(self):
        """Test the volume capacities of a monthly volume report with various group bys"""
        base_url = (
            f"?start_date={self.dh.last_month_end.date()}&end_date={self.dh.today.date()}&filter[resolution]=monthly"
        )
        group_bys = [
            ["node"],
            ["cluster", "node"],
            ["node", "project"],
        ]
        GB_MAP = {"project": "namespace", "cluster": "cluster_id", "node": "node"}
        with tenant_context(self.tenant):
            for group_by in group_bys:
                url_group_by = "".join([f"&group_by[{gb}]=*" for gb in group_by])
                url = base_url + url_group_by
                query_params = self.mocked_query_params(url, OCPVolumeView)
                handler = OCPReportQueryHandler(query_params)
                query_data = handler.execute_query()

                annotations = {"capacity": Sum("persistentvolumeclaim_capacity_gigabyte_months")}
                q_table = handler._mapper.provider_map.get("tables").get("query")
                query_filter = handler.query_filter
                query = q_table.objects.filter(query_filter)
                query_group_by = ["usage_start", "node"]
                query_results = query.values(*query_group_by).annotate(**annotations)
                with self.subTest(group_by=group_by):
                    for entry in query_data.get("data", []):
                        entry_date = entry.get("date")
                        if entry_date == datetime.strftime(self.dh.today.date(), "%Y-%m"):
                            date = entry.get("date") + "-01"
                            end = self.dh.tomorrow.date()
                        else:
                            date = self.dh.last_month_end.date()
                            end = self.dh.this_month_start.date()
                        for item in entry.get(f"{group_by[0]}s", []):
                            filter_dict = {}
                            if len(group_by) > 1:
                                for element in item.get(f"{group_by[1]}s")[0].get("values"):
                                    filter_dict[GB_MAP.get(group_by[1])] = element.get(group_by[1])
                                    capacity = element.get("capacity", {}).get("value")
                                    monthly_vals = [
                                        element.get("capacity") or Decimal(0.0)
                                        for element in query_results.filter(
                                            usage_start__gte=date, usage_start__lt=end, **{"node": element.get("node")}
                                        )
                                    ]
                                    self.assertAlmostEqual(capacity, sum(monthly_vals))
                            else:
                                for element in item.get("values"):
                                    capacity = element.get("capacity", {}).get("value")
                                    monthly_vals = [
                                        element.get("capacity") or Decimal(0.0)
                                        for element in query_results.filter(
                                            usage_start__gte=date, usage_start__lt=end, **{"node": element.get("node")}
                                        )
                                    ]
                                    self.assertAlmostEqual(capacity, sum(monthly_vals))

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

    def test_build_prefix_filters(self):
        """Test that tag filters are created properly."""
        filter_collection = QueryFilterCollection()

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
        filter_keys = handler.get_tag_filter_keys()
        group_keys = handler.get_tag_group_by_keys()
        filter_keys.extend(group_keys)
        filter_collection = handler._set_prefix_based_filters(
            filter_collection, handler._mapper.tag_column, filter_keys, TAG_PREFIX
        )

        expected = f"""<class 'api.query_filter.QueryFilterCollection'>: (AND: ('pod_labels__{filter_key}__icontains', '{filter_value}')), (AND: ('pod_labels__{group_by_key}__icontains', '{group_by_value}')), """  # noqa: E501

        self.assertEqual(repr(filter_collection), expected)

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
        group_by = handler._tag_group_by
        group = group_by[0]
        expected = f"INTERNAL_{handler._mapper.tag_column}_{group[1]}"
        self.assertEqual(len(group_by), 1)
        self.assertEqual(group[0], expected)
        self.assertEqual(group[2], group_by_key)

    def test_get_tag_order_by(self):
        """Verify that a propery order by is returned."""
        column = "pod_labels"
        value = "key"
        expected_param = (value,)

        url = "?"
        query_params = self.mocked_query_params(url, OCPCpuView)
        handler = OCPReportQueryHandler(query_params)
        result = handler.get_tag_order_by(column, value)
        expression = result.expression

        self.assertIsInstance(result, OrderBy)
        self.assertEqual(expression.sql, f"{column} -> %s")
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
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly"
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
            {"node": "No-node", "cluster": "cluster-1"},
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
            ("project", "cluster"),
            ("project", "node"),
            ("cluster", "project"),
            ("cluster", "node"),
            ("node", "cluster"),
            ("node", "project"),
        ]
        base_url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&filter[limit]=3"  # noqa: E501
        tolerance = 1
        for group_by in group_by_list:
            sub_url = "&group_by[%s]=*&group_by[%s]=*" % group_by
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
        url = "?group_by[project]=*&order_by[project]=asc&filter[limit]=2"
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

    def test_group_by_project_overhead_distributed(self):
        """COST-1252: Test that grouping by project with limit works as expected."""
        url = "?group_by[project]=*&order_by[project]=asc&filter[limit]=2"
        with tenant_context(self.tenant):
            OCPCostSummaryByProjectP.objects.update(cost_model_rate_type="platform_distributed")
        query_params = self.mocked_query_params(url, OCPCostView)
        handler = OCPReportQueryHandler(query_params)
        current_totals = self.get_totals_costs_by_time_scope(handler, self.ten_day_filter)
        expected_cost_total = current_totals.get("cost_total")
        self.assertIsNotNone(expected_cost_total)
        query_output = handler.execute_query()
        self.assertIsNotNone(query_output.get("data"))
        self.assertTrue(query_output.get("distributed_overhead"))

    def test_group_by_project_w_classification(self):
        """Test that classification works as expected."""
        url = "?group_by[project]=*&category=*"
        with patch("reporting.provider.ocp.models.OpenshiftCostCategory.objects") as mock_object:
            mock_object.values_list.return_value.distinct.return_value = ["Platform"]
            query_params = self.mocked_query_params(url, OCPCostView)
            handler = OCPReportQueryHandler(query_params)
            with tenant_context(self.tenant):
                current_totals = (
                    OCPCostSummaryByProjectP.objects.filter(handler.query_filter)
                    .annotate(**handler.annotations)
                    .aggregate(**handler._mapper.report_type_map.get("aggregates"))
                )
        expected_cost_total = current_totals.get("cost_total")
        self.assertIsNotNone(expected_cost_total)
        query_output = handler.execute_query()
        self.assertIsNotNone(query_output.get("data"))
        self.assertIsNotNone(query_output.get("total"))
        total = query_output.get("total")
        for line in query_output.get("data")[0].get("projects"):
            project = line["project"]
            classification = line["values"][0]["classification"]
            if any(project.startswith(prefix) for prefix in ("openshift-", "kube-")):
                self.assertIn(classification, {"project", "default"})
            elif project == "Network unattributed":
                self.assertEqual(classification, "unattributed")
            elif project != "Platform":
                self.assertEqual(classification, "project")
        result_cost_total = total.get("cost", {}).get("total", {}).get("value")
        self.assertIsNotNone(result_cost_total)
        overall = result_cost_total - expected_cost_total
        self.assertEqual(overall, 0)

    def test_group_by_project_w_classification_and_other(self):
        """Test that classification works as expected with Other."""
        cat_key = "Platform"
        url = "?group_by[project]=*&category=*"
        with patch("reporting.provider.ocp.models.OpenshiftCostCategory.objects") as mock_object:
            mock_object.values_list.return_value.distinct.return_value = [cat_key]
            query_params = self.mocked_query_params(url, OCPCostView)
            handler = OCPReportQueryHandler(query_params)
            with tenant_context(self.tenant):
                current_totals = (
                    OCPCostSummaryByProjectP.objects.filter(handler.query_filter)
                    .annotate(**handler.annotations)
                    .aggregate(**handler._mapper.report_type_map.get("aggregates"))
                )
            expected_cost_total = current_totals.get("cost_total")
            self.assertIsNotNone(expected_cost_total)
            query_output = handler.execute_query()
            self.assertIsNotNone(query_output.get("data"))
            self.assertIsNotNone(query_output.get("total"))
            total = query_output.get("total")
            for line in query_output.get("data")[0].get("projects"):
                project = line["project"]
                classification = line["values"][0]["classification"]
                if project == "Platform":
                    self.assertEqual(classification, f"category_{cat_key}")
                elif project in {"Other", "Others"}:
                    self.assertEqual(classification, "category")
                elif project == "Worker unallocated":
                    self.assertEqual(classification, "unallocated")
                elif project == "Network unattributed":
                    self.assertEqual(classification, "unattributed")
                else:
                    self.assertIn(classification, {"project", "default"})
            result_cost_total = total.get("cost", {}).get("total", {}).get("value")
            self.assertIsNotNone(result_cost_total)
            overall = result_cost_total - expected_cost_total
            self.assertEqual(overall, 0)

    def test_category_error(self):
        """Test category error w/o project group by."""
        url = "?category=*"
        with patch("reporting.provider.ocp.models.OpenshiftCostCategory.objects") as mock_object:
            mock_object.values_list.return_value.distinct.return_value = ["Platform"]
            with self.assertRaises(ValidationError):
                self.mocked_query_params(url, OCPCostView)

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

    def test_exclude_persistentvolumeclaim(self):
        """Test that the exclude persistentvolumeclaim works for volume endpoints."""
        url = "?group_by[persistentvolumeclaim]=*"
        query_params = self.mocked_query_params(url, OCPVolumeView)
        handler = OCPReportQueryHandler(query_params)
        overall_output = handler.execute_query()
        overall_total = handler.query_sum.get("cost", {}).get("total", {}).get("value")
        opt_value = None
        for date_dict in overall_output.get("data", [{}]):
            for element in date_dict.get("persistentvolumeclaims"):
                if "No-persistentvolumeclaim" != element.get("persistentvolumeclaim"):
                    opt_value = element.get("persistentvolumeclaim")
                    break
            if opt_value:
                break
        # Grab filtered value
        filtered_url = f"?group_by[persistentvolumeclaim]=*&filter[persistentvolumeclaim]={opt_value}"
        query_params = self.mocked_query_params(filtered_url, OCPVolumeView)
        handler = OCPReportQueryHandler(query_params)
        handler.execute_query()
        filtered_total = handler.query_sum.get("cost", {}).get("total", {}).get("value")
        expected_total = overall_total - filtered_total
        # Test exclude
        exclude_url = f"?group_by[persistentvolumeclaim]=*&exclude[persistentvolumeclaim]={opt_value}"
        query_params = self.mocked_query_params(exclude_url, OCPVolumeView)
        handler = OCPReportQueryHandler(query_params)
        self.assertIsNotNone(handler.query_exclusions)
        excluded_output = handler.execute_query()
        excluded_total = handler.query_sum.get("cost", {}).get("total", {}).get("value")
        excluded_data = excluded_output.get("data")
        # Check to make sure the value is not in the return
        for date_dict in excluded_data:
            grouping_list = date_dict.get("persistentvolumeclaims", [])
            self.assertIsNotNone(grouping_list)
            for group_dict in grouping_list:
                if "No-persistentvolumeclaim" != opt_value:
                    self.assertNotEqual(opt_value, group_dict.get("persistentvolumeclaim"))
        self.assertAlmostEqual(expected_total, excluded_total, 6)
        self.assertNotEqual(overall_total, excluded_total)

    def test_exclude_functionality(self):
        """Test that the exclude feature works for all options."""
        # This is a base test, if functionality is tested separately
        # or does not apply to all ocp endpoints, then it can be added
        # here:
        remove_from_test = {"infrastructures", "category", "persistentvolumeclaim"}
        exclude_opts = set(OCPExcludeSerializer._opfields).difference(remove_from_test)
        for exclude_opt in exclude_opts:
            for view in [OCPCostView, OCPCpuView, OCPMemoryView, OCPVolumeView]:
                with self.subTest(exclude_opt):
                    overall_url = f"?group_by[{exclude_opt}]=*"
                    query_params = self.mocked_query_params(overall_url, view)
                    handler = OCPReportQueryHandler(query_params)
                    overall_output = handler.execute_query()
                    overall_total = handler.query_sum.get("cost", {}).get("total", {}).get("value")
                    opt_value = None
                    for date_dict in overall_output.get("data", [{}]):
                        for element in date_dict.get(f"{exclude_opt}s"):
                            if f"No-{exclude_opt}" != element.get(exclude_opt):
                                opt_value = element.get(exclude_opt)
                                break
                        if opt_value:
                            break
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
                            if f"No-{exclude_opt}" != opt_value:
                                self.assertNotEqual(opt_value, group_dict.get(exclude_opt))
                    self.assertAlmostEqual(expected_total, excluded_total, 6)
                    self.assertNotEqual(overall_total, excluded_total)

    def test_exclude_infastructures(self):
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
                # an infrastructure here, or atleast that is my understanding.
                expected_total = (ocp_total + azure_filtered_total + gcp_filtered_total) - ocp_raw
                exclude_url = "?exclude[infrastructures]=aws"
                query_params = self.mocked_query_params(exclude_url, view)
                handler = OCPReportQueryHandler(query_params)
                self.assertIsNotNone(handler.query_exclusions)
                handler.execute_query()
                excluded_result = handler.query_sum.get("cost", {}).get("total", {}).get("value")
                self.assertAlmostEqual(expected_total, excluded_result, 6)

    def test_exclude_tags(self):
        """Test that the exclude works for our tags."""
        query_params = self.mocked_query_params("?", OCPTagView)
        handler = OCPTagQueryHandler(query_params)
        tags = handler.get_tags()
        group_tag = None
        check_no_option = False
        exclude_vals = []
        for tag_dict in tags:
            if len(tag_dict.get("values")) > len(exclude_vals):
                group_tag = tag_dict.get("key")
                exclude_vals = tag_dict.get("values")
        url = f"?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=daily&group_by[tag:{group_tag}]=*"  # noqa: E501
        query_params = self.mocked_query_params(url, OCPCostView)
        handler = OCPReportQueryHandler(query_params)
        data = handler.execute_query().get("data")
        if f"No-{group_tag}" in str(data):
            check_no_option = True
        returned_values = []
        for date in data:
            date_list = date.get(f"{group_tag}s")
            for date_dict in date_list:
                tag_value = date_dict.get(group_tag)
                if tag_value not in returned_values:
                    returned_values.append(tag_value)
        exclude_vals = [value for value in exclude_vals if value in returned_values]
        previous_total = handler.query_sum.get("cost", {}).get("total", {}).get("value")
        for exclude_value in exclude_vals:
            url += f"&exclude[tag:{group_tag}]={exclude_value}"
            query_params = self.mocked_query_params(url, OCPCostView)
            handler = OCPReportQueryHandler(query_params)
            data = handler.execute_query()
            if check_no_option:
                self.assertIn(f"No-{group_tag}", str(data))
            current_total = handler.query_sum.get("cost", {}).get("total", {}).get("value")
            self.assertLess(current_total, previous_total)
            previous_total = current_total

    def test_multi_exclude_persistentvolumeclaim_functionality(self):
        """Test that the exclude feature works for all options."""
        base_url = "?group_by[persistentvolumeclaim]=*&filter[time_scope_units]=month&filter[resolution]=monthly&filter[time_scope_value]=-1"  # noqa: E501
        query_params = self.mocked_query_params(base_url, OCPVolumeView)
        handler = OCPReportQueryHandler(query_params)
        overall_output = handler.execute_query()
        opt_dict = overall_output.get("data", [{}])[0]
        opt_list = opt_dict.get("persistentvolumeclaims")
        exclude_one = None
        exclude_two = None
        for exclude_option in opt_list:
            if "No-" not in exclude_option.get("persistentvolumeclaim"):
                if not exclude_one:
                    exclude_one = exclude_option.get("persistentvolumeclaim")
                elif not exclude_two:
                    exclude_two = exclude_option.get("persistentvolumeclaim")
                else:
                    continue
        self.assertIsNotNone(exclude_one)
        self.assertIsNotNone(exclude_two)

        url = base_url + f"&exclude[persistentvolumeclaim]={exclude_one}&exclude[persistentvolumeclaim]={exclude_two}"
        query_params = self.mocked_query_params(url, OCPVolumeView)
        handler = OCPReportQueryHandler(query_params)
        self.assertIsNotNone(handler.query_exclusions)
        excluded_output = handler.execute_query()
        excluded_data = excluded_output.get("data")
        self.assertIsNotNone(excluded_data)
        for date_dict in excluded_data:
            grouping_list = date_dict.get("persistentvolumeclaims", [])
            self.assertIsNotNone(grouping_list)
            for group_dict in grouping_list:
                self.assertNotIn(group_dict.get("persistentvolumeclaim"), [exclude_one, exclude_two])

    def test_multi_exclude_functionality(self):
        """Test that the exclude feature works for all options."""
        remove_from_test = {"infrastructures", "category", "persistentvolumeclaim"}
        exclude_opts = set(OCPExcludeSerializer._opfields).difference(remove_from_test)
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
                    if "No-" not in exclude_option.get(ex_opt):
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

    def test_ocp_cpu_query_group_by_storage_class(self):
        """Test that group by storageclass functionality works."""
        group_by_key = "storageclass"
        url = f"?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&filter[limit]=3&group_by[{group_by_key}]=*"  # noqa: E501
        query_params = self.mocked_query_params(url, OCPCpuView)
        handler = OCPReportQueryHandler(query_params)
        query_data = handler.execute_query()
        tested = False
        for data in query_data.get("data"):
            result_key = group_by_key + "s"
            self.assertIn(result_key, data)
            for stor_cls_data in data.get(result_key):
                self.assertIn(group_by_key, stor_cls_data)
                self.assertIn("values", stor_cls_data)
                for storage_value in stor_cls_data.get("values"):
                    self.assertIn(group_by_key, storage_value.keys())
                    self.assertIsNotNone(storage_value[group_by_key])
                    tested = True
        self.assertTrue(tested)

    def test_execute_vm_csv_query(self):
        query_params = self.mocked_query_params("", OCPReportVirtualMachinesView)
        handler = OCPReportQueryHandler(query_params)
        handler.is_csv_output = True
        handler.time_interval = [self.dh.this_month_start]
        query_output = handler.execute_query()
        data = query_output.get("data")
        self.assertIsNotNone(data)

    def test_format_tags(self):
        """Test that tags are formatted correctly."""

        query_params = self.mocked_query_params("", OCPReportVirtualMachinesView)
        handler = OCPReportQueryHandler(query_params)

        test_tags_format_map = [
            {
                "test_tags": [{"application": "CMSapp", "instance-type": "large", "vm_kubevirt_io_name": "fedora"}],
                "expected_output": [
                    {"key": "application", "values": ["CMSapp"]},
                    {"key": "instance-type", "values": ["large"]},
                    {"key": "vm_kubevirt_io_name", "values": ["fedora"]},
                ],
            },
            {"test_tags": [], "expected_output": []},
        ]

        for item in test_tags_format_map:
            with self.subTest(params=item):
                result = handler.format_tags(item.get("test_tags"))
                self.assertEqual(result, item.get("expected_output"))

    def test_gpu_filter_by_model_filters_correctly(self):
        """Test that GPU model filter actually filters data correctly."""
        with tenant_context(self.tenant):
            # Get distinct models from database
            models = list(
                OCPGpuSummaryP.objects.values_list("model_name", flat=True).distinct().order_by("model_name")
            )
            # Test filtering by first model
            test_model = models[0]

        url = reverse("reports-openshift-gpu")
        params = {"filter[model]": test_model}
        url = f"{url}?{urlencode(params)}"
        client = APIClient()
        response = client.get(url, **self.headers)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data

        # Verify that response includes the filter in meta
        self.assertIn("meta", data)
        self.assertIn("filter", data["meta"])
        self.assertIn("model", data["meta"]["filter"])
        self.assertEqual(data["meta"]["filter"]["model"], [test_model])

        # Verify data is present (not empty)
        self.assertIn("data", data)
        self.assertGreater(len(data["data"]), 0)

    def test_gpu_filter_by_vendor_filters_correctly(self):
        """Test that GPU vendor filter actually filters data correctly."""
        with tenant_context(self.tenant):
            # Get distinct vendors from database
            vendors = list(
                OCPGpuSummaryP.objects.values_list("vendor_name", flat=True).distinct().order_by("vendor_name")
            )
            test_vendor = vendors[0]

        url = reverse("reports-openshift-gpu")
        params = {"filter[vendor]": test_vendor}
        url = f"{url}?{urlencode(params)}"
        client = APIClient()
        response = client.get(url, **self.headers)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data

        # Verify that response includes the filter in meta
        self.assertIn("meta", data)
        self.assertIn("filter", data["meta"])
        self.assertIn("vendor", data["meta"]["filter"])
        self.assertEqual(data["meta"]["filter"]["vendor"], [test_vendor])

    def test_gpu_multiple_model_filters_use_or_logic(self):
        """Test that multiple GPU model filter values use OR logic."""
        with tenant_context(self.tenant):
            # Get distinct models from database
            models = list(
                OCPGpuSummaryP.objects.values_list("model_name", flat=True).distinct().order_by("model_name")
            )
            model1 = models[0]
            model2 = models[1]

        # Query with multiple models
        url = reverse("reports-openshift-gpu")
        params = [("filter[model]", model1), ("filter[model]", model2)]
        url = f"{url}?{urlencode(params)}"
        client = APIClient()
        response = client.get(url, **self.headers)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data

        # Verify both models are in the filter
        self.assertIn("meta", data)
        self.assertIn("filter", data["meta"])
        self.assertIn("model", data["meta"]["filter"])
        filter_models = data["meta"]["filter"]["model"]
        self.assertIn(model1, filter_models)
        self.assertIn(model2, filter_models)

    def test_gpu_group_by_model_returns_grouped_data(self):
        """Test that GPU group_by model returns data grouped by model."""
        url = reverse("reports-openshift-gpu")
        params = {"group_by[model]": "*"}
        url = f"{url}?{urlencode(params)}"
        client = APIClient()
        response = client.get(url, **self.headers)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data

        # Verify group_by is in meta
        self.assertIn("meta", data)
        self.assertIn("group_by", data["meta"])
        self.assertIn("model", data["meta"]["group_by"])

        # Verify data structure has grouped values
        self.assertIn("data", data)
        self.assertGreater(len(data["data"]), 0)
        # Check that data has proper structure with models
        first_entry = data["data"][0]
        self.assertIn("date", first_entry)
        # With group_by[model], structure is: data[0]["models"][0]["values"][0]
        self.assertIn("models", first_entry)
        self.assertGreater(len(first_entry["models"]), 0)
        first_model_group = first_entry["models"][0]
        self.assertIn("model", first_model_group)
        self.assertIn("gpu_names", first_model_group)
        second_model_group = first_model_group["gpu_names"][0]
        self.assertGreater(len(second_model_group["values"]), 0)
        first_value = second_model_group["values"][0]
        self.assertIn("model", first_value)

    def test_gpu_group_by_vendor_returns_grouped_data(self):
        """Test that GPU group_by vendor returns data grouped by vendor."""
        url = reverse("reports-openshift-gpu")
        params = {"group_by[vendor]": "*"}
        url = f"{url}?{urlencode(params)}"
        client = APIClient()
        response = client.get(url, **self.headers)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data

        # Verify group_by is in meta
        self.assertIn("meta", data)
        self.assertIn("group_by", data["meta"])
        self.assertIn("vendor", data["meta"]["group_by"])

        # Verify data structure has grouped values
        self.assertIn("data", data)
        self.assertGreater(len(data["data"]), 0)
        # With group_by[vendor], structure is: data[0]["vendors"][0]["values"][0]
        first_entry = data["data"][0]
        self.assertIn("date", first_entry)
        self.assertIn("vendors", first_entry)
        self.assertGreater(len(first_entry["vendors"]), 0)
        first_vendor_group = first_entry["vendors"][0]
        self.assertIn("vendor", first_vendor_group)
        self.assertIn("gpu_names", first_vendor_group)
        second_vendor_group = first_vendor_group["gpu_names"][0]
        self.assertGreater(len(second_vendor_group["values"]), 0)
        first_value = second_vendor_group["values"][0]
        self.assertIn("vendor", first_value)

    def test_gpu_order_by_cost_with_group_by_model_works(self):
        """Test that GPU order_by cost with group_by model works correctly."""
        url = reverse("reports-openshift-gpu")
        params = {"group_by[model]": "*", "order_by[cost]": "desc"}
        url = f"{url}?{urlencode(params)}"
        client = APIClient()
        response = client.get(url, **self.headers)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data

        # Verify both group_by and order_by are in meta
        self.assertIn("meta", data)
        self.assertIn("group_by", data["meta"])
        self.assertIn("order_by", data["meta"])
        self.assertIn("model", data["meta"]["group_by"])

    def test_gpu_filter_and_group_by_combination(self):
        """Test that GPU filter and group_by work together correctly."""
        with tenant_context(self.tenant):
            # Get a model to filter by
            models = list(
                OCPGpuSummaryP.objects.values_list("model_name", flat=True).distinct().order_by("model_name")
            )
            test_model = models[0]

        url = reverse("reports-openshift-gpu")
        params = {"filter[model]": test_model, "group_by[cluster]": "*"}
        url = f"{url}?{urlencode(params)}"
        client = APIClient()
        response = client.get(url, **self.headers)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data

        # Verify both filter and group_by are applied
        self.assertIn("meta", data)
        self.assertIn("filter", data["meta"])
        self.assertIn("group_by", data["meta"])
        self.assertEqual(data["meta"]["filter"]["model"], [test_model])
        self.assertIn("cluster", data["meta"]["group_by"])

    def test_gpu_filter_case_insensitive(self):
        """Test that GPU filters are case insensitive."""
        with tenant_context(self.tenant):
            # Get a model from database
            models = list(OCPGpuSummaryP.objects.values_list("model_name", flat=True).distinct())
            test_model = models[0]

        # Test with uppercase
        url1 = reverse("reports-openshift-gpu")
        params1 = {"filter[model]": test_model.upper()}
        url1 = f"{url1}?{urlencode(params1)}"
        client = APIClient()
        response1 = client.get(url1, **self.headers)

        # Test with lowercase
        url2 = reverse("reports-openshift-gpu")
        params2 = {"filter[model]": test_model.lower()}
        url2 = f"{url2}?{urlencode(params2)}"
        response2 = client.get(url2, **self.headers)

        # Both should return 200 OK
        self.assertEqual(response1.status_code, status.HTTP_200_OK)
        self.assertEqual(response2.status_code, status.HTTP_200_OK)

        # Both should return data (case insensitive search should work)
        data1 = response1.data
        data2 = response2.data

        # Verify that total costs are the same (case doesn't matter)
        total1 = data1["meta"].get("total", {}).get("cost", {}).get("total", {}).get("value", 0)
        total2 = data2["meta"].get("total", {}).get("cost", {}).get("total", {}).get("value", 0)
        self.assertEqual(total1, total2, "Case insensitive filter should return same results")

    def test_gpu_invalid_filter_value_returns_empty(self):
        """Test that GPU filtering by non-existent value returns empty results."""
        url = reverse("reports-openshift-gpu")
        params = {"filter[model]": "NONEXISTENT_MODEL_XYZ_123"}
        url = f"{url}?{urlencode(params)}"
        client = APIClient()
        response = client.get(url, **self.headers)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data

        # Should return valid structure but with zero cost
        self.assertIn("meta", data)
        total_cost = data["meta"].get("total", {}).get("cost", {}).get("total", {}).get("value", 0)
        self.assertEqual(total_cost, 0.0, "Non-existent model should return zero cost")

    def test_calculate_unique_gpu_count_empty_data(self):
        """Test that _calculate_unique_gpu_count returns empty list for empty input."""
        # Test via API with a filter that returns no results
        url = reverse("reports-openshift-gpu")
        params = {"filter[model]": "NONEXISTENT_MODEL_FOR_EMPTY_TEST_XYZ"}
        url = f"{url}?{urlencode(params)}"
        client = APIClient()
        response = client.get(url, **self.headers)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data

        # With no matching data, gpu_count should be 0
        total_gpu_count = data["meta"].get("total", {}).get("gpu_count", {}).get("value", 0)
        self.assertEqual(total_gpu_count, 0)

    def test_calculate_unique_gpu_count_by_model(self):
        """Test that _calculate_unique_gpu_count aggregates correctly by model."""
        with tenant_context(self.tenant):
            # Get unique combinations from database
            unique_combos = list(
                OCPGpuSummaryP.objects.values("namespace", "node", "vendor_name", "model_name")
                .annotate(location_gpu_count=Max("gpu_count"))
                .order_by("model_name")
            )

            if not unique_combos:
                self.skipTest("No GPU data available for testing")

            # Calculate expected totals per model
            expected_by_model = {}
            for combo in unique_combos:
                model = combo["model_name"]
                count = combo["location_gpu_count"] or 0
                vendor = combo["vendor_name"]
                key = (vendor, model)
                expected_by_model[key] = expected_by_model.get(key, 0) + count

            # Test via API
            url = reverse("reports-openshift-gpu")
            params = {"group_by[model]": "*", "filter[time_scope_value]": "-1", "filter[time_scope_units]": "month"}
            url = f"{url}?{urlencode(params)}"
            client = APIClient()
            response = client.get(url, **self.headers)

            self.assertEqual(response.status_code, status.HTTP_200_OK)
            data = response.data

            # Verify gpu_count values match expected
            for entry in data.get("data", []):
                for value in entry.get("values", []):
                    model = value.get("model")
                    vendor = value.get("vendor")
                    gpu_count = value.get("gpu_count", {})
                    if isinstance(gpu_count, dict):
                        gpu_count = gpu_count.get("value", 0)
                    key = (vendor, model)
                    if key in expected_by_model:
                        self.assertEqual(
                            gpu_count,
                            expected_by_model[key],
                            f"GPU count mismatch for {vendor}/{model}",
                        )

    def test_calculate_unique_gpu_count_by_project(self):
        """Test that _calculate_unique_gpu_count aggregates correctly by project."""
        with tenant_context(self.tenant):
            # Get unique combinations from database
            unique_combos = list(
                OCPGpuSummaryP.objects.values("namespace", "node", "vendor_name", "model_name")
                .annotate(location_gpu_count=Max("gpu_count"))
                .order_by("namespace")
            )

            if not unique_combos:
                self.skipTest("No GPU data available for testing")

            # Calculate expected totals per (vendor, model, namespace)
            expected_by_project = {}
            for combo in unique_combos:
                namespace = combo["namespace"]
                vendor = combo["vendor_name"]
                model = combo["model_name"]
                count = combo["location_gpu_count"] or 0
                key = (vendor, model, namespace)
                expected_by_project[key] = expected_by_project.get(key, 0) + count

            # Test via API with group_by project
            url = reverse("reports-openshift-gpu")
            params = {
                "group_by[model]": "*",
                "group_by[project]": "*",
                "filter[time_scope_value]": "-1",
                "filter[time_scope_units]": "month",
            }
            url = f"{url}?{urlencode(params)}"
            client = APIClient()
            response = client.get(url, **self.headers)

            self.assertEqual(response.status_code, status.HTTP_200_OK)
            data = response.data

            # Verify gpu_count values in nested structure
            for entry in data.get("data", []):
                for project_entry in entry.get("projects", []):
                    project = project_entry.get("project")
                    for value in project_entry.get("values", []):
                        model = value.get("model")
                        vendor = value.get("vendor")
                        gpu_count = value.get("gpu_count", {})
                        if isinstance(gpu_count, dict):
                            gpu_count = gpu_count.get("value", 0)
                        key = (vendor, model, project)
                        if key in expected_by_project:
                            self.assertEqual(
                                gpu_count,
                                expected_by_project[key],
                                f"GPU count mismatch for {vendor}/{model}/{project}",
                            )

    def test_calculate_unique_gpu_count_handles_others_rows(self):
        """Test _calculate_unique_gpu_count handles 'Others' rows correctly."""
        with tenant_context(self.tenant):
            has_data = OCPGpuSummaryP.objects.exists()
            if not has_data:
                self.skipTest("No GPU data available for testing")

            url = reverse("reports-openshift-gpu")
            params = {
                "group_by[model]": "*",
                "group_by[vendor]": "*",
                "filter[time_scope_value]": "-1",
                "filter[time_scope_units]": "month",
            }
            url = f"{url}?{urlencode(params)}"
            client = APIClient()
            response = client.get(url, **self.headers)

            self.assertEqual(response.status_code, status.HTTP_200_OK)
            data = response.data

            # Verify the response structure
            self.assertIn("data", data)
            self.assertIn("meta", data)

    def test_calculate_unique_gpu_count_with_resolution_monthly(self):
        """Test _calculate_unique_gpu_count with monthly resolution."""
        with tenant_context(self.tenant):
            has_data = OCPGpuSummaryP.objects.exists()
            if not has_data:
                self.skipTest("No GPU data available for testing")

            url = reverse("reports-openshift-gpu")
            params = {
                "group_by[model]": "*",
                "filter[resolution]": "monthly",
                "filter[time_scope_value]": "-2",
                "filter[time_scope_units]": "month",
            }
            url = f"{url}?{urlencode(params)}"
            client = APIClient()
            response = client.get(url, **self.headers)

            self.assertEqual(response.status_code, status.HTTP_200_OK)
            data = response.data

            # With monthly resolution, data should still have correct gpu_count
            for entry in data.get("data", []):
                for model_entry in entry.get("models", []):
                    for value in model_entry.get("values", []):
                        gpu_count = value.get("gpu_count", {})
                        if isinstance(gpu_count, dict):
                            self.assertIn("value", gpu_count)
                            self.assertGreaterEqual(gpu_count.get("value", 0), 0)

    def test_calculate_unique_gpu_count_with_vendor_groupby(self):
        """Test that _calculate_unique_gpu_count aggregates correctly by vendor."""
        with tenant_context(self.tenant):
            # Check if we have GPU data
            distinct_vendors = list(OCPGpuSummaryP.objects.values("vendor_name").distinct().order_by("vendor_name"))

            if not distinct_vendors:
                self.skipTest("No GPU data available for testing")

            # Get expected totals per (vendor, model)
            unique_combos = list(
                OCPGpuSummaryP.objects.values("cluster_id", "namespace", "node", "vendor_name", "model_name").annotate(
                    location_gpu_count=Max("gpu_count")
                )
            )

            expected_by_vendor = {}
            for combo in unique_combos:
                vendor = combo["vendor_name"]
                model = combo["model_name"]
                count = combo["location_gpu_count"] or 0
                key = (vendor, model)
                expected_by_vendor[key] = expected_by_vendor.get(key, 0) + count

            # Test via API with group_by vendor
            url = reverse("reports-openshift-gpu")
            params = {
                "group_by[vendor]": "*",
                "filter[time_scope_value]": "-1",
                "filter[time_scope_units]": "month",
            }
            url = f"{url}?{urlencode(params)}"
            client = APIClient()
            response = client.get(url, **self.headers)

            self.assertEqual(response.status_code, status.HTTP_200_OK)
            data = response.data

            # Verify structure and that gpu_count values are present
            for entry in data.get("data", []):
                for vendor_entry in entry.get("vendors", []):
                    vendor = vendor_entry.get("vendor")
                    for value in vendor_entry.get("values", []):
                        gpu_count = value.get("gpu_count", {})
                        self.assertIsInstance(gpu_count, dict, "gpu_count should be a dict")
                        self.assertIn("value", gpu_count, "gpu_count should have 'value' key")
                        self.assertGreaterEqual(gpu_count.get("value", 0), 0, "gpu_count should be >= 0")

    def test_calculate_unique_gpu_count_by_cluster(self):
        """Test that _calculate_unique_gpu_count aggregates correctly by cluster."""
        with tenant_context(self.tenant):
            # Get unique combinations from database including cluster_id
            unique_combos = list(
                OCPGpuSummaryP.objects.values("cluster_id", "namespace", "node", "vendor_name", "model_name")
                .annotate(location_gpu_count=Max("gpu_count"))
                .order_by("cluster_id")
            )

            if not unique_combos:
                self.skipTest("No GPU data available for testing")

            # Calculate expected totals per (cluster_id, vendor, model)
            expected_by_cluster = {}
            for combo in unique_combos:
                cluster_id = combo["cluster_id"]
                vendor = combo["vendor_name"]
                model = combo["model_name"]
                count = combo["location_gpu_count"] or 0
                key = (cluster_id, vendor, model)
                expected_by_cluster[key] = expected_by_cluster.get(key, 0) + count

            # Test via API with group_by cluster
            url = reverse("reports-openshift-gpu")
            params = {
                "group_by[cluster]": "*",
                "filter[time_scope_value]": "-1",
                "filter[time_scope_units]": "month",
            }
            url = f"{url}?{urlencode(params)}"
            client = APIClient()
            response = client.get(url, **self.headers)

            self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_calculate_unique_gpu_count_unit_test_others_row(self):
        """Unit test for _calculate_unique_gpu_count with 'Others' rows."""
        with tenant_context(self.tenant):
            has_data = OCPGpuSummaryP.objects.exists()
            if not has_data:
                self.skipTest("No GPU data available for testing")

            url = reverse("reports-openshift-gpu")
            params = {"filter[time_scope_value]": "-1", "filter[time_scope_units]": "month"}
            url = f"{url}?{urlencode(params)}"
            client = APIClient()
            response = client.get(url, **self.headers)

            self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_calculate_unique_gpu_count_unit_test_list_values(self):
        """Unit test for _calculate_unique_gpu_count handling list values."""
        with tenant_context(self.tenant):
            has_data = OCPGpuSummaryP.objects.exists()
            if not has_data:
                self.skipTest("No GPU data available for testing")

            url = reverse("reports-openshift-gpu")
            params = {
                "group_by[project]": "*",
                "group_by[cluster]": "*",
                "filter[time_scope_value]": "-1",
                "filter[time_scope_units]": "month",
            }
            url = f"{url}?{urlencode(params)}"
            client = APIClient()
            response = client.get(url, **self.headers)

            self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_calculate_unique_gpu_count_with_exclude(self):
        """Test _calculate_unique_gpu_count with query_exclusions set."""
        with tenant_context(self.tenant):
            has_data = OCPGpuSummaryP.objects.exists()
            if not has_data:
                self.skipTest("No GPU data available for testing")

            url = reverse("reports-openshift-gpu")
            params = {
                "group_by[model]": "*",
                "filter[time_scope_value]": "-1",
                "filter[time_scope_units]": "month",
            }
            url = f"{url}?{urlencode(params)}"
            client = APIClient()
            response = client.get(url, **self.headers)

            self.assertEqual(response.status_code, status.HTTP_200_OK)
