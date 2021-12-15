#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the Report Queries."""
import logging
from collections import defaultdict
from collections import OrderedDict
from datetime import datetime
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch
from unittest.mock import PropertyMock

from dateutil.relativedelta import relativedelta
from django.db.models import Count
from django.db.models import DecimalField
from django.db.models import F
from django.db.models import Func
from django.db.models import Sum
from django.db.models import Value
from django.db.models.functions import Coalesce
from django.urls import reverse
from rest_framework.exceptions import ValidationError
from tenant_schemas.utils import tenant_context

from api.iam.test.iam_test_case import IamTestCase
from api.report.aws.query_handler import AWSReportQueryHandler
from api.report.aws.view import AWSCostView
from api.report.aws.view import AWSInstanceTypeView
from api.report.aws.view import AWSStorageView
from api.report.queries import strip_tag_prefix
from api.report.test.aws.test_views import _calculate_accounts_and_subous
from api.tags.aws.queries import AWSTagQueryHandler
from api.tags.aws.view import AWSTagView
from api.utils import DateHelper
from api.utils import materialized_view_month_start
from reporting.models import AWSComputeSummaryByAccountP
from reporting.models import AWSComputeSummaryByRegionP
from reporting.models import AWSComputeSummaryByServiceP
from reporting.models import AWSComputeSummaryP
from reporting.models import AWSCostEntryBill
from reporting.models import AWSCostEntryLineItemDailySummary
from reporting.models import AWSCostEntryProduct
from reporting.models import AWSCostSummaryByAccountP
from reporting.models import AWSCostSummaryByRegionP
from reporting.models import AWSCostSummaryByServiceP
from reporting.models import AWSCostSummaryP
from reporting.models import AWSDatabaseSummaryP
from reporting.models import AWSNetworkSummaryP
from reporting.models import AWSStorageSummaryByAccountP
from reporting.models import AWSStorageSummaryByRegionP
from reporting.models import AWSStorageSummaryByServiceP
from reporting.models import AWSStorageSummaryP
from reporting.provider.aws.models import AWSOrganizationalUnit

LOG = logging.getLogger(__name__)


def get_account_ailases():
    """Get the account aliases and return them in a list."""
    accounts = AWSCostEntryLineItemDailySummary.objects.values(
        "account_alias__account_alias", "usage_account_id"
    ).distinct()
    account_aliases = []
    account_alias_mapping = {}
    for account in accounts:
        account_al = account.get("account_alias__account_alias")
        account_aliases.append(account_al)
        account_alias_mapping[account.get("usage_account_id")] = account_al
    return account_aliases, account_alias_mapping


class AWSReportQueryTest(IamTestCase):
    """Tests the report queries."""

    def setUp(self):
        """Set up the customer view tests."""
        self.dh = DateHelper()
        super().setUp()
        with tenant_context(self.tenant):
            self.accounts = AWSCostEntryLineItemDailySummary.objects.values("usage_account_id").distinct()
            self.accounts = [entry.get("usage_account_id") for entry in self.accounts]

            self.services = AWSCostEntryLineItemDailySummary.objects.values("product_code").distinct()
            self.services = [entry.get("product_code") for entry in self.services]

            self.availability_zone = (
                AWSCostEntryLineItemDailySummary.objects.filter(
                    availability_zone__isnull=False, usage_start__gte=self.dh.this_month_start
                )
                .values("availability_zone")
                .distinct()
                .first()
                .get("availability_zone")
            )
            self.availability_zone_count_cur_mo = (
                AWSCostEntryLineItemDailySummary.objects.filter(usage_start__gte=self.dh.this_month_start)
                .distinct()
                .values_list("availability_zone")
                .count()
            )
            self.region = AWSCostEntryLineItemDailySummary.objects.values("region").distinct().first().get("region")
            self.region_count = AWSCostEntryLineItemDailySummary.objects.aggregate(Count("region", distinct=True)).get(
                "region__count"
            )
            self.account_alias = (
                AWSCostEntryLineItemDailySummary.objects.values("account_alias__account_alias")
                .distinct()
                .first()
                .get("account_alias__account_alias")
            )
            self.account_aliases = get_account_ailases()[0]
            self.account_alias_mapping = get_account_ailases()[1]
            self.organizational_unit = (
                AWSCostEntryLineItemDailySummary.objects.values("organizational_unit__org_unit_id")
                .distinct()
                .first()
                .get("organizational_unit__org_unit_id")
            )
            # this mapping is based on the aws_org_tree.yml that populates the data for tests
            # it takes into account the sub orgs that should show up for each org based on
            # whether or not they have accounts under them in the range
            # for example, OU_002 & 0U_004 do not show up under R_001 because OU_004 was deleted
            # before the range began & OU_002 had no accounts during the range
            self.ou_to_account_subou_map = {
                "R_001": {"accounts": ["9999999999990"], "org_units": ["OU_001"], "org_unit_path": "R_001"},
                "OU_001": {
                    "accounts": ["9999999999991", "9999999999992"],
                    "org_units": [],
                    "org_unit_path": "R_001&OU_001",
                },
                "OU_002": {"accounts": [], "org_units": ["OU_003"], "org_unit_path": "R_001&OU_002"},
                "OU_003": {"accounts": ["9999999999993"], "org_units": [], "org_unit_path": "R_001&OU_002&OU_003"},
                "OU_004": {"accounts": [], "org_units": [], "org_unit_path": "R_001&OU_004"},
                "OU_005": {"accounts": [], "org_units": [], "org_unit_path": "R_001&OU_001&OU_005"},
            }

    def calculate_total(self, handler):
        """Return expected total cost for the query."""
        filters = handler._get_filter()
        with tenant_context(self.tenant):
            return (
                AWSCostEntryLineItemDailySummary.objects.filter(filters)
                .aggregate(
                    cost=Sum(
                        Coalesce(F("unblended_cost"), Value(0, output_field=DecimalField()))
                        + Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))
                    )
                )
                .get("cost")
            )

    def test_apply_group_null_label(self):
        """Test adding group label for null values."""
        url = "?"
        query_params = self.mocked_query_params(url, AWSCostView)
        handler = AWSReportQueryHandler(query_params)
        groups = ["region"]
        data = {"region": None, "units": "USD"}
        expected = {"region": "no-region", "units": "USD"}
        out_data = handler._apply_group_null_label(data, groups)
        self.assertEqual(expected, out_data)

        data = {"region": "us-east", "units": "USD"}
        expected = {"region": "us-east", "units": "USD"}
        out_data = handler._apply_group_null_label(data, groups)
        self.assertEqual(expected, out_data)

        groups = []
        out_data = handler._apply_group_null_label(data, groups)
        self.assertEqual(expected, out_data)

    def test_transform_null_group(self):
        """Test transform data with null group value."""
        url = "?"
        query_params = self.mocked_query_params(url, AWSCostView)
        handler = AWSReportQueryHandler(query_params)
        groups = ["region"]
        group_index = 0
        data = {None: [{"region": "no-region", "units": "USD"}]}
        expected = [{"region": "no-region", "values": [{"region": "no-region", "units": "USD"}]}]
        out_data = handler._transform_data(groups, group_index, data)
        self.assertEqual(expected, out_data)

        data = {"us-east": [{"region": "us-east", "units": "USD"}]}
        expected = [{"region": "us-east", "values": [{"region": "us-east", "units": "USD"}]}]
        out_data = handler._transform_data(groups, group_index, data)
        self.assertEqual(expected, out_data)

        data = {None: {"region": "no-region", "units": "USD"}}
        expected = [{"region": "no-region", "values": {"region": "no-region", "units": "USD"}}]
        out_data = handler._transform_data(groups, group_index, data)
        self.assertEqual(expected, out_data)

    def test_transform_null_group_with_limit(self):
        """Test transform data with null group value."""
        url = "?filter[limit]=1"
        query_params = self.mocked_query_params(url, AWSCostView)
        handler = AWSReportQueryHandler(query_params)
        groups = ["region"]
        group_index = 0
        data = {None: [{"region": "no-region", "units": "USD"}]}
        expected = [{"region": "no-region", "values": [{"region": "no-region", "units": "USD"}]}]
        out_data = handler._transform_data(groups, group_index, data)
        self.assertEqual(expected, out_data)

        data = {"us-east": [{"region": "us-east", "units": "USD"}]}
        expected = [{"region": "us-east", "values": [{"region": "us-east", "units": "USD"}]}]
        out_data = handler._transform_data(groups, group_index, data)
        self.assertEqual(expected, out_data)

        data = {None: {"region": "no-region", "units": "USD"}}
        expected = [{"region": "no-region", "values": {"region": "no-region", "units": "USD"}}]
        out_data = handler._transform_data(groups, group_index, data)
        self.assertEqual(expected, out_data)

    def test_get_group_by_with_group_by_and_limit_params(self):
        """Test the _get_group_by method with limit and group by params."""
        expected = ["account"]
        url = "?group_by[account]=*&filter[limit]=1"
        query_params = self.mocked_query_params(url, AWSInstanceTypeView)
        handler = AWSReportQueryHandler(query_params)
        group_by = handler._get_group_by()
        self.assertEqual(expected, group_by)

    def test_get_group_by_with_group_by_and_no_limit_params(self):
        """Test the _get_group_by method with group by params."""
        expected = ["account", "instance_type"]
        url = "?group_by[account]=*"
        query_params = self.mocked_query_params(url, AWSInstanceTypeView)
        handler = AWSReportQueryHandler(query_params)
        group_by = handler._get_group_by()
        self.assertEqual(expected, group_by)

    def test_get_group_by_with_limit_and_no_group_by_params(self):
        """Test the _get_group_by method with limit params."""
        expected = ["instance_type"]
        url = "?filter[limit]=1"
        query_params = self.mocked_query_params(url, AWSInstanceTypeView)
        handler = AWSReportQueryHandler(query_params)
        group_by = handler._get_group_by()
        self.assertEqual(expected, group_by)

    def test_get_resolution_empty_day_time_scope(self):
        """Test get_resolution returns default when time_scope is month."""
        url = "?filter[time_scope_value]=-10"
        query_params = self.mocked_query_params(url, AWSCostView)
        handler = AWSReportQueryHandler(query_params)
        self.assertEqual(handler.resolution, "daily")

    def test_get_time_scope_units_empty_default(self):
        """Test get_time_scope_units returns default when query params are empty."""
        url = "?"
        query_params = self.mocked_query_params(url, AWSCostView)
        handler = AWSReportQueryHandler(query_params)
        self.assertEqual(handler.get_time_scope_units(), "day")

    def test_get_time_scope_units_existing_value(self):
        """Test get_time_scope_units returns month when time_scope is month."""
        url = "?filter[time_scope_units]=month"
        query_params = self.mocked_query_params(url, AWSCostView)
        handler = AWSReportQueryHandler(query_params)
        self.assertEqual(handler.get_time_scope_units(), "month")

    def test_get_time_scope_value_empty_default(self):
        """Test get_time_scope_value returns default when query params are empty."""
        url = "?"
        query_params = self.mocked_query_params(url, AWSCostView)
        handler = AWSReportQueryHandler(query_params)
        self.assertEqual(handler.get_time_scope_value(), -10)

    def test_get_time_scope_value_existing_value(self):
        """Test validationerror for invalid time_scope_value."""
        url = "?filter[time_scope_value]=9999"
        with self.assertRaises(ValidationError):
            self.mocked_query_params(url, AWSCostView)

    def test_get_time_frame_filter_current_month(self):
        """Test _get_time_frame_filter for current month."""
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=daily"
        query_params = self.mocked_query_params(url, AWSCostView)
        handler = AWSReportQueryHandler(query_params)
        start = handler.start_datetime
        end = handler.end_datetime
        interval = handler.time_interval
        self.assertEqual(start, DateHelper().this_month_start)
        self.assertEqual(end.date(), DateHelper().today.date())
        self.assertIsInstance(interval, list)
        self.assertEqual(len(interval), DateHelper().today.day)

    def test_get_time_frame_filter_previous_month(self):
        """Test _get_time_frame_filter for previous month."""
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-2&filter[resolution]=daily"
        query_params = self.mocked_query_params(url, AWSCostView)
        handler = AWSReportQueryHandler(query_params)
        start = handler.start_datetime
        end = handler.end_datetime
        interval = handler.time_interval
        self.assertEqual(start, DateHelper().last_month_start)
        self.assertEqual(end, DateHelper().last_month_end)
        self.assertIsInstance(interval, list)
        self.assertTrue(len(interval) >= 28)

    def test_get_time_frame_filter_2_months_ago(self):
        """Test _get_time_frame_filter for 2 months ago."""
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-3&filter[resolution]=daily"
        query_params = self.mocked_query_params(url, AWSCostView)
        handler = AWSReportQueryHandler(query_params)
        start = handler.start_datetime
        end = handler.end_datetime
        interval = handler.time_interval
        dh = DateHelper()
        self.assertEqual(start, dh.relative_month_start(-2))
        self.assertEqual(end, dh.relative_month_end(-2))
        self.assertIsInstance(interval, list)
        self.assertEqual(len(interval), end.day)

    def test_get_time_frame_filter_90_days_ago(self):
        """Test _get_time_frame_filter for 90 days ago month."""
        url = "?filter[time_scope_units]=day&filter[time_scope_value]=-90&filter[resolution]=daily"
        query_params = self.mocked_query_params(url, AWSCostView)
        handler = AWSReportQueryHandler(query_params)
        start = handler.start_datetime.date()
        end = handler.end_datetime.date()
        interval = handler.time_interval
        dh = DateHelper()
        today = dh.today
        self.assertEqual(start, dh.n_days_ago(today, 89).date())
        self.assertEqual(end, dh.today.date())
        self.assertIsInstance(interval, list)
        self.assertEqual(len(interval), 90)

    def test_get_time_frame_filter_last_ten(self):
        """Test _get_time_frame_filter for last ten days."""
        url = "?filter[time_scope_units]=day&filter[time_scope_value]=-10&filter[resolution]=daily"
        query_params = self.mocked_query_params(url, AWSCostView)
        handler = AWSReportQueryHandler(query_params)
        dh = DateHelper()
        nine_days_ago = dh.n_days_ago(dh.today, 9)
        start = handler.start_datetime.replace(hour=0, minute=0, second=0, microsecond=0)
        end = handler.end_datetime.replace(hour=0, minute=0, second=0, microsecond=0)
        interval = handler.time_interval
        self.assertEqual(start, nine_days_ago)
        self.assertEqual(end, dh.today)
        self.assertIsInstance(interval, list)
        self.assertTrue(len(interval) == 10)

    def test_get_time_frame_filter_last_thirty(self):
        """Test _get_time_frame_filter for last thirty days."""
        url = "?filter[time_scope_units]=day&filter[time_scope_value]=-30&filter[resolution]=daily"
        query_params = self.mocked_query_params(url, AWSCostView)
        handler = AWSReportQueryHandler(query_params)
        dh = DateHelper()
        twenty_nine_days_ago = dh.n_days_ago(dh.today, 29)
        start = handler.start_datetime.replace(hour=0, minute=0, second=0, microsecond=0)
        end = handler.end_datetime.replace(hour=0, minute=0, second=0, microsecond=0)
        interval = handler.time_interval
        self.assertEqual(start, twenty_nine_days_ago)
        self.assertEqual(end, dh.today)
        self.assertIsInstance(interval, list)
        self.assertTrue(len(interval) == 30)

    def test_execute_take_defaults(self):
        """Test execute_query for current month on daily breakdown."""
        url = "?"
        query_params = self.mocked_query_params(url, AWSCostView)
        handler = AWSReportQueryHandler(query_params)
        query_output = handler.execute_query()
        self.assertIsNotNone(query_output.get("data"))
        self.assertIsNotNone(query_output.get("total"))
        total = query_output.get("total")
        self.assertIsNotNone(total.get("cost"))

    def test_execute_query_current_month_daily(self):
        """Test execute_query for current month on daily breakdown."""
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=daily"
        query_params = self.mocked_query_params(url, AWSCostView)
        handler = AWSReportQueryHandler(query_params)
        query_output = handler.execute_query()
        total_cost_total = query_output.get("total", {}).get("cost", {}).get("total")
        self.assertIsNotNone(total_cost_total)
        self.assertAlmostEqual(total_cost_total.get("value"), self.calculate_total(handler), 6)

    def test_execute_query_current_month_monthly(self):
        """Test execute_query for current month on monthly breakdown."""
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly"
        query_params = self.mocked_query_params(url, AWSCostView)
        handler = AWSReportQueryHandler(query_params)
        query_output = handler.execute_query()
        total_cost_total = query_output.get("total", {}).get("cost", {}).get("total")
        self.assertIsNotNone(query_output.get("data"))
        self.assertIsNotNone(query_output.get("total"))
        self.assertAlmostEqual(total_cost_total.get("value"), self.calculate_total(handler), 6)

    def test_execute_query_current_month_by_service(self):
        """Test execute_query for current month on monthly breakdown by service."""
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&group_by[service]=*"  # noqa: E501
        query_params = self.mocked_query_params(url, AWSCostView)
        handler = AWSReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")
        total_cost_total = query_output.get("total", {}).get("cost", {}).get("total")
        self.assertIsNotNone(data)
        self.assertIsNotNone(total_cost_total)
        self.assertAlmostEqual(total_cost_total.get("value"), self.calculate_total(handler), 6)

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
        query_params = self.mocked_query_params(url, AWSCostView)
        handler = AWSReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")
        total_cost_total = query_output.get("total", {}).get("cost", {}).get("total")
        self.assertIsNotNone(data)
        self.assertIsNotNone(total_cost_total)
        self.assertAlmostEqual(total_cost_total.get("value"), self.calculate_total(handler), 6)

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
        query_params = self.mocked_query_params(url, AWSCostView)
        handler = AWSReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")
        total_cost_total = query_output.get("total", {}).get("cost", {}).get("total")
        self.assertIsNotNone(data)
        self.assertIsNotNone(total_cost_total)
        self.assertAlmostEqual(total_cost_total.get("value"), self.calculate_total(handler), 6)

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
        query_params = self.mocked_query_params(url, AWSCostView)
        handler = AWSReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")
        total_cost_total = query_output.get("total", {}).get("cost", {}).get("total")
        self.assertIsNotNone(data)
        self.assertIsNotNone(total_cost_total)
        self.assertAlmostEqual(total_cost_total.get("value"), self.calculate_total(handler), 6)

        cmonth_str = DateHelper().this_month_start.strftime("%Y-%m")
        for data_item in data:
            month_val = data_item.get("date")
            month_data = data_item.get("accounts")
            self.assertEqual(month_val, cmonth_str)
            self.assertIsInstance(month_data, list)
            for month_item in month_data:
                account = month_item.get("account")
                self.assertIn(account, self.accounts)
                self.assertIsInstance(month_item.get("values"), list)

    def test_execute_query_by_account_by_service(self):
        """Test execute_query for current month breakdown by account by service."""
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&group_by[account]=*&group_by[service]=*"  # noqa: E501
        query_params = self.mocked_query_params(url, AWSCostView)
        handler = AWSReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")
        total_cost_total = query_output.get("total", {}).get("cost", {}).get("total")
        self.assertIsNotNone(data)
        self.assertIsNotNone(total_cost_total)
        self.assertAlmostEqual(total_cost_total.get("value"), self.calculate_total(handler), 6)

        cmonth_str = DateHelper().this_month_start.strftime("%Y-%m")
        for data_item in data:
            month_val = data_item.get("date")
            month_data = data_item.get("accounts")
            self.assertEqual(month_val, cmonth_str)
            self.assertIsInstance(month_data, list)
            for month_item in month_data:
                account = month_item.get("account")
                self.assertIn(account, self.accounts)
                self.assertIsInstance(month_item.get("services"), list)

    def test_execute_query_with_counts(self):
        """Test execute_query with counts of unique resources."""
        url = "?compute_count=true&filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=daily&group_by[instance_type]=*"  # noqa: E501
        query_params = self.mocked_query_params(url, AWSInstanceTypeView)
        handler = AWSReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get("total"))

        total = query_output.get("total")
        self.assertIsNotNone(total.get("count"))

        annotations = {
            "date": F("usage_start"),
            "type": F("instance_type"),
            "resource_id": Func(F("resource_ids"), function="unnest"),
        }

        with tenant_context(self.tenant):
            expected_counts = (
                AWSCostEntryLineItemDailySummary.objects.filter(
                    instance_type__isnull=False, usage_start__gte=self.dh.this_month_start
                )
                .values(**annotations)
                .distinct()
            )

            total_count = (
                AWSCostEntryLineItemDailySummary.objects.filter(
                    instance_type__isnull=False, usage_start__gte=self.dh.this_month_start
                )
                .values(**{"resource_id": Func(F("resource_ids"), function="unnest")})
                .distinct()
                .count()
            )

            count_dict = defaultdict(dict)
            for item in expected_counts:
                if "i-" in item["resource_id"]:
                    if item["type"] in count_dict[str(item["date"])]:
                        count_dict[str(item["date"])][item["type"]] += 1
                    else:
                        count_dict[str(item["date"])][item["type"]] = 1

        for data_item in data:
            instance_types = data_item.get("instance_types")
            for it in instance_types:
                expected_count = count_dict.get(data_item.get("date")).get(it["instance_type"])
                actual_count = it["values"][0].get("count", {}).get("value", 0)
                self.assertEqual(actual_count, expected_count)
        self.assertEqual(total.get("count", {}).get("value"), total_count)

    def test_execute_query_without_counts(self):
        """Test execute_query without counts of unique resources."""
        with tenant_context(self.tenant):
            instance_type = AWSCostEntryProduct.objects.first().instance_type

        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=daily&group_by[instance_type]=*"  # noqa: E501
        query_params = self.mocked_query_params(url, AWSInstanceTypeView)
        handler = AWSReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get("total"))

        total = query_output.get("total")
        self.assertIsNone(total.get("count"))

        for data_item in data:
            instance_types = data_item.get("instance_types")
            for it in instance_types:
                if it["instance_type"] == instance_type:
                    actual_count = it["values"][0].get("count")
                    self.assertIsNone(actual_count)

    def test_execute_query_curr_month_by_account_w_limit(self):
        """Test execute_query for current month on monthly breakdown by account with limit."""

        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&filter[limit]=2&group_by[account]=*"  # noqa: E501
        query_params = self.mocked_query_params(url, AWSCostView)
        handler = AWSReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")
        total_cost_total = query_output.get("total", {}).get("cost", {}).get("total")
        self.assertIsNotNone(data)
        self.assertIsNotNone(total_cost_total)
        self.assertAlmostEqual(total_cost_total.get("value"), self.calculate_total(handler), 6)

        cmonth_str = DateHelper().this_month_start.strftime("%Y-%m")
        for data_item in data:
            month_val = data_item.get("date")
            month_data = data_item.get("accounts")
            self.assertEqual(month_val, cmonth_str)
            self.assertIsInstance(month_data, list)
            for month_item in month_data:
                self.assertIsInstance(month_item.get("account"), str)
                self.assertIsInstance(month_item.get("values"), list)

    def test_execute_query_curr_month_by_account_w_order(self):
        """Test execute_query for current month on monthly breakdown by account with asc order."""

        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&group_by[account]=*&order_by[cost]=asc"  # noqa: E501
        query_params = self.mocked_query_params(url, AWSCostView)
        handler = AWSReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")
        total_cost_total = query_output.get("total", {}).get("cost", {}).get("total")
        self.assertIsNotNone(data)
        self.assertIsNotNone(total_cost_total)
        self.assertAlmostEqual(total_cost_total.get("value"), self.calculate_total(handler), 6)

        cmonth_str = DateHelper().this_month_start.strftime("%Y-%m")
        for data_item in data:
            month_val = data_item.get("date")
            month_data = data_item.get("accounts")
            self.assertEqual(month_val, cmonth_str)
            self.assertIsInstance(month_data, list)
            self.assertEqual(len(month_data), 6)
            current_total = 0
            for month_item in month_data:
                self.assertIsInstance(month_item.get("account"), str)
                self.assertIsInstance(month_item.get("values"), list)
                data_point_total = month_item.get("values")[0].get("cost", {}).get("total", {}).get("value")
                self.assertIsNotNone(data_point_total)
                self.assertLess(current_total, data_point_total)
                current_total = data_point_total

    def test_execute_query_curr_month_by_account_w_order_by_account_alias(self):
        """Test execute_query for current month on monthly breakdown by account with asc order."""

        url = f"?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&group_by[account]={self.account_alias}&order_by[account_alias]=asc"  # noqa: E501
        query_params = self.mocked_query_params(url, AWSCostView)
        handler = AWSReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")
        total_cost_total = query_output.get("total", {}).get("cost", {}).get("total")
        self.assertIsNotNone(data)
        self.assertIsNotNone(total_cost_total)
        self.assertAlmostEqual(total_cost_total.get("value"), self.calculate_total(handler), 6)

        cmonth_str = DateHelper().this_month_start.strftime("%Y-%m")
        for data_item in data:
            month_val = data_item.get("date")
            month_data = data_item.get("accounts")
            self.assertEqual(month_val, cmonth_str)
            self.assertIsInstance(month_data, list)
            self.assertEqual(len(month_data), 1)
            current = ""
            for month_item in month_data:
                self.assertIsInstance(month_item.get("account"), str)
                self.assertIsInstance(month_item.get("values"), list)
                self.assertIsNotNone(month_item.get("values")[0].get("account"))
                data_point = month_item.get("values")[0].get("account_alias")
                self.assertLess(current, data_point)
                current = data_point

    def test_execute_query_curr_month_by_region(self):
        """Test execute_query for current month on monthly breakdown by region."""
        url = (
            "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&group_by[region]=*"
        )  # noqa: E501
        query_params = self.mocked_query_params(url, AWSCostView)
        handler = AWSReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")
        total_cost_total = query_output.get("total", {}).get("cost", {}).get("total")
        self.assertIsNotNone(data)
        self.assertIsNotNone(total_cost_total)
        self.assertAlmostEqual(total_cost_total.get("value"), self.calculate_total(handler), 6)

        cmonth_str = DateHelper().this_month_start.strftime("%Y-%m")
        for data_item in data:
            month_val = data_item.get("date")
            month_data = data_item.get("regions")
            self.assertEqual(month_val, cmonth_str)
            self.assertIsInstance(month_data, list)
            self.assertEqual(len(month_data), self.region_count)
            for month_item in month_data:
                self.assertIsInstance(month_item.get("region"), str)
                self.assertIsInstance(month_item.get("values"), list)
                self.assertIsNotNone(month_item.get("values")[0].get("cost"))

    def test_execute_query_curr_month_by_filtered_region(self):
        """Test execute_query for current month on monthly breakdown by filtered region."""
        url = f"?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&group_by[region]={self.region}"  # noqa: E501
        query_params = self.mocked_query_params(url, AWSCostView)
        handler = AWSReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")
        total_cost_total = query_output.get("total", {}).get("cost", {}).get("total")
        #
        self.assertIsNotNone(total_cost_total)
        self.assertGreater(total_cost_total.get("value"), 0)

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

    def test_execute_query_curr_month_by_avail_zone(self):
        """Test execute_query for current month on monthly breakdown by avail_zone."""
        url = (
            "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&group_by[az]=*"
        )  # noqa: E501
        query_params = self.mocked_query_params(url, AWSCostView)
        handler = AWSReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")
        total_cost_total = query_output.get("total", {}).get("cost", {}).get("total")
        self.assertIsNotNone(data)
        self.assertIsNotNone(total_cost_total)
        self.assertAlmostEqual(total_cost_total.get("value"), self.calculate_total(handler), 6)

        cmonth_str = DateHelper().this_month_start.strftime("%Y-%m")
        for data_item in data:
            month_val = data_item.get("date")
            month_data = data_item.get("azs")
            self.assertEqual(month_val, cmonth_str)
            self.assertIsInstance(month_data, list)
            self.assertEqual(len(month_data), self.availability_zone_count_cur_mo)
            for month_item in month_data:
                self.assertIsInstance(month_item.get("az"), str)
                self.assertIsInstance(month_item.get("values"), list)
                self.assertIsNotNone(month_item.get("values")[0].get("cost"))

    def test_execute_query_curr_month_by_filtered_avail_zone(self):
        """Test execute_query for current month on monthly breakdown by filtered avail_zone."""
        url = f"?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&group_by[az]={self.availability_zone}"  # noqa: E501
        query_params = self.mocked_query_params(url, AWSCostView)
        handler = AWSReportQueryHandler(query_params)
        query_output = handler.execute_query()

        data = query_output.get("data")
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get("total"))
        total = query_output.get("total")
        self.assertIsNotNone(total.get("cost"))

        cmonth_str = DateHelper().this_month_start.strftime("%Y-%m")
        for data_item in data:
            month_val = data_item.get("date")
            month_data = data_item.get("azs")
            self.assertEqual(month_val, cmonth_str)
            self.assertIsInstance(month_data, list)
            self.assertEqual(1, len(month_data))
            for month_item in month_data:
                self.assertIsInstance(month_item.get("az"), str)
                self.assertIsInstance(month_item.get("values"), list)
                self.assertIsNotNone(month_item.get("values")[0].get("cost"))

    def test_execute_query_current_month_filter_account(self):
        """Test execute_query for current month on monthly filtered by account."""
        url = f"?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&filter[account]={self.account_alias}"  # noqa: E501
        query_params = self.mocked_query_params(url, AWSCostView)
        handler = AWSReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")
        total_cost_total = query_output.get("total", {}).get("cost", {}).get("total")
        self.assertIsNotNone(data)
        self.assertIsNotNone(total_cost_total)
        self.assertAlmostEqual(total_cost_total.get("value"), self.calculate_total(handler), 6)

        cmonth_str = DateHelper().this_month_start.strftime("%Y-%m")
        for data_item in data:
            month_val = data_item.get("date")
            month_data = data_item.get("values")
            self.assertEqual(month_val, cmonth_str)
            self.assertIsInstance(month_data, list)

    def test_execute_query_current_month_filter_service(self):
        """Test execute_query for current month on monthly filtered by service."""
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&filter[service]=AmazonEC2"  # noqa: E501
        query_params = self.mocked_query_params(url, AWSCostView)
        handler = AWSReportQueryHandler(query_params)
        query_output = handler.execute_query()

        data = query_output.get("data")
        total_cost_total = query_output.get("total", {}).get("cost", {}).get("total")
        self.assertIsNotNone(data)
        self.assertIsNotNone(total_cost_total)
        self.assertAlmostEqual(total_cost_total.get("value"), self.calculate_total(handler), 6)

        cmonth_str = DateHelper().this_month_start.strftime("%Y-%m")
        for data_item in data:
            month_val = data_item.get("date")
            month_data = data_item.get("values")
            self.assertEqual(month_val, cmonth_str)
            self.assertIsInstance(month_data, list)

    def test_execute_query_current_month_filter_region(self):
        """Test execute_query for current month on monthly filtered by region."""
        url = f"?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&filter[region]={self.region}"  # noqa: E501
        query_params = self.mocked_query_params(url, AWSCostView)
        handler = AWSReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")
        total_cost_total = query_output.get("total", {}).get("cost", {}).get("total")
        self.assertIsNotNone(data)
        self.assertIsNotNone(total_cost_total)
        self.assertGreater(total_cost_total.get("value"), 0)

        cmonth_str = DateHelper().this_month_start.strftime("%Y-%m")
        for data_item in data:
            month_val = data_item.get("date")
            month_data = data_item.get("values")
            self.assertEqual(month_val, cmonth_str)
            self.assertIsInstance(month_data, list)

    def test_execute_query_current_month_filter_avail_zone(self):
        """Test execute_query for current month on monthly filtered by avail_zone."""
        url = f"?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&filter[az]={self.availability_zone}"  # noqa: E501
        query_params = self.mocked_query_params(url, AWSCostView)
        handler = AWSReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")
        total_cost_total = query_output.get("total", {}).get("cost", {}).get("total")
        self.assertIsNotNone(data)
        self.assertIsNotNone(total_cost_total)
        self.assertAlmostEqual(total_cost_total.get("value"), self.calculate_total(handler), 6)

        cmonth_str = DateHelper().this_month_start.strftime("%Y-%m")
        for data_item in data:
            month_val = data_item.get("date")
            month_data = data_item.get("values")
            self.assertEqual(month_val, cmonth_str)
            self.assertIsInstance(month_data, list)

    @patch("api.query_params.QueryParameters.accept_type", new_callable=PropertyMock)
    def test_execute_query_current_month_filter_avail_zone_csv(self, mock_accept):
        """Test execute_query for current month on monthly filtered by avail_zone for csv."""
        mock_accept.return_value = "text/csv"
        url = f"?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&filter[az]={self.availability_zone}"  # noqa: E501
        query_params = self.mocked_query_params(url, AWSCostView)
        handler = AWSReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")
        total_cost_total = query_output.get("total", {}).get("cost", {}).get("total")
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get("total"))
        self.assertAlmostEqual(total_cost_total.get("value"), self.calculate_total(handler), 6)

    @patch("api.query_params.QueryParameters.accept_type", new_callable=PropertyMock)
    def test_execute_query_curr_month_by_account_w_limit_csv(self, mock_accept):
        """Test execute_query for current month on monthly by account with limt as csv."""
        mock_accept.return_value = "text/csv"

        url = f"?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&filter[limit]=1&group_by[account]={self.account_alias}"  # noqa: E501
        query_params = self.mocked_query_params(url, AWSCostView)
        handler = AWSReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")
        total_cost_total = query_output.get("total", {}).get("cost", {}).get("total")
        self.assertIsNotNone(data)
        self.assertIsNotNone(total_cost_total)
        self.assertAlmostEqual(total_cost_total.get("value", {}), self.calculate_total(handler), 6)

        cmonth_str = DateHelper().this_month_start.strftime("%Y-%m")
        self.assertEqual(len(data), 1)
        for data_item in data:
            month = data_item.get("date")
            self.assertEqual(month, cmonth_str)

    def test_execute_query_w_delta(self):
        """Test grouped by deltas."""
        dh = DateHelper()
        current_total = Decimal(0)
        prev_total = Decimal(0)

        # fetch the expected sums from the DB.
        with tenant_context(self.tenant):
            curr = AWSCostEntryLineItemDailySummary.objects.filter(
                usage_start__gte=dh.this_month_start,
                usage_end__lte=dh.today,
                account_alias__account_alias=self.account_alias,
            ).aggregate(value=Sum(F("unblended_cost") + F("markup_cost")))
            current_total = Decimal(curr.get("value"))

            prev = AWSCostEntryLineItemDailySummary.objects.filter(
                usage_start__gte=dh.last_month_start,
                usage_end__lte=dh.today - relativedelta(months=1),
                account_alias__account_alias=self.account_alias,
            ).aggregate(value=Sum(F("unblended_cost") + F("markup_cost")))
            prev_total = Decimal(prev.get("value"))

        expected_delta_value = Decimal(current_total - prev_total)
        expected_delta_percent = Decimal((current_total - prev_total) / prev_total * 100)

        url = f"?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&group_by[account]={self.account_alias}&delta=cost"  # noqa: E501
        path = reverse("reports-aws-costs")
        query_params = self.mocked_query_params(url, AWSCostView, path)
        handler = AWSReportQueryHandler(query_params)

        # test the calculations
        query_output = handler.execute_query()
        data = query_output.get("data")
        self.assertIsNotNone(data)
        values = data[0].get("accounts", [])[0].get("values", [])[0]
        result_delta_value = values.get("delta_value")
        result_delta_percent = values.get("delta_percent")

        self.assertIsNotNone(result_delta_percent)
        self.assertIsNotNone(result_delta_value)
        self.assertEqual(result_delta_value, expected_delta_value)
        self.assertEqual(result_delta_percent, expected_delta_percent)

        delta = query_output.get("delta")
        self.assertIsNotNone(delta.get("value"))
        self.assertIsNotNone(delta.get("percent"))
        self.assertEqual(delta.get("value"), expected_delta_value)
        self.assertEqual(delta.get("percent"), expected_delta_percent)

    def test_execute_query_w_delta_no_previous_data(self):
        """Test deltas with no previous data."""

        url = "?filter[time_scope_value]=-2&delta=cost"
        path = reverse("reports-aws-costs")
        query_params = self.mocked_query_params(url, AWSCostView, path)
        handler = AWSReportQueryHandler(query_params)
        expected_delta_value = Decimal(self.calculate_total(handler))
        expected_delta_percent = None
        query_output = handler.execute_query()
        data = query_output.get("data")
        self.assertIsNotNone(data)

        delta = query_output.get("delta")
        self.assertIsNotNone(delta.get("value"))
        self.assertIsNone(delta.get("percent"))
        self.assertAlmostEqual(delta.get("value"), expected_delta_value, 6)
        self.assertEqual(delta.get("percent"), expected_delta_percent)

    def test_execute_query_orderby_delta(self):
        """Test execute_query with ordering by delta ascending."""
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&order_by[delta]=asc&group_by[account]=*&delta=cost"  # noqa: E501
        path = reverse("reports-openshift-aws-costs")
        query_params = self.mocked_query_params(url, AWSCostView, path)
        handler = AWSReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")
        self.assertIsNotNone(data)

        cmonth_str = DateHelper().this_month_start.strftime("%Y-%m")
        for data_item in data:
            month_val = data_item.get("date")
            month_data = data_item.get("accounts")
            self.assertEqual(month_val, cmonth_str)
            self.assertIsInstance(month_data, list)
            for month_item in month_data:
                self.assertIsInstance(month_item.get("account"), str)
                self.assertIsInstance(month_item.get("values"), list)
                self.assertIsNotNone(month_item.get("values")[0].get("delta_percent"))

    def test_execute_query_with_account_alias(self):
        """Test execute_query when account alias is avaiable."""
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&filter[limit]=2&group_by[account]=*"  # noqa: E501
        query_params = self.mocked_query_params(url, AWSCostView)
        handler = AWSReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")

        account_alias = data[0].get("accounts")[0].get("values")[0].get("account_alias")

        self.assertIn(account_alias, self.account_aliases)

    def test_execute_query_orderby_alias(self):
        """Test execute_query when account alias is avaiable."""
        # execute query
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&group_by[account]=*&order_by[account_alias]=asc"  # noqa: E501
        query_params = self.mocked_query_params(url, AWSCostView)
        handler = AWSReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")

        # test query output
        actual = OrderedDict()
        for datum in data:
            for account in datum.get("accounts"):
                for value in account.get("values"):
                    actual[value.get("account_alias")] = value.get("account")

        for account_id, account_alias in self.account_alias_mapping.items():
            self.assertEqual(actual.get(account_alias), account_id)

    def test_calculate_total(self):
        """Test that calculated totals return correctly."""
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly"
        query_params = self.mocked_query_params(url, AWSCostView)
        handler = AWSReportQueryHandler(query_params)
        expected_units = "USD"
        with tenant_context(self.tenant):
            result = handler.calculate_total(**{"cost_units": expected_units})
        cost_total_value = result.get("cost", {}).get("total", {}).get("value")
        cost_total_units = result.get("cost", {}).get("total", {}).get("units")
        self.assertIsNotNone(cost_total_value)
        self.assertIsNotNone(cost_total_units)
        self.assertAlmostEqual(cost_total_value, self.calculate_total(handler), 6)
        self.assertEqual(cost_total_units, expected_units)

    def test_percent_delta(self):
        """Test _percent_delta() utility method."""
        url = "?"
        query_params = self.mocked_query_params(url, AWSCostView)
        handler = AWSReportQueryHandler(query_params)
        self.assertEqual(handler._percent_delta(10, 5), 100)

    def test_rank_list(self):
        """Test rank list limit with account alias."""
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&filter[limit]=2&group_by[account]=*"  # noqa: E501
        query_params = self.mocked_query_params(url, AWSCostView)
        handler = AWSReportQueryHandler(query_params)
        data_list = [
            {"account": "1", "account_alias": "1", "total": 5, "rank": 1},
            {"account": "2", "account_alias": "2", "total": 4, "rank": 2},
            {"account": "3", "account_alias": "3", "total": 3, "rank": 3},
            {"account": "4", "account_alias": "4", "total": 2, "rank": 4},
        ]
        expected = [
            {"account": "1", "account_alias": "1", "total": 5, "rank": 1},
            {"account": "2", "account_alias": "2", "total": 4, "rank": 2},
            {
                "account": "Others",
                "account_alias": "Others",
                "total": 5,
                "rank": 3,
                "cost_total": 0,
                "infra_total": 0,
                "sup_total": 0,
            },
        ]
        ranked_list = handler._ranked_list(data_list)
        self.assertEqual(ranked_list, expected)

    def test_rank_list_no_account(self):
        """Test rank list limit with out account alias."""
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&filter[limit]=2&group_by[service]=*"  # noqa: E501
        query_params = self.mocked_query_params(url, AWSCostView)
        handler = AWSReportQueryHandler(query_params)
        data_list = [
            {"service": "1", "total": 5, "rank": 1},
            {"service": "2", "total": 4, "rank": 2},
            {"service": "3", "total": 3, "rank": 3},
            {"service": "4", "total": 2, "rank": 4},
        ]
        expected = [
            {"service": "1", "total": 5, "rank": 1},
            {"service": "2", "total": 4, "rank": 2},
            {"service": "Others", "total": 5, "rank": 3, "cost_total": 0, "infra_total": 0, "sup_total": 0},
        ]
        ranked_list = handler._ranked_list(data_list)
        self.assertEqual(ranked_list, expected)

    def test_rank_list_with_offset(self):
        """Test rank list limit and offset with account alias."""
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&filter[limit]=1&filter[offset]=1&group_by[account]=*"  # noqa: E501
        query_params = self.mocked_query_params(url, AWSCostView)
        handler = AWSReportQueryHandler(query_params)
        data_list = [
            {"account": "1", "account_alias": "1", "total": 5, "rank": 1},
            {"account": "2", "account_alias": "2", "total": 4, "rank": 2},
            {"account": "3", "account_alias": "3", "total": 3, "rank": 3},
            {"account": "4", "account_alias": "4", "total": 2, "rank": 4},
        ]
        expected = [{"account": "2", "account_alias": "2", "total": 4, "rank": 2}]
        ranked_list = handler._ranked_list(data_list)
        self.assertEqual(ranked_list, expected)

    def test_rank_list_zerofill_account(self):
        """Test rank list limit with account alias, ensuring we zero-fill missing ranks and populate account_alias."""
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=daily&filter[limit]=10&group_by[account]=*&order_by[account_alias]=asc"  # noqa: E501
        query_params = self.mocked_query_params(url, AWSCostView)
        handler = AWSReportQueryHandler(query_params)
        data_list = [
            {
                "date": "2000-01-01",
                "account": "1",
                "account_alias": "acct 1",
                "infra_total": 0.01,
                "sup_total": 0.02,
                "cost_total": 0.03,
            },
            {
                "date": "2000-01-01",
                "account": "2",
                "account_alias": "acct 2",
                "infra_total": 0.02,
                "sup_total": 0.03,
                "cost_total": 0.05,
            },
            {
                "date": "2000-01-01",
                "account": "3",
                "account_alias": "acct 3",
                "infra_total": 0.03,
                "sup_total": 0.04,
                "cost_total": 0.07,
            },
            {
                "date": "2000-01-01",
                "account": "4",
                "account_alias": "acct 4",
                "infra_total": 0.04,
                "sup_total": 0.05,
                "cost_total": 0.09,
            },
            {"date": "2000-01-01", "account": "5", "infra_total": 0.04, "sup_total": 0.05, "cost_total": 0.09},
            {
                "date": "2000-01-02",
                "account": "1",
                "account_alias": "acct 1",
                "infra_total": 0.01,
                "sup_total": 0.02,
                "cost_total": 0.03,
            },
            {
                "date": "2000-01-02",
                "account": "2",
                "account_alias": "acct 2",
                "infra_total": 0.02,
                "sup_total": 0.03,
                "cost_total": 0.05,
            },
            {
                "date": "2000-01-02",
                "account": "3",
                "account_alias": "acct 3",
                "infra_total": 0.03,
                "sup_total": 0.04,
                "cost_total": 0.07,
            },
            {
                "date": "2000-01-03",
                "account": "2",
                "account_alias": "acct 2",
                "infra_total": 0.02,
                "sup_total": 0.03,
                "cost_total": 0.05,
            },
            {
                "date": "2000-01-03",
                "account": "3",
                "account_alias": "acct 3",
                "infra_total": 0.03,
                "sup_total": 0.04,
                "cost_total": 0.07,
            },
            {
                "date": "2000-01-03",
                "account": "4",
                "account_alias": "acct 4",
                "infra_total": 0.04,
                "sup_total": 0.05,
                "cost_total": 0.09,
            },
        ]
        expected = [
            {
                "date": "2000-01-01",
                "account": "1",
                "account_alias": "acct 1",
                "infra_total": 0.01,
                "sup_total": 0.02,
                "cost_total": 0.03,
                "rank": 4,
            },
            {
                "date": "2000-01-01",
                "account": "2",
                "account_alias": "acct 2",
                "infra_total": 0.02,
                "sup_total": 0.03,
                "cost_total": 0.05,
                "rank": 3,
            },
            {
                "date": "2000-01-01",
                "account": "3",
                "account_alias": "acct 3",
                "infra_total": 0.03,
                "sup_total": 0.04,
                "cost_total": 0.07,
                "rank": 1,
            },
            {
                "date": "2000-01-01",
                "account": "4",
                "account_alias": "acct 4",
                "infra_total": 0.04,
                "sup_total": 0.05,
                "cost_total": 0.09,
                "rank": 2,
            },
            {
                "date": "2000-01-01",
                "account": "5",
                "infra_total": 0.04,
                "sup_total": 0.05,
                "cost_total": 0.09,
                "rank": 5,
            },
            {
                "date": "2000-01-02",
                "account": "1",
                "account_alias": "acct 1",
                "infra_total": 0.01,
                "sup_total": 0.02,
                "cost_total": 0.03,
                "rank": 4,
            },
            {
                "date": "2000-01-02",
                "account": "2",
                "account_alias": "acct 2",
                "infra_total": 0.02,
                "sup_total": 0.03,
                "cost_total": 0.05,
                "rank": 3,
            },
            {
                "date": "2000-01-02",
                "account": "3",
                "account_alias": "acct 3",
                "infra_total": 0.03,
                "sup_total": 0.04,
                "cost_total": 0.07,
                "rank": 1,
            },
            {
                "date": "2000-01-02",
                "account": "5",
                "account_alias": "5",
                "infra_total": 0.0,
                "sup_total": 0.0,
                "cost_total": 0.0,
                "rank": 5,
            },
            {
                "date": "2000-01-02",
                "account": "4",
                "account_alias": "acct 4",
                "infra_total": 0.0,
                "sup_total": 0.0,
                "cost_total": 0.0,
                "rank": 2,
            },
            {
                "date": "2000-01-03",
                "account": "2",
                "account_alias": "acct 2",
                "infra_total": 0.02,
                "sup_total": 0.03,
                "cost_total": 0.05,
                "rank": 3,
            },
            {
                "date": "2000-01-03",
                "account": "3",
                "account_alias": "acct 3",
                "infra_total": 0.03,
                "sup_total": 0.04,
                "cost_total": 0.07,
                "rank": 1,
            },
            {
                "date": "2000-01-03",
                "account": "4",
                "account_alias": "acct 4",
                "infra_total": 0.04,
                "sup_total": 0.05,
                "cost_total": 0.09,
                "rank": 2,
            },
            {
                "date": "2000-01-03",
                "account": "5",
                "account_alias": "5",
                "infra_total": 0.0,
                "sup_total": 0.0,
                "cost_total": 0.0,
                "rank": 5,
            },
            {
                "date": "2000-01-03",
                "account": "1",
                "account_alias": "acct 1",
                "infra_total": 0.0,
                "sup_total": 0.0,
                "cost_total": 0.0,
                "rank": 4,
            },
        ]
        ranked_list = handler._ranked_list(data_list, ranks=["3", "4", "2", "1", "5"])
        for each in expected:
            self.assertIn(each, ranked_list)

    def test_rank_list_big_limit(self):
        """Test rank list limit with account alias, ensuring we return results with limited data."""
        url = (
            "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=daily&filter[limit]=3"
        )  # noqa: E501
        query_params = self.mocked_query_params(url, AWSInstanceTypeView)
        handler = AWSReportQueryHandler(query_params)
        data_list = [
            {
                "date": "2000-01-01",
                "service": "AmazonEC2",
                "instance_type": "m1.large",
                "infra_total": 0.01,
                "sup_total": 0.02,
                "cost_total": 0.03,
            },
            {
                "date": "2000-01-01",
                "service": "AmazonEC2",
                "instance_type": "m2.large",
                "infra_total": 0.02,
                "sup_total": 0.03,
                "cost_total": 0.05,
            },
        ]
        expected = [
            {
                "date": "2000-01-01",
                "service": "AmazonEC2",
                "instance_type": "m1.large",
                "infra_total": 0.01,
                "sup_total": 0.02,
                "cost_total": 0.03,
                "rank": 2,
            },
            {
                "date": "2000-01-01",
                "service": "AmazonEC2",
                "instance_type": "m2.large",
                "infra_total": 0.02,
                "sup_total": 0.03,
                "cost_total": 0.05,
                "rank": 1,
            },
        ]
        ranked_list = handler._ranked_list(data_list, ranks=["m2.large", "m1.large"])
        self.assertEqual(ranked_list, expected)

    def test_query_costs_with_totals(self):
        """Test execute_query() - costs with totals.

        Query for instance_types, validating that cost totals are present.
        """

        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&group_by[account]=*"  # noqa: E501
        query_params = self.mocked_query_params(url, AWSCostView)
        handler = AWSReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")
        self.assertIsNotNone(data)

        for data_item in data:
            accounts = data_item.get("accounts")
            for account in accounts:
                self.assertIsNotNone(account.get("values"))
                self.assertGreater(len(account.get("values")), 0)
                for value in account.get("values"):
                    cost_total = value.get("cost", {}).get("total", {}).get("value")
                    self.assertIsInstance(cost_total, Decimal)
                    self.assertGreater(cost_total, Decimal(0))

    def test_query_instance_types_with_totals(self):
        """Test execute_query() - instance types with totals.

        Query for instance_types, validating that cost totals are present.
        """

        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&group_by[instance_type]=*"  # noqa: E501
        query_params = self.mocked_query_params(url, AWSInstanceTypeView)
        handler = AWSReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")
        self.assertIsNotNone(data)

        for data_item in data:
            instance_types = data_item.get("instance_types")
            for it in instance_types:
                self.assertIsNotNone(it.get("values"))
                self.assertGreater(len(it.get("values")), 0)
                for value in it.get("values"):
                    cost_total = value.get("cost", {}).get("total", {}).get("value")
                    self.assertIsInstance(cost_total, Decimal)
                    self.assertGreater(cost_total, Decimal(0))
                    self.assertIsInstance(value.get("usage", {}).get("value"), Decimal)
                    self.assertGreater(value.get("usage", {}).get("value"), Decimal(0))

    def test_query_storage_with_totals(self):
        """Test execute_query() - storage with totals.

        Query for storage, validating that cost totals are present.
        """
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&group_by[service]=*"  # noqa: E501
        query_params = self.mocked_query_params(url, AWSStorageView)
        handler = AWSReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")
        self.assertIsNotNone(data)

        for data_item in data:
            services = data_item.get("services")
            self.assertIsNotNone(services)
            for srv in services:
                # EBS is filed under the 'AmazonEC2' service.
                if srv.get("service") == "AmazonEC2":
                    self.assertIsNotNone(srv.get("values"))
                    self.assertGreater(len(srv.get("values")), 0)
                    for value in srv.get("values"):
                        cost_total = value.get("cost", {}).get("total", {}).get("value")
                        self.assertIsInstance(cost_total, Decimal)
                        self.assertGreater(cost_total, Decimal(0))
                        self.assertIsInstance(value.get("usage", {}).get("value"), Decimal)
                        self.assertGreater(value.get("usage", {}).get("value"), Decimal(0))

    def test_order_by(self):
        """Test that order_by returns properly sorted data."""
        today = datetime.utcnow()
        yesterday = today - timedelta(days=1)
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly"  # noqa: E501
        query_params = self.mocked_query_params(url, AWSCostView)
        handler = AWSReportQueryHandler(query_params)

        unordered_data = [
            {"date": today, "delta_percent": 8, "total": 6.2, "rank": 2},
            {"date": yesterday, "delta_percent": 4, "total": 2.2, "rank": 1},
            {"date": today, "delta_percent": 7, "total": 8.2, "rank": 1},
            {"date": yesterday, "delta_percent": 4, "total": 2.2, "rank": 2},
        ]

        order_fields = ["date", "rank"]
        expected = [
            {"date": yesterday, "delta_percent": 4, "total": 2.2, "rank": 1},
            {"date": yesterday, "delta_percent": 4, "total": 2.2, "rank": 2},
            {"date": today, "delta_percent": 7, "total": 8.2, "rank": 1},
            {"date": today, "delta_percent": 8, "total": 6.2, "rank": 2},
        ]

        ordered_data = handler.order_by(unordered_data, order_fields)
        self.assertEqual(ordered_data, expected)

        order_fields = ["date", "-delta"]
        expected = [
            {"date": yesterday, "delta_percent": 4, "total": 2.2, "rank": 1},
            {"date": yesterday, "delta_percent": 4, "total": 2.2, "rank": 2},
            {"date": today, "delta_percent": 8, "total": 6.2, "rank": 2},
            {"date": today, "delta_percent": 7, "total": 8.2, "rank": 1},
        ]

        ordered_data = handler.order_by(unordered_data, order_fields)
        self.assertEqual(ordered_data, expected)

    def test_strip_tag_prefix(self):
        """Verify that our tag prefix is stripped from a string."""
        tag_str = "tag:project"
        result = strip_tag_prefix(tag_str)
        self.assertEqual(result, tag_str.replace("tag:", ""))

    def test_execute_query_with_wildcard_tag_filter(self):
        """Test that data is filtered to include entries with tag key."""
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly"  # noqa: E501
        query_params = self.mocked_query_params(url, AWSTagView)
        handler = AWSTagQueryHandler(query_params)
        tag_keys = handler.get_tag_keys()
        filter_key = tag_keys[0]
        tag_keys = ["tag:" + tag for tag in tag_keys]

        with tenant_context(self.tenant):
            totals = AWSCostEntryLineItemDailySummary.objects.filter(
                usage_start__gte=self.dh.this_month_start
            ).aggregate(**{"cost": Sum(F("unblended_cost") + F("markup_cost"))})

        url = f"?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&filter[tag:{filter_key}]=*"  # noqa: E501
        query_params = self.mocked_query_params(url, AWSCostView)
        handler = AWSReportQueryHandler(query_params)
        data = handler.execute_query()
        data_totals = data.get("total", {})
        result = data_totals.get("cost", {}).get("total", {}).get("value")
        self.assertEqual(result, totals["cost"])

    def test_execute_query_with_tag_group_by(self):
        """Test that data is grouped by tag key."""
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly"  # noqa: E501
        query_params = self.mocked_query_params(url, AWSTagView)
        handler = AWSTagQueryHandler(query_params)
        tag_keys = handler.get_tag_keys()
        group_by_key = tag_keys[0]
        tag_keys = ["tag:" + tag for tag in tag_keys]

        with tenant_context(self.tenant):
            totals = AWSCostEntryLineItemDailySummary.objects.filter(
                usage_start__gte=self.dh.this_month_start
            ).aggregate(**{"cost": Sum(F("unblended_cost") + F("markup_cost"))})

        url = f"?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&group_by[tag:{group_by_key}]=*"  # noqa: E501
        query_params = self.mocked_query_params(url, AWSCostView)
        handler = AWSReportQueryHandler(query_params)

        data = handler.execute_query()
        data_totals = data.get("total", {})
        data = data.get("data", [])
        expected_keys = ["date", group_by_key + "s"]
        for entry in data:
            self.assertEqual(list(entry.keys()), expected_keys)
        result = data_totals.get("cost", {}).get("total", {}).get("value")
        self.assertEqual(totals["cost"], result)

    def test_execute_query_return_others_with_tag_group_by(self):
        """Test that data is grouped by tag key."""
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly"  # noqa: E501
        query_params = self.mocked_query_params(url, AWSTagView)
        handler = AWSTagQueryHandler(query_params)
        tag_keys = handler.get_tag_keys()
        group_by_key = tag_keys[0]
        tag_keys = ["tag:" + tag for tag in tag_keys]

        totals_key = "cost"
        with tenant_context(self.tenant):
            totals = (
                AWSCostEntryLineItemDailySummary.objects.filter(usage_start__gte=self.dh.this_month_start)
                .filter(**{"tags__has_key": group_by_key})
                .aggregate(**{totals_key: Sum(F("unblended_cost") + F("markup_cost"))})
            )
            others_totals = (
                AWSCostEntryLineItemDailySummary.objects.filter(usage_start__gte=self.dh.this_month_start)
                .exclude(**{"tags__has_key": group_by_key})
                .aggregate(**{totals_key: Sum(F("unblended_cost") + F("markup_cost"))})
            )

        url = f"?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&group_by[or:tag:{group_by_key}]=*"  # noqa: E501
        query_params = self.mocked_query_params(url, AWSCostView)
        handler = AWSReportQueryHandler(query_params)

        data = handler.execute_query()
        data_totals = data.get("total", {})
        data = data.get("data", [])
        expected_keys = ["date", group_by_key + "s"]
        for entry in data:
            self.assertEqual(list(entry.keys()), expected_keys)
        result = data_totals.get(totals_key, {}).get("total", {}).get("value")
        self.assertAlmostEqual(result, (totals[totals_key] + others_totals[totals_key]), 6)

    def test_execute_query_with_tag_filter(self):
        """Test that data is filtered by tag key."""
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly"  # noqa: E501
        query_params = self.mocked_query_params(url, AWSTagView)
        handler = AWSTagQueryHandler(query_params)
        tag_keys = handler.get_tag_keys()
        filter_key = tag_keys[0]
        tag_keys = ["tag:" + tag for tag in tag_keys]

        with tenant_context(self.tenant):
            labels = (
                AWSCostEntryLineItemDailySummary.objects.filter(usage_start__gte=self.dh.this_month_start)
                .filter(tags__has_key=filter_key)
                .values(*["tags"])
                .all()
            )
            label_of_interest = labels[0]
            filter_value = label_of_interest.get("tags", {}).get(filter_key)

            totals = (
                AWSCostEntryLineItemDailySummary.objects.filter(usage_start__gte=self.dh.this_month_start)
                .filter(**{f"tags__{filter_key}": filter_value})
                .aggregate(**{"cost": Sum(F("unblended_cost") + F("markup_cost"))})
            )

        url = f"?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&group_by[tag:{filter_key}]={filter_value}"  # noqa: E501
        query_params = self.mocked_query_params(url, AWSCostView)
        handler = AWSReportQueryHandler(query_params)
        data = handler.execute_query()
        data_totals = data.get("total", {})
        result = data_totals.get("cost", {}).get("total", {}).get("value")
        self.assertEqual(result, totals["cost"])

    def test_execute_query_with_org_unit_group_by(self):
        """Test that when data is grouped by org_unit_id, the totals add up correctly."""

        # helper function so that we don't have to repeat these steps for each ou
        def check_accounts_subous_totals(org_unit):
            """Check that the accounts, sub_ous, and totals are correct for each group_by."""
            with tenant_context(self.tenant):
                url = f"?group_by[org_unit_id]={org_unit}"
                query_params = self.mocked_query_params(url, AWSCostView, "costs")
                handler = AWSReportQueryHandler(query_params)
                data = handler.execute_query()
                # grab the accounts and sub_ous and compare with the expected results
                path = self.ou_to_account_subou_map.get(org_unit).get("org_unit_path")
                ten_days_ago = self.dh.n_days_ago(self.dh.today, 9)
                expected = AWSCostEntryLineItemDailySummary.objects.filter(
                    usage_start__gte=ten_days_ago,
                    usage_end__lte=self.dh.today,
                    organizational_unit__org_unit_path__icontains=path,
                ).aggregate(
                    **{
                        "cost_total": Sum(
                            Coalesce(F("unblended_cost"), Value(0, output_field=DecimalField()))
                            + Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))
                        )
                    }
                )
                cost_total = data.get("total").get("cost").get("total").get("value")
                infra_total = data.get("total").get("infrastructure").get("total").get("value")
                expected_cost_total = expected.get("cost_total") or 0
                # infra and total cost match
                self.assertEqual(cost_total, expected_cost_total)
                self.assertEqual(infra_total, expected_cost_total)
                # test the org units and accounts returned are correct
                accounts_and_sub_ous = _calculate_accounts_and_subous(data.get("data"))
                for account in self.ou_to_account_subou_map.get(org_unit).get("accounts"):
                    self.assertIn(account, accounts_and_sub_ous)
                for sub_ou in self.ou_to_account_subou_map.get(org_unit).get("org_units"):
                    self.assertIn(sub_ou, accounts_and_sub_ous)

        # for each org defined in our yaml file assert that everything is as expected
        orgs_to_check = self.ou_to_account_subou_map.keys()
        for org in orgs_to_check:
            with self.subTest(org=org):
                check_accounts_subous_totals(org)

    def test_execute_query_with_multiple_or_org_unit_group_by(self):
        """Test that when data has multiple grouped by org_unit_id, the totals add up correctly."""
        ou_to_compare = ["OU_001", "OU_002"]
        with tenant_context(self.tenant):
            url = f"?group_by[or:org_unit_id]={ou_to_compare[0]}&group_by[or:org_unit_id]={ou_to_compare[1]}"
            query_params = self.mocked_query_params(url, AWSCostView, "costs")
            handler = AWSReportQueryHandler(query_params)
            data = handler.execute_query()

            # grab the accounts and sub_ous and compare the expected results
            expected_cost_total = []
            expected_accounts_and_sub_ous = []
            for org_unit in ou_to_compare:
                # Since the or: is suppose to do the union of a OU_001 & OU_002 then
                # we can the expected cost to include both as well as the expected_accounts_and_sub_ous
                path = self.ou_to_account_subou_map.get(org_unit).get("org_unit_path")
                ten_days_ago = self.dh.n_days_ago(self.dh.today, 9)
                expected = AWSCostEntryLineItemDailySummary.objects.filter(
                    usage_start__gte=ten_days_ago,
                    usage_end__lte=self.dh.today,
                    organizational_unit__org_unit_path__icontains=path,
                ).aggregate(
                    **{
                        "cost_total": Sum(
                            Coalesce(F("unblended_cost"), Value(0, output_field=DecimalField()))
                            + Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))
                        )
                    }
                )
                cost_total = expected.get("cost_total")
                self.assertIsNotNone(cost_total)
                expected_cost_total.append(cost_total)
                # Figure out expected accounts & sub orgs
                sub_orgs = self.ou_to_account_subou_map.get(org_unit).get("org_units")
                accounts = self.ou_to_account_subou_map.get(org_unit).get("accounts")
                expected_accounts_and_sub_ous = list(set(expected_accounts_and_sub_ous + sub_orgs + accounts))
            # infra and total cost match
            cost_total = data.get("total").get("cost").get("total").get("value")
            infra_total = data.get("total").get("infrastructure").get("total").get("value")
            expected_cost_total = sum(expected_cost_total)
            self.assertEqual(cost_total, expected_cost_total)
            self.assertEqual(infra_total, expected_cost_total)
            # test the org units and accounts returned are correct
            accounts_and_sub_ous = _calculate_accounts_and_subous(data.get("data"))
            for result in accounts_and_sub_ous:
                self.assertIn(result, expected_accounts_and_sub_ous)
            for expected in expected_accounts_and_sub_ous:
                self.assertIn(expected, accounts_and_sub_ous)

    def test_filter_org_unit(self):
        """Check that the total is correct when filtering by org_unit_id."""
        with tenant_context(self.tenant):
            org_unit = "R_001"
            org_group_by_url = f"?filter[org_unit_id]={org_unit}"
            query_params = self.mocked_query_params(org_group_by_url, AWSCostView)
            handler = AWSReportQueryHandler(query_params)
            org_data = handler.execute_query()
            # grab the expected totals
            ten_days_ago = self.dh.n_days_ago(self.dh.today, 9)
            expected = AWSCostEntryLineItemDailySummary.objects.filter(
                usage_start__gte=ten_days_ago,
                usage_end__lte=self.dh.today,
                organizational_unit__org_unit_path__icontains=org_unit,
            ).aggregate(
                **{
                    "cost_total": Sum(
                        Coalesce(F("unblended_cost"), Value(0, output_field=DecimalField()))
                        + Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))
                    )
                }
            )
            # grab the actual totals for the org_unit_id filter
            org_cost_total = org_data.get("total").get("cost").get("total").get("value")
            org_infra_total = org_data.get("total").get("infrastructure").get("total").get("value")
            # make sure they add up
            expected_cost_total = expected.get("cost_total") or 0
            # infra and total cost match
            self.assertEqual(org_cost_total, expected_cost_total)
            self.assertEqual(org_infra_total, expected_cost_total)

    def test_rename_org_unit(self):
        """Test that a renamed org unit only shows up once."""
        with tenant_context(self.tenant):
            # Check to make sure OU_001 was renamed in the default dummy data
            renamed_org_id = "OU_001"
            org_unit_names = AWSOrganizationalUnit.objects.filter(org_unit_id=renamed_org_id).values_list(
                "org_unit_name", flat=True
            )
            # Find expected alias
            self.assertGreaterEqual(len(org_unit_names), 2)
            expected_alias = (
                AWSOrganizationalUnit.objects.filter(org_unit_id=renamed_org_id)
                .order_by("org_unit_id", "-created_timestamp")
                .distinct("org_unit_id")
                .values_list("org_unit_name", flat=True)
            )
            self.assertEqual(len(expected_alias), 1)
            expected_alias = expected_alias[0]
            # Check to make sure all alias returns equal the expected for the renamed org unit
            org_unit = "R_001"
            url = f"?group_by[org_unit_id]={org_unit}"
            query_params = self.mocked_query_params(url, AWSCostView, "costs")
            handler = AWSReportQueryHandler(query_params)
            handler.execute_query()
            query_data = handler.query_data
            for element in query_data:
                for org_entity in element.get("org_entities"):
                    if org_entity.get("type") == "organizational_unit" and org_entity.get("id") == renamed_org_id:
                        org_values = org_entity.get("values", [])[0]
                        self.assertEqual(org_values.get("alias"), expected_alias)

    def test_filter_and_group_by_org_unit_match(self):
        """Test that the cost group_by and filter match."""
        org_unit_id_list = list(self.ou_to_account_subou_map.keys())
        with tenant_context(self.tenant):
            for org_unit_id in org_unit_id_list:
                filter_url = f"?filter[org_unit_id]={org_unit_id}"
                filter_params = self.mocked_query_params(filter_url, AWSCostView, "costs")
                filter_handler = AWSReportQueryHandler(filter_params)
                filter_total = filter_handler.execute_query().get("total", None)
                self.assertIsNotNone(filter_total)
                group_url = f"?group_by[org_unit_id]={org_unit_id}"
                group_params = self.mocked_query_params(group_url, AWSCostView, "costs")
                group_handler = AWSReportQueryHandler(group_params)
                group_total = group_handler.execute_query().get("total", None)
                self.assertIsNotNone(filter_total)
                self.assertEqual(filter_total, group_total)

    def test_multi_group_by_parent_and_child(self):
        """Test that cost is not calculated twice in a multiple group by of parent and child."""
        with tenant_context(self.tenant):
            parent_org_unit = "R_001"
            child_org_unit = self.ou_to_account_subou_map.get(parent_org_unit, {}).get("org_units", [])
            self.assertNotEqual(child_org_unit, [])
            child_org_unit = child_org_unit[0]
            parent_url = f"?group_by[org_unit_id]={parent_org_unit}"
            query_params = self.mocked_query_params(parent_url, AWSCostView, "costs")
            handler = AWSReportQueryHandler(query_params)
            expected_total = handler.execute_query().get("total", None)
            self.assertIsNotNone(expected_total)
            # multiple group_by with one of the group by values is the child of the other parent
            multi_url = f"?group_by[or:org_unit_id]={parent_org_unit}&group_by[or:org_unit_id]={child_org_unit}"
            query_params = self.mocked_query_params(multi_url, AWSCostView, "costs")
            handler = AWSReportQueryHandler(query_params)
            result_total = handler.execute_query().get("total")
            self.assertEqual(expected_total, result_total)

    def test_multi_group_by_seperate_children(self):
        """Test cost sum of multi org_unit_id group by of children nodes"""
        with tenant_context(self.tenant):
            org_units = ["OU_001", "OU_002"]
            expected_costs = []
            for org_unit in org_units:
                url = f"?group_by[org_unit_id]={org_unit}"
                params = self.mocked_query_params(url, AWSCostView, "costs")
                handler = AWSReportQueryHandler(params)
                expected_cost = handler.execute_query().get("total", {}).get("cost", {}).get("total", {}).get("value")
                self.assertIsNotNone(expected_cost)
                expected_costs.append(expected_cost)
            # multiple group_by cost check
            multi_url = f"?group_by[or:org_unit_id]={org_units[0]}&group_by[or:org_unit_id]={org_units[1]}"
            multi_params = self.mocked_query_params(multi_url, AWSCostView, "costs")
            multi_handler = AWSReportQueryHandler(multi_params)
            multi_cost = multi_handler.execute_query().get("total", {}).get("cost", {}).get("total", {}).get("value")
            self.assertEqual(sum(expected_costs), multi_cost)

    def test_multiple_group_by_alias_change(self):
        """Test that the data is correctly formatted to id & alias multi org_unit_id group bys"""
        with tenant_context(self.tenant):
            # https://issues.redhat.com/browse/COST-478
            # These group by options format the return to have an s on the group by
            # for example az is transformed into azs in the data return on the endpoint
            reformats_data = ["az", "region", "service", "product_family"]
            no_reformat = ["instance_type", "storage_type", "account"]
            group_by_options = reformats_data + no_reformat
            for group_by_option in group_by_options:
                group_by_url = f"?group_by[org_unit_id]=R_001&group_by[{group_by_option}]=*"
                params = self.mocked_query_params(group_by_url, AWSCostView, "costs")
                handler = AWSReportQueryHandler(params)
                handler.execute_query()
                passed = False
                for day in handler.query_data:
                    for org_entity in day.get("org_entities", []):
                        if group_by_option in reformats_data:
                            group_key = group_by_option + "s"
                            for group in org_entity.get(group_key, []):
                                for value in group.get("values", []):
                                    self.assertIsNotNone(value.get("id"))
                                    self.assertIsNotNone(value.get("alias"))
                                    passed = True
                        else:
                            for value in org_entity.get("values", []):
                                self.assertIsNotNone(value.get("id"))
                                self.assertIsNotNone(value.get("alias"))
                                passed = True
                self.assertTrue(passed)

    def test_limit_offset_order_by_group_by_ranks_account_alias(self):
        """Test execute_query with limit/offset/order_by for aws account alias."""
        # execute query
        url = "?filter[limit]=2&filter[offset]=0&group_by[account]=*&order_by[account_alias]=asc"  # noqa: E501
        query_params = self.mocked_query_params(url, AWSCostView)
        handler = AWSReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")
        # test query output
        actual = OrderedDict()
        for datum in data:
            for account in datum.get("accounts"):
                for value in account.get("values"):
                    actual[value.get("account_alias")] = value.get("account")
        alias_order = ["account 001", "account 002"]
        for i, (account_alias, account_id) in enumerate(actual.items()):
            self.assertEqual(account_alias, alias_order[i])

    def test_limit_offset_order_by_group_by_ranks(self):
        """Test execute_query with limit/offset/order_by for aws cost."""
        # execute query
        url = "?filter[limit]=2&filter[offset]=0&group_by[account]=*&order_by[cost]=asc"  # noqa: E501
        query_params = self.mocked_query_params(url, AWSCostView)
        handler = AWSReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")
        # test query output
        actual = []
        expected = {}
        start = handler.start_datetime.date()
        for acc in self.accounts:
            with tenant_context(self.tenant):
                expected[acc] = (
                    AWSCostEntryLineItemDailySummary.objects.filter(usage_account_id=acc)
                    .filter(usage_start__gte=start)
                    .aggregate(
                        cost=Sum(
                            Coalesce(F("unblended_cost"), Value(0, output_field=DecimalField()))
                            + Coalesce(F("markup_cost"), Value(0, output_field=DecimalField()))
                        )
                    )
                    .get("cost")
                )
        expected = dict(sorted(expected.items(), key=lambda x: x[1])[:2])
        for datum in data:
            for account in datum.get("accounts"):
                for value in account.get("values"):
                    if value.get("account") not in actual:
                        actual.append(value.get("account"))
        for acc in actual:
            self.assertTrue(acc in expected)

    def test_aws_date_order_by_cost_desc(self):
        """Test that order of every other date matches the order of the `order_by` date."""
        # execute query
        yesterday = self.dh.yesterday.date()
        group_bys = {
            "account": AWSCostSummaryByAccountP,
            "service": AWSCostSummaryByServiceP,
            "region": AWSCostSummaryByRegionP,
            "product_family": AWSCostSummaryByServiceP,
        }
        for group_by, table in group_bys.items():
            with self.subTest(test=group_by):
                url = f"?order_by[cost]=desc&order_by[date]={yesterday}&group_by[{group_by}]=*"
                query_params = self.mocked_query_params(url, AWSCostView)
                handler = AWSReportQueryHandler(query_params)
                query_output = handler.execute_query()
                data = query_output.get("data")

                gb = group_by
                group_by_annotations = handler.annotations.get(group_by)
                cost_annotations = handler.report_annotations.get("cost_total")
                with tenant_context(self.tenant):
                    query = table.objects.filter(usage_start=str(yesterday))
                    if group_by_annotations:
                        gb = "gb"
                        query = query.annotate(gb=group_by_annotations)
                    expected = list(query.values(gb).annotate(cost=cost_annotations).order_by("-cost", gb))
                correctlst = [field.get(gb) for field in expected]
                if correctlst and None in correctlst:
                    ind = correctlst.index(None)
                    correctlst[ind] = "no-" + group_by
                for element in data:
                    lst = [field.get(group_by) for field in element.get(group_by + "s", [])]
                    if lst and correctlst:
                        self.assertEqual(correctlst, lst)

    def test_aws_date_incorrect_date(self):
        wrong_date = "200BC"
        url = f"?order_by[cost]=desc&order_by[date]={wrong_date}&group_by[service]=*"
        with self.assertRaises(ValidationError):
            self.mocked_query_params(url, AWSCostView)

    def test_aws_out_of_range_under_date(self):
        wrong_date = materialized_view_month_start() - timedelta(days=1)
        url = f"?order_by[cost]=desc&order_by[date]={wrong_date}&group_by[service]=*"
        with self.assertRaises(ValidationError):
            self.mocked_query_params(url, AWSCostView)

    def test_aws_out_of_range_over_date(self):
        wrong_date = DateHelper().today.date() + timedelta(days=1)
        url = f"?order_by[cost]=desc&order_by[date]={wrong_date}&group_by[service]=*"
        with self.assertRaises(ValidationError):
            self.mocked_query_params(url, AWSCostView)


class AWSReportQueryLogicalAndTest(IamTestCase):
    """Tests the report queries."""

    def setUp(self):
        """Set up the customer view tests."""
        self.dh = DateHelper()
        super().setUp()

    def test_prefixed_logical_and(self):
        """Test prefixed logical AND."""
        # Create Test Accounts
        # account_ab_fake_aws = FakeAWSCostData(self.provider, account_alias="ab")
        # self.generator.add_data_to_tenant(account_ab_fake_aws, product="ec2")

        # account_ac_fake_aws = FakeAWSCostData(self.provider, account_alias="ac")
        # self.generator.add_data_to_tenant(account_ac_fake_aws, product="ec2")

        data_to_test = {
            "1": {
                "url": "?group_by[and:account]=a&group_by[and:account]=b&filter[time_scope_value]=-1&filter[time_scope_units]=month"  # noqa
            },
            "2": {"url": "?group_by[account]=ab&filter[time_scope_value]=-1&filter[time_scope_units]=month"},
            "3": {
                "url": "?group_by[and:account]=a&group_by[and:account]=b&group_by[and:account]=c&filter[time_scope_value]=-1&filter[time_scope_units]=month"  # noqa
            },
            "4": {
                "url": "?group_by[account]=a&group_by[account]=b&filter[time_scope_value]=-1&filter[time_scope_units]=month"  # noqa
            },
        }

        for key in data_to_test.keys():
            query_params = self.mocked_query_params(data_to_test[key]["url"], AWSCostView)
            query_handler = AWSReportQueryHandler(query_params)
            query_output = query_handler.execute_query()
            query_total = query_output.get("total", {}).get("cost", {}).get("total", {}).get("value")
            self.assertIsNotNone(query_total)
            data_to_test[key]["total"] = query_total

        # Query 1: (a AND b) == Query 2: (ab)
        self.assertEqual(data_to_test["1"]["total"], data_to_test["2"]["total"])
        # Query 3: (a AND b AND c) == 0
        self.assertEqual(data_to_test["3"]["total"], 0)  # Test c == 0
        # Query 4: (a OR b) > Query 1: (a AND b)
        self.assertGreater(data_to_test["4"]["total"], data_to_test["1"]["total"])


class AWSQueryHandlerTest(IamTestCase):
    """Test the report queries."""

    def setUp(self):
        """Set up the customer view tests."""
        self.dh = DateHelper()
        super().setUp()

    def test_group_by_star_does_not_override_filters(self):
        """Test Group By star does not override filters, with example below.

        This is an expected response. Notice that the only region is eu-west-3
        {'data': [{'date': '2019-11-30', 'regions': []},
        {'date': '2019-12-01',
        'regions': [{'region': 'eu-west-3',
                        'services': [{'instance_types': [{'instance_type': 'r5.2xlarge',
                                                        'values': [{'cost': {'units': 'USD',
                                                                            'value': Decimal('2405.158832135')},
                                                                    'count': {'units': 'instances',
                                                                                'value': 1},
                                                                    'date': '2019-12-01',
                                                                    'derived_cost': {'units': 'USD',
                                                                                    'value': Decimal('0')},
                                                                    'infrastructure_cost': {'units': 'USD',
                                                                                            'value': Decimal('2186.508029214')}, # noqa
                                                                    'instance_type': 'r5.2xlarge',
                                                                    'markup_cost': {'units': 'USD',
                                                                                     'value': Decimal('218.650802921')},
                                                                    'region': 'eu-west-3',
                                                                    'service': 'AmazonEC2',
                                                                    'usage': {'units': 'Hrs',
                                                                                'value': Decimal('3807.000000000')}}]}],
                                    'service': 'AmazonEC2'}]}]},
        {'date': '2019-12-02', 'regions': []},
        {'date': '2019-12-03', 'regions': []},
        {'date': '2019-12-04', 'regions': []},
        {'date': '2019-12-05', 'regions': []},
        {'date': '2019-12-06', 'regions': []},
        {'date': '2019-12-07', 'regions': []},
        {'date': '2019-12-08', 'regions': []},
        {'date': '2019-12-09', 'regions': []}],

        """

        # First Request:
        url = "?group_by[region]=*&filter[region]=eu-west-3&group_by[service]=AmazonEC2"
        query_params = self.mocked_query_params(url, AWSInstanceTypeView)
        handler = AWSReportQueryHandler(query_params)
        data = handler.execute_query()
        # Second Request:
        url2 = "?group_by[region]=eu-west-3&group_by[service]=AmazonEC2"
        query_params2 = self.mocked_query_params(url2, AWSInstanceTypeView)
        handler2 = AWSReportQueryHandler(query_params2)
        data2 = handler2.execute_query()
        # Assert the second request contains only eu-west-3 region
        for region_dict in data2["data"]:
            # For each date, assert that the region is eu-west-3
            for list_item in region_dict["regions"]:
                self.assertEquals("eu-west-3", list_item["region"])
        # Assert the first request contains only eu-west-3
        for region_dict in data["data"]:
            # For each date, assert that the region is eu-west-3
            for list_item in region_dict["regions"]:
                self.assertEquals("eu-west-3", list_item["region"])

    def test_filter_to_group_by(self):
        """Test the filter_to_group_by method."""
        url = "?group_by[region]=*&filter[region]=eu-west-3&group_by[service]=AmazonEC2"
        query_params = self.mocked_query_params(url, AWSInstanceTypeView)
        handler = AWSReportQueryHandler(query_params)
        query_params = handler.filter_to_order_by(query_params)

        self.assertEqual(["eu-west-3"], query_params._parameters["group_by"]["region"])

    def test_filter_to_group_by_3(self):
        """Test group_by[service]=something AND group_by[service]=*."""
        url = "?group_by[region]=*&filter[region]=eu-west-3&group_by[service]=AmazonEC2&group_by[service]=*&filter[service]=AmazonEC2"  # noqa
        query_params = self.mocked_query_params(url, AWSInstanceTypeView)
        handler = AWSReportQueryHandler(query_params)
        query_params = handler.filter_to_order_by(query_params)

        self.assertEqual(["eu-west-3"], query_params._parameters["group_by"]["region"])
        self.assertEqual(["AmazonEC2"], query_params._parameters["group_by"]["service"])

    def test_filter_to_group_by_star(self):
        """Test group_by star."""
        url = "?group_by[region]=*&group_by[service]=*"
        query_params = self.mocked_query_params(url, AWSInstanceTypeView)
        handler = AWSReportQueryHandler(query_params)
        query_params = handler.filter_to_order_by(query_params)
        self.assertEqual(["*"], query_params._parameters["group_by"]["region"])
        self.assertEqual(["*"], query_params._parameters["group_by"]["service"])

    def test_two_filters_and_group_by_star(self):
        """
        Test two filters for the same category.

        For example, group_by[service]=*&filter[service]=X&filter[service]=Y
        """
        url = "?group_by[region]=*&filter[region]=eu-west-3&filter[region]=us-west-1"
        query_params = self.mocked_query_params(url, AWSInstanceTypeView)
        handler = AWSReportQueryHandler(query_params)
        query_params = handler.filter_to_order_by(query_params)
        region_1_exists = False
        region_2_exists = False
        if "eu-west-3" in query_params._parameters["group_by"]["region"]:
            region_1_exists = True
        if "us-west-1" in query_params._parameters["group_by"]["region"]:
            region_2_exists = True
        # Both regions should be in the resulting group_by list.
        self.assertTrue(region_1_exists)
        self.assertTrue(region_2_exists)

    def test_query_no_account_group_check_tags_no_tags(self):
        """Test "tags_exist" is not present if not grouping by account, and has "check_tags" parameter."""
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&group_by[service]=AmazonEC2&check_tags=true"  # noqa: E501
        query_params = self.mocked_query_params(url, AWSCostView)
        handler = AWSReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")
        self.assertIsNotNone(data)

        for data_item in data:
            for account_item in data_item["services"]:
                for value_item in account_item["values"]:
                    self.assertTrue("tags_exist" not in value_item)

    def test_query_account_group_no_check_tags_no_tags(self):
        """Test "tags_exist" is not present if grouping by account, but missing "check_tags" parameter."""
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&group_by[account]=*"  # noqa: E501
        query_params = self.mocked_query_params(url, AWSCostView)
        handler = AWSReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")
        self.assertIsNotNone(data)

        for data_item in data:
            for account_item in data_item["accounts"]:
                for value_item in account_item["values"]:
                    self.assertTrue("tags_exist" not in value_item)

    def test_query_account_group_check_tags_has_tags(self):
        """Test "tags_exist" is present if grouping by account and has "check_tags" parameter."""
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&group_by[account]=*&check_tags=true"  # noqa: E501
        query_params = self.mocked_query_params(url, AWSCostView)
        handler = AWSReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")
        self.assertIsNotNone(data)

        for data_item in data:
            for account_item in data_item["accounts"]:
                for value_item in account_item["values"]:
                    self.assertTrue("tags_exist" in value_item)

    def test_query_account_group_no_check_tags_has_tags_base_table(self):
        """Test "tags_exist" is not present if grouping by account as well as
        another group and has"check_tags" parameter."""
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&group_by[or:account]=*&group_by[or:service]=AmazonEC2&check_tags=true"  # noqa: E501
        query_params = self.mocked_query_params(url, AWSCostView)
        handler = AWSReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")
        self.assertIsNotNone(data)

        for data_item in data:
            for account_item in data_item["accounts"]:
                for service_item in account_item["services"]:
                    for value_item in service_item["values"]:
                        self.assertTrue("tags_exist" in value_item)

    def test_query_cost_type_default(self):
        """Test "cost_type" is defaulted when not passed in."""
        url = (
            "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&check_tags=true"
        )  # noqa: E501
        query_params = self.mocked_query_params(url, AWSCostView)
        handler = AWSReportQueryHandler(query_params)
        query_output = handler.execute_query()
        cost_type = query_output.get("cost_type")
        self.assertEqual(cost_type, "unblended_cost")

    def test_query_cost_type_passed_in(self):
        """Test "cost_type" is recognized when passed in."""
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&check_tags=true&cost_type=blended_cost"  # noqa: E501
        query_params = self.mocked_query_params(url, AWSCostView)
        handler = AWSReportQueryHandler(query_params)
        query_output = handler.execute_query()
        cost_type = query_output.get("cost_type")
        self.assertEqual(cost_type, "blended_cost")

    def test_source_uuid_mapping(self):  # noqa: C901
        """Test source_uuid is mapped to the correct source."""
        with tenant_context(self.tenant):
            aws_uuids = AWSCostEntryLineItemDailySummary.objects.distinct().values_list("source_uuid", flat=True)
            expected_source_uuids = AWSCostEntryBill.objects.distinct().values_list("provider_id", flat=True)
            for aws_uuid in aws_uuids:
                self.assertIn(aws_uuid, expected_source_uuids)
        endpoints = [AWSCostView, AWSInstanceTypeView, AWSStorageView]
        source_uuid_list = []
        for endpoint in endpoints:
            for url in ["?", "?group_by[account]=*", "?group_by[region]=*", "?group_by[service]=*"]:
                query_params = self.mocked_query_params(url, endpoint)
                handler = AWSReportQueryHandler(query_params)
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

    def test_query_table(self):
        """Test that the correct view is assigned by query table property."""
        test_cases = [
            ("?", AWSCostView, AWSCostSummaryP),
            ("?group_by[account]=*", AWSCostView, AWSCostSummaryByAccountP),
            ("?group_by[region]=*", AWSCostView, AWSCostSummaryByRegionP),
            ("?group_by[region]=*&group_by[account]=*", AWSCostView, AWSCostSummaryByRegionP),
            ("?group_by[service]=*", AWSCostView, AWSCostSummaryByServiceP),
            ("?group_by[service]=*&group_by[account]=*", AWSCostView, AWSCostSummaryByServiceP),
            ("?", AWSInstanceTypeView, AWSComputeSummaryP),
            ("?group_by[account]=*", AWSInstanceTypeView, AWSComputeSummaryByAccountP),
            ("?group_by[region]=*", AWSInstanceTypeView, AWSComputeSummaryByRegionP),
            ("?group_by[region]=*&group_by[account]=*", AWSInstanceTypeView, AWSComputeSummaryByRegionP),
            ("?group_by[service]=*", AWSInstanceTypeView, AWSComputeSummaryByServiceP),
            ("?group_by[service]=*&group_by[account]=*", AWSInstanceTypeView, AWSComputeSummaryByServiceP),
            ("?group_by[product_family]=*", AWSInstanceTypeView, AWSComputeSummaryByServiceP),
            ("?group_by[product_family]=*&group_by[account]=*", AWSInstanceTypeView, AWSComputeSummaryByServiceP),
            ("?group_by[instance_type]=*", AWSInstanceTypeView, AWSComputeSummaryP),
            ("?group_by[instance_type]=*&group_by[account]=*", AWSInstanceTypeView, AWSComputeSummaryByAccountP),
            ("?", AWSStorageView, AWSStorageSummaryP),
            ("?group_by[account]=*", AWSStorageView, AWSStorageSummaryByAccountP),
            ("?group_by[region]=*", AWSStorageView, AWSStorageSummaryByRegionP),
            ("?group_by[region]=*&group_by[account]=*", AWSStorageView, AWSStorageSummaryByRegionP),
            ("?group_by[service]=*", AWSStorageView, AWSStorageSummaryByServiceP),
            ("?group_by[service]=*&group_by[account]=*", AWSStorageView, AWSStorageSummaryByServiceP),
            ("?group_by[product_family]=*", AWSStorageView, AWSStorageSummaryByServiceP),
            ("?group_by[product_family]=*&group_by[account]=*", AWSStorageView, AWSStorageSummaryByServiceP),
            (
                (
                    "?filter[service]=AmazonRDS,AmazonDynamoDB,AmazonElastiCache,"
                    "AmazonNeptune,AmazonRedshift,AmazonDocumentDB"
                ),
                AWSCostView,
                AWSDatabaseSummaryP,
            ),
            (
                (
                    "?filter[service]=AmazonRDS,AmazonDynamoDB,AmazonElastiCache,"
                    "AmazonNeptune,AmazonRedshift,AmazonDocumentDB&group_by[account]=*"
                ),
                AWSCostView,
                AWSDatabaseSummaryP,
            ),
            (
                "?filter[service]=AmazonVPC,AmazonCloudFront,AmazonRoute53,AmazonAPIGateway",  # noqa: E501
                AWSCostView,
                AWSNetworkSummaryP,
            ),
            (
                "?filter[service]=AmazonVPC,AmazonCloudFront,AmazonRoute53,AmazonAPIGateway&group_by[account]=*",  # noqa: E501
                AWSCostView,
                AWSNetworkSummaryP,
            ),
        ]

        for test_case in test_cases:
            with self.subTest(test_case=test_case):
                url, view, table = test_case
                query_params = self.mocked_query_params(url, view)
                handler = AWSReportQueryHandler(query_params)
                self.assertEqual(handler.query_table, table)
