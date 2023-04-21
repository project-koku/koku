#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the Report Queries."""
from datetime import datetime
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
from api.models import Provider
from api.query_filter import QueryFilter
from api.report.azure.openshift.query_handler import OCPAzureReportQueryHandler
from api.report.azure.openshift.serializers import OCPAzureExcludeSerializer
from api.report.azure.openshift.view import OCPAzureCostView
from api.report.azure.openshift.view import OCPAzureInstanceTypeView
from api.report.azure.openshift.view import OCPAzureStorageView
from api.report.test.util.constants import AZURE_SERVICE_NAMES
from api.tags.azure.openshift.queries import OCPAzureTagQueryHandler
from api.tags.azure.openshift.view import OCPAzureTagView
from api.utils import DateHelper
from api.utils import materialized_view_month_start
from reporting.models import AzureCostEntryBill
from reporting.models import OCPAzureComputeSummaryP
from reporting.models import OCPAzureCostLineItemProjectDailySummaryP
from reporting.models import OCPAzureCostSummaryByAccountP
from reporting.models import OCPAzureCostSummaryByLocationP
from reporting.models import OCPAzureCostSummaryByServiceP
from reporting.models import OCPAzureCostSummaryP
from reporting.models import OCPAzureDatabaseSummaryP
from reporting.models import OCPAzureNetworkSummaryP
from reporting.models import OCPAzureStorageSummaryP


class OCPAzureQueryHandlerTestNoData(IamTestCase):
    """Tests for the OCP report query handler with no data."""

    def setUp(self):
        """Set up the customer view tests."""
        super().setUp()
        self.dh = DateHelper()

        self.this_month_filter = {"usage_start__gte": self.dh.this_month_start.date()}
        self.ten_day_filter = {"usage_start__gte": self.dh.n_days_ago(self.dh.today, 9).date()}
        self.thirty_day_filter = {"usage_start__gte": self.dh.n_days_ago(self.dh.today, 29).date()}
        self.last_month_filter = {
            "usage_start__gte": self.dh.last_month_start.date(),
            "usage_end__lte": self.dh.last_month_end.date(),
        }


class OCPAzureQueryHandlerTest(IamTestCase):
    """Tests for the OCP report query handler."""

    def setUp(self):
        """Set up the customer view tests."""
        super().setUp()
        self.dh = DateHelper()

        # Use one of the test-runner created providers
        self.provider = Provider.objects.filter(type=Provider.PROVIDER_OCP).first()

        self.this_month_filter = {"usage_start__gte": self.dh.this_month_start}
        self.ten_day_filter = {"usage_start__gte": self.dh.n_days_ago(self.dh.today, 9)}
        self.thirty_day_filter = {"usage_start__gte": self.dh.n_days_ago(self.dh.today, 29)}
        self.last_month_filter = {
            "usage_start__gte": self.dh.last_month_start,
            "usage_end__lte": self.dh.last_month_end,
        }
        with tenant_context(self.tenant):
            self.services = OCPAzureCostLineItemProjectDailySummaryP.objects.values("service_name").distinct()
            self.services = [entry.get("service_name") for entry in self.services]

    def get_totals_by_time_scope(self, handler, filters=None):
        if filters is None:
            filters = self.ten_day_filter
        aggregates = handler._mapper.report_type_map.get("aggregates")
        with tenant_context(self.tenant):
            return (
                OCPAzureCostLineItemProjectDailySummaryP.objects.filter(**filters)
                .annotate(**handler.annotations)
                .aggregate(**aggregates)
            )

    def test_execute_sum_query_storage(self):
        """Test that the sum query runs properly."""
        url = "?"
        query_params = self.mocked_query_params(url, OCPAzureStorageView)
        handler = OCPAzureReportQueryHandler(query_params)
        query_output = handler.execute_query()
        self.assertIsNotNone(query_output.get("data"))
        self.assertIsNotNone(query_output.get("total"))

        filt = {"service_name__contains": "Storage", "unit_of_measure__exact": "GB-Mo"}
        filt.update(self.ten_day_filter)
        current_totals = self.get_totals_by_time_scope(handler, filt)
        total = query_output.get("total")
        self.assertEqual(total.get("cost", {}).get("total", {}).get("value", 0), current_totals.get("cost_total", 1))

    def test_execute_sum_query_instance_types(self):
        """Test that the sum query runs properly."""
        url = "?"
        query_params = self.mocked_query_params(url, OCPAzureInstanceTypeView)
        handler = OCPAzureReportQueryHandler(query_params)
        query_output = handler.execute_query()
        self.assertIsNotNone(query_output.get("data"))
        self.assertIsNotNone(query_output.get("total"))

        filters = {**self.ten_day_filter, "instance_type__isnull": False, "unit_of_measure__exact": "Hrs"}
        current_totals = self.get_totals_by_time_scope(handler, filters)
        total = query_output.get("total")
        self.assertEqual(total.get("cost", {}).get("total", {}).get("value", 0), current_totals.get("cost_total", 1))

    def test_execute_query_current_month_daily(self):
        """Test execute_query for current month on daily breakdown."""
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=daily"
        query_params = self.mocked_query_params(url, OCPAzureCostView)
        handler = OCPAzureReportQueryHandler(query_params)
        query_output = handler.execute_query()
        self.assertIsNotNone(query_output.get("data"))
        self.assertIsNotNone(query_output.get("total"))
        total = query_output.get("total")
        self.assertIsNotNone(total.get("cost"))

        current_totals = self.get_totals_by_time_scope(handler, self.this_month_filter)
        self.assertEqual(total.get("cost", {}).get("total", {}).get("value", 0), current_totals.get("cost_total", 1))

    def test_execute_query_current_month_by_account(self):
        """Test execute_query for current month on monthly breakdown by account."""
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&group_by[subscription_guid]=*"  # noqa: E501
        query_params = self.mocked_query_params(url, OCPAzureCostView)
        handler = OCPAzureReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get("total"))
        total = query_output.get("total")
        self.assertIsNotNone(total.get("cost"))

        current_totals = self.get_totals_by_time_scope(handler, self.this_month_filter)
        self.assertEqual(total.get("cost", {}).get("total", {}).get("value", 0), current_totals.get("cost_total", 1))

        cmonth_str = DateHelper().this_month_start.strftime("%Y-%m")
        for data_item in data:
            month_val = data_item.get("date", "not-a-date")
            month_data = data_item.get("subscription_guids")
            self.assertEqual(month_val, cmonth_str)
            self.assertIsInstance(month_data, list)
            for month_item in month_data:
                self.assertIsInstance(month_item.get("values"), list)

    def test_execute_query_current_month_by_service(self):
        """Test execute_query for current month on monthly breakdown by service."""
        valid_services = list(AZURE_SERVICE_NAMES)
        url = "?filter[limit]=10&filter[offset]=5&filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&group_by[service_name]=*"  # noqa: E501
        query_params = self.mocked_query_params(url, OCPAzureCostView)
        handler = OCPAzureReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get("total"))
        total = query_output.get("total")
        current_totals = self.get_totals_by_time_scope(handler, self.this_month_filter)
        self.assertIsNotNone(total.get("cost"))
        self.assertEqual(total.get("cost", {}).get("total", {}).get("value", 0), current_totals.get("cost_total", 1))

        cmonth_str = self.dh.this_month_start.strftime("%Y-%m")
        for data_item in data:
            month_val = data_item.get("date", "not-a-date")
            month_data = data_item.get("service_names")
            self.assertEqual(month_val, cmonth_str)
            self.assertIsInstance(month_data, list)
            for month_item in month_data:
                name = month_item.get("service_name")
                self.assertIn(name, valid_services)
                self.assertIsInstance(month_item.get("values"), list)

    def test_execute_query_by_filtered_service(self):
        """Test execute_query monthly breakdown by filtered service."""
        with tenant_context(self.tenant):
            valid_services = [
                service[0]
                for service in OCPAzureCostLineItemProjectDailySummaryP.objects.values_list("service_name").distinct()
            ]
            service = valid_services[0]
        url = f"?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&group_by[service_name]={service}"  # noqa: E501
        query_params = self.mocked_query_params(url, OCPAzureCostView)
        handler = OCPAzureReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")
        total = query_output.get("total")
        self.assertIsNotNone(data)
        self.assertIsNotNone(total)
        filters = {**self.this_month_filter, "service_name__icontains": service}
        for filt in handler._mapper.report_type_map.get("filter"):
            if filt:
                qf = QueryFilter(**filt)
                filters.update({qf.composed_query_string(): qf.parameter})
        current_totals = self.get_totals_by_time_scope(handler, filters)
        self.assertIsNotNone(total.get("cost"))
        self.assertEqual(total.get("cost", {}).get("total", {}).get("value", 0), current_totals.get("cost_total", 1))

        cmonth_str = self.dh.this_month_start.strftime("%Y-%m")
        for data_item in data:
            month_val = data_item.get("date", "not-a-date")
            month_data = data_item.get("service_names")
            self.assertEqual(month_val, cmonth_str)
            self.assertIsInstance(month_data, list)
            for month_item in month_data:
                name = month_item.get("service_name")
                self.assertIn(name, valid_services)
                self.assertIsInstance(month_item.get("values"), list)

    def test_execute_query_curr_month_by_subscription_guid_w_limit(self):
        """Test execute_query for current month on monthly breakdown by subscription_guid with limit."""
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&filter[limit]=2&group_by[subscription_guid]=*"  # noqa: E501
        query_params = self.mocked_query_params(url, OCPAzureCostView)
        handler = OCPAzureReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get("total"))
        total = query_output.get("total")
        current_totals = self.get_totals_by_time_scope(handler, self.this_month_filter)
        self.assertIsNotNone(total.get("cost"))
        self.assertEqual(total.get("cost", {}).get("total", {}).get("value", 0), current_totals.get("cost_total", 1))

        cmonth_str = DateHelper().this_month_start.strftime("%Y-%m")
        for data_item in data:
            month_val = data_item.get("date", "not-a-date")
            month_data = data_item.get("subscription_guids")
            self.assertEqual(month_val, cmonth_str)
            self.assertIsInstance(month_data, list)
            self.assertEqual(1, len(month_data))
            for month_item in month_data:
                self.assertIsInstance(month_item.get("subscription_guid"), str)
                self.assertIsInstance(month_item.get("values"), list)

    def test_execute_query_curr_month_by_subscription_guid_w_order(self):
        """Test execute_query for current month on monthly breakdown by subscription_guid with asc order."""
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&order_by[cost]=asc&group_by[subscription_guid]=*"  # noqa: E501
        query_params = self.mocked_query_params(url, OCPAzureCostView)
        handler = OCPAzureReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get("total"))
        total = query_output.get("total")
        current_totals = self.get_totals_by_time_scope(handler, self.this_month_filter)
        self.assertIsNotNone(total.get("cost"))
        self.assertEqual(total.get("cost", {}).get("total", {}).get("value", 0), current_totals.get("cost_total", 1))

        cmonth_str = self.dh.this_month_start.strftime("%Y-%m")
        for data_item in data:
            month_val = data_item.get("date", "not-a-date")
            month_data = data_item.get("subscription_guids")
            self.assertEqual(month_val, cmonth_str)
            self.assertIsInstance(month_data, list)
            self.assertEqual(len(month_data), 1)
            current_total = 0
            for month_item in month_data:
                self.assertIsInstance(month_item.get("subscription_guid"), str)
                self.assertIsInstance(month_item.get("values"), list)
                self.assertIsNotNone(month_item.get("values")[0].get("cost", {}).get("total", {}).get("value"))
                data_point_total = month_item.get("values")[0].get("cost", {}).get("total", {}).get("value")
                self.assertLess(current_total, data_point_total)
                current_total = data_point_total

    def test_execute_query_curr_month_by_subscription_guid_w_order_by_subscription_guid(self):
        """Test execute_query for current month on monthly breakdown by subscription_guid with asc order."""
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&order_by[subscription_guid]=asc&group_by[subscription_guid]=*"  # noqa: E501
        query_params = self.mocked_query_params(url, OCPAzureCostView)
        handler = OCPAzureReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get("total"))
        total = query_output.get("total")
        current_totals = self.get_totals_by_time_scope(handler, self.this_month_filter)
        self.assertIsNotNone(total.get("cost"))
        self.assertEqual(total.get("cost", {}).get("total", {}).get("value", 0), current_totals.get("cost_total", 1))

        cmonth_str = self.dh.this_month_start.strftime("%Y-%m")
        for data_item in data:
            month_val = data_item.get("date", "not-a-date")
            month_data = data_item.get("subscription_guids")
            self.assertEqual(month_val, cmonth_str)
            self.assertIsInstance(month_data, list)
            self.assertEqual(len(month_data), 1)
            current = "0"
            for month_item in month_data:
                self.assertIsInstance(month_item.get("subscription_guid"), str)
                self.assertIsInstance(month_item.get("values"), list)
                self.assertIsNotNone(month_item.get("values")[0].get("subscription_guid"))
                data_point = month_item.get("values")[0].get("subscription_guid")
                if data_point == "1 Other":
                    continue
                self.assertLess(current, data_point)
                current = data_point

    def test_execute_query_by_project(self):
        """Test execute_query group_by project."""
        url = "?group_by[project]=*"
        query_params = self.mocked_query_params(url, OCPAzureCostView)
        handler = OCPAzureReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")
        self.assertIsNotNone(data)
        for data_item in data:
            projects_data = data_item.get("projects")
            for project_item in projects_data:
                self.assertIsInstance(project_item.get("project"), str)

    def test_execute_query_by_project_w_category(self):
        """Test execute group_by project query with category."""
        url = "?group_by[project]=*&category=*"
        with patch("reporting.provider.ocp.models.OpenshiftCostCategory.objects") as mock_object:
            mock_object.values_list.return_value.distinct.return_value = ["Platform"]
            query_params = self.mocked_query_params(url, OCPAzureCostView)
            handler = OCPAzureReportQueryHandler(query_params)
            query_output = handler.execute_query()
            data = query_output.get("data")
            self.assertIsNotNone(data)
            for data_item in data:
                projects_data = data_item.get("projects")
                for project_item in projects_data:
                    if project_item.get("project") != "Platform":
                        self.assertTrue(project_item.get("values")[0].get("classification"), "project")

    def test_execute_query_curr_month_by_cluster(self):
        """Test execute_query for current month on monthly breakdown by group_by cluster."""
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&group_by[cluster]=*"  # noqa: E501
        query_params = self.mocked_query_params(url, OCPAzureCostView)
        handler = OCPAzureReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get("total"))
        total = query_output.get("total")
        current_totals = self.get_totals_by_time_scope(handler, self.this_month_filter)
        self.assertIsNotNone(total.get("cost"))
        self.assertEqual(total.get("cost", {}).get("total", {}).get("value", 0), current_totals.get("cost_total", 1))

        cmonth_str = DateHelper().this_month_start.strftime("%Y-%m")
        for data_item in data:
            month_val = data_item.get("date", "not-a-date")
            month_data = data_item.get("clusters")
            self.assertEqual(month_val, cmonth_str)
            self.assertIsInstance(month_data, list)
            for month_item in month_data:
                self.assertIsInstance(month_item.get("cluster"), str)
                self.assertIsInstance(month_item.get("values"), list)
                self.assertIsNotNone(month_item.get("values")[0].get("cost"))

    def test_execute_query_by_filtered_cluster(self):
        """Test execute_query monthly breakdown by filtered cluster."""
        with tenant_context(self.tenant):
            cluster = OCPAzureCostLineItemProjectDailySummaryP.objects.values("cluster_id")[0].get("cluster_id")
        url = f"?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&group_by[cluster]={cluster}"  # noqa: E501
        query_params = self.mocked_query_params(url, OCPAzureCostView)
        handler = OCPAzureReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get("total"))
        total = query_output.get("total")
        filters = {**self.this_month_filter, "cluster_id__icontains": cluster}
        for filt in handler._mapper.report_type_map.get("filter"):
            if filt:
                qf = QueryFilter(**filt)
                filters.update({qf.composed_query_string(): qf.parameter})
        current_totals = self.get_totals_by_time_scope(handler, filters)
        self.assertIsNotNone(total.get("cost"))
        self.assertEqual(total.get("cost", {}).get("total", {}).get("value", 0), current_totals.get("cost_total", 1))

        cmonth_str = self.dh.this_month_start.strftime("%Y-%m")
        for data_item in data:
            month_val = data_item.get("date", "not-a-date")
            month_data = data_item.get("clusters")
            self.assertEqual(month_val, cmonth_str)
            self.assertIsInstance(month_data, list)
            for month_item in month_data:
                self.assertIsInstance(month_item.get("cluster"), str)
                self.assertIsInstance(month_item.get("values"), list)
                self.assertIsNotNone(month_item.get("values")[0].get("cost"))

    def test_execute_query_curr_month_by_filtered_resource_location(self):
        """Test execute_query for current month on monthly breakdown by filtered resource_location."""
        with tenant_context(self.tenant):
            location = (
                OCPAzureCostLineItemProjectDailySummaryP.objects.filter(
                    usage_start__gte=self.dh.this_month_start.date()
                )
                .values("resource_location")[0]
                .get("resource_location")
            )
        url = f"?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&group_by[resource_location]={location}"  # noqa: E501
        query_params = self.mocked_query_params(url, OCPAzureCostView)
        handler = OCPAzureReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get("total"))
        total = query_output.get("total")
        filters = {**self.this_month_filter, "resource_location__icontains": location}
        current_totals = self.get_totals_by_time_scope(handler, filters)
        self.assertIsNotNone(total.get("cost"))
        self.assertEqual(total.get("cost", {}).get("total", {}).get("value", 0), current_totals.get("cost_total", 1))

        cmonth_str = DateHelper().this_month_start.strftime("%Y-%m")
        for data_item in data:
            month_val = data_item.get("date", "not-a-date")
            month_data = data_item.get("resource_locations")
            self.assertEqual(month_val, cmonth_str)
            self.assertIsInstance(month_data, list)
            for month_item in month_data:
                self.assertIsInstance(month_item.get("resource_location"), str)
                self.assertIsInstance(month_item.get("values"), list)
                self.assertIsNotNone(month_item.get("values")[0].get("cost"))

    def test_execute_query_current_month_filter_subscription_guid(self):
        """Test execute_query for current month on monthly filtered by subscription_guid."""
        with tenant_context(self.tenant):
            guid = OCPAzureCostLineItemProjectDailySummaryP.objects.values("subscription_guid")[0].get(
                "subscription_guid"
            )
        url = f"?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&filter[subscription_guid]={guid}"  # noqa: E501
        query_params = self.mocked_query_params(url, OCPAzureCostView)
        handler = OCPAzureReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get("total"))
        total = query_output.get("total")
        filters = {**self.this_month_filter, "subscription_guid": guid}
        current_totals = self.get_totals_by_time_scope(handler, filters)
        self.assertIsNotNone(total.get("cost"))
        self.assertEqual(total.get("cost", {}).get("total", {}).get("value", 0), current_totals.get("cost_total", 1))

        cmonth_str = self.dh.this_month_start.strftime("%Y-%m")
        for data_item in data:
            month_val = data_item.get("date", "not-a-date")
            month_data = data_item.get("values")
            self.assertEqual(month_val, cmonth_str)
            self.assertIsInstance(month_data, list)

    def test_execute_query_current_month_filter_service(self):
        """Test execute_query for current month on monthly filtered by service."""
        with tenant_context(self.tenant):
            service = OCPAzureCostLineItemProjectDailySummaryP.objects.values("service_name")[0].get("service_name")
        url = f"?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&filter[service_name]={service}"  # noqa: E501
        query_params = self.mocked_query_params(url, OCPAzureCostView)
        handler = OCPAzureReportQueryHandler(query_params)
        query_output = handler.execute_query()

        data = query_output.get("data")
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get("total"))

        total = query_output.get("total")
        filters = {**self.this_month_filter, "service_name__icontains": service}
        for filt in handler._mapper.report_type_map.get("filter"):
            if filt:
                qf = QueryFilter(**filt)
                filters.update({qf.composed_query_string(): qf.parameter})
        current_totals = self.get_totals_by_time_scope(handler, filters)
        self.assertIsNotNone(total.get("cost"))
        self.assertEqual(total.get("cost", {}).get("total", {}).get("value", 0), current_totals.get("cost_total", 1))

        cmonth_str = self.dh.this_month_start.strftime("%Y-%m")
        for data_item in data:
            month_val = data_item.get("date", "not-a-date")
            month_data = data_item.get("values")
            self.assertEqual(month_val, cmonth_str)
            self.assertIsInstance(month_data, list)

    def test_execute_query_current_month_filter_resource_location(self):
        """Test execute_query for current month on monthly filtered by resource_location."""
        with tenant_context(self.tenant):
            location = (
                OCPAzureCostLineItemProjectDailySummaryP.objects.filter(
                    usage_start__gte=self.dh.this_month_start.date()
                )
                .values("resource_location")[0]
                .get("resource_location")
            )
        url = f"?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&filter[resource_location]={location}"  # noqa: E501
        query_params = self.mocked_query_params(url, OCPAzureCostView)
        handler = OCPAzureReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get("total"))
        total = query_output.get("total")
        filters = {**self.this_month_filter, "resource_location__icontains": location}
        current_totals = self.get_totals_by_time_scope(handler, filters)
        self.assertIsNotNone(total.get("cost"))
        self.assertEqual(total.get("cost", {}).get("total", {}).get("value", 0), current_totals.get("cost_total", 1))

        cmonth_str = DateHelper().this_month_start.strftime("%Y-%m")
        for data_item in data:
            month_val = data_item.get("date", "not-a-date")
            month_data = data_item.get("values")
            self.assertEqual(month_val, cmonth_str)
            self.assertIsInstance(month_data, list)

    def test_execute_query_current_month_exclude_service(self):
        """Test execute_query for current month on monthly excluded by service."""
        with tenant_context(self.tenant):
            service = OCPAzureCostLineItemProjectDailySummaryP.objects.values("service_name")[0].get("service_name")
        url = f"?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&exclude[service_name]={service}"  # noqa: E501
        query_params = self.mocked_query_params(url, OCPAzureCostView)
        handler = OCPAzureReportQueryHandler(query_params)
        query_output = handler.execute_query()

        data = query_output.get("data")
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get("total"))

    @patch("api.query_params.QueryParameters.accept_type", new_callable=PropertyMock)
    def test_execute_query_current_month_filter_resource_location_csv(self, mock_accept):
        """Test execute_query on monthly filtered by resource_location for csv."""
        mock_accept.return_value = "text/csv"
        with tenant_context(self.tenant):
            location = (
                OCPAzureCostLineItemProjectDailySummaryP.objects.filter(
                    usage_start__gte=self.dh.this_month_start.date()
                )
                .values("resource_location")[0]
                .get("resource_location")
            )
        url = f"?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&filter[resource_location]={location}"  # noqa: E501
        query_params = self.mocked_query_params(url, OCPAzureCostView)
        handler = OCPAzureReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get("total"))
        total = query_output.get("total")
        filters = {**self.this_month_filter, "resource_location__icontains": location}
        current_totals = self.get_totals_by_time_scope(handler, filters)
        self.assertIsNotNone(total.get("cost"))
        self.assertEqual(total.get("cost", {}).get("total", {}).get("value", 0), current_totals.get("cost_total", 1))

        cmonth_str = DateHelper().this_month_start.strftime("%Y-%m")
        self.assertEqual(len(data), 1)
        for data_item in data:
            month_val = data_item.get("date", "not-a-date")
            self.assertEqual(month_val, cmonth_str)

    @patch("api.query_params.QueryParameters.accept_type", new_callable=PropertyMock)
    def test_execute_query_curr_month_by_subscription_guid_w_limit_csv(self, mock_accept):
        """Test execute_query for current month on monthly by subscription_guid with limt as csv."""
        mock_accept.return_value = "text/csv"

        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&filter[limit]=2&group_by[subscription_guid]=*"  # noqa: E501
        query_params = self.mocked_query_params(url, OCPAzureCostView)
        handler = OCPAzureReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")

        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get("total"))
        total = query_output.get("total")
        current_totals = self.get_totals_by_time_scope(handler, self.this_month_filter)
        self.assertIsNotNone(total.get("cost"))
        self.assertEqual(total.get("cost", {}).get("total", {}).get("value", 0), current_totals.get("cost_total", 1))

        cmonth_str = self.dh.this_month_start.strftime("%Y-%m")
        self.assertEqual(len(data), 1)
        for data_item in data:
            month = data_item.get("date", "not-a-date")
            self.assertEqual(month, cmonth_str)

    def test_execute_query_w_delta(self):
        """Test grouped by deltas."""

        path = reverse("reports-openshift-azure-costs")
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&group_by[subscription_guid]=*&delta=cost"  # noqa: E501
        query_params = self.mocked_query_params(url, OCPAzureCostView, path)
        handler = OCPAzureReportQueryHandler(query_params)
        # test the calculations
        query_output = handler.execute_query()
        data = query_output.get("data")
        self.assertIsNotNone(data)

        subs = data[0].get("subscription_guids", [{}])
        if isinstance(self.dh.this_month_start, datetime):
            v_this_month_start = self.dh.this_month_start.date()
        else:
            v_this_month_start = self.dh.this_month_start
        if isinstance(self.dh.today, datetime):
            v_today = self.dh.today.date()
            v_today_last_month = (self.dh.today - relativedelta(months=1)).date()
        else:
            v_today = self.dh.today
            v_today_last_month = self.dh.today = relativedelta(months=1)
        if isinstance(self.dh.last_month_start, datetime):
            v_last_month_start = self.dh.last_month_start.date()
        else:
            v_last_month_start = self.dh.last_month_start

        for sub in subs:
            current_total = Decimal(0)
            prev_total = Decimal(0)

            # fetch the expected sums from the DB.
            with tenant_context(self.tenant):
                curr = OCPAzureCostLineItemProjectDailySummaryP.objects.filter(
                    usage_start__gte=v_this_month_start,
                    usage_start__lte=v_today,
                    subscription_guid=sub.get("subscription_guid"),
                ).aggregate(value=Sum(F("pretax_cost") + F("markup_cost")))
                current_total = Decimal(curr.get("value"))

                prev = OCPAzureCostLineItemProjectDailySummaryP.objects.filter(
                    usage_start__gte=v_last_month_start,
                    usage_start__lte=v_today_last_month,
                    subscription_guid=sub.get("subscription_guid"),
                ).aggregate(value=Sum(F("pretax_cost") + F("markup_cost")))
                prev_total = Decimal(prev.get("value", Decimal(0)))

            expected_delta_value = Decimal(current_total - prev_total)
            expected_delta_percent = Decimal((current_total - prev_total) / prev_total * 100)

            values = sub.get("values", [{}])[0]
            self.assertIn("delta_value", values)
            self.assertIn("delta_percent", values)
            self.assertEqual(values.get("delta_value", "str"), expected_delta_value)
            self.assertEqual(values.get("delta_percent", "str"), expected_delta_percent)

        current_total = Decimal(0)
        prev_total = Decimal(0)

        # fetch the expected sums from the DB.
        with tenant_context(self.tenant):
            curr = OCPAzureCostLineItemProjectDailySummaryP.objects.filter(
                usage_start__gte=self.dh.this_month_start, usage_start__lte=self.dh.today
            ).aggregate(value=Sum(F("pretax_cost") + F("markup_cost")))
            current_total = Decimal(curr.get("value"))

            prev = OCPAzureCostLineItemProjectDailySummaryP.objects.filter(
                usage_start__gte=self.dh.last_month_start, usage_start__lte=self.dh.today - relativedelta(months=1)
            ).aggregate(value=Sum(F("pretax_cost") + F("markup_cost")))
            prev_total = Decimal(prev.get("value"))

        expected_delta_value = Decimal(current_total - prev_total)
        expected_delta_percent = Decimal((current_total - prev_total) / prev_total * 100)

        delta = query_output.get("delta")
        self.assertIsNotNone(delta.get("value"))
        self.assertIsNotNone(delta.get("percent"))
        self.assertEqual(delta.get("value", "str"), expected_delta_value)
        self.assertEqual(delta.get("percent", "str"), expected_delta_percent)

    def test_execute_query_w_delta_no_previous_data(self):
        """Test deltas with no previous data."""
        url = "?filter[time_scope_value]=-2&delta=cost"
        path = reverse("reports-openshift-azure-costs")
        query_params = self.mocked_query_params(url, OCPAzureCostView, path)
        handler = OCPAzureReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")
        self.assertIsNotNone(data)
        total_cost = query_output.get("total", {}).get("cost", {}).get("total").get("value", 1)
        delta = query_output.get("delta")
        self.assertIsNotNone(delta.get("value"))
        self.assertIsNone(delta.get("percent", 0))
        self.assertAlmostEqual(delta.get("value", 0), total_cost, 6)

    def test_execute_query_orderby_delta(self):
        """Test execute_query with ordering by delta ascending."""
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&order_by[delta]=asc&group_by[subscription_guid]=*&delta=cost"  # noqa: E501
        path = reverse("reports-openshift-azure-costs")
        query_params = self.mocked_query_params(url, OCPAzureCostView, path)
        handler = OCPAzureReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")
        self.assertIsNotNone(data)
        cmonth_str = self.dh.this_month_start.strftime("%Y-%m")
        for data_item in data:
            month_val = data_item.get("date", "not-a-date")
            month_data = data_item.get("subscription_guids")
            self.assertEqual(month_val, cmonth_str)
            self.assertIsInstance(month_data, list)
            for month_item in month_data:
                self.assertIsInstance(month_item.get("subscription_guid"), str)
                self.assertIsInstance(month_item.get("values"), list)
                self.assertIsInstance(month_item.get("values")[0].get("delta_value"), Decimal)

    def test_calculate_total(self):
        """Test that calculated totals return correctly."""
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly"
        query_params = self.mocked_query_params(url, OCPAzureCostView)
        handler = OCPAzureReportQueryHandler(query_params)
        expected_units = "USD"
        with tenant_context(self.tenant):
            result = handler.calculate_total(**{"cost_units": expected_units})

        current_totals = self.get_totals_by_time_scope(handler, self.this_month_filter)
        self.assertEqual(result.get("cost", {}).get("total", {}).get("value", 0), current_totals.get("cost_total", 1))
        self.assertEqual(result.get("cost", {}).get("total", {}).get("units", "not-USD"), expected_units)

    def test_percent_delta(self):
        """Test _percent_delta() utility method."""
        url = "?"
        query_params = self.mocked_query_params(url, OCPAzureCostView)
        handler = OCPAzureReportQueryHandler(query_params)
        self.assertEqual(handler._percent_delta(10, 5), 100)

    def test_rank_list_by_subscription_guid(self):
        """Test rank list limit with subscription_guid alias."""
        # No need to fill db
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&filter[limit]=2&group_by[subscription_guid]=*"  # noqa: E501
        query_params = self.mocked_query_params(url, OCPAzureCostView)
        handler = OCPAzureReportQueryHandler(query_params)

        ranks = [
            {"subscription_guid": "1", "rank": 1, "source_uuid": ["1"]},
            {"subscription_guid": "2", "rank": 2, "source_uuid": ["1"]},
            {"subscription_guid": "3", "rank": 3, "source_uuid": ["1"]},
            {"subscription_guid": "4", "rank": 4, "source_uuid": ["1"]},
        ]

        data_list = [
            {
                "subscription_guid": "1",
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
                "subscription_guid": "2",
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
                "subscription_guid": "3",
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
                "subscription_guid": "4",
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
                "subscription_guid": "1",
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
                "subscription_guid": "2",
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
                "subscription_guid": "Others",
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

    def test_rank_list_by_service_name(self):
        """Test rank list limit with service_name grouping."""
        # No need to fill db
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&filter[limit]=2&group_by[service_name]=*"  # noqa: E501
        query_params = self.mocked_query_params(url, OCPAzureCostView)
        handler = OCPAzureReportQueryHandler(query_params)
        ranks = [
            {"service_name": "1", "rank": 1, "source_uuid": ["1"]},
            {"service_name": "2", "rank": 2, "source_uuid": ["1"]},
            {"service_name": "3", "rank": 3, "source_uuid": ["1"]},
            {"service_name": "4", "rank": 4, "source_uuid": ["1"]},
        ]
        data_list = [
            {
                "service_name": "1",
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
                "service_name": "2",
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
                "service_name": "3",
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
                "service_name": "4",
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
                "service_name": "1",
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
                "service_name": "2",
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
                "service_name": "Others",
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
        """Test rank list limit and offset with subscription_guid alias."""
        # No need to fill db
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&filter[limit]=1&filter[offset]=1&group_by[subscription_guid]=*"  # noqa: E501
        query_params = self.mocked_query_params(url, OCPAzureCostView)
        handler = OCPAzureReportQueryHandler(query_params)

        ranks = [
            {"subscription_guid": "1", "rank": 1, "source_uuid": ["1"]},
            {"subscription_guid": "2", "rank": 2, "source_uuid": ["1"]},
            {"subscription_guid": "3", "rank": 3, "source_uuid": ["1"]},
            {"subscription_guid": "4", "rank": 4, "source_uuid": ["1"]},
        ]

        data_list = [
            {
                "subscription_guid": "1",
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
                "subscription_guid": "2",
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
                "subscription_guid": "3",
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
                "subscription_guid": "4",
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
                "subscription_guid": "2",
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
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&group_by[subscription_guid]=*"  # noqa: E501
        query_params = self.mocked_query_params(url, OCPAzureCostView)
        handler = OCPAzureReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")
        self.assertIsNotNone(data)

        for data_item in data:
            subscription_guids = data_item.get("subscription_guids")
            for subscription_guid in subscription_guids:
                self.assertIsNotNone(subscription_guid.get("values"))
                self.assertGreater(len(subscription_guid.get("values")), 0)
                for value in subscription_guid.get("values"):
                    self.assertIsInstance(value.get("cost", {}).get("total", {}).get("value"), Decimal)
                    self.assertGreater(value.get("cost", {}).get("total", {}).get("value"), Decimal(0))

    def test_query_instance_types_with_totals(self):
        """Test execute_query() - instance types with totals.

        Query for instance_types, validating that cost totals are present.

        """
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&group_by[instance_type]=*"  # noqa: E501
        query_params = self.mocked_query_params(url, OCPAzureInstanceTypeView)
        handler = OCPAzureReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")
        self.assertIsNotNone(data)

        for data_item in data:
            instance_types = data_item.get("instance_types")
            for it in instance_types:
                self.assertIsNotNone(it.get("values"))
                self.assertGreater(len(it.get("values")), 0)
                for value in it.get("values"):
                    self.assertIsInstance(value.get("cost", {}).get("total", {}).get("value"), Decimal)
                    self.assertGreaterEqual(
                        value.get("cost", {}).get("total", {}).get("value").quantize(Decimal(".0001"), ROUND_HALF_UP),
                        Decimal(0),
                    )
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
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&group_by[service_name]=*"  # noqa: E501
        query_params = self.mocked_query_params(url, OCPAzureStorageView)
        handler = OCPAzureReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")
        self.assertIsNotNone(data)

        for data_item in data:
            services = data_item.get("service_names")
            self.assertIsNotNone(services)
            for srv in services:
                self.assertIsNotNone(srv.get("values"))
                self.assertGreater(len(srv.get("values")), 0)
                for value in srv.get("values"):
                    self.assertIsInstance(value.get("cost", {}).get("total", {}).get("value"), Decimal)
                    self.assertGreater(value.get("cost", {}).get("total", {}).get("value"), Decimal(0))
                    # FIXME: usage doesn't have units yet. waiting on MSFT
                    # self.assertIsInstance(value.get('usage', {}).get('value'), Decimal)
                    # self.assertGreater(value.get('usage', {}).get('value'), Decimal(0))
                    self.assertIsInstance(value.get("usage", {}), dict)
                    self.assertGreater(value.get("usage", {}).get("value", {}), Decimal(0))

    def test_order_by(self):
        """Test that order_by returns properly sorted data."""
        # Do not need to fill db
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly"
        query_params = self.mocked_query_params(url, OCPAzureCostView)
        handler = OCPAzureReportQueryHandler(query_params)

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
        # Do not need to fill db
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly"
        query_params = self.mocked_query_params(url, OCPAzureCostView)
        handler = OCPAzureReportQueryHandler(query_params)

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

    def test_query_table(self):
        """Test that the correct view is assigned by query table property."""
        url = "?"
        query_params = self.mocked_query_params(url, OCPAzureCostView)
        handler = OCPAzureReportQueryHandler(query_params)
        self.assertEqual(handler.query_table, OCPAzureCostSummaryP)

        url = "?group_by[subscription_guid]=*"
        query_params = self.mocked_query_params(url, OCPAzureCostView)
        handler = OCPAzureReportQueryHandler(query_params)
        self.assertEqual(handler.query_table, OCPAzureCostSummaryByAccountP)

        url = "?group_by[resource_location]=*"
        query_params = self.mocked_query_params(url, OCPAzureCostView)
        handler = OCPAzureReportQueryHandler(query_params)
        self.assertEqual(handler.query_table, OCPAzureCostSummaryByLocationP)

        url = "?group_by[resource_location]=*&group_by[subscription_guid]=*"
        query_params = self.mocked_query_params(url, OCPAzureCostView)
        handler = OCPAzureReportQueryHandler(query_params)
        self.assertEqual(handler.query_table, OCPAzureCostSummaryByLocationP)

        url = "?group_by[service_name]=*"
        query_params = self.mocked_query_params(url, OCPAzureCostView)
        handler = OCPAzureReportQueryHandler(query_params)
        self.assertEqual(handler.query_table, OCPAzureCostSummaryByServiceP)

        url = "?group_by[service_name]=*&group_by[subscription_guid]=*"
        query_params = self.mocked_query_params(url, OCPAzureCostView)
        handler = OCPAzureReportQueryHandler(query_params)
        self.assertEqual(handler.query_table, OCPAzureCostSummaryByServiceP)

        url = "?"
        query_params = self.mocked_query_params(url, OCPAzureInstanceTypeView)
        handler = OCPAzureReportQueryHandler(query_params)
        self.assertEqual(handler.query_table, OCPAzureComputeSummaryP)

        url = "?group_by[subscription_guid]=*"
        query_params = self.mocked_query_params(url, OCPAzureInstanceTypeView)
        handler = OCPAzureReportQueryHandler(query_params)
        self.assertEqual(handler.query_table, OCPAzureComputeSummaryP)

        url = "?"
        query_params = self.mocked_query_params(url, OCPAzureStorageView)
        handler = OCPAzureReportQueryHandler(query_params)
        self.assertEqual(handler.query_table, OCPAzureStorageSummaryP)

        url = "?group_by[subscription_guid]=*"
        query_params = self.mocked_query_params(url, OCPAzureStorageView)
        handler = OCPAzureReportQueryHandler(query_params)
        self.assertEqual(handler.query_table, OCPAzureStorageSummaryP)

        url = (
            "?filter[service_name]=Virtual Network,VPN,DNS,Traffic Manager,"
            "ExpressRoute,Load Balancer,Application Gateway"
        )
        query_params = self.mocked_query_params(url, OCPAzureCostView)
        handler = OCPAzureReportQueryHandler(query_params)
        self.assertEqual(handler.query_table, OCPAzureNetworkSummaryP)

        url = (
            "?filter[service_name]=Virtual Network,VPN,DNS,Traffic Manager,"
            "ExpressRoute,Load Balancer,Application Gateway"
            "&group_by[subscription_guid]=*"
        )
        query_params = self.mocked_query_params(url, OCPAzureCostView)
        handler = OCPAzureReportQueryHandler(query_params)
        self.assertEqual(handler.query_table, OCPAzureNetworkSummaryP)

        url = "?filter[service_name]=Cosmos DB,Cache for Redis,Database"
        query_params = self.mocked_query_params(url, OCPAzureCostView)
        handler = OCPAzureReportQueryHandler(query_params)
        self.assertEqual(handler.query_table, OCPAzureDatabaseSummaryP)

        url = "?filter[service_name]=Cosmos DB,Cache for Redis,Database" "&group_by[subscription_guid]=*"
        query_params = self.mocked_query_params(url, OCPAzureCostView)
        handler = OCPAzureReportQueryHandler(query_params)
        self.assertEqual(handler.query_table, OCPAzureDatabaseSummaryP)

    def test_source_uuid_mapping(self):  # noqa: C901
        """Test source_uuid is mapped to the correct source."""
        endpoints = [OCPAzureCostView, OCPAzureInstanceTypeView, OCPAzureStorageView]
        with tenant_context(self.tenant):
            expected_source_uuids = list(AzureCostEntryBill.objects.distinct().values_list("provider_id", flat=True))
        source_uuid_list = []
        for endpoint in endpoints:
            urls = ["?"]
            if endpoint == OCPAzureCostView:
                urls.extend(
                    ["?group_by[subscription_guid]=*", "?group_by[resource_location]=*", "group_by[service_name]=*"]
                )
            for url in urls:
                query_params = self.mocked_query_params(url, endpoint)
                handler = OCPAzureReportQueryHandler(query_params)
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

    def test_ocp_azure_date_order_by_cost_desc(self):
        """Test that order of every other date matches the order of the `order_by` date."""
        yesterday = self.dh.yesterday.date()
        url = f"?filter[limit]=10&filter[offset]=0&order_by[cost]=desc&order_by[date]={yesterday}&group_by[service_name]=*"  # noqa: E501
        query_params = self.mocked_query_params(url, OCPAzureCostView)
        handler = OCPAzureReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")
        exch_annotation = handler.annotations.get("exchange_rate")
        cost_annotation = handler.report_annotations.get("cost_total")
        with tenant_context(self.tenant):
            expected = list(
                OCPAzureCostSummaryByServiceP.objects.filter(usage_start=str(yesterday))
                .annotate(exchange_rate=exch_annotation)
                .values("service_name")
                .annotate(cost=cost_annotation)
                .order_by("-cost")
            )
        correctlst = [service.get("service_name") for service in expected]
        tested = False
        for element in data:
            lst = [service.get("service_name") for service in element.get("service_names", [])]
            if lst and correctlst:
                self.assertEqual(correctlst, lst)
                tested = True
        self.assertTrue(tested)

    def test_ocp_azure_date_incorrect_date(self):
        wrong_date = "200BC"
        url = f"?order_by[cost]=desc&order_by[date]={wrong_date}&group_by[service_name]=*"
        with self.assertRaises(ValidationError):
            self.mocked_query_params(url, OCPAzureCostView)

    def test_ocp_azure_out_of_range_under_date(self):
        wrong_date = materialized_view_month_start() - timedelta(days=1)
        url = f"?order_by[cost]=desc&order_by[date]={wrong_date}&group_by[service_name]=*"
        with self.assertRaises(ValidationError):
            self.mocked_query_params(url, OCPAzureCostView)

    def test_ocp_azure_out_of_range_over_date(self):
        wrong_date = DateHelper().today.date() + timedelta(days=1)
        url = f"?order_by[cost]=desc&order_by[date]={wrong_date}&group_by[service_name]=*"
        with self.assertRaises(ValidationError):
            self.mocked_query_params(url, OCPAzureCostView)

    def test_ocp_azure_date_with_no_data(self):
        # This test will group by a date that is out of range for data generated.
        # The data will still return data because other dates will still generate data.
        yesterday = self.dh.yesterday.date()
        yesterday_month = self.dh.yesterday - relativedelta(months=2)

        url = f"?group_by[service_name]=*&order_by[cost]=desc&order_by[date]={yesterday_month.date()}&end_date={yesterday}&start_date={yesterday_month.date()}"  # noqa: E501
        query_params = self.mocked_query_params(url, OCPAzureCostView)
        handler = OCPAzureReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")
        self.assertIsNotNone(data)

    @patch("api.query_params.enable_negative_filtering", return_value=True)
    def test_exclude_functionality(self, _):
        """Test that the exclude feature works for all options."""
        exclude_opts = OCPAzureExcludeSerializer._opfields
        for exclude_opt in exclude_opts:
            for view in [OCPAzureCostView, OCPAzureStorageView, OCPAzureInstanceTypeView]:
                with self.subTest((exclude_opt, view)):
                    overall_url = f"?group_by[{exclude_opt}]=*"
                    query_params = self.mocked_query_params(overall_url, view)
                    handler = OCPAzureReportQueryHandler(query_params)
                    overall_output = handler.execute_query()
                    overall_total = handler.query_sum.get("cost", {}).get("total", {}).get("value")
                    opt_dict = overall_output.get("data", [{}])[0]
                    opt_dict = opt_dict.get(f"{exclude_opt}s")[0]
                    opt_value = opt_dict.get(exclude_opt)
                    if "No-" in opt_value:
                        # Hanlde cases where "No-instance-type" is returned
                        continue
                    # Grab filtered value
                    filtered_url = f"?group_by[{exclude_opt}]=*&filter[{exclude_opt}]={opt_value}"
                    query_params = self.mocked_query_params(filtered_url, view)
                    handler = OCPAzureReportQueryHandler(query_params)
                    handler.execute_query()
                    filtered_total = handler.query_sum.get("cost", {}).get("total", {}).get("value")
                    expected_total = overall_total - filtered_total
                    # Test exclude
                    exclude_url = f"?group_by[{exclude_opt}]=*&exclude[{exclude_opt}]={opt_value}"
                    query_params = self.mocked_query_params(exclude_url, view)
                    handler = OCPAzureReportQueryHandler(query_params)
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
        url = "?"
        query_params = self.mocked_query_params("?", OCPAzureTagView)
        handler = OCPAzureTagQueryHandler(query_params)
        tags = handler.get_tags()
        group_tag = None
        check_no_option = False
        exclude_vals = []
        for tag_dict in tags:
            if len(tag_dict.get("values")) > len(exclude_vals):
                group_tag = tag_dict.get("key")
                exclude_vals = tag_dict.get("values")
        url = f"?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=daily&group_by[tag:{group_tag}]=*"  # noqa: E501
        query_params = self.mocked_query_params(url, OCPAzureCostView)
        handler = OCPAzureReportQueryHandler(query_params)
        data = handler.execute_query().get("data")
        if f"No-{group_tag}" in str(data):
            check_no_option = True
        previous_total = handler.query_sum.get("cost", {}).get("total", {}).get("value")
        for exclude_value in exclude_vals:
            url += f"&exclude[tag:{group_tag}]={exclude_value}"
            query_params = self.mocked_query_params(url, OCPAzureCostView)
            handler = OCPAzureReportQueryHandler(query_params)
            data = handler.execute_query()
            if check_no_option:
                self.assertIn(f"No-{group_tag}", str(data))
            current_total = handler.query_sum.get("cost", {}).get("total", {}).get("value")
            self.assertLess(current_total, previous_total)
            previous_total = current_total

    @patch("api.query_params.enable_negative_filtering", return_value=True)
    def test_multi_exclude_functionality(self, _):
        """Test that the exclude feature works for all options."""
        exclude_opts = OCPAzureExcludeSerializer._opfields
        for ex_opt in exclude_opts:
            base_url = f"?group_by[{ex_opt}]=*&filter[time_scope_units]=month&filter[resolution]=monthly&filter[time_scope_value]=-1"  # noqa: E501
            for view in [OCPAzureCostView, OCPAzureStorageView, OCPAzureInstanceTypeView]:
                query_params = self.mocked_query_params(base_url, view)
                handler = OCPAzureReportQueryHandler(query_params)
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
                    handler = OCPAzureReportQueryHandler(query_params)
                    self.assertIsNotNone(handler.query_exclusions)
                    excluded_output = handler.execute_query()
                    excluded_data = excluded_output.get("data")
                    self.assertIsNotNone(excluded_data)
                    for date_dict in excluded_data:
                        grouping_list = date_dict.get(f"{ex_opt}s", [])
                        self.assertIsNotNone(grouping_list)
                        for group_dict in grouping_list:
                            self.assertNotIn(group_dict.get(ex_opt), [exclude_one, exclude_two])
