#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the Report Queries."""
import copy
import logging
from datetime import timedelta

from rest_framework.exceptions import ValidationError
from tenant_schemas.utils import tenant_context

from api.iam.test.iam_test_case import IamTestCase
from api.report.aws.openshift.query_handler import OCPAWSReportQueryHandler
from api.report.aws.openshift.view import OCPAWSCostView
from api.report.aws.openshift.view import OCPAWSInstanceTypeView
from api.report.aws.openshift.view import OCPAWSStorageView
from api.report.queries import check_view_filter_and_group_by_criteria
from api.utils import DateHelper
from api.utils import materialized_view_month_start
from reporting.models import AWSCostEntryBill
from reporting.models import OCPAWSComputeSummaryP
from reporting.models import OCPAWSCostLineItemDailySummary
from reporting.models import OCPAWSCostSummaryByAccountP
from reporting.models import OCPAWSCostSummaryByRegionP
from reporting.models import OCPAWSCostSummaryByServiceP
from reporting.models import OCPAWSCostSummaryP
from reporting.models import OCPAWSDatabaseSummaryP
from reporting.models import OCPAWSNetworkSummaryP
from reporting.models import OCPAWSStorageSummaryP

LOG = logging.getLogger(__name__)


class OCPAWSQueryHandlerTestNoData(IamTestCase):
    """Tests for the OCP report query handler with no data."""

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

    def test_execute_sum_query_instance_types(self):
        """Test that the sum query runs properly for instance-types."""
        url = "?"
        query_params = self.mocked_query_params(url, OCPAWSInstanceTypeView)
        handler = OCPAWSReportQueryHandler(query_params)
        query_output = handler.execute_query()
        self.assertIsNotNone(query_output.get("data"))
        self.assertIsNotNone(query_output.get("total"))
        total = query_output.get("total")
        self.assertIsNotNone(total.get("cost"))
        self.assertIsInstance(total.get("cost"), dict)
        self.assertNotEqual(total.get("cost").get("total", {}).get("value"), 0)
        self.assertEqual(total.get("cost").get("total", {}).get("units"), "USD")
        self.assertIsNotNone(total.get("usage"))
        self.assertIsInstance(total.get("usage"), dict)
        self.assertNotEqual(total.get("usage").get("value"), 0)
        self.assertEqual(total.get("usage").get("units"), "Hrs")
        self.assertIsNotNone(total.get("count"))
        self.assertIsInstance(total.get("count"), dict)
        self.assertNotEqual(total.get("count").get("value"), 0)
        self.assertEqual(total.get("count").get("units"), "instances")


class OCPAWSQueryHandlerTest(IamTestCase):
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
            self.services = OCPAWSCostLineItemDailySummary.objects.values("product_code").distinct()
            self.services = [entry.get("product_code") for entry in self.services]

    def get_totals_by_time_scope(self, aggregates, filters=None):
        """Return the total aggregates for a time period."""
        if filters is None:
            filters = self.ten_day_filter
        with tenant_context(self.tenant):
            return OCPAWSCostLineItemDailySummary.objects.filter(**filters).aggregate(**aggregates)

    def test_execute_sum_query_storage(self):
        """Test that the sum query runs properly."""
        url = "?"
        query_params = self.mocked_query_params(url, OCPAWSStorageView)
        handler = OCPAWSReportQueryHandler(query_params)
        filt = {"product_family__contains": "Storage"}
        filt.update(self.ten_day_filter)
        aggregates = handler._mapper.report_type_map.get("aggregates")
        current_totals = self.get_totals_by_time_scope(aggregates, filt)
        query_output = handler.execute_query()
        self.assertIsNotNone(query_output.get("data"))
        self.assertIsNotNone(query_output.get("total"))
        total = query_output.get("total")
        self.assertEqual(total.get("cost", {}).get("total", {}).get("value", 0), current_totals.get("cost_total", 1))

    def test_execute_query_current_month_daily(self):
        """Test execute_query for current month on daily breakdown."""
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=daily"
        query_params = self.mocked_query_params(url, OCPAWSCostView)
        handler = OCPAWSReportQueryHandler(query_params)
        query_output = handler.execute_query()
        self.assertIsNotNone(query_output.get("data"))
        self.assertIsNotNone(query_output.get("total"))
        total = query_output.get("total")
        self.assertIsNotNone(total.get("cost"))

        aggregates = handler._mapper.report_type_map.get("aggregates")
        current_totals = self.get_totals_by_time_scope(aggregates, self.this_month_filter)
        self.assertEqual(total.get("cost", {}).get("total", {}).get("value", 0), current_totals.get("cost_total", 1))

    def test_execute_query_current_month_monthly(self):
        """Test execute_query for current month on monthly breakdown."""
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=daily"
        query_params = self.mocked_query_params(url, OCPAWSCostView)
        handler = OCPAWSReportQueryHandler(query_params)
        query_output = handler.execute_query()
        self.assertIsNotNone(query_output.get("data"))
        self.assertIsNotNone(query_output.get("total"))
        total = query_output.get("total")
        self.assertIsNotNone(total.get("cost"))

        aggregates = handler._mapper.report_type_map.get("aggregates")
        current_totals = self.get_totals_by_time_scope(aggregates, self.this_month_filter)
        self.assertEqual(total.get("cost", {}).get("total", {}).get("value", 0), current_totals.get("cost_total", 1))

    def test_execute_query_current_month_by_service(self):
        """Test execute_query for current month on monthly breakdown by service."""
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&group_by[service]=*"  # noqa: E501
        query_params = self.mocked_query_params(url, OCPAWSCostView)
        handler = OCPAWSReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get("total"))
        total = query_output.get("total")
        self.assertIsNotNone(total.get("cost"))

        aggregates = handler._mapper.report_type_map.get("aggregates")
        current_totals = self.get_totals_by_time_scope(aggregates, self.this_month_filter)
        self.assertEqual(total.get("cost", {}).get("total", {}).get("value", 0), current_totals.get("cost_total", 1))

        cmonth_str = DateHelper().this_month_start.strftime("%Y-%m")
        for data_item in data:
            month_val = data_item.get("date")
            month_data = data_item.get("services")
            self.assertEqual(month_val, cmonth_str)
            self.assertIsInstance(month_data, list)
            for month_item in month_data:
                service = month_item.get("service")
                self.assertIn(service, self.services)
                self.assertIsInstance(month_item.get("values"), list)

    def test_execute_query_by_filtered_service(self):
        """Test execute_query monthly breakdown by filtered service."""
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&group_by[service]=AmazonEC2"  # noqa: E501
        query_params = self.mocked_query_params(url, OCPAWSCostView)
        handler = OCPAWSReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get("total"))
        total = query_output.get("total")
        self.assertIsNotNone(total.get("cost"))

        aggregates = handler._mapper.report_type_map.get("aggregates")
        filt = copy.deepcopy(self.this_month_filter)
        filt["product_code"] = "AmazonEC2"
        current_totals = self.get_totals_by_time_scope(aggregates, filt)
        self.assertEqual(total.get("cost", {}).get("total", {}).get("value", 0), current_totals.get("cost_total", 1))

        cmonth_str = DateHelper().this_month_start.strftime("%Y-%m")
        for data_item in data:
            month_val = data_item.get("date")
            month_data = data_item.get("services")
            self.assertEqual(month_val, cmonth_str)
            self.assertIsInstance(month_data, list)
            for month_item in month_data:
                compute = month_item.get("service")
                self.assertEqual(compute, "AmazonEC2")
                self.assertIsInstance(month_item.get("values"), list)

    def test_query_by_partial_filtered_service(self):
        """Test execute_query monthly breakdown by filtered service."""
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&group_by[service]=eC2"  # noqa: E501
        query_params = self.mocked_query_params(url, OCPAWSCostView)
        handler = OCPAWSReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get("total"))
        total = query_output.get("total")
        self.assertIsNotNone(total.get("cost"))
        filt = copy.deepcopy(self.this_month_filter)
        filt["product_code__icontains"] = "ec2"
        aggregates = handler._mapper.report_type_map.get("aggregates")
        current_totals = self.get_totals_by_time_scope(aggregates, filt)
        self.assertEqual(total.get("cost", {}).get("total", {}).get("value", 0), current_totals.get("cost_total", 1))

        cmonth_str = DateHelper().this_month_start.strftime("%Y-%m")
        for data_item in data:
            month_val = data_item.get("date")
            month_data = data_item.get("services")
            self.assertEqual(month_val, cmonth_str)
            self.assertIsInstance(month_data, list)
            for month_item in month_data:
                compute = month_item.get("service")
                self.assertEqual(compute, "AmazonEC2")
                self.assertIsInstance(month_item.get("values"), list)

    def test_execute_query_current_month_by_account(self):
        """Test execute_query for current month on monthly breakdown by account."""
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&group_by[account]=*"  # noqa: E501
        query_params = self.mocked_query_params(url, OCPAWSCostView)
        handler = OCPAWSReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get("total"))
        total = query_output.get("total")
        self.assertIsNotNone(total.get("cost"))

        aggregates = handler._mapper.report_type_map.get("aggregates")
        current_totals = self.get_totals_by_time_scope(aggregates, self.this_month_filter)
        self.assertEqual(total.get("cost", {}).get("total", {}).get("value", 0), current_totals.get("cost_total", 1))

        cmonth_str = DateHelper().this_month_start.strftime("%Y-%m")
        for data_item in data:
            month_val = data_item.get("date", "not-a-date")
            month_data = data_item.get("accounts", "not-a-list")
            self.assertEqual(month_val, cmonth_str)
            self.assertIsInstance(month_data, list)
            for month_item in month_data:
                self.assertIsInstance(month_item.get("values"), list)

    def test_execute_query_by_account_by_service(self):
        """Test execute_query for current month breakdown by account by service."""
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&group_by[account]=*&group_by[service]=*"  # noqa: E501
        query_params = self.mocked_query_params(url, OCPAWSCostView)
        handler = OCPAWSReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get("total"))
        total = query_output.get("total")
        self.assertIsNotNone(total.get("cost"))

        aggregates = handler._mapper.report_type_map.get("aggregates")
        current_totals = self.get_totals_by_time_scope(aggregates, self.this_month_filter)
        self.assertEqual(total.get("cost", {}).get("total", {}).get("value", 0), current_totals.get("cost_total", 1))

        cmonth_str = DateHelper().this_month_start.strftime("%Y-%m")
        for data_item in data:
            month_val = data_item.get("date", "not-a-date")
            month_data = data_item.get("accounts", "not-a-string")
            self.assertEqual(month_val, cmonth_str)
            self.assertIsInstance(month_data, list)
            for month_item in month_data:
                self.assertIsInstance(month_item.get("services"), list)

    def test_check_view_filter_and_group_by_criteria(self):
        """Test that all filter and group by checks return the correct result."""
        good_group_by_options = ["account", "service", "region", "cluster", "product_family"]
        bad_group_by_options = ["project", "node"]

        for option in good_group_by_options:
            filter_keys = {option}
            group_by_keys = set()
            self.assertTrue(check_view_filter_and_group_by_criteria(filter_keys, group_by_keys))

            filter_keys = set()
            group_by_keys = {option}
            self.assertTrue(check_view_filter_and_group_by_criteria(filter_keys, group_by_keys))

        # Different group by and filter
        filter_keys = {"account"}
        group_by_keys = {"cluster"}
        self.assertTrue(check_view_filter_and_group_by_criteria(filter_keys, group_by_keys))

        # Multiple group bys
        filter_keys = set()
        group_by_keys = {"cluster", "account"}
        self.assertTrue(check_view_filter_and_group_by_criteria(filter_keys, group_by_keys))

        # Multiple filters
        filter_keys = {"cluster", "account"}
        group_by_keys = set()
        self.assertTrue(check_view_filter_and_group_by_criteria(filter_keys, group_by_keys))

        # Project and node unsupported
        for option in bad_group_by_options:
            filter_keys = {option}
            group_by_keys = set()
            self.assertFalse(check_view_filter_and_group_by_criteria(filter_keys, group_by_keys))

            filter_keys = set()
            group_by_keys = {option}
            self.assertFalse(check_view_filter_and_group_by_criteria(filter_keys, group_by_keys))

    def test_query_table(self):
        """Test that the correct view is assigned by query table property."""
        url = "?"
        query_params = self.mocked_query_params(url, OCPAWSCostView)
        handler = OCPAWSReportQueryHandler(query_params)
        self.assertEqual(handler.query_table, OCPAWSCostSummaryP)

        url = "?group_by[account]=*"
        query_params = self.mocked_query_params(url, OCPAWSCostView)
        handler = OCPAWSReportQueryHandler(query_params)
        self.assertEqual(handler.query_table, OCPAWSCostSummaryByAccountP)

        url = "?group_by[region]=*"
        query_params = self.mocked_query_params(url, OCPAWSCostView)
        handler = OCPAWSReportQueryHandler(query_params)
        self.assertEqual(handler.query_table, OCPAWSCostSummaryByRegionP)

        url = "?group_by[region]=*&group_by[account]=*"
        query_params = self.mocked_query_params(url, OCPAWSCostView)
        handler = OCPAWSReportQueryHandler(query_params)
        self.assertEqual(handler.query_table, OCPAWSCostSummaryByRegionP)

        url = "?group_by[service]=*"
        query_params = self.mocked_query_params(url, OCPAWSCostView)
        handler = OCPAWSReportQueryHandler(query_params)
        self.assertEqual(handler.query_table, OCPAWSCostSummaryByServiceP)

        url = "?group_by[service]=*&group_by[account]=*"
        query_params = self.mocked_query_params(url, OCPAWSCostView)
        handler = OCPAWSReportQueryHandler(query_params)
        self.assertEqual(handler.query_table, OCPAWSCostSummaryByServiceP)

        url = "?"
        query_params = self.mocked_query_params(url, OCPAWSInstanceTypeView)
        handler = OCPAWSReportQueryHandler(query_params)
        self.assertEqual(handler.query_table, OCPAWSComputeSummaryP)

        url = "?group_by[account]=*"
        query_params = self.mocked_query_params(url, OCPAWSInstanceTypeView)
        handler = OCPAWSReportQueryHandler(query_params)
        self.assertEqual(handler.query_table, OCPAWSComputeSummaryP)

        url = "?"
        query_params = self.mocked_query_params(url, OCPAWSStorageView)
        handler = OCPAWSReportQueryHandler(query_params)
        self.assertEqual(handler.query_table, OCPAWSStorageSummaryP)

        url = "?group_by[account]=*"
        query_params = self.mocked_query_params(url, OCPAWSStorageView)
        handler = OCPAWSReportQueryHandler(query_params)
        self.assertEqual(handler.query_table, OCPAWSStorageSummaryP)

        url = "?filter[service]=AmazonVPC,AmazonCloudFront,AmazonRoute53,AmazonAPIGateway"
        query_params = self.mocked_query_params(url, OCPAWSCostView)
        handler = OCPAWSReportQueryHandler(query_params)
        self.assertEqual(handler.query_table, OCPAWSNetworkSummaryP)

        url = "?filter[service]=AmazonVPC,AmazonCloudFront,AmazonRoute53,AmazonAPIGateway&group_by[account]=*"
        query_params = self.mocked_query_params(url, OCPAWSCostView)
        handler = OCPAWSReportQueryHandler(query_params)
        self.assertEqual(handler.query_table, OCPAWSNetworkSummaryP)

        url = (
            "?filter[service]=AmazonRDS,AmazonDynamoDB,AmazonElastiCache,AmazonNeptune,AmazonRedshift,AmazonDocumentDB"
        )
        query_params = self.mocked_query_params(url, OCPAWSCostView)
        handler = OCPAWSReportQueryHandler(query_params)
        self.assertEqual(handler.query_table, OCPAWSDatabaseSummaryP)

        url = (
            "?filter[service]=AmazonRDS,AmazonDynamoDB,AmazonElastiCache,AmazonNeptune,AmazonRedshift,AmazonDocumentDB"
            "&group_by[account]=*"
        )
        query_params = self.mocked_query_params(url, OCPAWSCostView)
        handler = OCPAWSReportQueryHandler(query_params)
        self.assertEqual(handler.query_table, OCPAWSDatabaseSummaryP)

    def test_source_uuid_mapping(self):  # noqa: C901
        """Test source_uuid is mapped to the correct source."""
        endpoints = [OCPAWSCostView, OCPAWSInstanceTypeView, OCPAWSStorageView]
        with tenant_context(self.tenant):
            expected_source_uuids = list(AWSCostEntryBill.objects.distinct().values_list("provider_id", flat=True))
        source_uuid_list = []
        for endpoint in endpoints:
            urls = ["?"]
            if endpoint == OCPAWSCostView:
                urls.extend(["?group_by[account]=*", "?group_by[service]=*", "?group_by[region]=*"])
            for url in urls:
                query_params = self.mocked_query_params(url, endpoint)
                handler = OCPAWSReportQueryHandler(query_params)
                query_output = handler.execute_query()
                for dictionary in query_output.get("data"):
                    for _, value in dictionary.items():
                        if isinstance(value, list):
                            for item in value:
                                if isinstance(item, dict):
                                    if "values" in item.keys():
                                        value = item["values"][0]
                                        source_uuid_list.extend(value.get("source_uuid"))
        self.assertNotEquals(source_uuid_list, [])
        for source_uuid in source_uuid_list:
            self.assertIn(source_uuid, expected_source_uuids)

    def test_ocp_aws_date_order_by_cost_desc(self):
        """Test that order of every other date matches the order of the `order_by` date."""
        yesterday = self.dh.yesterday.date()
        url = f"?order_by[cost]=desc&order_by[date]={yesterday}&group_by[service]=*"
        query_params = self.mocked_query_params(url, OCPAWSCostView)
        handler = OCPAWSReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")

        svc_annotations = handler.annotations.get("service")
        cost_annotation = handler.report_annotations.get("cost_total")
        with tenant_context(self.tenant):
            expected = list(
                OCPAWSCostSummaryByServiceP.objects.filter(usage_start=str(yesterday))
                .annotate(service=svc_annotations)
                .values("service")
                .annotate(cost=cost_annotation)
                .order_by("-cost")
            )
        correctlst = [service.get("service") for service in expected]
        for element in data:
            lst = [service.get("service") for service in element.get("services", [])]
            if lst and correctlst:
                self.assertEqual(correctlst, lst)

    def test_ocp_aws_date_incorrect_date(self):
        wrong_date = "200BC"
        url = f"?order_by[cost]=desc&order_by[date]={wrong_date}&group_by[service]=*"
        with self.assertRaises(ValidationError):
            self.mocked_query_params(url, OCPAWSCostView)

    def test_ocp_aws_out_of_range_under_date(self):
        wrong_date = materialized_view_month_start() - timedelta(days=1)
        url = f"?order_by[cost]=desc&order_by[date]={wrong_date}&group_by[service]=*"
        with self.assertRaises(ValidationError):
            self.mocked_query_params(url, OCPAWSCostView)

    def test_ocp_aws_out_of_range_over_date(self):
        wrong_date = DateHelper().today.date() + timedelta(days=1)
        url = f"?order_by[cost]=desc&order_by[date]={wrong_date}&group_by[service]=*"
        with self.assertRaises(ValidationError):
            self.mocked_query_params(url, OCPAWSCostView)
