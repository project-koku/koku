#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test GCP Report Queries."""
from datetime import timedelta
from decimal import Decimal
from decimal import ROUND_HALF_UP
from unittest.mock import patch
from unittest.mock import PropertyMock

from dateutil.relativedelta import relativedelta
from django.db.models import F
from django.db.models import Sum
from django.urls import reverse
from django_tenants.utils import tenant_context
from rest_framework.exceptions import ValidationError

from api.iam.test.iam_test_case import IamTestCase
from api.query_filter import QueryFilter
from api.report.gcp.query_handler import GCPReportQueryHandler
from api.report.gcp.serializers import GCPExcludeSerializer
from api.report.gcp.view import GCPCostView
from api.report.gcp.view import GCPInstanceTypeView
from api.report.gcp.view import GCPStorageView
from api.tags.gcp.queries import GCPTagQueryHandler
from api.tags.gcp.view import GCPTagView
from api.utils import DateHelper
from api.utils import materialized_view_month_start
from reporting.models import GCPCostEntryBill
from reporting.models import GCPCostEntryLineItemDailySummary
from reporting.models import GCPCostSummaryByAccountP
from reporting.models import GCPCostSummaryByProjectP
from reporting.models import GCPCostSummaryByServiceP
from reporting.models import GCPCostSummaryP
from reporting.models import GCPTagsSummary


class GCPReportQueryHandlerTest(IamTestCase):
    """Tests for the GCP report query handler."""

    def setUp(self):
        """Set up the customer view tests."""
        super().setUp()
        self.dh = DateHelper()
        # The monthly filters for gcp only use the invoice month
        # check out this pr for more information:
        # https://github.com/project-koku/koku/pull/3098
        self.this_month_filter = {
            "invoice_month__in": self.dh.gcp_find_invoice_months_in_date_range(
                self.dh.this_month_start, self.dh.this_month_end
            )
        }
        self.ten_day_filter = {
            "usage_start__gte": self.dh.n_days_ago(self.dh.today, 9),
            "invoice_month__in": self.dh.gcp_find_invoice_months_in_date_range(
                self.dh.n_days_ago(self.dh.today, 9), self.dh.today
            ),
        }
        self.thirty_day_filter = {
            "usage_start__gte": self.dh.n_days_ago(self.dh.today, 29),
            "invoice_month__in": self.dh.gcp_find_invoice_months_in_date_range(
                self.dh.n_days_ago(self.dh.today, 29), self.dh.today
            ),
        }
        self.last_month_filter = {
            "invoice_month__in": self.dh.gcp_find_invoice_months_in_date_range(
                self.dh.last_month_start, self.dh.last_month_end
            )
        }
        with tenant_context(self.tenant):
            self.services = GCPCostEntryLineItemDailySummary.objects.values("service_alias").distinct()
            self.services = [entry.get("service_alias") for entry in self.services]

    def get_totals_costs_by_time_scope(self, handler, filters=None):
        if filters is None:
            filters = self.this_month_filter
        aggregates = handler._mapper.report_type_map.get("aggregates")
        with tenant_context(self.tenant):
            result = (
                GCPCostEntryLineItemDailySummary.objects.filter(**filters)
                .annotate(**handler.annotations)
                .aggregate(**aggregates)
            )
            for key in result:
                if result[key] is None:
                    result[key] = Decimal(0)
            return result

    def test_execute_sum_query_costs(self):
        """Test that the sum query runs properly for the costs endpoint."""
        url = "?"
        query_params = self.mocked_query_params(url, GCPCostView)
        handler = GCPReportQueryHandler(query_params)
        current_totals = self.get_totals_costs_by_time_scope(handler, self.ten_day_filter)
        query_output = handler.execute_query()
        self.assertIsNotNone(query_output.get("data"))
        self.assertIsNotNone(query_output.get("total"))
        total = query_output.get("total")
        # It is better to not use .get on current totals because if the key doesn't exist
        # you can end up comparing to empty .get() are equal.
        self.assertEqual(total.get("cost", {}).get("total").get("value"), current_totals["cost_total"])

    def test_execute_take_defaults(self):
        """Test execute_query for current month on daily breakdown."""
        url = "?"
        query_params = self.mocked_query_params(url, GCPCostView)
        handler = GCPReportQueryHandler(query_params)
        query_output = handler.execute_query()
        self.assertIsNotNone(query_output.get("data"))
        self.assertIsNotNone(query_output.get("total"))
        total = query_output.get("total")
        self.assertIsNotNone(total.get("cost"))

    def test_execute_query_current_month_daily(self):
        """Test execute_query for current month on daily breakdown."""
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=daily"
        query_params = self.mocked_query_params(url, GCPCostView)
        handler = GCPReportQueryHandler(query_params)
        query_output = handler.execute_query()
        self.assertIsNotNone(query_output.get("data"))
        self.assertIsNotNone(query_output.get("total"))
        total = query_output.get("total")
        current_totals = self.get_totals_costs_by_time_scope(handler, self.this_month_filter)
        self.assertIsNotNone(total.get("cost"))
        self.assertEqual(total.get("cost", {}).get("total").get("value"), current_totals["cost_total"])

    def test_execute_query_current_month_monthly(self):
        """Test execute_query for current month on monthly breakdown."""
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=daily"
        query_params = self.mocked_query_params(url, GCPCostView)
        handler = GCPReportQueryHandler(query_params)
        query_output = handler.execute_query()
        self.assertIsNotNone(query_output.get("data"))
        self.assertIsNotNone(query_output.get("total"))
        total = query_output.get("total")
        current_totals = self.get_totals_costs_by_time_scope(handler, self.this_month_filter)
        self.assertIsNotNone(total.get("cost"))
        self.assertEqual(total.get("cost", {}).get("total").get("value"), current_totals["cost_total"])

    def test_execute_query_current_month_by_service(self):
        """Test execute_query for current month on monthly breakdown by service."""
        with tenant_context(self.tenant):
            valid_services = [
                service[0]
                for service in GCPCostEntryLineItemDailySummary.objects.values_list("service_alias").distinct()
            ]
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&group_by[service]=*"  # noqa: E501
        query_params = self.mocked_query_params(url, GCPCostView)
        handler = GCPReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get("total"))
        total = query_output.get("total")
        current_totals = self.get_totals_costs_by_time_scope(handler, self.this_month_filter)
        self.assertIsNotNone(total.get("cost"))
        self.assertEqual(total.get("cost", {}).get("total").get("value"), current_totals["cost_total"])

        cmonth_str = self.dh.this_month_start.strftime("%Y-%m")
        for data_item in data:
            month_val = data_item.get("date")
            month_data = data_item.get("services")
            self.assertEqual(month_val, cmonth_str)
            self.assertIsInstance(month_data, list)
            for month_item in month_data:
                name = month_item.get("service")
                self.assertIn(name, valid_services)
                self.assertIsInstance(month_item.get("values"), list)

    def test_query_group_by_partial_filtered_service(self):
        """Test execute_query monthly breakdown by filtered service."""
        # This might change as we add more gcp generators to nise
        with tenant_context(self.tenant):
            valid_services = [
                service[0]
                for service in GCPCostEntryLineItemDailySummary.objects.values_list("service_alias").distinct()
            ]
            service = valid_services[0]
        url = f"?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&group_by[service]={service}"  # noqa: E501
        query_params = self.mocked_query_params(url, GCPCostView)
        handler = GCPReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get("total"))
        total = query_output.get("total")
        filters = {**self.this_month_filter, "service_alias__icontains": service}
        for filt in handler._mapper.report_type_map.get("filter"):
            if filt:
                qf = QueryFilter(**filt)
                filters.update({qf.composed_query_string(): qf.parameter})
        current_totals = self.get_totals_costs_by_time_scope(handler, filters)
        self.assertIsNotNone(total.get("cost"))
        self.assertEqual(total.get("cost", {}).get("total").get("value"), current_totals["cost_total"])

        cmonth_str = self.dh.this_month_start.strftime("%Y-%m")
        for data_item in data:
            month_val = data_item.get("date")
            month_data = data_item.get("services")
            self.assertEqual(month_val, cmonth_str)
            self.assertIsInstance(month_data, list)
            for month_item in month_data:
                name = month_item.get("service")
                self.assertIn(name, valid_services)
                self.assertIsInstance(month_item.get("values"), list)

    def test_execute_query_by_filtered_service(self):
        """Test execute_query monthly breakdown by filtered service."""
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&filter[service]=*"  # noqa: E501
        query_params = self.mocked_query_params(url, GCPCostView)
        handler = GCPReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get("total"))
        total = query_output.get("total")
        current_totals = self.get_totals_costs_by_time_scope(handler, self.this_month_filter)
        self.assertIsNotNone(total.get("cost"))
        self.assertEqual(total.get("cost", {}).get("total").get("value"), current_totals["cost_total"])

        for data_item in data:
            self.assertIsInstance(data_item.get("values"), list)

    def test_query_by_partial_filtered_service(self):
        """Test execute_query monthly breakdown by filtered service."""
        with tenant_context(self.tenant):
            valid_services = [
                service[0] for service in GCPCostEntryLineItemDailySummary.objects.values_list("service_id").distinct()
            ]
            service = valid_services[0]
        url = f"?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&filter[service]={service}"  # noqa: E501
        query_params = self.mocked_query_params(url, GCPCostView)
        handler = GCPReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get("total"))
        total = query_output.get("total")
        filters = {**self.this_month_filter, "service_id__icontains": service}
        for filt in handler._mapper.report_type_map.get("filter"):
            if filt:
                qf = QueryFilter(**filt)
                filters.update({qf.composed_query_string(): qf.parameter})
        current_totals = self.get_totals_costs_by_time_scope(handler, filters)
        self.assertIsNotNone(total.get("cost"))
        self.assertEqual(total.get("cost", {}).get("total").get("value"), current_totals["cost_total"])

        for data_item in data:
            self.assertIsInstance(data_item.get("values"), list)

    def test_execute_query_current_month_by_account(self):
        """Test execute_query for current month on monthly breakdown by account."""
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&group_by[account]=*"  # noqa: E501
        query_params = self.mocked_query_params(url, GCPCostView)
        handler = GCPReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get("total"))
        total = query_output.get("total")
        current_totals = self.get_totals_costs_by_time_scope(handler, self.this_month_filter)
        self.assertIsNotNone(total.get("cost"))
        self.assertEqual(total.get("cost", {}).get("total").get("value"), current_totals["cost_total"])

        cmonth_str = self.dh.this_month_start.strftime("%Y-%m")
        for data_item in data:
            month_val = data_item.get("date")
            month_data = data_item.get("accounts")
            self.assertEqual(month_val, cmonth_str)
            self.assertIsInstance(month_data, list)
            for month_item in month_data:
                self.assertIsNotNone(month_item.get("account"))
                self.assertIsInstance(month_item.get("values"), list)

    def test_execute_query_by_account_by_service(self):
        """Test execute_query for current month breakdown by account by service."""
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&group_by[account]=*&group_by[service]=*"  # noqa: E501
        query_params = self.mocked_query_params(url, GCPCostView)
        handler = GCPReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get("total"))
        total = query_output.get("total")
        current_totals = self.get_totals_costs_by_time_scope(handler, self.this_month_filter)
        self.assertIsNotNone(total.get("cost"))
        self.assertEqual(total.get("cost", {}).get("total").get("value"), current_totals["cost_total"])

        cmonth_str = DateHelper().this_month_start.strftime("%Y-%m")
        for data_item in data:
            month_val = data_item.get("date")
            month_data = data_item.get("accounts")
            self.assertEqual(month_val, cmonth_str)
            self.assertIsInstance(month_data, list)
            for month_item in month_data:
                self.assertIsNotNone(month_item.get("account"))
                self.assertIsInstance(month_item.get("services"), list)

    def test_execute_query_curr_month_by_service_w_limit(self):
        """Test execute_query for current month on monthly breakdown by service with limit."""
        # This might change as we add more gcp generators to nise
        limit = 1
        url = f"?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&filter[limit]={limit}&group_by[service]=*"  # noqa: E501
        query_params = self.mocked_query_params(url, GCPCostView)
        handler = GCPReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get("total"))
        total = query_output.get("total")
        current_totals = self.get_totals_costs_by_time_scope(handler, self.this_month_filter)
        self.assertIsNotNone(total.get("cost"))
        self.assertEqual(total.get("cost", {}).get("total").get("value"), current_totals["cost_total"])

        cmonth_str = DateHelper().this_month_start.strftime("%Y-%m")
        for data_item in data:
            month_val = data_item.get("date")
            month_data = data_item.get("services")
            self.assertEqual(month_val, cmonth_str)
            self.assertIsInstance(month_data, list)
            self.assertEqual(len(month_data), limit + 1)
            other_string_created = False
            for month_item in month_data:
                service = month_item.get("service")
                self.assertIsInstance(service, str)
                if "Other" in service:
                    other_string_created = True
                self.assertIsInstance(month_item.get("values"), list)
            self.assertTrue(other_string_created)

    def test_execute_query_curr_month_by_account_w_order(self):
        """Test execute_query for current month on monthly breakdown by account with asc order."""
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&order_by[cost]=asc&group_by[account]=*"  # noqa: E501
        query_params = self.mocked_query_params(url, GCPCostView)
        handler = GCPReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get("total"))
        total = query_output.get("total")
        current_totals = self.get_totals_costs_by_time_scope(handler, self.this_month_filter)
        self.assertIsNotNone(total.get("cost"))
        self.assertEqual(total.get("cost", {}).get("total").get("value"), current_totals["cost_total"])

        cmonth_str = self.dh.this_month_start.strftime("%Y-%m")
        for data_item in data:
            month_val = data_item.get("date")
            month_data = data_item.get("accounts")
            self.assertEqual(month_val, cmonth_str)
            self.assertIsInstance(month_data, list)
            self.assertEqual(len(month_data), 1)
            current_total = 0
            for month_item in month_data:
                self.assertIsInstance(month_item.get("account"), str)
                self.assertIsInstance(month_item.get("values"), list)
                data_point_total = month_item.get("values")[0].get("cost", {}).get("total", {}).get("value")
                self.assertIsNotNone(data_point_total)
                self.assertLess(current_total, data_point_total)
                current_total = data_point_total

    def test_execute_query_curr_month_by_account_w_order_by_account(self):
        """Test execute_query for current month on monthly breakdown by account with asc order."""
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-2&filter[resolution]=monthly&order_by[account]=asc&group_by[account]=*"  # noqa: E501
        query_params = self.mocked_query_params(url, GCPCostView)
        handler = GCPReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get("total"))
        total = query_output.get("total")
        current_totals = self.get_totals_costs_by_time_scope(handler, self.last_month_filter)
        self.assertIsNotNone(total.get("cost"))
        self.assertEqual(total.get("cost", {}).get("total").get("value"), current_totals["cost_total"])

        cmonth_str = self.dh.last_month_start.strftime("%Y-%m")
        for data_item in data:
            month_val = data_item.get("date")
            month_data = data_item.get("accounts")
            self.assertEqual(month_val, cmonth_str)
            self.assertIsInstance(month_data, list)
            self.assertEqual(len(month_data), 1)
            current = "0"
            for month_item in month_data:
                self.assertIsInstance(month_item.get("account"), str)
                self.assertIsInstance(month_item.get("values"), list)
                self.assertIsNotNone(month_item.get("values")[0].get("account"))
                data_point = month_item.get("values")[0].get("account")
                if data_point == "1 Other":
                    continue
                self.assertLess(current, data_point)
                current = data_point

    def test_execute_query_curr_month_by_project(self):
        """Test execute_query for current month on monthly breakdown by project."""
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&group_by[gcp_project]=*"  # noqa: E501
        with tenant_context(self.tenant):
            project_count = (
                GCPCostEntryLineItemDailySummary.objects.filter(usage_start__gte=self.dh.this_month_start)
                .values_list("project_id")
                .distinct()
                .count()
            )
        query_params = self.mocked_query_params(url, GCPCostView)
        handler = GCPReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get("total"))
        total = query_output.get("total")
        current_totals = self.get_totals_costs_by_time_scope(handler, self.this_month_filter)
        self.assertIsNotNone(total.get("cost"))
        self.assertEqual(total.get("cost", {}).get("total").get("value"), current_totals["cost_total"])

        cmonth_str = DateHelper().this_month_start.strftime("%Y-%m")
        for data_item in data:
            month_val = data_item.get("date")
            month_data = data_item.get("gcp_projects")
            self.assertEqual(month_val, cmonth_str)
            self.assertIsInstance(month_data, list)
            self.assertEqual(len(month_data), project_count)
            for month_item in month_data:
                self.assertIsInstance(month_item.get("gcp_project"), str)
                self.assertIsInstance(month_item.get("values"), list)
                self.assertIsNotNone(month_item.get("values")[0].get("cost"))

    def test_execute_query_curr_month_by_filtered_project(self):
        """Test execute_query for current month on monthly breakdown by filtered project."""
        with tenant_context(self.tenant):
            project = (
                GCPCostEntryLineItemDailySummary.objects.filter(usage_start__gte=self.dh.this_month_start)
                .values("project_id")[0]
                .get("project_id")
            )
        url = f"?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&group_by[gcp_project]={project}"  # noqa: E501
        query_params = self.mocked_query_params(url, GCPCostView)
        handler = GCPReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get("total"))
        total = query_output.get("total")
        filters = {**self.this_month_filter, "project_id": project}
        current_totals = self.get_totals_costs_by_time_scope(handler, filters)
        self.assertIsNotNone(total.get("cost"))
        self.assertEqual(total.get("cost", {}).get("total").get("value"), current_totals["cost_total"])

        cmonth_str = DateHelper().this_month_start.strftime("%Y-%m")
        for data_item in data:
            month_val = data_item.get("date")
            month_data = data_item.get("gcp_projects")
            self.assertEqual(month_val, cmonth_str)
            self.assertIsInstance(month_data, list)
            for month_item in month_data:
                self.assertIsInstance(month_item.get("gcp_project"), str)
                self.assertIsInstance(month_item.get("values"), list)
                self.assertIsNotNone(month_item.get("values")[0].get("cost"))

    def test_execute_query_current_month_filter_account(self):
        """Test execute_query for current month on monthly filtered by account."""
        with tenant_context(self.tenant):
            account = GCPCostEntryLineItemDailySummary.objects.filter(
                usage_start__gte=self.dh.this_month_start
            ).values("account_id")[0]
        url = f"?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&filter[account]={account}"  # noqa: E501
        query_params = self.mocked_query_params(url, GCPCostView)
        handler = GCPReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get("total"))
        total = query_output.get("total")
        filters = {**self.this_month_filter, "account_id": account}
        current_totals = self.get_totals_costs_by_time_scope(handler, filters)
        self.assertIsNotNone(total.get("cost"))
        self.assertEqual(total.get("cost", {}).get("total").get("value"), current_totals["cost_total"])

        cmonth_str = self.dh.this_month_start.strftime("%Y-%m")
        for data_item in data:
            month_val = data_item.get("date")
            month_data = data_item.get("values")
            self.assertEqual(month_val, cmonth_str)
            self.assertIsInstance(month_data, list)

    def test_execute_query_current_month_filter_service(self):
        """Test execute_query for current month on monthly filtered by service."""
        with tenant_context(self.tenant):
            service = GCPCostEntryLineItemDailySummary.objects.values("service_id")[0].get("service_id")
        url = f"?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&filter[service]={service}"  # noqa: E501
        query_params = self.mocked_query_params(url, GCPCostView)
        handler = GCPReportQueryHandler(query_params)
        query_output = handler.execute_query()

        data = query_output.get("data")
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get("total"))

        total = query_output.get("total")
        filters = {**self.this_month_filter, "service_id__icontains": service}
        for filt in handler._mapper.report_type_map.get("filter"):
            if filt:
                qf = QueryFilter(**filt)
                filters.update({qf.composed_query_string(): qf.parameter})
        current_totals = self.get_totals_costs_by_time_scope(handler, filters)
        self.assertIsNotNone(total.get("cost"))
        self.assertEqual(total.get("cost", {}).get("total").get("value"), current_totals["cost_total"])

        cmonth_str = self.dh.this_month_start.strftime("%Y-%m")
        for data_item in data:
            month_val = data_item.get("date")
            month_data = data_item.get("values")
            self.assertEqual(month_val, cmonth_str)
            self.assertIsInstance(month_data, list)

    def test_execute_query_current_month_filter_region(self):
        """Test execute_query for current month on monthly filtered by region."""
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&filter[region]=*"  # noqa: E501
        query_params = self.mocked_query_params(url, GCPCostView)
        handler = GCPReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get("total"))
        total = query_output.get("total")
        filters = {**self.this_month_filter}
        current_totals = self.get_totals_costs_by_time_scope(handler, filters)
        self.assertIsNotNone(total.get("cost"))
        self.assertEqual(total.get("cost", {}).get("total").get("value"), current_totals["cost_total"])

        cmonth_str = DateHelper().this_month_start.strftime("%Y-%m")
        for data_item in data:
            month_val = data_item.get("date")
            month_data = data_item.get("values")
            self.assertEqual(month_val, cmonth_str)
            self.assertIsInstance(month_data, list)

    def test_execute_query_current_month_exclude_service(self):
        """Test execute_query for current month on monthly excluded by service."""
        with tenant_context(self.tenant):
            service = GCPCostEntryLineItemDailySummary.objects.values("service_id")[0].get("service_id")
        url = f"?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&exclude[service]={service}"  # noqa: E501
        query_params = self.mocked_query_params(url, GCPCostView)
        handler = GCPReportQueryHandler(query_params)
        query_output = handler.execute_query()

        data = query_output.get("data")
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get("total"))

    @patch("api.query_params.QueryParameters.accept_type", new_callable=PropertyMock)
    def test_execute_query_current_month_filter_region_csv(self, mock_accept):
        """Test execute_query on monthly filtered by region for csv."""
        mock_accept.return_value = "text/csv"
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&filter[region]=*"  # noqa: E501
        query_params = self.mocked_query_params(url, GCPCostView)
        handler = GCPReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get("total"))
        total = query_output.get("total")
        filters = {**self.this_month_filter}
        current_totals = self.get_totals_costs_by_time_scope(handler, filters)
        self.assertIsNotNone(total.get("cost"))
        self.assertEqual(total.get("cost", {}).get("total").get("value"), current_totals["cost_total"])

        cmonth_str = DateHelper().this_month_start.strftime("%Y-%m")
        self.assertEqual(len(data), 1)
        for data_item in data:
            month_val = data_item.get("date")
            self.assertEqual(month_val, cmonth_str)

    @patch("api.query_params.QueryParameters.accept_type", new_callable=PropertyMock)
    def test_execute_query_curr_month_by_account_w_limit_csv(self, mock_accept):
        """Test execute_query for current month on monthly by account with limt as csv."""
        mock_accept.return_value = "text/csv"

        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&filter[limit]=2&group_by[account]=*"  # noqa: E501
        query_params = self.mocked_query_params(url, GCPCostView)
        handler = GCPReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")

        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get("total"))
        total = query_output.get("total")
        current_totals = self.get_totals_costs_by_time_scope(handler, self.this_month_filter)
        self.assertIsNotNone(total.get("cost"))
        self.assertEqual(total.get("cost", {}).get("total").get("value"), current_totals["cost_total"])

        cmonth_str = self.dh.this_month_start.strftime("%Y-%m")
        self.assertEqual(len(data), 1)
        for data_item in data:
            month = data_item.get("date")
            self.assertEqual(month, cmonth_str)

    def test_execute_query_w_delta(self):
        """Test grouped by deltas."""
        path = reverse("reports-gcp-costs")
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&group_by[account]=*&delta=cost"  # noqa: E501
        query_params = self.mocked_query_params(url, GCPCostView, path)
        handler = GCPReportQueryHandler(query_params)
        # test the calculations
        query_output = handler.execute_query()
        data = query_output.get("data")
        self.assertIsNotNone(data)

        accounts = data[0].get("accounts", [{}])
        current_invoice_month = self.dh.gcp_find_invoice_months_in_date_range(
            self.dh.this_month_start, self.dh.this_month_end
        )
        last_invoice_month = self.dh.gcp_find_invoice_months_in_date_range(
            self.dh.last_month_start, self.dh.last_month_end
        )

        for account in accounts:
            current_total = Decimal(0)
            prev_total = Decimal(0)

            # fetch the expected sums from the DB.
            with tenant_context(self.tenant):
                curr = GCPCostEntryLineItemDailySummary.objects.filter(
                    invoice_month__in=current_invoice_month,
                    account_id=account.get("account"),
                    usage_start__gte=self.dh.this_month_start,
                    usage_start__lte=self.dh.today,
                ).aggregate(value=Sum(F("unblended_cost") + F("markup_cost") + F("credit_amount")))
                current_total = Decimal(curr.get("value"))

                prev = GCPCostEntryLineItemDailySummary.objects.filter(
                    invoice_month__in=last_invoice_month,
                    account_id=account.get("account"),
                    usage_start__gte=self.dh.last_month_start,
                    usage_start__lte=self.dh.today - relativedelta(months=1),
                ).aggregate(value=Sum(F("unblended_cost") + F("markup_cost") + F("credit_amount")))
                prev_total = Decimal(prev.get("value", Decimal(0)))

            expected_delta_value = Decimal(current_total - prev_total)
            expected_delta_percent = Decimal((current_total - prev_total) / prev_total * 100)

            values = account.get("values", [{}])[0]
            self.assertIn("delta_value", values)
            self.assertIn("delta_percent", values)
            self.assertEqual(values.get("delta_value"), expected_delta_value)
            self.assertEqual(values.get("delta_percent"), expected_delta_percent)

        current_total = Decimal(0)
        prev_total = Decimal(0)

        # fetch the expected sums from the DB.
        with tenant_context(self.tenant):
            curr = GCPCostEntryLineItemDailySummary.objects.filter(
                invoice_month__in=current_invoice_month,
                usage_start__gte=self.dh.this_month_start,
                usage_start__lte=self.dh.today,
            ).aggregate(value=Sum(F("unblended_cost") + F("markup_cost") + F("credit_amount")))
            current_total = Decimal(curr.get("value"))

            prev = GCPCostEntryLineItemDailySummary.objects.filter(
                invoice_month__in=last_invoice_month,
                usage_start__gte=self.dh.last_month_start,
                usage_start__lte=self.dh.today - relativedelta(months=1),
            ).aggregate(value=Sum(F("unblended_cost") + F("markup_cost") + F("credit_amount")))
            prev_total = Decimal(prev.get("value"))

        expected_delta_value = Decimal(current_total - prev_total)
        expected_delta_percent = Decimal((current_total - prev_total) / prev_total * 100)

        delta = query_output.get("delta")
        self.assertIsNotNone(delta.get("value"))
        self.assertIsNotNone(delta.get("percent"))
        self.assertEqual(delta.get("value"), expected_delta_value)
        self.assertEqual(delta.get("percent"), expected_delta_percent)

    def test_execute_query_w_delta_no_previous_data(self):
        """Test deltas with no previous data."""
        url = "?filter[time_scope_value]=-2&delta=cost"
        path = reverse("reports-gcp-costs")
        query_params = self.mocked_query_params(url, GCPCostView, path)
        handler = GCPReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")
        self.assertIsNotNone(data)
        total_cost = query_output.get("total", {}).get("cost", {}).get("total")
        self.assertIsNotNone(total_cost)
        delta = query_output.get("delta")
        self.assertIsNotNone(delta.get("value"))
        self.assertIsNone(delta.get("percent"))
        self.assertEqual(delta.get("value"), total_cost.get("value"))
        self.assertEqual(delta.get("percent"), None)

    def test_execute_query_orderby_delta(self):
        """Test execute_query with ordering by delta ascending."""
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&order_by[delta]=asc&group_by[account]=*&delta=cost"  # noqa: E501
        path = reverse("reports-gcp-costs")
        query_params = self.mocked_query_params(url, GCPCostView, path)
        handler = GCPReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")
        self.assertIsNotNone(data)
        cmonth_str = self.dh.this_month_start.strftime("%Y-%m")
        for data_item in data:
            month_val = data_item.get("date")
            month_data = data_item.get("accounts")
            self.assertEqual(month_val, cmonth_str)
            self.assertIsInstance(month_data, list)
            for month_item in month_data:
                self.assertIsInstance(month_item.get("account"), str)
                self.assertIsInstance(month_item.get("values"), list)
                self.assertIsInstance(month_item.get("values")[0].get("delta_value"), Decimal)

    def test_calculate_total(self):
        """Test that calculated totals return correctly."""
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly"
        query_params = self.mocked_query_params(url, GCPCostView)
        handler = GCPReportQueryHandler(query_params)
        expected_units = "USD"
        with tenant_context(self.tenant):
            result = handler.calculate_total(**{"cost_units": expected_units})

        current_totals = self.get_totals_costs_by_time_scope(handler, self.last_month_filter)
        cost_total = result.get("cost", {}).get("total")
        self.assertIsNotNone(cost_total)
        self.assertEqual(cost_total.get("value"), current_totals["cost_total"])
        self.assertEqual(cost_total.get("units"), expected_units)

    def test_percent_delta(self):
        """Test _percent_delta() utility method."""
        url = "?"
        query_params = self.mocked_query_params(url, GCPCostView)
        handler = GCPReportQueryHandler(query_params)
        self.assertEqual(handler._percent_delta(10, 5), 100)

    def test_rank_list_by_account(self):
        """Test rank list limit with account alias."""
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&filter[limit]=2&group_by[account]=*"  # noqa: E501
        query_params = self.mocked_query_params(url, GCPCostView)
        handler = GCPReportQueryHandler(query_params)
        ranks = [
            {"account": "1", "rank": 1, "source_uuid": ["1"]},
            {"account": "2", "rank": 2, "source_uuid": ["1"]},
            {"account": "3", "rank": 3, "source_uuid": ["1"]},
            {"account": "4", "rank": 4, "source_uuid": ["1"]},
        ]

        data_list = [
            {
                "account": "1",
                "date": "2022-05",
                "cost_credit": 1,
                "infra_credit": 1,
                "sup_credit": 1,
                "cost_markup": 1,
                "cost_raw": 1,
                "cost_total": 1,
                "cost_usage": 1,
                "infra_markup": 1,
                "infra_raw": 1,
                "infra_total": 1,
                "infra_usage": 1,
                "sup_markup": 1,
                "sup_raw": 1,
                "sup_total": 1,
                "sup_usage": 1,
                "cost_units": "USD",
                "source_uuid": ["1"],
            },
            {
                "account": "2",
                "date": "2022-05",
                "cost_credit": 1,
                "infra_credit": 1,
                "sup_credit": 1,
                "cost_markup": 1,
                "cost_raw": 1,
                "cost_total": 1,
                "cost_usage": 1,
                "infra_markup": 1,
                "infra_raw": 1,
                "infra_total": 1,
                "infra_usage": 1,
                "sup_markup": 1,
                "sup_raw": 1,
                "sup_total": 1,
                "sup_usage": 1,
                "cost_units": "USD",
                "source_uuid": ["1"],
            },
            {
                "account": "3",
                "date": "2022-05",
                "cost_credit": 1,
                "infra_credit": 1,
                "sup_credit": 1,
                "cost_markup": 1,
                "cost_raw": 1,
                "cost_total": 1,
                "cost_usage": 1,
                "infra_markup": 1,
                "infra_raw": 1,
                "infra_total": 1,
                "infra_usage": 1,
                "sup_markup": 1,
                "sup_raw": 1,
                "sup_total": 1,
                "sup_usage": 1,
                "cost_units": "USD",
                "source_uuid": ["1"],
            },
            {
                "account": "4",
                "date": "2022-05",
                "cost_credit": 1,
                "infra_credit": 1,
                "sup_credit": 1,
                "cost_markup": 1,
                "cost_raw": 1,
                "cost_total": 1,
                "cost_usage": 1,
                "infra_markup": 1,
                "infra_raw": 1,
                "infra_total": 1,
                "infra_usage": 1,
                "sup_markup": 1,
                "sup_raw": 1,
                "sup_total": 1,
                "sup_usage": 1,
                "cost_units": "USD",
                "source_uuid": ["1"],
            },
        ]
        expected = [
            {
                "account": "1",
                "rank": 1,
                "date": "2022-05",
                "cost_credit": 1,
                "infra_credit": 1,
                "sup_credit": 1,
                "cost_markup": 1,
                "cost_raw": 1,
                "cost_total": 1,
                "cost_usage": 1,
                "infra_markup": 1,
                "infra_raw": 1,
                "infra_total": 1,
                "infra_usage": 1,
                "sup_markup": 1,
                "sup_raw": 1,
                "sup_total": 1,
                "sup_usage": 1,
                "cost_units": "USD",
                "source_uuid": ["1"],
            },
            {
                "account": "2",
                "rank": 2,
                "date": "2022-05",
                "cost_credit": 1,
                "infra_credit": 1,
                "sup_credit": 1,
                "cost_markup": 1,
                "cost_raw": 1,
                "cost_total": 1,
                "cost_usage": 1,
                "infra_markup": 1,
                "infra_raw": 1,
                "infra_total": 1,
                "infra_usage": 1,
                "sup_markup": 1,
                "sup_raw": 1,
                "sup_total": 1,
                "sup_usage": 1,
                "cost_units": "USD",
                "source_uuid": ["1"],
            },
            {
                "account": "Others",
                "rank": 3,
                "date": "2022-05",
                "cost_credit": 2,
                "infra_credit": 2,
                "sup_credit": 2,
                "cost_markup": 2,
                "cost_raw": 2,
                "cost_total": 2,
                "cost_usage": 2,
                "infra_markup": 2,
                "infra_raw": 2,
                "infra_total": 2,
                "infra_usage": 2,
                "sup_markup": 2,
                "sup_raw": 2,
                "sup_total": 2,
                "sup_usage": 2,
                "cost_units": "USD",
                "source_uuid": ["1"],
            },
        ]
        ranked_list = handler._ranked_list(data_list, ranks)
        for i in range(len(ranked_list)):
            for key in ranked_list[i]:
                self.assertEqual(ranked_list[i][key], expected[i][key])

    def test_rank_list_by_service_alias(self):
        """Test rank list limit with service_alias grouping."""
        # This might change as we add more gcp generators to nise
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&filter[limit]=2&group_by[service]=*"  # noqa: E501
        query_params = self.mocked_query_params(url, GCPCostView)
        handler = GCPReportQueryHandler(query_params)
        ranks = [
            {"service": "1", "rank": 1, "source_uuid": ["1"]},
            {"service": "2", "rank": 2, "source_uuid": ["1"]},
            {"service": "3", "rank": 3, "source_uuid": ["1"]},
            {"service": "4", "rank": 4, "source_uuid": ["1"]},
        ]

        data_list = [
            {
                "service": "1",
                "date": "2022-05",
                "cost_credit": 1,
                "infra_credit": 1,
                "sup_credit": 1,
                "cost_markup": 1,
                "cost_raw": 1,
                "cost_total": 1,
                "cost_usage": 1,
                "infra_markup": 1,
                "infra_raw": 1,
                "infra_total": 1,
                "infra_usage": 1,
                "sup_markup": 1,
                "sup_raw": 1,
                "sup_total": 1,
                "sup_usage": 1,
                "cost_units": "USD",
                "source_uuid": ["1"],
            },
            {
                "service": "2",
                "date": "2022-05",
                "cost_credit": 1,
                "infra_credit": 1,
                "sup_credit": 1,
                "cost_markup": 1,
                "cost_raw": 1,
                "cost_total": 1,
                "cost_usage": 1,
                "infra_markup": 1,
                "infra_raw": 1,
                "infra_total": 1,
                "infra_usage": 1,
                "sup_markup": 1,
                "sup_raw": 1,
                "sup_total": 1,
                "sup_usage": 1,
                "cost_units": "USD",
                "source_uuid": ["1"],
            },
            {
                "service": "3",
                "date": "2022-05",
                "cost_credit": 1,
                "infra_credit": 1,
                "sup_credit": 1,
                "cost_markup": 1,
                "cost_raw": 1,
                "cost_total": 1,
                "cost_usage": 1,
                "infra_markup": 1,
                "infra_raw": 1,
                "infra_total": 1,
                "infra_usage": 1,
                "sup_markup": 1,
                "sup_raw": 1,
                "sup_total": 1,
                "sup_usage": 1,
                "cost_units": "USD",
                "source_uuid": ["1"],
            },
            {
                "service": "4",
                "date": "2022-05",
                "cost_credit": 1,
                "infra_credit": 1,
                "sup_credit": 1,
                "cost_markup": 1,
                "cost_raw": 1,
                "cost_total": 1,
                "cost_usage": 1,
                "infra_markup": 1,
                "infra_raw": 1,
                "infra_total": 1,
                "infra_usage": 1,
                "sup_markup": 1,
                "sup_raw": 1,
                "sup_total": 1,
                "sup_usage": 1,
                "cost_units": "USD",
                "source_uuid": ["1"],
            },
        ]
        expected = [
            {
                "service": "1",
                "rank": 1,
                "date": "2022-05",
                "cost_credit": 1,
                "infra_credit": 1,
                "sup_credit": 1,
                "cost_markup": 1,
                "cost_raw": 1,
                "cost_total": 1,
                "cost_usage": 1,
                "infra_markup": 1,
                "infra_raw": 1,
                "infra_total": 1,
                "infra_usage": 1,
                "sup_markup": 1,
                "sup_raw": 1,
                "sup_total": 1,
                "sup_usage": 1,
                "cost_units": "USD",
                "source_uuid": ["1"],
            },
            {
                "service": "2",
                "rank": 2,
                "date": "2022-05",
                "cost_credit": 1,
                "infra_credit": 1,
                "sup_credit": 1,
                "cost_markup": 1,
                "cost_raw": 1,
                "cost_total": 1,
                "cost_usage": 1,
                "infra_markup": 1,
                "infra_raw": 1,
                "infra_total": 1,
                "infra_usage": 1,
                "sup_markup": 1,
                "sup_raw": 1,
                "sup_total": 1,
                "sup_usage": 1,
                "cost_units": "USD",
                "source_uuid": ["1"],
            },
            {
                "service": "Others",
                "rank": 3,
                "date": "2022-05",
                "cost_credit": 2,
                "infra_credit": 2,
                "sup_credit": 2,
                "cost_markup": 2,
                "cost_raw": 2,
                "cost_total": 2,
                "cost_usage": 2,
                "infra_markup": 2,
                "infra_raw": 2,
                "infra_total": 2,
                "infra_usage": 2,
                "sup_markup": 2,
                "sup_raw": 2,
                "sup_total": 2,
                "sup_usage": 2,
                "cost_units": "USD",
                "source_uuid": ["1"],
            },
        ]
        ranked_list = handler._ranked_list(data_list, ranks)
        for i in range(len(ranked_list)):
            for key in ranked_list[i]:
                self.assertEqual(ranked_list[i][key], expected[i][key])

    def test_rank_list_with_offset(self):
        """Test rank list limit and offset with account alias."""
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&filter[limit]=1&filter[offset]=1&group_by[account]=*"  # noqa: E501
        query_params = self.mocked_query_params(url, GCPCostView)
        handler = GCPReportQueryHandler(query_params)
        ranks = [
            {"account": "1", "rank": 1, "source_uuid": ["1"]},
            {"account": "2", "rank": 2, "source_uuid": ["1"]},
            {"account": "3", "rank": 3, "source_uuid": ["1"]},
            {"account": "4", "rank": 4, "source_uuid": ["1"]},
        ]

        data_list = [
            {
                "account": "1",
                "date": "2022-05",
                "cost_credit": 1,
                "infra_credit": 1,
                "sup_credit": 1,
                "cost_markup": 1,
                "cost_raw": 1,
                "cost_total": 1,
                "cost_usage": 1,
                "infra_markup": 1,
                "infra_raw": 1,
                "infra_total": 1,
                "infra_usage": 1,
                "sup_markup": 1,
                "sup_raw": 1,
                "sup_total": 1,
                "sup_usage": 1,
                "cost_units": "USD",
                "source_uuid": ["1"],
            },
            {
                "account": "2",
                "date": "2022-05",
                "cost_credit": 1,
                "infra_credit": 1,
                "sup_credit": 1,
                "cost_markup": 1,
                "cost_raw": 1,
                "cost_total": 1,
                "cost_usage": 1,
                "infra_markup": 1,
                "infra_raw": 1,
                "infra_total": 1,
                "infra_usage": 1,
                "sup_markup": 1,
                "sup_raw": 1,
                "sup_total": 1,
                "sup_usage": 1,
                "cost_units": "USD",
                "source_uuid": ["1"],
            },
            {
                "account": "3",
                "date": "2022-05",
                "cost_credit": 1,
                "infra_credit": 1,
                "sup_credit": 1,
                "cost_markup": 1,
                "cost_raw": 1,
                "cost_total": 1,
                "cost_usage": 1,
                "infra_markup": 1,
                "infra_raw": 1,
                "infra_total": 1,
                "infra_usage": 1,
                "sup_markup": 1,
                "sup_raw": 1,
                "sup_total": 1,
                "sup_usage": 1,
                "cost_units": "USD",
                "source_uuid": ["1"],
            },
            {
                "account": "4",
                "date": "2022-05",
                "cost_credit": 1,
                "infra_credit": 1,
                "sup_credit": 1,
                "cost_markup": 1,
                "cost_raw": 1,
                "cost_total": 1,
                "cost_usage": 1,
                "infra_markup": 1,
                "infra_raw": 1,
                "infra_total": 1,
                "infra_usage": 1,
                "sup_markup": 1,
                "sup_raw": 1,
                "sup_total": 1,
                "sup_usage": 1,
                "cost_units": "USD",
                "source_uuid": ["1"],
            },
        ]
        expected = [
            {
                "account": "2",
                "date": "2022-05",
                "cost_credit": 1,
                "infra_credit": 1,
                "sup_credit": 1,
                "cost_markup": 1,
                "cost_raw": 1,
                "cost_total": 1,
                "cost_usage": 1,
                "infra_markup": 1,
                "infra_raw": 1,
                "infra_total": 1,
                "infra_usage": 1,
                "sup_markup": 1,
                "sup_raw": 1,
                "sup_total": 1,
                "sup_usage": 1,
                "cost_units": "USD",
                "source_uuid": ["1"],
                "rank": 2,
            },
        ]
        ranked_list = handler._ranked_list(data_list, ranks)
        for i in range(len(ranked_list)):
            for key in ranked_list[i]:
                self.assertEqual(ranked_list[i][key], expected[i][key])

    def test_query_costs_with_totals(self):
        """Test execute_query() - costs with totals.

        Query for instance_types, validating that cost totals are present.

        """
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&group_by[account]=*"  # noqa: E501
        query_params = self.mocked_query_params(url, GCPCostView)
        handler = GCPReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")
        self.assertIsNotNone(data)

        for data_item in data:
            accounts = data_item.get("accounts")
            for account in accounts:
                self.assertIsNotNone(account.get("values"))
                self.assertGreater(len(account.get("values")), 0)
                for value in account.get("values"):
                    cost_total_value = value.get("cost", {}).get("total", {}).get("value")
                    self.assertIsInstance(cost_total_value, Decimal)
                    self.assertGreater(cost_total_value, Decimal(0))

    def test_order_by(self):
        """Test that order_by returns properly sorted data."""
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly"
        query_params = self.mocked_query_params(url, GCPCostView)
        handler = GCPReportQueryHandler(query_params)

        unordered_data = [
            {"date": self.dh.today, "delta_percent": 8, "total": 6.2, "rank": 2},
            {"date": self.dh.yesterday, "delta_percent": 4, "total": 2.2, "rank": 1},
            {"date": self.dh.today, "delta_percent": 7, "total": 8.2, "rank": 1},
            {"date": self.dh.yesterday, "delta_percent": 4, "total": 2.2, "rank": 2},
        ]

        order_fields = ["date", "rank"]
        expected = [
            {"date": self.dh.yesterday, "delta_percent": 4, "total": 2.2, "rank": 1},
            {"date": self.dh.yesterday, "delta_percent": 4, "total": 2.2, "rank": 2},
            {"date": self.dh.today, "delta_percent": 7, "total": 8.2, "rank": 1},
            {"date": self.dh.today, "delta_percent": 8, "total": 6.2, "rank": 2},
        ]

        ordered_data = handler.order_by(unordered_data, order_fields)
        self.assertEqual(ordered_data, expected)

        order_fields = ["date", "-delta"]
        expected = [
            {"date": self.dh.yesterday, "delta_percent": 4, "total": 2.2, "rank": 1},
            {"date": self.dh.yesterday, "delta_percent": 4, "total": 2.2, "rank": 2},
            {"date": self.dh.today, "delta_percent": 8, "total": 6.2, "rank": 2},
            {"date": self.dh.today, "delta_percent": 7, "total": 8.2, "rank": 1},
        ]

        ordered_data = handler.order_by(unordered_data, order_fields)
        self.assertEqual(ordered_data, expected)

    def test_query_table(self):
        """Test that the correct view is assigned by query table property."""
        test_cases = [
            ("?", GCPCostView, GCPCostSummaryP),
            ("?group_by[account]=*", GCPCostView, GCPCostSummaryByAccountP),
            ("?group_by[gcp_project]=*", GCPCostView, GCPCostSummaryByProjectP),
            ("?group_by[gcp_project]=*&group_by[account]=*", GCPCostView, GCPCostSummaryByProjectP),
            ("?group_by[service]=*", GCPCostView, GCPCostSummaryByServiceP),
            ("?group_by[service]=*&group_by[account]=*", GCPCostView, GCPCostSummaryByServiceP),
            (
                "?filter[service]=Database,Cosmos%20DB,Cache%20for%20Redis&group_by[account]=*",
                GCPCostView,
                GCPCostSummaryByServiceP,
            ),
            (
                "?filter[service]=Virtual%20Network,VPN,DNS,Traffic%20Manager,ExpressRoute,Load%20Balancer,Application%20Gateway",  # noqa: E501
                GCPCostView,
                GCPCostSummaryByServiceP,
            ),
            (
                "?filter[service]=Virtual%20Network,VPN,DNS,Traffic%20Manager,ExpressRoute,Load%20Balancer,Application%20Gateway&group_by[account]=*",  # noqa: E501
                GCPCostView,
                GCPCostSummaryByServiceP,
            ),
        ]

        for test_case in test_cases:
            with self.subTest(test_case=test_case):
                url, view, table = test_case
                query_params = self.mocked_query_params(url, view)
                handler = GCPReportQueryHandler(query_params)
                self.assertEqual(handler.query_table, table)

    def test_source_uuid_mapping(self):  # noqa: C901
        """Test source_uuid is mapped to the correct source."""
        # Find the correct expected source uuid:
        with tenant_context(self.tenant):
            gcp_uuids = GCPCostEntryLineItemDailySummary.objects.distinct().values_list("source_uuid", flat=True)
            expected_source_uuids = GCPCostEntryBill.objects.distinct().values_list("provider_id", flat=True)
            for gcp_uuid in gcp_uuids:
                self.assertIn(gcp_uuid, expected_source_uuids)
        endpoints = [GCPCostView]
        source_uuid_list = []
        for endpoint in endpoints:
            urls = ["?"]
            if endpoint == GCPCostView:
                urls.extend(
                    ["?group_by[account]=*", "?group_by[gcp_project]=*", "group_by[region]=*", "?group_by[service]=*"]
                )
            for url in urls:
                query_params = self.mocked_query_params(url, endpoint)
                handler = GCPReportQueryHandler(query_params)
                query_output = handler.execute_query()
                for dictionary in query_output.get("data"):
                    for _, value in dictionary.items():
                        if isinstance(value, list):
                            for item in value:
                                if isinstance(item, dict):
                                    if "values" in item.keys():
                                        value = item["values"][0]
                                        source_uuid_list.extend(value.get("source_uuid"))
        self.assertNotEqual(source_uuid_list, [])
        for source_uuid in source_uuid_list:
            self.assertIn(source_uuid, expected_source_uuids)

    def test_execute_query_annotate(self):
        """Test that query enters cost unit and usage unit ."""
        with tenant_context(self.tenant):
            account = GCPCostEntryLineItemDailySummary.objects.filter(
                usage_start__gte=self.dh.this_month_start
            ).values("account_id")[0]
        url = f"?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&filter[account]={account}"  # noqa: E501
        query_params = self.mocked_query_params(url, GCPCostView)
        handler = GCPReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get("total"))
        total = query_output.get("total")
        filters = {**self.this_month_filter, "account_id": account}
        current_totals = self.get_totals_costs_by_time_scope(handler, filters)
        self.assertIsNotNone(total.get("cost"))
        self.assertEqual(total.get("cost", {}).get("total").get("value"), current_totals["cost_total"])

        cmonth_str = self.dh.this_month_start.strftime("%Y-%m")
        for data_item in data:
            month_val = data_item.get("date")
            self.assertEqual(month_val, cmonth_str)

    def test_execute_sum_query_instance_type(self):
        """Test that the sum query runs properly."""
        url = "?"
        query_params = self.mocked_query_params(url, GCPInstanceTypeView)
        handler = GCPReportQueryHandler(query_params)

        filters = self.ten_day_filter
        for filt in handler._mapper.report_type_map.get("filter"):
            qf = QueryFilter(**filt)
            filters.update({qf.composed_query_string(): qf.parameter})
        current_totals = self.get_totals_costs_by_time_scope(handler, filters)
        expected_cost_total = current_totals.get("cost_total")
        self.assertIsNotNone(expected_cost_total)
        query_output = handler.execute_query()

        self.assertIsNotNone(query_output.get("data"))
        self.assertIsNotNone(query_output.get("total"))
        total = query_output.get("total")
        self.assertIsNotNone(total.get("usage", {}).get("value"))
        self.assertEqual(total.get("usage", {}).get("value"), current_totals.get("usage"))
        result_cost_total = total.get("cost", {}).get("total", {}).get("value")
        self.assertIsNotNone(result_cost_total)
        self.assertEqual(result_cost_total, expected_cost_total)

    def test_query_instance_types_with_totals(self):
        """Test execute_query() - instance types with totals.

        Query for instance_types, validating that cost totals are present.

        """
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&group_by[instance_type]=*"  # noqa: E501
        query_params = self.mocked_query_params(url, GCPInstanceTypeView)
        handler = GCPReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")
        self.assertIsNotNone(data)

        for data_item in data:
            instance_types = data_item.get("instance_types")
            for it in instance_types:
                self.assertIsNotNone(it.get("values"))
                self.assertGreater(len(it.get("values")), 0)
                for value in it.get("values"):
                    cost_value = value.get("cost", {}).get("total", {}).get("value")
                    self.assertIsNotNone(cost_value)
                    self.assertIsInstance(cost_value, Decimal)
                    self.assertGreaterEqual(cost_value.quantize(Decimal(".0001"), ROUND_HALF_UP), Decimal(0))
                    self.assertIsInstance(value.get("usage", {}), dict)
                    self.assertGreaterEqual(
                        value.get("usage", {}).get("value", {}).quantize(Decimal(".0001"), ROUND_HALF_UP), Decimal(0)
                    )

    def test_execute_query_annotate_instance_types(self):
        """Test that query enters cost unit and usage unit ."""
        with tenant_context(self.tenant):
            account = GCPCostEntryLineItemDailySummary.objects.filter(
                usage_start__gte=self.dh.this_month_start
            ).values("account_id")[0]
        url = f"?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&filter[account]={account}"  # noqa: E501
        query_params = self.mocked_query_params(url, GCPInstanceTypeView)
        handler = GCPReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get("total"))
        total = query_output.get("total")
        filters = {**self.this_month_filter, "account_id": account}
        current_totals = self.get_totals_costs_by_time_scope(handler, filters)
        expected_cost_total = current_totals.get("cost_total")
        self.assertIsNotNone(expected_cost_total)
        result_cost_total = total.get("cost", {}).get("total", {}).get("value")
        self.assertIsNotNone(result_cost_total)
        self.assertEqual(result_cost_total, expected_cost_total)

        cmonth_str = self.dh.this_month_start.strftime("%Y-%m")
        for data_item in data:
            month_val = data_item.get("date")
            self.assertEqual(month_val, cmonth_str)

    def test_execute_query_group_by_tag(self):
        """Test execute_query for current month on monthly breakdown by service."""
        with tenant_context(self.tenant):
            tag_object = GCPTagsSummary.objects.first()
            key = tag_object.key
            value = tag_object.values[0]
        url = f"?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&group_by[tag:{key}]={value}"  # noqa: E501
        query_params = self.mocked_query_params(url, GCPCostView)
        handler = GCPReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get("total"))

    def test_query_storage_with_totals(self):
        """Test execute_query() - storage with totals.

        Query for storage, validating that cost totals are present.
        """
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&group_by[service]=*"  # noqa: E501
        query_params = self.mocked_query_params(url, GCPStorageView)
        handler = GCPReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")
        self.assertIsNotNone(data)
        service_checked = False
        for data_item in data:
            services = data_item.get("services")
            self.assertIsNotNone(services)
            for srv in services:
                if srv.get("service") == "Cloud Storage":
                    self.assertIsNotNone(srv.get("values"))
                    self.assertGreater(len(srv.get("values")), 0)
                    for value in srv.get("values"):
                        cost_total = value.get("cost", {}).get("total", {}).get("value")
                        self.assertIsInstance(cost_total, Decimal)
                        self.assertNotEqual(cost_total, Decimal(0))
                        self.assertIsInstance(value.get("usage", {}).get("value"), Decimal)
                    service_checked = True
        self.assertTrue(service_checked)

    def test_gcp_date_order_by_cost_desc(self):
        """Test that order of every other date matches the order of the `order_by` date."""
        yesterday = self.dh.yesterday.date()
        url = f"?filter[limit]=10&filter[offset]=0&order_by[cost]=desc&order_by[date]={yesterday}&group_by[service]=*"
        query_params = self.mocked_query_params(url, GCPCostView)
        handler = GCPReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")
        svc_annotations = handler.annotations.get("service")
        exch_annotation = handler.annotations.get("exchange_rate")
        cost_annotation = handler.report_annotations.get("cost_total")
        with tenant_context(self.tenant):
            expected = list(
                GCPCostSummaryByServiceP.objects.filter(usage_start=str(yesterday))
                .annotate(service=svc_annotations, exchange_rate=exch_annotation)
                .values("service")
                .annotate(cost=cost_annotation)
                .order_by("-cost")
            )
        correctlst = [service.get("service") for service in expected]
        tested = False
        for element in data:
            lst = [service.get("service") for service in element.get("services", [])]
            if lst and correctlst:
                self.assertCountEqual(correctlst, lst)
                tested = True
        self.assertTrue(tested)

    def test_gcp_date_incorrect_date(self):
        wrong_date = "200BC"
        url = f"?order_by[cost]=desc&order_by[date]={wrong_date}&group_by[service]=*"
        with self.assertRaises(ValidationError):
            self.mocked_query_params(url, GCPCostView)

    def test_gcp_out_of_range_under_date(self):
        wrong_date = materialized_view_month_start() - timedelta(days=1)
        url = f"?order_by[cost]=desc&order_by[date]={wrong_date}&group_by[service]=*"
        with self.assertRaises(ValidationError):
            self.mocked_query_params(url, GCPCostView)

    def test_gcp_out_of_range_over_date(self):
        wrong_date = DateHelper().today.date() + timedelta(days=1)
        url = f"?order_by[cost]=desc&order_by[date]={wrong_date}&group_by[service]=*"
        with self.assertRaises(ValidationError):
            self.mocked_query_params(url, GCPCostView)

    def test_gcp_date_with_no_data(self):
        # This test will group by a date that is out of range for data generated.
        # The data will still return data because other dates will still generate data.
        yesterday = self.dh.yesterday.date()
        yesterday_month = self.dh.yesterday - relativedelta(months=2)

        url = f"?group_by[gcp_project]=*&order_by[cost]=desc&order_by[date]={yesterday_month.date()}&end_date={yesterday}&start_date={yesterday_month.date()}"  # noqa: E501
        query_params = self.mocked_query_params(url, GCPCostView)
        handler = GCPReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")
        self.assertIsNotNone(data)

    def test_exclude_functionality(self):
        """Test that the exclude feature works for all options."""
        exclude_opts = GCPExcludeSerializer._opfields
        for exclude_opt in exclude_opts:
            for view in [GCPCostView, GCPStorageView, GCPInstanceTypeView]:
                with self.subTest(exclude_opt):
                    overall_url = f"?group_by[{exclude_opt}]=*"
                    query_params = self.mocked_query_params(overall_url, view)
                    handler = GCPReportQueryHandler(query_params)
                    overall_output = handler.execute_query()
                    overall_total = handler.query_sum.get("cost", {}).get("total", {}).get("value")
                    opt_dict = overall_output.get("data", [{}])[0]
                    opt_dict = opt_dict.get(f"{exclude_opt}s")[0]
                    opt_value = opt_dict.get(exclude_opt)
                    # Grab filtered value
                    filtered_url = f"?group_by[{exclude_opt}]=*&filter[{exclude_opt}]={opt_value}"
                    query_params = self.mocked_query_params(filtered_url, view)
                    handler = GCPReportQueryHandler(query_params)
                    handler.execute_query()
                    filtered_total = handler.query_sum.get("cost", {}).get("total", {}).get("value")
                    expected_total = overall_total - filtered_total
                    # Test exclude
                    exclude_url = f"?group_by[{exclude_opt}]=*&exclude[{exclude_opt}]={opt_value}"
                    query_params = self.mocked_query_params(exclude_url, view)
                    handler = GCPReportQueryHandler(query_params)
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

    def test_exclude_tags(self):
        """Test that the exclude works for our tags."""
        query_params = self.mocked_query_params("?", GCPTagView)
        handler = GCPTagQueryHandler(query_params)
        tags = handler.get_tags()
        group_tag = None
        check_no_option = False
        exclude_vals = []
        for tag_dict in tags:
            if len(tag_dict.get("values")) > len(exclude_vals):
                group_tag = tag_dict.get("key")
                exclude_vals = tag_dict.get("values")
        url = f"?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=daily&group_by[tag:{group_tag}]=*"  # noqa: E501
        query_params = self.mocked_query_params(url, GCPCostView)
        handler = GCPReportQueryHandler(query_params)
        data = handler.execute_query().get("data")
        if f"No-{group_tag}" in str(data):
            check_no_option = True
        previous_total = handler.query_sum.get("cost", {}).get("total", {}).get("value")
        for exclude_value in exclude_vals:
            url += f"&exclude[tag:{group_tag}]={exclude_value}"
            query_params = self.mocked_query_params(url, GCPCostView)
            handler = GCPReportQueryHandler(query_params)
            data = handler.execute_query()
            if check_no_option:
                self.assertIn(f"No-{group_tag}", str(data))
            current_total = handler.query_sum.get("cost", {}).get("total", {}).get("value")
            self.assertLess(current_total, previous_total)
            previous_total = current_total

    def test_multi_exclude_functionality(self):
        """Test that the exclude feature works for all options."""
        exclude_opts = GCPExcludeSerializer._opfields
        for ex_opt in exclude_opts:
            base_url = f"?group_by[{ex_opt}]=*&filter[time_scope_units]=month&filter[resolution]=monthly&filter[time_scope_value]=-1"  # noqa: E501
            for view in [GCPCostView, GCPStorageView, GCPInstanceTypeView]:
                query_params = self.mocked_query_params(base_url, view)
                handler = GCPReportQueryHandler(query_params)
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
                    handler = GCPReportQueryHandler(query_params)
                    self.assertIsNotNone(handler.query_exclusions)
                    excluded_output = handler.execute_query()
                    excluded_data = excluded_output.get("data")
                    self.assertIsNotNone(excluded_data)
                    for date_dict in excluded_data:
                        grouping_list = date_dict.get(f"{ex_opt}s", [])
                        self.assertIsNotNone(grouping_list)
                        for group_dict in grouping_list:
                            self.assertNotIn(group_dict.get(ex_opt), [exclude_one, exclude_two])
