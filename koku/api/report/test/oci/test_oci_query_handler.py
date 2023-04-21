#
# Copyright 2022 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the OCI Provider query handler."""
from datetime import timedelta
from decimal import Decimal
from decimal import ROUND_HALF_UP
from unittest.mock import patch
from unittest.mock import PropertyMock
from uuid import UUID

from dateutil.relativedelta import relativedelta
from django.db.models import F
from django.db.models import Sum
from django_tenants.utils import tenant_context
from rest_framework.exceptions import ValidationError

from api.iam.test.iam_test_case import IamTestCase
from api.query_filter import QueryFilter
from api.report.oci.query_handler import OCIReportQueryHandler
from api.report.oci.serializers import OCIExcludeSerializer
from api.report.oci.view import OCICostView
from api.report.oci.view import OCIInstanceTypeView
from api.report.oci.view import OCIStorageView
from api.tags.oci.queries import OCITagQueryHandler
from api.tags.oci.view import OCITagView
from api.utils import DateHelper
from api.utils import materialized_view_month_start
from reporting.models import OCIComputeSummaryByAccountP
from reporting.models import OCIComputeSummaryP
from reporting.models import OCICostEntryBill
from reporting.models import OCICostEntryLineItemDailySummary
from reporting.models import OCICostSummaryByAccountP
from reporting.models import OCICostSummaryByServiceP
from reporting.models import OCICostSummaryP
from reporting.models import OCIDatabaseSummaryP
from reporting.models import OCINetworkSummaryP
from reporting.models import OCIStorageSummaryByAccountP
from reporting.models import OCIStorageSummaryP


class OCIReportQueryHandlerTest(IamTestCase):
    """OCI report view test cases."""

    def setUp(self):
        """Set up the customer view tests."""
        super().setUp()
        self.dh = DateHelper()
        self.this_month_filter = {"usage_start__gte": self.dh.this_month_start}
        self.ten_day_filter = {"usage_start__gte": self.dh.n_days_ago(self.dh.today, 9)}
        self.thirty_day_filter = {"usage_start__gte": self.dh.n_days_ago(self.dh.today, 29)}
        self.last_month_filter = {
            "usage_start__gte": self.dh.last_month_start,
            "usage_start__lte": self.dh.last_month_end,
        }
        with tenant_context(self.tenant):
            self.services = OCICostEntryLineItemDailySummary.objects.values("product_service").distinct()
            self.services = [entry.get("product_service") for entry in self.services]

    def get_totals_costs_by_time_scope(self, handler, filters=None):
        """Return the total costs aggregates for a time period."""
        if filters is None:
            filters = self.this_month_filter
        aggregates = handler._mapper.report_type_map.get("aggregates")
        with tenant_context(self.tenant):
            result = (
                OCICostEntryLineItemDailySummary.objects.filter(**filters)
                .annotate(**handler.annotations)
                .aggregate(**aggregates)
            )
            for key in result:
                if result[key] is None:
                    result[key] = Decimal(0)
            return result

    def test_execute_sum_query(self):
        """Test that the sum query runs properly."""
        url = "?"
        query_params = self.mocked_query_params(url, OCIInstanceTypeView)
        handler = OCIReportQueryHandler(query_params)

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

    def test_execute_sum_query_costs(self):
        """Test that the sum query runs properly for the costs endpoint."""
        url = "?"
        query_params = self.mocked_query_params(url, OCICostView)
        handler = OCIReportQueryHandler(query_params)
        current_totals = self.get_totals_costs_by_time_scope(handler, self.ten_day_filter)
        expected_cost_total = current_totals.get("cost_total")
        self.assertIsNotNone(expected_cost_total)
        query_output = handler.execute_query()
        self.assertIsNotNone(query_output.get("data"))
        self.assertIsNotNone(query_output.get("total"))
        result_cost_total = query_output.get("total").get("cost", {}).get("total", {}).get("value")
        self.assertIsNotNone(result_cost_total)
        self.assertEqual(result_cost_total, expected_cost_total)

    def test_execute_take_defaults(self):
        """Test execute_query for current month on daily breakdown."""
        url = "?"
        query_params = self.mocked_query_params(url, OCICostView)
        handler = OCIReportQueryHandler(query_params)
        query_output = handler.execute_query()
        self.assertIsNotNone(query_output.get("data"))
        self.assertIsNotNone(query_output.get("total"))
        total = query_output.get("total")
        self.assertIsNotNone(total.get("cost"))

    def test_execute_query_current_month_daily(self):
        """Test execute_query for current month on daily breakdown."""
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=daily"
        query_params = self.mocked_query_params(url, OCICostView)
        handler = OCIReportQueryHandler(query_params)
        query_output = handler.execute_query()
        self.assertIsNotNone(query_output.get("data"))
        self.assertIsNotNone(query_output.get("total"))
        total = query_output.get("total")
        current_totals = self.get_totals_costs_by_time_scope(handler, self.this_month_filter)
        expected_cost_total = current_totals.get("cost_total")
        self.assertIsNotNone(expected_cost_total)
        result_cost_total = total.get("cost", {}).get("total", {}).get("value")
        self.assertIsNotNone(result_cost_total)
        self.assertEqual(result_cost_total, expected_cost_total)

    def test_execute_query_current_month_monthly(self):
        """Test execute_query for current month on monthly breakdown."""
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=daily"
        query_params = self.mocked_query_params(url, OCICostView)
        handler = OCIReportQueryHandler(query_params)
        query_output = handler.execute_query()
        self.assertIsNotNone(query_output.get("data"))
        self.assertIsNotNone(query_output.get("total"))
        total = query_output.get("total")
        current_totals = self.get_totals_costs_by_time_scope(handler, self.this_month_filter)
        expected_cost_total = current_totals.get("cost_total")
        self.assertIsNotNone(expected_cost_total)
        result_cost_total = total.get("cost", {}).get("total", {}).get("value")
        self.assertIsNotNone(result_cost_total)
        self.assertEqual(result_cost_total, expected_cost_total)

    def test_execute_query_current_month_by_service(self):
        """Test execute_query for current month on monthly breakdown by service."""
        with tenant_context(self.tenant):
            valid_services = [
                service[0]
                for service in OCICostEntryLineItemDailySummary.objects.values_list("product_service").distinct()
            ]
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&group_by[product_service]=*"  # noqa: E501
        query_params = self.mocked_query_params(url, OCICostView)
        handler = OCIReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get("total"))
        total = query_output.get("total")
        current_totals = self.get_totals_costs_by_time_scope(handler, self.this_month_filter)
        expected_cost_total = current_totals.get("cost_total")
        self.assertIsNotNone(expected_cost_total)
        result_cost_total = total.get("cost", {}).get("total", {}).get("value")
        self.assertIsNotNone(result_cost_total)
        self.assertEqual(result_cost_total, expected_cost_total)

        cmonth_str = self.dh.this_month_start.strftime("%Y-%m")
        for data_item in data:
            month_val = data_item.get("date")
            month_data = data_item.get("product_services")
            self.assertEqual(month_val, cmonth_str)
            self.assertIsInstance(month_data, list)
            for month_item in month_data:
                name = month_item.get("product_service")
                self.assertIn(name, valid_services)
                self.assertIsInstance(month_item.get("values"), list)

    def test_execute_query_by_filtered_service(self):
        """Test execute_query monthly breakdown by filtered service."""
        with tenant_context(self.tenant):
            valid_services = [
                service[0]
                for service in OCICostEntryLineItemDailySummary.objects.values_list("product_service").distinct()
            ]
            service = valid_services[0]
        url = f"?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&group_by[product_service]={service}"  # noqa: E501
        query_params = self.mocked_query_params(url, OCICostView)
        handler = OCIReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get("total"))
        total = query_output.get("total")
        filters = {**self.this_month_filter, "product_service__icontains": service}
        for filt in handler._mapper.report_type_map.get("filter"):
            if filt:
                qf = QueryFilter(**filt)
                filters[qf.composed_query_string()] = qf.parameter
        current_totals = self.get_totals_costs_by_time_scope(handler, filters)
        expected_cost_total = current_totals.get("cost_total")
        self.assertIsNotNone(expected_cost_total)
        result_cost_total = total.get("cost", {}).get("total", {}).get("value")
        self.assertIsNotNone(result_cost_total)
        self.assertEqual(result_cost_total, expected_cost_total)

        cmonth_str = self.dh.this_month_start.strftime("%Y-%m")
        for data_item in data:
            month_val = data_item.get("date")
            month_data = data_item.get("product_services")
            self.assertEqual(month_val, cmonth_str)
            self.assertIsInstance(month_data, list)
            for month_item in month_data:
                name = month_item.get("product_service")
                self.assertIn(name, valid_services)
                self.assertIsInstance(month_item.get("values"), list)

    def test_query_by_partial_filtered_service(self):
        """Test execute_query monthly breakdown by filtered service."""
        with tenant_context(self.tenant):
            valid_services = [
                service[0]
                for service in OCICostEntryLineItemDailySummary.objects.values_list("product_service").distinct()
            ]
            service = valid_services[0]
        url = f"?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&group_by[product_service]={service}"  # noqa: E501
        query_params = self.mocked_query_params(url, OCICostView)
        handler = OCIReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get("total"))
        total = query_output.get("total")
        filters = {**self.this_month_filter, "product_service__icontains": service}
        for filt in handler._mapper.report_type_map.get("filter"):
            if filt:
                qf = QueryFilter(**filt)
                filters.update({qf.composed_query_string(): qf.parameter})
        current_totals = self.get_totals_costs_by_time_scope(handler, filters)
        expected_cost_total = current_totals.get("cost_total")
        self.assertIsNotNone(expected_cost_total)
        result_cost_total = total.get("cost", {}).get("total", {}).get("value")
        self.assertIsNotNone(result_cost_total)
        self.assertEqual(result_cost_total, expected_cost_total)

        cmonth_str = self.dh.this_month_start.strftime("%Y-%m")
        for data_item in data:
            month_val = data_item.get("date")
            month_data = data_item.get("product_services")
            self.assertEqual(month_val, cmonth_str)
            self.assertIsInstance(month_data, list)
            for month_item in month_data:
                name = month_item.get("product_service")
                self.assertIn(name, valid_services)
                self.assertIsInstance(month_item.get("values"), list)

    def test_execute_query_current_month_by_tenant(self):
        """Test execute_query for current month on monthly breakdown by tenant."""
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&group_by[payer_tenant_id]=*"  # noqa: E501
        query_params = self.mocked_query_params(url, OCICostView)
        handler = OCIReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get("total"))
        total = query_output.get("total")
        current_totals = self.get_totals_costs_by_time_scope(handler, self.this_month_filter)
        expected_cost_total = current_totals.get("cost_total")
        self.assertIsNotNone(expected_cost_total)
        result_cost_total = total.get("cost", {}).get("total", {}).get("value")
        self.assertIsNotNone(result_cost_total)
        self.assertEqual(result_cost_total, expected_cost_total)

        cmonth_str = self.dh.this_month_start.strftime("%Y-%m")
        for data_item in data:
            month_val = data_item.get("date")
            month_data = data_item.get("payer_tenant_ids")
            self.assertEqual(month_val, cmonth_str)
            self.assertIsInstance(month_data, list)
            for month_item in month_data:
                try:
                    UUID(month_item.get("payer_tenant_id"), version=4)
                except ValueError as exc:
                    self.fail(exc)
                self.assertIsInstance(month_item.get("values"), list)

    def test_execute_query_by_tenant_by_service(self):
        """Test execute_query for current month breakdown by tenant by service."""
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&group_by[payer_tenant_id]=*&group_by[product_service]=*"  # noqa: E501
        query_params = self.mocked_query_params(url, OCICostView)
        handler = OCIReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get("total"))
        total = query_output.get("total")
        current_totals = self.get_totals_costs_by_time_scope(handler, self.this_month_filter)
        expected_cost_total = current_totals.get("cost_total")
        self.assertIsNotNone(expected_cost_total)
        result_cost_total = total.get("cost", {}).get("total", {}).get("value")
        self.assertIsNotNone(result_cost_total)
        self.assertEqual(result_cost_total, expected_cost_total)

        cmonth_str = DateHelper().this_month_start.strftime("%Y-%m")
        for data_item in data:
            month_val = data_item.get("date")
            month_data = data_item.get("payer_tenant_ids")
            self.assertEqual(month_val, cmonth_str)
            self.assertIsInstance(month_data, list)
            for month_item in month_data:
                try:
                    UUID(month_item.get("payer_tenant_id"), version=4)
                except ValueError as exc:
                    self.fail(exc)
                self.assertIsInstance(month_item.get("product_services"), list)

    def test_execute_query_curr_month_by_tenant_w_limit(self):
        """Test execute_query for current month on monthly breakdown by tenant with limit."""
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&filter[limit]=2&group_by[payer_tenant_id]=*"  # noqa: E501
        query_params = self.mocked_query_params(url, OCICostView)
        handler = OCIReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get("total"))
        total = query_output.get("total")
        current_totals = self.get_totals_costs_by_time_scope(handler, self.this_month_filter)
        expected_cost_total = current_totals.get("cost_total")
        self.assertIsNotNone(expected_cost_total)
        result_cost_total = total.get("cost", {}).get("total", {}).get("value")
        self.assertIsNotNone(result_cost_total)
        self.assertEqual(result_cost_total, expected_cost_total)

        cmonth_str = DateHelper().this_month_start.strftime("%Y-%m")
        for data_item in data:
            month_val = data_item.get("date")
            month_data = data_item.get("payer_tenant_ids")
            self.assertEqual(month_val, cmonth_str)
            self.assertIsInstance(month_data, list)
            self.assertEqual(len(month_data), 1)
            for month_item in month_data:
                self.assertIsInstance(month_item.get("payer_tenant_id"), str)
                self.assertIsInstance(month_item.get("values"), list)

    def test_execute_query_curr_month_by_tenant_w_order(self):
        """Test execute_query for current month on monthly breakdown by tenant with asc order."""
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&order_by[cost]=asc&group_by[payer_tenant_id]=*"  # noqa: E501
        query_params = self.mocked_query_params(url, OCICostView)
        handler = OCIReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get("total"))
        total = query_output.get("total")
        current_totals = self.get_totals_costs_by_time_scope(handler, self.this_month_filter)
        expected_cost_total = current_totals.get("cost_total")
        self.assertIsNotNone(expected_cost_total)
        result_cost_total = total.get("cost", {}).get("total", {}).get("value")
        self.assertIsNotNone(result_cost_total)
        self.assertEqual(result_cost_total, expected_cost_total)

        cmonth_str = self.dh.this_month_start.strftime("%Y-%m")
        for data_item in data:
            month_val = data_item.get("date")
            month_data = data_item.get("payer_tenant_ids")
            self.assertEqual(month_val, cmonth_str)
            self.assertIsInstance(month_data, list)
            self.assertEqual(len(month_data), 1)
            current_total = 0
            for month_item in month_data:
                self.assertIsInstance(month_item.get("payer_tenant_id"), str)
                self.assertIsInstance(month_item.get("values"), list)
                data_point_total = month_item.get("values")[0].get("cost", {}).get("total", {}).get("value")
                self.assertIsNotNone(data_point_total)
                self.assertLess(current_total, data_point_total)
                current_total = data_point_total

    def test_execute_query_curr_month_by_tenant_w_order_by_tenant(self):
        """Test execute_query for current month on monthly breakdown by tenant with asc order."""
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&order_by[cost]=asc&group_by[payer_tenant_id]=*"  # noqa: E501
        query_params = self.mocked_query_params(url, OCICostView)
        handler = OCIReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get("total"))
        total = query_output.get("total")
        current_totals = self.get_totals_costs_by_time_scope(handler, self.this_month_filter)
        expected_cost_total = current_totals.get("cost_total")
        self.assertIsNotNone(expected_cost_total)
        result_cost_total = total.get("cost", {}).get("total", {}).get("value")
        self.assertIsNotNone(result_cost_total)
        self.assertEqual(result_cost_total, expected_cost_total)

        cmonth_str = self.dh.this_month_start.strftime("%Y-%m")
        for data_item in data:
            month_val = data_item.get("date")
            month_data = data_item.get("payer_tenant_ids")
            self.assertEqual(month_val, cmonth_str)
            self.assertIsInstance(month_data, list)
            self.assertEqual(len(month_data), 1)
            current = "0"
            for month_item in month_data:
                self.assertIsInstance(month_item.get("payer_tenant_id"), str)
                self.assertIsInstance(month_item.get("values"), list)
                self.assertIsNotNone(month_item.get("values")[0].get("payer_tenant_id"))
                data_point = month_item.get("values")[0].get("payer_tenant_id")
                if data_point == "1 Other":
                    continue
                self.assertLess(current, data_point)
                current = data_point

    def test_execute_query_curr_month_by_region(self):
        """Test execute_query for current month on monthly breakdown by region."""
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&group_by[region]=*"  # noqa: E501
        with tenant_context(self.tenant):
            location_count = (
                OCICostEntryLineItemDailySummary.objects.filter(usage_start__gte=self.dh.this_month_start)
                .values_list("region")
                .distinct()
                .count()
            )
        query_params = self.mocked_query_params(url, OCICostView)
        handler = OCIReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get("total"))
        total = query_output.get("total")
        current_totals = self.get_totals_costs_by_time_scope(handler, self.this_month_filter)
        expected_cost_total = current_totals.get("cost_total")
        self.assertIsNotNone(expected_cost_total)
        result_cost_total = total.get("cost", {}).get("total", {}).get("value")
        self.assertIsNotNone(result_cost_total)
        self.assertEqual(result_cost_total, expected_cost_total)

        cmonth_str = DateHelper().this_month_start.strftime("%Y-%m")
        for data_item in data:
            month_val = data_item.get("date")
            month_data = data_item.get("regions")
            self.assertEqual(month_val, cmonth_str)
            self.assertIsInstance(month_data, list)
            self.assertEqual(len(month_data), location_count)
            for month_item in month_data:
                self.assertIsInstance(month_item.get("region"), str)
                self.assertIsInstance(month_item.get("values"), list)
                self.assertIsNotNone(month_item.get("values")[0].get("cost"))

    def test_execute_query_curr_month_by_filtered_region(self):
        """Test execute_query for current month on monthly breakdown by filtered region."""
        with tenant_context(self.tenant):
            location = (
                OCICostEntryLineItemDailySummary.objects.filter(usage_start__gte=self.dh.this_month_start)
                .values("region")[0]
                .get("region")
            )
        url = f"?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&group_by[region]={location}"  # noqa: E501
        query_params = self.mocked_query_params(url, OCICostView)
        handler = OCIReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get("total"))
        total = query_output.get("total")
        filters = {**self.this_month_filter}
        filters["region__icontains"] = location
        current_totals = self.get_totals_costs_by_time_scope(handler, filters)
        expected_cost_total = current_totals.get("cost_total")
        self.assertIsNotNone(expected_cost_total)
        result_cost_total = total.get("cost", {}).get("total", {}).get("value")
        self.assertIsNotNone(result_cost_total)
        self.assertEqual(result_cost_total, expected_cost_total)

        cmonth_str = DateHelper().this_month_start.strftime("%Y-%m")
        for data_item in data:
            month_val = data_item.get("date")
            month_data = data_item.get("regions")
            self.assertEqual(month_val, cmonth_str)
            self.assertIsInstance(month_data, list)
            for month_item in month_data:
                self.assertIsInstance(month_item.get("region"), str)
                self.assertIsInstance(month_item.get("values"), list)
                self.assertIsNotNone(month_item.get("values")[0].get("cost"))

    def test_execute_query_current_month_filter_tenant(self):
        """Test execute_query for current month on monthly filtered by tenant."""
        with tenant_context(self.tenant):
            tenant = OCICostEntryLineItemDailySummary.objects.filter(usage_start__gte=self.dh.this_month_start).values(
                "payer_tenant_id"
            )[0]
        url = f"?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&filter[payer_tenant_id]={tenant}"  # noqa: E501
        query_params = self.mocked_query_params(url, OCICostView)
        handler = OCIReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get("total"))
        total = query_output.get("total")
        filters = {**self.this_month_filter, "payer_tenant_id": tenant}
        current_totals = self.get_totals_costs_by_time_scope(handler, filters)
        expected_cost_total = current_totals.get("cost_total")
        self.assertIsNotNone(expected_cost_total)
        result_cost_total = total.get("cost", {}).get("total", {}).get("value")
        self.assertIsNotNone(result_cost_total)
        self.assertEqual(result_cost_total, expected_cost_total)

        cmonth_str = self.dh.this_month_start.strftime("%Y-%m")
        for data_item in data:
            month_val = data_item.get("date")
            month_data = data_item.get("values")
            self.assertEqual(month_val, cmonth_str)
            self.assertIsInstance(month_data, list)

    def test_execute_query_current_month_filter_service(self):
        """Test execute_query for current month on monthly filtered by service."""
        with tenant_context(self.tenant):
            service = OCICostEntryLineItemDailySummary.objects.values("product_service")[0].get("product_service")
        url = f"?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&filter[product_service]={service}"  # noqa: E501
        query_params = self.mocked_query_params(url, OCICostView)
        handler = OCIReportQueryHandler(query_params)
        query_output = handler.execute_query()

        data = query_output.get("data")
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get("total"))

        total = query_output.get("total")
        filters = {**self.this_month_filter, "product_service__icontains": service}
        for filt in handler._mapper.report_type_map.get("filter"):
            if filt:
                qf = QueryFilter(**filt)
                filters.update({qf.composed_query_string(): qf.parameter})
        current_totals = self.get_totals_costs_by_time_scope(handler, filters)
        expected_cost_total = current_totals.get("cost_total")
        self.assertIsNotNone(expected_cost_total)
        result_cost_total = total.get("cost", {}).get("total", {}).get("value")
        self.assertIsNotNone(result_cost_total)
        self.assertEqual(result_cost_total, expected_cost_total)

        cmonth_str = self.dh.this_month_start.strftime("%Y-%m")
        for data_item in data:
            month_val = data_item.get("date")
            month_data = data_item.get("values")
            self.assertEqual(month_val, cmonth_str)
            self.assertIsInstance(month_data, list)

    def test_execute_query_current_month_filter_region(self):
        """Test execute_query for current month on monthly filtered by region."""
        with tenant_context(self.tenant):
            location = (
                OCICostEntryLineItemDailySummary.objects.filter(usage_start__gte=self.dh.this_month_start)
                .values("region")[0]
                .get("region")
            )
        url = f"?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&filter[region]={location}"  # noqa: E501
        query_params = self.mocked_query_params(url, OCICostView)
        handler = OCIReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get("total"))
        total = query_output.get("total")
        filters = {**self.this_month_filter}
        filters["region__icontains"] = location
        current_totals = self.get_totals_costs_by_time_scope(handler, filters)
        expected_cost_total = current_totals.get("cost_total")
        self.assertIsNotNone(expected_cost_total)
        result_cost_total = total.get("cost", {}).get("total", {}).get("value")
        self.assertIsNotNone(result_cost_total)
        self.assertEqual(result_cost_total, expected_cost_total)

        cmonth_str = DateHelper().this_month_start.strftime("%Y-%m")
        for data_item in data:
            month_val = data_item.get("date")
            month_data = data_item.get("values")
            self.assertEqual(month_val, cmonth_str)
            self.assertIsInstance(month_data, list)

    def test_execute_query_current_month_exclude_service(self):
        """Test execute_query for current month on monthly excluded by service."""
        with tenant_context(self.tenant):
            service = OCICostEntryLineItemDailySummary.objects.values("product_service")[0].get("product_service")
        url = f"?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&exclude[product_service]={service}"  # noqa: E501
        query_params = self.mocked_query_params(url, OCICostView)
        handler = OCIReportQueryHandler(query_params)
        query_output = handler.execute_query()

        data = query_output.get("data")
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get("total"))

        total = query_output.get("total")
        result_cost_total = total.get("cost", {}).get("total", {}).get("value")
        self.assertIsNotNone(result_cost_total)

    @patch("api.query_params.QueryParameters.accept_type", new_callable=PropertyMock)
    def test_execute_query_current_month_filter_region_csv(self, mock_accept):
        """Test execute_query on monthly filtered by region for csv."""
        with tenant_context(self.tenant):
            location = (
                OCICostEntryLineItemDailySummary.objects.filter(usage_start__gte=self.dh.this_month_start)
                .values("region")[0]
                .get("region")
            )
        mock_accept.return_value = "text/csv"
        url = f"?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&filter[region]={location}"  # noqa: E501
        query_params = self.mocked_query_params(url, OCICostView)
        handler = OCIReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get("total"))
        total = query_output.get("total")
        filters = {**self.this_month_filter}
        filters["region__icontains"] = location
        current_totals = self.get_totals_costs_by_time_scope(handler, filters)
        expected_cost_total = current_totals.get("cost_total")
        self.assertIsNotNone(expected_cost_total)
        result_cost_total = total.get("cost", {}).get("total", {}).get("value")
        self.assertIsNotNone(result_cost_total)
        self.assertEqual(result_cost_total, expected_cost_total)

        cmonth_str = DateHelper().this_month_start.strftime("%Y-%m")
        self.assertEqual(len(data), 1)
        for data_item in data:
            month_val = data_item.get("date")
            self.assertEqual(month_val, cmonth_str)

    @patch("api.query_params.QueryParameters.accept_type", new_callable=PropertyMock)
    def test_execute_query_curr_month_by_tenant_w_limit_csv(self, mock_accept):
        """Test execute_query for current month on monthly by tenant with limt as csv."""
        mock_accept.return_value = "text/csv"

        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&filter[limit]=2&group_by[payer_tenant_id]=*"  # noqa: E501
        query_params = self.mocked_query_params(url, OCICostView)
        handler = OCIReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")

        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get("total"))
        total = query_output.get("total")
        current_totals = self.get_totals_costs_by_time_scope(handler, self.this_month_filter)
        expected_cost_total = current_totals.get("cost_total")
        self.assertIsNotNone(expected_cost_total)
        result_cost_total = total.get("cost", {}).get("total", {}).get("value")
        self.assertIsNotNone(result_cost_total)
        self.assertEqual(result_cost_total, expected_cost_total)

        cmonth_str = self.dh.this_month_start.strftime("%Y-%m")
        self.assertEqual(len(data), 1)
        for data_item in data:
            month = data_item.get("date")
            self.assertEqual(month, cmonth_str)

    def test_calculate_total(self):
        """Test that calculated totals return correctly."""
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly"
        query_params = self.mocked_query_params(url, OCICostView)
        handler = OCIReportQueryHandler(query_params)
        expected_units = "USD"
        with tenant_context(self.tenant):
            result = handler.calculate_total(**{"cost_units": expected_units})

        current_totals = self.get_totals_costs_by_time_scope(handler, self.this_month_filter)
        cost_total = result.get("cost", {}).get("total")
        self.assertIsNotNone(cost_total)
        self.assertEqual(cost_total.get("value"), current_totals.get("cost_total"))
        self.assertEqual(cost_total.get("units"), expected_units)

    def test_percent_delta(self):
        """Test _percent_delta() utility method."""
        url = "?"
        query_params = self.mocked_query_params(url, OCICostView)
        handler = OCIReportQueryHandler(query_params)
        self.assertEqual(handler._percent_delta(10, 5), 100)

    def test_rank_list_by_tenant(self):
        """Test rank list limit with tenant alias."""
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&filter[limit]=2&group_by[payer_tenant_id]=*"  # noqa: E501
        query_params = self.mocked_query_params(url, OCICostView)
        handler = OCIReportQueryHandler(query_params)
        ranks = [
            {"payer_tenant_id": "1", "rank": 1, "source_uuid": ["1"]},
            {"payer_tenant_id": "2", "rank": 2, "source_uuid": ["1"]},
            {"payer_tenant_id": "3", "rank": 3, "source_uuid": ["1"]},
            {"payer_tenant_id": "4", "rank": 4, "source_uuid": ["1"]},
        ]

        data_list = [
            {
                "payer_tenant_id": "1",
                "date": "2022-05",
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
                "payer_tenant_id": "2",
                "date": "2022-05",
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
                "payer_tenant_id": "3",
                "date": "2022-05",
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
                "payer_tenant_id": "4",
                "date": "2022-05",
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
                "payer_tenant_id": "1",
                "rank": 1,
                "date": "2022-05",
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
                "payer_tenant_id": "2",
                "rank": 2,
                "date": "2022-05",
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
                "payer_tenant_id": "Others",
                "rank": 3,
                "date": "2022-05",
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

    def test_rank_list_by_product_service(self):
        """Test rank list limit with product_service grouping."""
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&filter[limit]=2&group_by[product_service]=*"  # noqa: E501
        query_params = self.mocked_query_params(url, OCICostView)
        handler = OCIReportQueryHandler(query_params)
        ranks = [
            {"product_service": "1", "rank": 1, "source_uuid": ["1"]},
            {"product_service": "2", "rank": 2, "source_uuid": ["1"]},
            {"product_service": "3", "rank": 3, "source_uuid": ["1"]},
            {"product_service": "4", "rank": 4, "source_uuid": ["1"]},
        ]
        data_list = [
            {
                "product_service": "1",
                "date": "2022-05",
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
                "product_service": "2",
                "date": "2022-05",
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
                "product_service": "3",
                "date": "2022-05",
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
                "product_service": "4",
                "date": "2022-05",
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
                "product_service": "1",
                "rank": 1,
                "date": "2022-05",
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
                "product_service": "2",
                "rank": 2,
                "date": "2022-05",
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
                "product_service": "Others",
                "rank": 3,
                "date": "2022-05",
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
        """Test rank list limit and offset with tenant alias."""
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&filter[limit]=1&filter[offset]=1&group_by[payer_tenant_id]=*"  # noqa: E501
        query_params = self.mocked_query_params(url, OCICostView)
        handler = OCIReportQueryHandler(query_params)
        ranks = [
            {"payer_tenant_id": "1", "rank": 1, "source_uuid": ["1"]},
            {"payer_tenant_id": "2", "rank": 2, "source_uuid": ["1"]},
            {"payer_tenant_id": "3", "rank": 3, "source_uuid": ["1"]},
            {"payer_tenant_id": "4", "rank": 4, "source_uuid": ["1"]},
        ]

        data_list = [
            {
                "payer_tenant_id": "1",
                "date": "2022-05",
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
                "payer_tenant_id": "2",
                "date": "2022-05",
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
                "payer_tenant_id": "3",
                "date": "2022-05",
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
                "payer_tenant_id": "4",
                "date": "2022-05",
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
                "payer_tenant_id": "2",
                "date": "2022-05",
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
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&group_by[payer_tenant_id]=*"  # noqa: E501
        query_params = self.mocked_query_params(url, OCICostView)
        handler = OCIReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")
        self.assertIsNotNone(data)

        for data_item in data:
            tenants = data_item.get("payer_tenant_ids")
            for tenant in tenants:
                self.assertIsNotNone(tenant.get("values"))
                self.assertGreater(len(tenant.get("values")), 0)
                for value in tenant.get("values"):
                    cost_total_value = value.get("cost", {}).get("total", {}).get("value")
                    self.assertIsInstance(cost_total_value, Decimal)
                    self.assertGreater(cost_total_value, Decimal(0))

    def test_query_instance_types_with_totals(self):
        """Test execute_query() - instance types with totals.

        Query for instance_types, validating that cost totals are present.

        """
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&group_by[instance_type]=*"  # noqa: E501
        query_params = self.mocked_query_params(url, OCIInstanceTypeView)
        handler = OCIReportQueryHandler(query_params)
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
                    # FIXME: usage doesn't have units yet. waiting on MSFT
                    # self.assertIsInstance(value.get('usage', {}).get('value'), Decimal)
                    # self.assertGreater(value.get('usage', {}).get('value'), Decimal(0))
                    self.assertIsInstance(value.get("usage", {}), dict)
                    self.assertGreaterEqual(
                        value.get("usage", {}).get("value", {}).quantize(Decimal(".0001"), ROUND_HALF_UP), Decimal(0)
                    )

    def test_query_storage_with_totals(self):
        """Test execute_query() - storage with totals.

        Query for storage, validating that cost totals are present.

        """
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&group_by[product_service]=*"  # noqa: E501
        query_params = self.mocked_query_params(url, OCIStorageView)
        handler = OCIReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")
        self.assertIsNotNone(data)

        for data_item in data:
            services = data_item.get("product_services")
            self.assertIsNotNone(services)
            for srv in services:
                self.assertIsNotNone(srv.get("values"))
                self.assertGreater(len(srv.get("values")), 0)
                for value in srv.get("values"):
                    cost_value = value.get("cost", {}).get("total", {}).get("value")
                    self.assertIsNotNone(cost_value)
                    self.assertIsInstance(cost_value, Decimal)
                    self.assertGreater(cost_value, Decimal(0))
                    # FIXME: usage doesn't have units yet. waiting on MSFT
                    # self.assertIsInstance(value.get('usage', {}).get('value'), Decimal)
                    # self.assertGreater(value.get('usage', {}).get('value'), Decimal(0))
                    self.assertIsInstance(value.get("usage", {}), dict)
                    self.assertGreater(value.get("usage", {}).get("value", {}), Decimal(0))
                    self.assertIsNone(value.get("count"))

    def test_order_by(self):
        """Test that order_by returns properly sorted data."""
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly"
        query_params = self.mocked_query_params(url, OCICostView)
        handler = OCIReportQueryHandler(query_params)

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

    def test_order_by_null_values(self):
        """Test that order_by returns properly sorted data with null data."""
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly"
        query_params = self.mocked_query_params(url, OCICostView)
        handler = OCIReportQueryHandler(query_params)

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

    def test_execute_query_with_tag_filter(self):
        """Test that data is filtered by tag key."""
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly"
        query_params = self.mocked_query_params(url, OCITagView)
        handler = OCITagQueryHandler(query_params)
        tag_keys = handler.get_tag_keys()
        filter_key = tag_keys[0]
        tag_keys = ["tag:" + tag for tag in tag_keys]

        ag_key = "cost_total"
        with tenant_context(self.tenant):
            labels = (
                OCICostEntryLineItemDailySummary.objects.filter(usage_start__gte=self.dh.this_month_start)
                .filter(tags__has_key=filter_key)
                .values(*["tags"])
                .all()
            )
            label_of_interest = labels[0]
            filter_value = label_of_interest.get("tags", {}).get(filter_key)

            totals = (
                OCICostEntryLineItemDailySummary.objects.filter(usage_start__gte=self.dh.this_month_start)
                .filter(**{f"tags__{filter_key}": filter_value})
                .aggregate(**{ag_key: Sum(F("markup_cost") + F("cost"))})
            )

        url = f"?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&filter[tag:{filter_key}]={filter_value}"  # noqa: E501
        query_params = self.mocked_query_params(url, OCICostView)
        handler = OCIReportQueryHandler(query_params)

        data = handler.execute_query()
        data_totals = data.get("total", {})
        result = data_totals.get("cost", {}).get("total")
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result.get("value"), totals[ag_key], 6)

    def test_execute_query_with_wildcard_tag_filter(self):
        """Test that data is filtered to include entries with tag key."""
        # Pick tags for the same month we query on later
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly"
        query_params = self.mocked_query_params(url, OCITagView)
        handler = OCITagQueryHandler(query_params)
        tag_keys = handler.get_tag_keys()
        filter_key = tag_keys[0]
        tag_keys = ["tag:" + tag for tag in tag_keys]

        ag_key = "cost_total"
        with tenant_context(self.tenant):
            totals = OCICostEntryLineItemDailySummary.objects.filter(
                usage_start__gte=self.dh.this_month_start, tags__has_key=filter_key
            ).aggregate(**{ag_key: Sum(F("markup_cost") + F("cost"))})

        url = f"?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&filter[tag:{filter_key}]=*"  # noqa: E501
        query_params = self.mocked_query_params(url, OCICostView)
        handler = OCIReportQueryHandler(query_params)

        data = handler.execute_query()
        data_totals = data.get("total", {})
        result = data_totals.get("cost", {}).get("total")
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result.get("value"), totals[ag_key], 6)

    def test_execute_query_with_tag_group_by(self):
        """Test that data is grouped by tag key."""
        # Pick tags for the same month we query on later
        url = "filter[resolution]=monthly&filter[time_scope_value]=-1&filter[time_scope_units]=month"
        query_params = self.mocked_query_params(url, OCITagView)
        handler = OCITagQueryHandler(query_params)
        tag_keys = handler.get_tag_keys()
        group_by_key = tag_keys[0]
        tag_keys = ["tag:" + tag for tag in tag_keys]

        ag_key = "cost_total"
        with tenant_context(self.tenant):
            totals = OCICostEntryLineItemDailySummary.objects.filter(
                usage_start__gte=self.dh.this_month_start
            ).aggregate(**{ag_key: Sum(F("markup_cost") + F("cost"))})

        url = f"?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&group_by[tag:{group_by_key}]=*"  # noqa: E501
        query_params = self.mocked_query_params(url, OCICostView)
        handler = OCIReportQueryHandler(query_params)

        data = handler.execute_query()
        data_totals = data.get("total", {})
        data = data.get("data", [])
        expected_keys = ["date", group_by_key + "s"]
        for entry in data:
            self.assertEqual(list(entry.keys()), expected_keys)
        result = data_totals.get("cost", {}).get("total")
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result.get("value"), totals[ag_key], 6)

    def test_query_table(self):
        """Test that the correct view is assigned by query table property."""
        test_cases = [
            ("?", OCICostView, OCICostSummaryP),
            ("?group_by[payer_tenant_id]=*", OCICostView, OCICostSummaryByAccountP),
            ("?group_by[product_service]=*", OCICostView, OCICostSummaryByServiceP),
            ("?group_by[product_service]=*&group_by[payer_tenant_id]=*", OCICostView, OCICostSummaryByServiceP),
            ("?", OCIInstanceTypeView, OCIComputeSummaryP),
            ("?group_by[payer_tenant_id]=*", OCIInstanceTypeView, OCIComputeSummaryByAccountP),
            ("?", OCIStorageView, OCIStorageSummaryP),
            ("?group_by[payer_tenant_id]=*", OCIStorageView, OCIStorageSummaryByAccountP),
            ("?filter[product_service]=Autonomous Database", OCICostView, OCIDatabaseSummaryP),
            (
                "?filter[product_service]=Autonomous Database&group_by[payer_tenant_id]=*",
                OCICostView,
                OCIDatabaseSummaryP,
            ),
            (
                "?filter[product_service]=Networking Gateways",  # noqa: E501
                OCICostView,
                OCINetworkSummaryP,
            ),
            (
                "?filter[product_service]=Networking Gateways&group_by[payer_tenant_id]=*",  # noqa: E501
                OCICostView,
                OCINetworkSummaryP,
            ),
        ]

        for test_case in test_cases:
            with self.subTest(test_case=test_case):
                url, view, table = test_case
                query_params = self.mocked_query_params(url, view)
                handler = OCIReportQueryHandler(query_params)
                self.assertEqual(handler.query_table, table)

    def test_source_uuid_mapping(self):  # noqa: C901
        """Test source_uuid is mapped to the correct source."""
        # Find the correct expected source uuid:
        with tenant_context(self.tenant):
            oci_uuids = OCICostEntryLineItemDailySummary.objects.distinct().values_list("source_uuid", flat=True)
            expected_source_uuids = OCICostEntryBill.objects.distinct().values_list("provider_id", flat=True)
            for oci_uuid in oci_uuids:
                self.assertIn(oci_uuid, expected_source_uuids)
        endpoints = [OCICostView, OCIInstanceTypeView, OCIStorageView]
        source_uuid_list = []
        for endpoint in endpoints:
            urls = ["?"]
            if endpoint == OCICostView:
                urls.extend(["?group_by[region]=*", "group_by[product_service]=*"])
            for url in urls:
                query_params = self.mocked_query_params(url, endpoint)
                handler = OCIReportQueryHandler(query_params)
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
            tenant = OCICostEntryLineItemDailySummary.objects.filter(usage_start__gte=self.dh.this_month_start).values(
                "payer_tenant_id"
            )[0]
        url = f"?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&filter[payer_tenant_id]={tenant}"  # noqa: E501
        query_params = self.mocked_query_params(url, OCIInstanceTypeView)
        handler = OCIReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get("total"))
        total = query_output.get("total")
        filters = {**self.this_month_filter, "payer_tenant_id": tenant}
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

    def test_oci_date_order_by_cost_desc(self):
        """Test that order of every other date matches the order of the `order_by` date."""
        # execute query
        yesterday = self.dh.yesterday.date()
        url = f"?filter[limit]=10&filter[offset]=0&order_by[cost]=desc&order_by[date]={yesterday}&group_by[product_service]=*"  # noqa: E501
        query_params = self.mocked_query_params(url, OCICostView)
        handler = OCIReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")

        exch_annotation = handler.annotations.get("exchange_rate")
        cost_annotation = handler.report_annotations.get("cost_total")
        with tenant_context(self.tenant):
            expected = list(
                OCICostSummaryByServiceP.objects.filter(usage_start=str(yesterday))
                .annotate(exchange_rate=exch_annotation)
                .values("product_service")
                .annotate(cost=cost_annotation)
                .order_by("-cost")
            )

        ranking_map = {}
        count = 1
        tested = False
        for service in expected:
            ranking_map[service.get("product_service")] = count
            count += 1
        for element in data:
            previous = 0
            for service in element.get("product_services"):
                product_service = service.get("product_service")
                # This if is cause some days may not have same services.
                # however we want the services that do match to be in the
                # same order
                if product_service in ranking_map.keys():
                    self.assertGreaterEqual(ranking_map[product_service], previous)
                    previous = ranking_map[product_service]
                    tested = True
        self.assertTrue(tested)

    def test_oci_date_incorrect_date(self):
        wrong_date = "200BC"
        url = f"?order_by[cost]=desc&order_by[date]={wrong_date}&group_by[product_service]=*"
        with self.assertRaises(ValidationError):
            self.mocked_query_params(url, OCICostView)

    def test_oci_out_of_range_under_date(self):
        wrong_date = materialized_view_month_start() - timedelta(days=1)
        url = f"?order_by[cost]=desc&order_by[date]={wrong_date}&group_by[product_service]=*"
        with self.assertRaises(ValidationError):
            self.mocked_query_params(url, OCICostView)

    def test_oci_out_of_range_over_date(self):
        wrong_date = DateHelper().today.date() + timedelta(days=1)
        url = f"?order_by[cost]=desc&order_by[date]={wrong_date}&group_by[product_service]=*"
        with self.assertRaises(ValidationError):
            self.mocked_query_params(url, OCICostView)

    def test_oci_date_with_no_data(self):
        # This test will group by a date that is out of range for data generated.
        # The data will still return data because other dates will still generate data.
        yesterday = DateHelper().today.date()
        yesterday_month = yesterday - relativedelta(months=2)

        url = f"?group_by[product_service]=*&order_by[cost]=desc&order_by[date]={yesterday_month}&end_date={yesterday}&start_date={yesterday_month}"  # noqa: E501
        query_params = self.mocked_query_params(url, OCICostView)
        handler = OCIReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")
        self.assertIsNotNone(data)

    @patch("api.query_params.enable_negative_filtering", return_value=True)
    def test_exclude_functionality(self, *args):
        """Test that the exclude feature works for all options."""
        exclude_opts = OCIExcludeSerializer._opfields
        for exclude_opt in exclude_opts:
            for view in [OCICostView, OCIStorageView, OCIInstanceTypeView]:
                with self.subTest(exclude_opt):
                    overall_url = f"?group_by[{exclude_opt}]=*"
                    query_params = self.mocked_query_params(overall_url, view)
                    handler = OCIReportQueryHandler(query_params)
                    overall_output = handler.execute_query()
                    overall_total = handler.query_sum.get("cost", {}).get("total", {}).get("value")
                    opt_dict = overall_output.get("data", [{}])[0]
                    if not opt_dict.get(f"{exclude_opt}s"):
                        # TODO: figure out why this sometimes returns none
                        continue
                    opt_dict = opt_dict.get(f"{exclude_opt}s")[0]
                    opt_value = opt_dict.get(exclude_opt, "")
                    if opt_value.startswith("No-"):
                        # Hanlde cases where "No-instance-type" is returned
                        continue
                    # Grab filtered value
                    filtered_url = f"?group_by[{exclude_opt}]=*&filter[{exclude_opt}]={opt_value}"
                    query_params = self.mocked_query_params(filtered_url, view)
                    handler = OCIReportQueryHandler(query_params)
                    handler.execute_query()
                    filtered_total = handler.query_sum.get("cost", {}).get("total", {}).get("value")
                    expected_total = overall_total - filtered_total
                    # Test exclude
                    exclude_url = f"?group_by[{exclude_opt}]=*&exclude[{exclude_opt}]={opt_value}"
                    query_params = self.mocked_query_params(exclude_url, view)
                    handler = OCIReportQueryHandler(query_params)
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
    def test_exclude_tags(self, _):
        """Test that the exclude works for our tags."""
        query_params = self.mocked_query_params("?", OCITagView)
        handler = OCITagQueryHandler(query_params)
        tags = handler.get_tags()
        group_tag = None
        check_no_option = False
        exclude_vals = []
        for tag_dict in tags:
            if len(tag_dict.get("values")) > len(exclude_vals):
                group_tag = tag_dict.get("key")
                exclude_vals = tag_dict.get("values")
        url = f"?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=daily&group_by[tag:{group_tag}]=*"  # noqa: E501
        query_params = self.mocked_query_params(url, OCICostView)
        handler = OCIReportQueryHandler(query_params)
        data = handler.execute_query().get("data")
        if f"No-{group_tag}" in str(data):
            check_no_option = True
        previous_total = handler.query_sum.get("cost", {}).get("total", {}).get("value")
        for exclude_value in exclude_vals:
            url += f"&exclude[tag:{group_tag}]={exclude_value}"
            query_params = self.mocked_query_params(url, OCICostView)
            handler = OCIReportQueryHandler(query_params)
            url = handler.execute_query()
            if check_no_option:
                self.assertIn(f"No-{group_tag}", str(data))
            current_total = handler.query_sum.get("cost", {}).get("total", {}).get("value")
            self.assertLess(current_total, previous_total)
            previous_total = current_total

    @patch("api.query_params.enable_negative_filtering", return_value=True)
    def test_multi_exclude_functionality(self, *args):
        """Test that the exclude feature works for all options."""
        exclude_opts = OCIExcludeSerializer._opfields
        for ex_opt in exclude_opts:
            base_url = f"?group_by[{ex_opt}]=*&filter[time_scope_units]=month&filter[resolution]=monthly&filter[time_scope_value]=-1"  # noqa: E501
            for view in [OCICostView, OCIStorageView, OCIInstanceTypeView]:
                query_params = self.mocked_query_params(base_url, view)
                handler = OCIReportQueryHandler(query_params)
                overall_output = handler.execute_query()
                opt_dict = overall_output.get("data", [{}])[0]
                opt_list = opt_dict.get(f"{ex_opt}s", [])
                exclude_one = None
                exclude_two = None
                for exclude_option in opt_list:
                    _exclude_option = exclude_option.get(ex_opt, "")
                    if not _exclude_option.startswith("No-"):
                        if not exclude_one:
                            exclude_one = _exclude_option
                        elif not exclude_two:
                            exclude_two = _exclude_option
                        else:
                            continue
                if not exclude_one or not exclude_two:
                    continue
                url = base_url + f"&exclude[or:{ex_opt}]={exclude_one}&exclude[or:{ex_opt}]={exclude_two}"
                with self.subTest(url=url, view=view, ex_opt=ex_opt):
                    query_params = self.mocked_query_params(url, view)
                    handler = OCIReportQueryHandler(query_params)
                    self.assertIsNotNone(handler.query_exclusions)
                    excluded_output = handler.execute_query()
                    excluded_data = excluded_output.get("data")
                    self.assertIsNotNone(excluded_data)
                    for date_dict in excluded_data:
                        grouping_list = date_dict.get(f"{ex_opt}s", [])
                        self.assertIsNotNone(grouping_list)
                        for group_dict in grouping_list:
                            self.assertNotIn(group_dict.get(ex_opt), [exclude_one, exclude_two])
