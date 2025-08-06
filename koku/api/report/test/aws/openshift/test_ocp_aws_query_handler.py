#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the Report Queries."""
import copy
from datetime import timedelta

from dateutil.relativedelta import relativedelta
from django.urls import reverse
from django_tenants.utils import tenant_context
from rest_framework.exceptions import ValidationError

from api.iam.test.iam_test_case import IamTestCase
from api.report.aws.openshift.query_handler import OCPAWSReportQueryHandler
from api.report.aws.openshift.serializers import OCPAWSExcludeSerializer
from api.report.aws.openshift.view import OCPAWSCostView
from api.report.aws.openshift.view import OCPAWSInstanceTypeView
from api.report.aws.openshift.view import OCPAWSStorageView
from api.report.constants import AWS_CATEGORY_PREFIX
from api.report.queries import check_view_filter_and_group_by_criteria
from api.report.test.util.constants import AWS_CONSTANTS
from api.tags.aws.openshift.queries import OCPAWSTagQueryHandler
from api.tags.aws.openshift.view import OCPAWSTagView
from api.utils import DateHelper
from api.utils import materialized_view_month_start
from reporting.models import AWSCostEntryBill
from reporting.models import OCPAWSComputeSummaryP
from reporting.models import OCPAWSCostLineItemProjectDailySummaryP
from reporting.models import OCPAWSCostSummaryByAccountP
from reporting.models import OCPAWSCostSummaryByRegionP
from reporting.models import OCPAWSCostSummaryByServiceP
from reporting.models import OCPAWSCostSummaryP
from reporting.models import OCPAWSDatabaseSummaryP
from reporting.models import OCPAWSNetworkSummaryP
from reporting.models import OCPAWSStorageSummaryP


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
        self.aws_category_tuple = AWS_CONSTANTS["cost_category"]

        with tenant_context(self.tenant):
            self.services = OCPAWSCostLineItemProjectDailySummaryP.objects.values("product_code").distinct()
            self.services = [entry.get("product_code") for entry in self.services]

    def get_totals_by_time_scope(self, handler, filters=None):
        if filters is None:
            filters = self.ten_day_filter
        aggregates = handler._mapper.report_type_map.get("aggregates")
        with tenant_context(self.tenant):
            return (
                OCPAWSCostLineItemProjectDailySummaryP.objects.filter(**filters)
                .annotate(**handler.annotations)
                .aggregate(**aggregates)
            )

    def test_execute_sum_query_storage(self):
        """Test that the sum query runs properly."""
        url = "?"
        query_params = self.mocked_query_params(url, OCPAWSStorageView)
        handler = OCPAWSReportQueryHandler(query_params)
        filt = {"product_family__contains": "Storage"}
        filt.update(self.ten_day_filter)
        current_totals = self.get_totals_by_time_scope(handler, filt)
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

        current_totals = self.get_totals_by_time_scope(handler, self.this_month_filter)
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

        current_totals = self.get_totals_by_time_scope(handler, self.this_month_filter)
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

        current_totals = self.get_totals_by_time_scope(handler, self.this_month_filter)
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

        filt = copy.deepcopy(self.this_month_filter)
        filt["product_code"] = "AmazonEC2"
        current_totals = self.get_totals_by_time_scope(handler, filt)
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
        current_totals = self.get_totals_by_time_scope(handler, filt)
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

        current_totals = self.get_totals_by_time_scope(handler, self.this_month_filter)
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

        current_totals = self.get_totals_by_time_scope(handler, self.this_month_filter)
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
        self.assertNotEqual(source_uuid_list, [])
        for source_uuid in source_uuid_list:
            self.assertIn(source_uuid, expected_source_uuids)

    def test_ocp_aws_date_order_by_cost_desc(self):
        """Test that order of every other date matches the order of the `order_by` date."""
        yesterday = self.dh.yesterday.date()
        url = f"?filter[limit]=10&filter[offset]=0&order_by[cost]=desc&order_by[date]={yesterday}&group_by[service]=*"
        query_params = self.mocked_query_params(url, OCPAWSCostView)
        handler = OCPAWSReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")

        svc_annotations = handler.annotations.get("service")
        exch_annotations = handler.annotations.get("exchange_rate")
        cost_annotation = handler.report_annotations.get("cost_total")
        with tenant_context(self.tenant):
            expected = list(
                OCPAWSCostSummaryByServiceP.objects.filter(usage_start=str(yesterday))
                .annotate(service=svc_annotations, exchange_rate=exch_annotations)
                .values("service")
                .annotate(cost=cost_annotation)
                .order_by("-cost")
            )
        tested = False
        ranking_map = {}
        count = 1
        for service in expected:
            ranking_map[service.get("service")] = count
            count += 1
        for element in data:
            previous = 0
            for service in element.get("services"):
                service_name = service.get("service")
                if service_name in ranking_map.keys():
                    self.assertGreaterEqual(ranking_map[service_name], previous)
                    previous = ranking_map[service_name]
                    tested = True
        self.assertTrue(tested)

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

    def test_ocp_aws_date_with_no_data(self):
        # This test will group by a date that is out of range for data generated.
        # The data will still return data because other dates will still generate data.
        yesterday = self.dh.yesterday.date()
        yesterday_month = self.dh.yesterday - relativedelta(months=2)

        url = f"?group_by[service]=*&order_by[cost]=desc&order_by[date]={yesterday_month.date()}&end_date={yesterday}&start_date={yesterday_month.date()}"  # noqa: E501
        query_params = self.mocked_query_params(url, OCPAWSCostView)
        handler = OCPAWSReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")
        self.assertIsNotNone(data)

    def test_exclude_functionality(self):
        """Test that the exclude feature works for all options."""
        exclude_opts = list(OCPAWSExcludeSerializer._opfields)
        # az needed to be tested separate cause
        # no info was available in the response for az, inbstance_type, stoprage_type
        exclude_opts.remove("az")
        exclude_opts.remove("instance_type")
        exclude_opts.remove("storage_type")
        for exclude_opt in exclude_opts:
            for view in [OCPAWSCostView, OCPAWSStorageView, OCPAWSInstanceTypeView]:
                with self.subTest(exclude_opt):
                    # Grab overall value
                    overall_url = f"?group_by[{exclude_opt}]=*"
                    query_params = self.mocked_query_params(overall_url, view)
                    handler = OCPAWSReportQueryHandler(query_params)
                    overall_output = handler.execute_query()
                    overall_total = handler.query_sum.get("cost", {}).get("total", {}).get("value")
                    opt_dict = overall_output.get("data", [{}])[0]
                    opt_dict = opt_dict.get(f"{exclude_opt}s")[0]
                    opt_value = opt_dict.get(exclude_opt)
                    # Grab filtered value
                    filtered_url = f"?group_by[{exclude_opt}]=*&filter[{exclude_opt}]={opt_value}"
                    query_params = self.mocked_query_params(filtered_url, view)
                    handler = OCPAWSReportQueryHandler(query_params)
                    handler.execute_query()
                    filtered_total = handler.query_sum.get("cost", {}).get("total", {}).get("value")
                    expected_total = overall_total - filtered_total
                    # Test exclude
                    exclude_url = f"?group_by[{exclude_opt}]=*&exclude[{exclude_opt}]={opt_value}"
                    query_params = self.mocked_query_params(exclude_url, view)
                    handler = OCPAWSReportQueryHandler(query_params)
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

    def test_exclude_availability_zone(self):
        """Test that the exclude feature works for all options."""
        exclude_opt = "az"
        for view in [OCPAWSCostView, OCPAWSStorageView, OCPAWSInstanceTypeView]:
            filters = {"usage_start__gte": str(self.dh.n_days_ago(self.dh.today, 8).date())}
            with self.subTest(view=view):
                with tenant_context(self.tenant):
                    if view == OCPAWSStorageView:
                        filters["product_family__icontains"] = "Storage"
                    elif view == OCPAWSInstanceTypeView:
                        filters["instance_type__isnull"] = False
                    az_list = (
                        OCPAWSCostLineItemProjectDailySummaryP.objects.filter(**filters)
                        .values_list("availability_zone", flat=True)
                        .distinct()
                    )
                    opt_value = az_list[0]
                # Grab overall value
                overall_url = f"?group_by[{exclude_opt}]=*"
                query_params = self.mocked_query_params(overall_url, view)
                handler = OCPAWSReportQueryHandler(query_params)
                handler.execute_query()
                overall_total = handler.query_sum.get("cost", {}).get("total", {}).get("value")
                # Grab filtered value
                filtered_url = f"?group_by[{exclude_opt}]=*&filter[{exclude_opt}]={opt_value}"
                query_params = self.mocked_query_params(filtered_url, view)
                handler = OCPAWSReportQueryHandler(query_params)
                handler.execute_query()
                filtered_total = handler.query_sum.get("cost", {}).get("total", {}).get("value")
                expected_total = overall_total - filtered_total
                # Test exclude
                exclude_url = f"?group_by[{exclude_opt}]=*&exclude[{exclude_opt}]={opt_value}"
                query_params = self.mocked_query_params(exclude_url, view)
                handler = OCPAWSReportQueryHandler(query_params)
                self.assertIsNotNone(handler.query_exclusions)
                handler.execute_query()
                excluded_total = handler.query_sum.get("cost", {}).get("total", {}).get("value")
                self.assertAlmostEqual(expected_total, excluded_total, 6)
                self.assertNotEqual(overall_total, excluded_total)

    def test_exclude_tags(self):
        """Test that the exclude works for our tags."""
        query_params = self.mocked_query_params("?", OCPAWSTagView)
        handler = OCPAWSTagQueryHandler(query_params)
        tags = handler.get_tags()
        group_tag = None
        check_no_option = False
        exclude_vals = []
        for tag_dict in tags:
            if len(tag_dict.get("values")) > len(exclude_vals):
                group_tag = tag_dict.get("key")
                exclude_vals = tag_dict.get("values")
        url = f"?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=daily&group_by[tag:{group_tag}]=*"  # noqa: E501
        query_params = self.mocked_query_params(url, OCPAWSCostView)
        handler = OCPAWSReportQueryHandler(query_params)
        # spot check for no-option
        data = handler.execute_query().get("data")
        if f"No-{group_tag}" in str(data):
            check_no_option = True
        previous_total = handler.query_sum.get("cost", {}).get("total", {}).get("value")
        for exclude_value in exclude_vals:
            url += f"&exclude[tag:{group_tag}]={exclude_value}"
            query_params = self.mocked_query_params(url, OCPAWSCostView)
            handler = OCPAWSReportQueryHandler(query_params)
            data = handler.execute_query()
            if check_no_option:
                self.assertIn(f"No-{group_tag}", str(data))
            current_total = handler.query_sum.get("cost", {}).get("total", {}).get("value")
            self.assertLess(current_total, previous_total)
            previous_total = current_total

    def test_multi_exclude_functionality(self):
        """Test that the exclude feature works for all options."""
        exclude_opts = list(OCPAWSExcludeSerializer._opfields)
        exclude_opts.remove("az")
        exclude_opts.remove("instance_type")
        exclude_opts.remove("storage_type")
        for ex_opt in exclude_opts:
            base_url = f"?group_by[{ex_opt}]=*&filter[time_scope_units]=month&filter[resolution]=monthly&filter[time_scope_value]=-1"  # noqa: E501
            for view in [OCPAWSCostView, OCPAWSStorageView, OCPAWSInstanceTypeView]:
                query_params = self.mocked_query_params(base_url, view)
                handler = OCPAWSReportQueryHandler(query_params)
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
                    handler = OCPAWSReportQueryHandler(query_params)
                    self.assertIsNotNone(handler.query_exclusions)
                    excluded_output = handler.execute_query()
                    excluded_data = excluded_output.get("data")
                    self.assertIsNotNone(excluded_data)
                    for date_dict in excluded_data:
                        grouping_list = date_dict.get(f"{ex_opt}s", [])
                        self.assertIsNotNone(grouping_list)
                        for group_dict in grouping_list:
                            self.assertNotIn(group_dict.get(ex_opt), [exclude_one, exclude_two])

    def test_ocp_aws_category_api_options_monthly(self):
        """Test execute_query for current month on monthly filter aws_category"""
        base_url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly"
        aws_cat_dict = self.aws_category_tuple[0]
        aws_cat_key = list(aws_cat_dict.keys())[0]
        filter_args = {
            "usage_start__gte": self.dh.this_month_start,
            "usage_start__lte": self.dh.today,
            f"aws_cost_category__{aws_cat_key}__icontains": aws_cat_dict[aws_cat_key],
        }
        group_by_key = f"&group_by[{AWS_CATEGORY_PREFIX}{aws_cat_key}]=*"
        filter_key = f"&filter[{AWS_CATEGORY_PREFIX}{aws_cat_key}]={aws_cat_dict[aws_cat_key]}"
        exclude_key = f"&exclude[{AWS_CATEGORY_PREFIX}{aws_cat_key}]={aws_cat_dict[aws_cat_key]}"
        results = {}
        filter_value = 0
        for sub_url in [group_by_key, filter_key, exclude_key]:
            with self.subTest(sub_url=sub_url):
                url = base_url + sub_url
                query_params = self.mocked_query_params(
                    url, OCPAWSCostView, path=reverse("reports-openshift-aws-costs")
                )
                handler = OCPAWSReportQueryHandler(query_params)
                if sub_url == filter_key:
                    filter_value = self.get_totals_by_time_scope(handler, filter_args)
                query_output = handler.execute_query()
                data = query_output.get("data")
                total_cost_total = query_output.get("total", {}).get("cost", {}).get("total")
                self.assertIsNotNone(data)
                self.assertIsNotNone(total_cost_total)
                results[sub_url] = total_cost_total.get("value")
        # Validate filter
        self.assertLess(results[filter_key], results[group_by_key])
        self.assertEqual(results[filter_key], filter_value.get("cost_total"))
        # Validate Exclude
        excluded_expected = results[group_by_key] - results[filter_key]
        self.assertEqual(results[exclude_key], excluded_expected)

    def test_ocp_aws_category_multiple_filter(self):
        """Test execute_query for current month on monthly filter aws_category"""
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly"
        # build url & expected values
        expected_value = []
        filter_args = []
        for idx in [0, 1]:
            dikt = self.aws_category_tuple[idx]
            key = list(dikt.keys())[0]
            substring = f"&filter[or:{AWS_CATEGORY_PREFIX}{key}]={dikt[key]}"
            url = url + substring
            filter_args.append(
                {
                    "usage_start__gte": self.dh.this_month_start,
                    "usage_start__lte": self.dh.today,
                    f"aws_cost_category__{key}__icontains": dikt[key],
                }
            )

        query_params = self.mocked_query_params(url, OCPAWSCostView, path=reverse("reports-openshift-aws-costs"))
        handler = OCPAWSReportQueryHandler(query_params)
        for filter_arg in filter_args:
            expected_value.append(self.get_totals_by_time_scope(handler, filter_arg).get("cost_total"))
        query_output = handler.execute_query()
        data = query_output.get("data")
        total_cost_total = query_output.get("total", {}).get("cost", {}).get("total", {}).get("value")
        self.assertIsNotNone(total_cost_total)
        self.assertIsNotNone(data)
        self.assertAlmostEqual(sum(expected_value), total_cost_total)

    def test_ocp_aws_category_multiple_exclude(self):
        """Test execute_query for current month on monthly filter aws_category"""
        base_url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly"
        exclude_url = base_url
        # build url & expected values
        expected_value = []
        filter_args = []
        for idx in [0, 1]:
            dikt = self.aws_category_tuple[idx]
            key = list(dikt.keys())[0]
            exclude_url += f"&exclude[or:{AWS_CATEGORY_PREFIX}{key}]={dikt[key]}"
            filter_args.append(
                {
                    "usage_start__gte": self.dh.this_month_start,
                    "usage_start__lte": self.dh.today,
                    f"aws_cost_category__{key}__icontains": dikt[key],
                }
            )
        aws_cat_dict = self.aws_category_tuple[0]
        aws_cat_key = list(aws_cat_dict.keys())[0]
        group_url = base_url + f"&group_by[{AWS_CATEGORY_PREFIX}{aws_cat_key}]=*"
        results = {}
        for url in [exclude_url, group_url]:
            query_params = self.mocked_query_params(url, OCPAWSCostView, path=reverse("reports-openshift-aws-costs"))
            handler = OCPAWSReportQueryHandler(query_params)
            if expected_value == []:
                for filter_arg in filter_args:
                    expected_value.append(self.get_totals_by_time_scope(handler, filter_arg).get("cost_total"))
            query_output = handler.execute_query()
            data = query_output.get("data")
            total_cost_total = query_output.get("total", {}).get("cost", {}).get("total", {}).get("value")
            results[url] = total_cost_total
        difference = results[group_url] - results[exclude_url]
        self.assertIsNotNone(total_cost_total)
        self.assertIsNotNone(data)
        self.assertAlmostEqual(sum(expected_value), difference)
