#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Test the Report Queries."""
import logging
from datetime import timedelta
from decimal import Decimal
from decimal import ROUND_HALF_UP
from unittest.mock import patch
from unittest.mock import PropertyMock
from uuid import uuid4

from dateutil.relativedelta import relativedelta
from django.db.models import F
from django.db.models import Sum
from django.urls import reverse
from rest_framework.exceptions import ValidationError
from tenant_schemas.utils import tenant_context

from api.currency.utils import exchange_dictionary
from api.iam.test.iam_test_case import IamTestCase
from api.models import Provider
from api.query_filter import QueryFilter
from api.report.gcp.openshift.query_handler import OCPGCPReportQueryHandler
from api.report.gcp.openshift.view import OCPGCPCostView
from api.report.gcp.openshift.view import OCPGCPInstanceTypeView
from api.report.gcp.openshift.view import OCPGCPStorageView
from api.report.test.util.constants import GCP_SERVICE_ALIASES
from api.utils import DateHelper
from api.utils import materialized_view_month_start
from reporting.models import GCPCostEntryBill
from reporting.models import OCPGCPComputeSummaryP
from reporting.models import OCPGCPCostLineItemDailySummaryP
from reporting.models import OCPGCPCostSummaryByAccountP
from reporting.models import OCPGCPCostSummaryByServiceP
from reporting.models import OCPGCPCostSummaryP
from reporting.models import OCPGCPStorageSummaryP


LOG = logging.getLogger(__name__)

RATES = {"USD": "1"}


class OCPGCPQueryHandlerTestNoData(IamTestCase):
    """Tests for the OCP report query handler with no data."""

    def setUp(self):
        """Set up the customer view tests."""
        super().setUp()
        self.dh = DateHelper()
        exchange_dictionary(RATES)

        self.this_month_filter = {"usage_start__gte": self.dh.this_month_start.date()}
        self.ten_day_filter = {"usage_start__gte": self.dh.n_days_ago(self.dh.today, 9).date()}
        self.thirty_day_filter = {"usage_start__gte": self.dh.n_days_ago(self.dh.today, 29).date()}
        self.last_month_filter = {
            "usage_start__gte": self.dh.last_month_start.date(),
            "usage_end__lte": self.dh.last_month_end.date(),
        }

    def test_execute_sum_query_instance_types_1(self):
        """Test that the sum query runs properly for instance-types."""
        url = "?group_by[account]=not-a-real-account"
        query_params = self.mocked_query_params(url, OCPGCPInstanceTypeView)
        handler = OCPGCPReportQueryHandler(query_params)
        query_output = handler.execute_query()
        self.assertIsNotNone(query_output.get("data"))
        self.assertIsNotNone(query_output.get("total"))
        total = query_output.get("total")
        keys_units = {"usage": "hour", "infrastructure": "USD", "supplementary": "USD", "cost": "USD"}
        has_total_list = ["cost", "infrastructure", "supplementary"]
        for key, unit in keys_units.items():
            self.assertIsNotNone(total.get(key))
            self.assertIsInstance(total.get(key), dict)
            if key in has_total_list:
                self.assertEqual(total.get(key).get("total", {}).get("value"), 0)
                self.assertEqual(total.get(key).get("total", {}).get("units"), unit)
            else:
                self.assertEqual(total.get(key).get("value"), 0)
                self.assertEqual(total.get(key).get("units"), unit)


class OCPGCPQueryHandlerTest(IamTestCase):
    """Tests for the OCP report query handler."""

    def setUp(self):
        """Set up the customer view tests."""
        super().setUp()
        self.dh = DateHelper()
        exchange_dictionary(RATES)

        # Use one of the test-runner created providers
        self.provider = Provider.objects.filter(type=Provider.PROVIDER_OCP).first()

        self.this_month_filter = {"usage_start__gte": self.dh.this_month_start}
        self.ten_day_filter = {"usage_start__gte": self.dh.n_days_ago(self.dh.today, 9)}
        self.thirty_day_filter = {"usage_start__gte": self.dh.n_days_ago(self.dh.today, 29)}
        self.last_month_filter = {
            "usage_start__gte": self.dh.last_month_start,
            "usage_end__lte": self.dh.last_month_end,
        }

    def get_totals_by_time_scope(self, aggregates, filters=None):
        """Return the total aggregates for a time period."""
        if filters is None:
            filters = self.ten_day_filter
        with tenant_context(self.tenant):
            return OCPGCPCostLineItemDailySummaryP.objects.filter(**filters).aggregate(**aggregates)

    def test_execute_query_w_delta_no_previous_data(self):
        """Test deltas with no previous data."""
        url = "?filter[time_scope_value]=-2&delta=cost"
        path = reverse("reports-openshift-gcp-costs")
        query_params = self.mocked_query_params(url, OCPGCPCostView, path)
        handler = OCPGCPReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")
        self.assertIsNotNone(data)
        total_cost = query_output.get("total", {}).get("cost", {}).get("total").get("value", 1)
        delta = query_output.get("delta")
        self.assertIsNotNone(delta.get("value"))
        self.assertIsNone(delta.get("percent", 0))
        self.assertEqual(delta.get("value", 0), total_cost)

    def test_execute_query_orderby_delta(self):
        """Test execute_query with ordering by delta ascending."""
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&order_by[delta]=asc&group_by[account]=*&delta=cost"  # noqa: E501
        path = reverse("reports-openshift-gcp-costs")
        query_params = self.mocked_query_params(url, OCPGCPCostView, path)
        handler = OCPGCPReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")
        self.assertIsNotNone(data)
        cmonth_str = self.dh.this_month_start.strftime("%Y-%m")
        for data_item in data:
            month_val = data_item.get("date", "not-a-date")
            month_data = data_item.get("accounts")
            self.assertEqual(month_val, cmonth_str)
            self.assertIsInstance(month_data, list)
            for month_item in month_data:
                self.assertIsInstance(month_item.get("account"), str)
                self.assertIsInstance(month_item.get("values"), list)
                self.assertIsInstance(month_item.get("values")[0].get("delta_value"), Decimal)

    def test_percent_delta(self):
        """Test _percent_delta() utility method."""
        url = "?"
        query_params = self.mocked_query_params(url, OCPGCPCostView)
        handler = OCPGCPReportQueryHandler(query_params)
        self.assertEqual(handler._percent_delta(10, 5), 100)

    def test_rank_list_by_account(self):
        """Test rank list limit with account alias."""
        # No need to fill db
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&filter[limit]=2&group_by[account]=*"  # noqa: E501
        query_params = self.mocked_query_params(url, OCPGCPCostView)
        handler = OCPGCPReportQueryHandler(query_params)
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

    def test_rank_list_by_service(self):
        """Test rank list limit with service grouping."""
        # No need to fill db
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&filter[limit]=2&group_by[service]=*"  # noqa: E501
        query_params = self.mocked_query_params(url, OCPGCPCostView)
        handler = OCPGCPReportQueryHandler(query_params)
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
        # No need to fill db
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&filter[limit]=1&filter[offset]=1&group_by[account]=*"  # noqa: E501
        query_params = self.mocked_query_params(url, OCPGCPCostView)
        handler = OCPGCPReportQueryHandler(query_params)
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
        query_params = self.mocked_query_params(url, OCPGCPCostView)
        handler = OCPGCPReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")
        self.assertIsNotNone(data)

        for data_item in data:
            accounts = data_item.get("accounts")
            for account in accounts:
                self.assertIsNotNone(account.get("values"))
                self.assertGreater(len(account.get("values")), 0)
                for value in account.get("values"):
                    self.assertIsInstance(value.get("cost", {}).get("total", {}).get("value"), Decimal)
                    self.assertGreater(value.get("cost", {}).get("total", {}).get("value"), Decimal(0))

    def test_query_storage_with_totals(self):
        """Test execute_query() - storage with totals.

        Query for storage, validating that cost totals are present.

        """
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&group_by[service]=*"  # noqa: E501
        query_params = self.mocked_query_params(url, OCPGCPStorageView)
        handler = OCPGCPReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")
        self.assertIsNotNone(data)

        for data_item in data:
            services = data_item.get("services")
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
        query_params = self.mocked_query_params(url, OCPGCPCostView)
        handler = OCPGCPReportQueryHandler(query_params)

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
        query_params = self.mocked_query_params(url, OCPGCPCostView)
        handler = OCPGCPReportQueryHandler(query_params)

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

    def test_query_table(self):
        """Test that the correct view is assigned by query table property."""
        url = "?"
        query_params = self.mocked_query_params(url, OCPGCPCostView)
        handler = OCPGCPReportQueryHandler(query_params)
        self.assertEqual(handler.query_table, OCPGCPCostSummaryP)

        url = "?group_by[account]=*"
        query_params = self.mocked_query_params(url, OCPGCPCostView)
        handler = OCPGCPReportQueryHandler(query_params)
        self.assertEqual(handler.query_table, OCPGCPCostSummaryByAccountP)

        url = "?group_by[service]=*"
        query_params = self.mocked_query_params(url, OCPGCPCostView)
        handler = OCPGCPReportQueryHandler(query_params)
        self.assertEqual(handler.query_table, OCPGCPCostSummaryByServiceP)

        url = "?group_by[service]=*&group_by[account]=*"
        query_params = self.mocked_query_params(url, OCPGCPCostView)
        handler = OCPGCPReportQueryHandler(query_params)
        self.assertEqual(handler.query_table, OCPGCPCostSummaryByServiceP)

        url = "?"
        query_params = self.mocked_query_params(url, OCPGCPInstanceTypeView)
        handler = OCPGCPReportQueryHandler(query_params)
        self.assertEqual(handler.query_table, OCPGCPComputeSummaryP)

        url = "?group_by[account]=*"
        query_params = self.mocked_query_params(url, OCPGCPInstanceTypeView)
        handler = OCPGCPReportQueryHandler(query_params)
        self.assertEqual(handler.query_table, OCPGCPComputeSummaryP)

        url = "?"
        query_params = self.mocked_query_params(url, OCPGCPStorageView)
        handler = OCPGCPReportQueryHandler(query_params)
        self.assertEqual(handler.query_table, OCPGCPStorageSummaryP)

        url = "?group_by[account]=*"
        query_params = self.mocked_query_params(url, OCPGCPStorageView)
        handler = OCPGCPReportQueryHandler(query_params)
        self.assertEqual(handler.query_table, OCPGCPStorageSummaryP)

        # url = (
        #     "?filter[service]=Virtual Network,VPN,DNS,Traffic Manager,"
        #     "ExpressRoute,Load Balancer,Application Gateway"
        # )
        # query_params = self.mocked_query_params(url, OCPGCPCostView)
        # handler = OCPGCPReportQueryHandler(query_params)
        # self.assertEqual(handler.query_table, OCPGCPNetworkSummaryP)

        # url = (
        #     "?filter[service]=Virtual Network,VPN,DNS,Traffic Manager,"
        #     "ExpressRoute,Load Balancer,Application Gateway"
        #     "&group_by[account]=*"
        # )
        # query_params = self.mocked_query_params(url, OCPGCPCostView)
        # handler = OCPGCPReportQueryHandler(query_params)
        # self.assertEqual(handler.query_table, OCPGCPNetworkSummaryP)

        # url = "?filter[service]=Cosmos DB,Cache for Redis,Database"
        # query_params = self.mocked_query_params(url, OCPGCPCostView)
        # handler = OCPGCPReportQueryHandler(query_params)
        # self.assertEqual(handler.query_table, OCPGCPDatabaseSummaryP)

        # url = "?filter[service]=Cosmos DB,Cache for Redis,Database" "&group_by[account]=*"
        # query_params = self.mocked_query_params(url, OCPGCPCostView)
        # handler = OCPGCPReportQueryHandler(query_params)
        # self.assertEqual(handler.query_table, OCPGCPDatabaseSummaryP)

    def test_ocp_gcp_date_order_by_cost_desc(self):
        """Test execute_query with order by date for correct order of services."""
        yesterday = self.dh.yesterday.date()
        url = f"?order_by[cost]=desc&order_by[date]={yesterday}&group_by[service]=*"
        query_params = self.mocked_query_params(url, OCPGCPCostView)
        handler = OCPGCPReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")
        cost_annotation = handler.report_annotations.get("cost_total")
        with tenant_context(self.tenant):
            expected = list(
                OCPGCPCostSummaryByServiceP.objects.filter(usage_start=str(yesterday))
                .values("service_alias")
                .annotate(cost=cost_annotation)
                .order_by("-cost")
            )
        correctlst = [service.get("service_alias") for service in expected]
        for element in data:
            lst = [service.get("service") for service in element.get("services", [])]
            if lst and correctlst:
                self.assertEqual(correctlst, lst)

    def test_ocp_gcp_date_incorrect_date(self):
        wrong_date = "200BC"
        url = f"?order_by[cost]=desc&order_by[date]={wrong_date}&group_by[service]=*"  # noqa: E501
        with self.assertRaises(ValidationError):
            self.mocked_query_params(url, OCPGCPCostView)

    def test_ocp_gcp_out_of_range_under_date(self):
        wrong_date = materialized_view_month_start() - timedelta(days=1)
        url = f"?order_by[cost]=desc&order_by[date]={wrong_date}&group_by[service]=*"
        with self.assertRaises(ValidationError):
            self.mocked_query_params(url, OCPGCPCostView)

    def test_ocp_gcp_out_of_range_over_date(self):
        wrong_date = DateHelper().today.date() + timedelta(days=1)
        url = f"?order_by[cost]=desc&order_by[date]={wrong_date}&group_by[service]=*"
        with self.assertRaises(ValidationError):
            self.mocked_query_params(url, OCPGCPCostView)

    def test_execute_query_by_filtered_cluster(self):
        """Test execute_query monthly breakdown by filtered cluster."""
        with tenant_context(self.tenant):
            cluster = OCPGCPCostLineItemDailySummaryP.objects.values("cluster_id")[0].get("cluster_id")
        url = f"?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&group_by[cluster]={cluster}"  # noqa: E501
        query_params = self.mocked_query_params(url, OCPGCPCostView)
        handler = OCPGCPReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get("total"))
        total = query_output.get("total")
        aggregates = handler._mapper.report_type_map.get("aggregates")
        filters = {**self.this_month_filter, "cluster_id__icontains": cluster}
        for filt in handler._mapper.report_type_map.get("filter"):
            if filt:
                qf = QueryFilter(**filt)
                filters[qf.composed_query_string()] = qf.parameter
        current_totals = self.get_totals_by_time_scope(aggregates, filters)
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

    def test_execute_query_by_filtered_service(self):
        """Test execute_query monthly breakdown by filtered service."""
        with tenant_context(self.tenant):
            valid_services = [
                service[0]
                for service in OCPGCPCostLineItemDailySummaryP.objects.values_list("service_alias").distinct()
            ]
            service = valid_services[0]
        url = f"?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&group_by[service]={service}"  # noqa: E501
        query_params = self.mocked_query_params(url, OCPGCPCostView)
        handler = OCPGCPReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")
        total = query_output.get("total")
        self.assertIsNotNone(data)
        self.assertIsNotNone(total)
        aggregates = handler._mapper.report_type_map.get("aggregates")
        filters = {**self.this_month_filter, "service_alias__icontains": service}
        for filt in handler._mapper.report_type_map.get("filter"):
            if filt:
                qf = QueryFilter(**filt)
                filters[qf.composed_query_string()] = qf.parameter
        current_totals = self.get_totals_by_time_scope(aggregates, filters)
        self.assertIsNotNone(total.get("cost"))
        self.assertEqual(total.get("cost", {}).get("total", {}).get("value", 0), current_totals.get("cost_total", 1))

        cmonth_str = self.dh.this_month_start.strftime("%Y-%m")
        for data_item in data:
            month_val = data_item.get("date", "not-a-date")
            month_data = data_item.get("services")
            self.assertEqual(month_val, cmonth_str)
            self.assertIsInstance(month_data, list)
            for month_item in month_data:
                name = month_item.get("service")
                self.assertIn(name, valid_services)
                self.assertIsInstance(month_item.get("values"), list)

    def test_execute_query_current_month_filter_service(self):
        """Test execute_query for current month on monthly filtered by service."""
        with tenant_context(self.tenant):
            service = OCPGCPCostLineItemDailySummaryP.objects.values("service_alias")[0].get("service_alias")
        url = f"?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&filter[service]={service}"  # noqa: E501
        query_params = self.mocked_query_params(url, OCPGCPCostView)
        handler = OCPGCPReportQueryHandler(query_params)
        query_output = handler.execute_query()

        data = query_output.get("data")
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get("total"))

        total = query_output.get("total")
        aggregates = handler._mapper.report_type_map.get("aggregates")
        filters = {**self.this_month_filter, "service_alias__icontains": service}
        for filt in handler._mapper.report_type_map.get("filter"):
            if filt:
                qf = QueryFilter(**filt)
                filters[qf.composed_query_string()] = qf.parameter
        current_totals = self.get_totals_by_time_scope(aggregates, filters)
        self.assertIsNotNone(total.get("cost"))
        self.assertEqual(total.get("cost", {}).get("total", {}).get("value", 0), current_totals.get("cost_total", 1))

        cmonth_str = self.dh.this_month_start.strftime("%Y-%m")
        for data_item in data:
            month_val = data_item.get("date", "not-a-date")
            month_data = data_item.get("values")
            self.assertEqual(month_val, cmonth_str)
            self.assertIsInstance(month_data, list)

    def test_execute_query_current_month_filter_account(self):
        """Test execute_query for current month on monthly filtered by account."""
        with tenant_context(self.tenant):
            account = OCPGCPCostLineItemDailySummaryP.objects.values("account_id")[0].get("account_id")
        url = f"?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&filter[account]={account}"  # noqa: E501
        query_params = self.mocked_query_params(url, OCPGCPCostView)
        handler = OCPGCPReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get("total"))
        total = query_output.get("total")
        aggregates = handler._mapper.report_type_map.get("aggregates")
        filters = {**self.this_month_filter, "account_id": account}
        current_totals = self.get_totals_by_time_scope(aggregates, filters)
        self.assertIsNotNone(total.get("cost"))
        self.assertEqual(total.get("cost", {}).get("total", {}).get("value", 0), current_totals.get("cost_total", 1))

        cmonth_str = self.dh.this_month_start.strftime("%Y-%m")
        for data_item in data:
            month_val = data_item.get("date", "not-a-date")
            month_data = data_item.get("values")
            self.assertEqual(month_val, cmonth_str)
            self.assertIsInstance(month_data, list)

    def test_execute_query_current_month_exclude_service(self):
        """Test execute_query for current month on monthly excluded by service."""
        with tenant_context(self.tenant):
            service = OCPGCPCostLineItemDailySummaryP.objects.values("service_alias")[0].get("service_alias")
        url = f"?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&exclude[service]={service}"  # noqa: E501
        query_params = self.mocked_query_params(url, OCPGCPCostView)
        handler = OCPGCPReportQueryHandler(query_params)
        query_output = handler.execute_query()

        data = query_output.get("data")
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get("total"))

    def test_execute_query_w_delta(self):
        """Test grouped by deltas."""

        path = reverse("reports-openshift-gcp-costs")
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&group_by[account]=*&delta=cost"  # noqa: E501
        query_params = self.mocked_query_params(url, OCPGCPCostView, path)
        handler = OCPGCPReportQueryHandler(query_params)
        # test the calculations
        query_output = handler.execute_query()
        data = query_output.get("data")
        self.assertIsNotNone(data)

        subs = data[0].get("accounts", [{}])
        v_today = self.dh.today.date()
        v_this_month_start = self.dh.this_month_start.date()
        v_today_last_month = (self.dh.today - relativedelta(months=1)).date()
        v_last_month_start = self.dh.last_month_start.date()

        for sub in subs:
            current_total = Decimal(0)
            prev_total = Decimal(0)

            # fetch the expected sums from the DB.
            with tenant_context(self.tenant):
                curr = OCPGCPCostSummaryByAccountP.objects.filter(
                    usage_start__gte=v_this_month_start, usage_start__lte=v_today, account_id=sub.get("account")
                ).aggregate(value=Sum(F("unblended_cost") + F("markup_cost") + F("credit_amount")))
                current_total = Decimal(curr.get("value"))

                prev = OCPGCPCostSummaryByAccountP.objects.filter(
                    usage_start__gte=v_last_month_start,
                    usage_start__lte=v_today_last_month,
                    account_id=sub.get("account"),
                ).aggregate(value=Sum(F("unblended_cost") + F("markup_cost") + F("credit_amount")))
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
            curr = OCPGCPCostSummaryByAccountP.objects.filter(
                usage_start__gte=self.dh.this_month_start, usage_start__lte=self.dh.today
            ).aggregate(value=Sum(F("unblended_cost") + F("markup_cost") + F("credit_amount")))
            current_total = Decimal(curr.get("value"))

            prev = OCPGCPCostSummaryByAccountP.objects.filter(
                usage_start__gte=self.dh.last_month_start, usage_start__lte=self.dh.today - relativedelta(months=1)
            ).aggregate(value=Sum(F("unblended_cost") + F("markup_cost") + F("credit_amount")))
            prev_total = Decimal(prev.get("value"))

        expected_delta_value = Decimal(current_total - prev_total)
        expected_delta_percent = Decimal((current_total - prev_total) / prev_total * 100)

        delta = query_output.get("delta")
        self.assertIsNotNone(delta.get("value"))
        self.assertIsNotNone(delta.get("percent"))
        self.assertEqual(delta.get("value", "str"), expected_delta_value)
        self.assertEqual(delta.get("percent", "str"), expected_delta_percent)

    def test_query_instance_types_with_totals(self):
        """Test execute_query() - instance types with totals.

        Query for instance_types, validating that cost totals are present.

        """
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&group_by[instance_type]=*"  # noqa: E501
        query_params = self.mocked_query_params(url, OCPGCPInstanceTypeView)
        handler = OCPGCPReportQueryHandler(query_params)
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
                    self.assertIsInstance(value.get("usage", {}), dict)
                    self.assertGreaterEqual(
                        value.get("usage", {}).get("value", {}).quantize(Decimal(".0001"), ROUND_HALF_UP), Decimal(0)
                    )

    def test_calculate_total(self):
        """Test that calculated totals return correctly."""
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly"
        query_params = self.mocked_query_params(url, OCPGCPCostView)
        handler = OCPGCPReportQueryHandler(query_params)
        expected_units = "USD"
        with tenant_context(self.tenant):
            result = handler.calculate_total(**{"cost_units": expected_units})

        aggregates = handler._mapper.report_type_map.get("aggregates")
        current_totals = self.get_totals_by_time_scope(aggregates, self.this_month_filter)
        self.assertEqual(result.get("cost", {}).get("total", {}).get("value", 0), current_totals.get("cost_total", 1))
        self.assertEqual(result.get("cost", {}).get("total", {}).get("units", "not-USD"), expected_units)

    def test_execute_query_curr_month_by_account_w_limit(self):
        """Test execute_query for current month on monthly breakdown by account with limit."""
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&filter[limit]=2&group_by[account]=*"  # noqa: E501
        query_params = self.mocked_query_params(url, OCPGCPCostView)
        handler = OCPGCPReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get("total"))
        total = query_output.get("total")
        aggregates = handler._mapper.report_type_map.get("aggregates")
        current_totals = self.get_totals_by_time_scope(aggregates, self.this_month_filter)
        self.assertIsNotNone(total.get("cost"))
        self.assertAlmostEqual(
            total.get("cost", {}).get("total", {}).get("value", 0), current_totals.get("cost_total", 1), 6
        )

        cmonth_str = DateHelper().this_month_start.strftime("%Y-%m")
        for data_item in data:
            month_val = data_item.get("date", "not-a-date")
            month_data = data_item.get("accounts")
            self.assertEqual(month_val, cmonth_str)
            self.assertIsInstance(month_data, list)
            self.assertEqual(1, len(month_data))
            for month_item in month_data:
                self.assertIsInstance(month_item.get("account"), str)
                self.assertIsInstance(month_item.get("values"), list)

    @patch("api.query_params.QueryParameters.accept_type", new_callable=PropertyMock)
    def test_execute_query_curr_month_by_account_w_limit_csv(self, mock_accept):
        """Test execute_query for current month on monthly by account with limt as csv."""
        mock_accept.return_value = "text/csv"

        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&filter[limit]=1&group_by[account]=*"  # noqa: E501
        query_params = self.mocked_query_params(url, OCPGCPCostView)
        handler = OCPGCPReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")
        self.assertIsNotNone(data)
        total = query_output.get("total")
        aggregates = handler._mapper.report_type_map.get("aggregates")
        current_totals = self.get_totals_by_time_scope(aggregates, self.this_month_filter)
        self.assertIsNotNone(current_totals)
        self.assertAlmostEqual(
            total.get("cost", {}).get("total", {}).get("value", 0), current_totals.get("cost_total", 1), 6
        )

        cmonth_str = DateHelper().this_month_start.strftime("%Y-%m")
        self.assertEqual(len(data), 1)
        for data_item in data:
            month = data_item.get("date")
            self.assertEqual(month, cmonth_str)

    def test_execute_query_curr_month_by_account_w_order(self):
        """Test execute_query for current month on monthly breakdown by account with asc order."""
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&order_by[cost]=asc&group_by[account]=*"  # noqa: E501
        query_params = self.mocked_query_params(url, OCPGCPCostView)
        handler = OCPGCPReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get("total"))
        total = query_output.get("total")
        aggregates = handler._mapper.report_type_map.get("aggregates")
        current_totals = self.get_totals_by_time_scope(aggregates, self.this_month_filter)
        self.assertIsNotNone(total.get("cost"))
        self.assertEqual(total.get("cost", {}).get("total", {}).get("value", 0), current_totals.get("cost_total", 1))

        cmonth_str = self.dh.this_month_start.strftime("%Y-%m")
        for data_item in data:
            month_val = data_item.get("date", "not-a-date")
            month_data = data_item.get("accounts")
            self.assertEqual(month_val, cmonth_str)
            self.assertIsInstance(month_data, list)
            self.assertEqual(len(month_data), 1)
            current_total = 0
            for month_item in month_data:
                self.assertIsInstance(month_item.get("account"), str)
                self.assertIsInstance(month_item.get("values"), list)
                self.assertIsNotNone(month_item.get("values")[0].get("cost", {}).get("total", {}).get("value"))
                data_point_total = month_item.get("values")[0].get("cost", {}).get("total", {}).get("value")
                self.assertLess(current_total, data_point_total)
                current_total = data_point_total

    def test_execute_query_curr_month_by_account_w_order_by_account(self):
        """Test execute_query for current month on monthly breakdown by account with asc order."""
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&order_by[account]=asc&group_by[account]=*"  # noqa: E501
        query_params = self.mocked_query_params(url, OCPGCPCostView)
        handler = OCPGCPReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get("total"))
        total = query_output.get("total")
        aggregates = handler._mapper.report_type_map.get("aggregates")
        current_totals = self.get_totals_by_time_scope(aggregates, self.this_month_filter)
        self.assertIsNotNone(total.get("cost"))
        self.assertEqual(total.get("cost", {}).get("total", {}).get("value", 0), current_totals.get("cost_total", 1))

        cmonth_str = self.dh.this_month_start.strftime("%Y-%m")
        for data_item in data:
            month_val = data_item.get("date", "not-a-date")
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

    def test_source_uuid_mapping(self):
        """Test source_uuid is mapped to the correct source."""
        endpoints = [OCPGCPCostView, OCPGCPInstanceTypeView, OCPGCPStorageView]
        with tenant_context(self.tenant):
            expected_source_uuids = list(GCPCostEntryBill.objects.distinct().values_list("provider_id", flat=True))
        source_uuid_list = []
        for endpoint in endpoints:
            urls = ["?"]
            if endpoint == OCPGCPCostView:
                urls.extend(["?group_by[account]=*", "?group_by[project]=*", "group_by[service]=*"])
            for url in urls:
                query_params = self.mocked_query_params(url, endpoint)
                handler = OCPGCPReportQueryHandler(query_params)
                query_output = handler.execute_query()
                for dikt in query_output.get("data", {}):
                    for v in dikt.get("values", []):
                        source_uuid_list.extend(v.get("source_uuid"))
        self.assertNotEqual(source_uuid_list, [])
        for source_uuid in source_uuid_list:
            self.assertIn(source_uuid, expected_source_uuids)

    def test_execute_query_curr_month_by_cluster(self):
        """Test execute_query for current month on monthly breakdown by group_by cluster."""
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&group_by[cluster]=*"  # noqa: E501
        query_params = self.mocked_query_params(url, OCPGCPCostView)
        handler = OCPGCPReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get("total"))
        total = query_output.get("total")
        aggregates = handler._mapper.report_type_map.get("aggregates")
        current_totals = self.get_totals_by_time_scope(aggregates, self.this_month_filter)
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

    def test_execute_query_current_month_by_account(self):
        """Test execute_query for current month on monthly breakdown by account."""
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&group_by[account]=*"  # noqa: E501
        query_params = self.mocked_query_params(url, OCPGCPCostView)
        handler = OCPGCPReportQueryHandler(query_params)
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
            month_data = data_item.get("accounts")
            self.assertEqual(month_val, cmonth_str)
            self.assertIsInstance(month_data, list)
            for month_item in month_data:
                self.assertIsInstance(month_item.get("values"), list)

    def test_execute_query_current_month_by_service(self):
        """Test execute_query for current month on monthly breakdown by service."""
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&group_by[service]=*"  # noqa: E501
        query_params = self.mocked_query_params(url, OCPGCPCostView)
        handler = OCPGCPReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get("total"))
        total = query_output.get("total")
        aggregates = handler._mapper.report_type_map.get("aggregates")
        current_totals = self.get_totals_by_time_scope(aggregates, self.this_month_filter)
        self.assertIsNotNone(total.get("cost"))
        self.assertEqual(total.get("cost", {}).get("total", {}).get("value", 0), current_totals.get("cost_total", 1))

        cmonth_str = self.dh.this_month_start.strftime("%Y-%m")
        for data_item in data:
            month_val = data_item.get("date", "not-a-date")
            month_data = data_item.get("services")
            self.assertEqual(month_val, cmonth_str)
            self.assertIsInstance(month_data, list)
            for month_item in month_data:
                name = month_item.get("service")
                self.assertIn(name, GCP_SERVICE_ALIASES)
                self.assertIsInstance(month_item.get("values"), list)

    def test_execute_query_current_month_daily(self):
        """Test execute_query for current month on daily breakdown."""
        url = "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=daily"
        query_params = self.mocked_query_params(url, OCPGCPCostView)
        handler = OCPGCPReportQueryHandler(query_params)
        query_output = handler.execute_query()
        self.assertIsNotNone(query_output.get("data"))
        self.assertIsNotNone(query_output.get("total"))
        total = query_output.get("total")
        self.assertIsNotNone(total.get("cost"))

        aggregates = handler._mapper.report_type_map.get("aggregates")
        current_totals = self.get_totals_by_time_scope(aggregates, self.this_month_filter)
        self.assertEqual(total.get("cost", {}).get("total", {}).get("value", 0), current_totals.get("cost_total", 1))

    def test_execute_sum_query_instance_types_2(self):
        """Test that the sum query runs properly."""
        url = "?"
        query_params = self.mocked_query_params(url, OCPGCPInstanceTypeView)
        handler = OCPGCPReportQueryHandler(query_params)
        query_output = handler.execute_query()
        self.assertIsNotNone(query_output.get("data"))
        self.assertIsNotNone(query_output.get("total"))

        aggregates = handler._mapper.report_type_map.get("aggregates")
        filters = {**self.ten_day_filter, "instance_type__isnull": False}
        current_totals = self.get_totals_by_time_scope(aggregates, filters)
        total = query_output.get("total")
        self.assertEqual(total.get("cost", {}).get("total", {}).get("value", 0), current_totals.get("cost_total", 1))

    def test_ocp_gcp_date_with_no_data(self):
        # This test will group by a date that is out of range for data generated.
        # The data will still return data because other dates will still generate data.
        yesterday = self.dh.yesterday.date()
        yesterday_month = self.dh.yesterday - relativedelta(months=2)

        url = f"?group_by[service]=*&order_by[cost]=desc&order_by[date]={yesterday_month.date()}&end_date={yesterday}&start_date={yesterday_month.date()}"  # noqa: E501
        query_params = self.mocked_query_params(url, OCPGCPCostView)
        handler = OCPGCPReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get("data")
        self.assertIsNotNone(data)


class OCPGCPReportQueryTestCurrency(IamTestCase):
    """Tests currency for report queries."""

    def setUp(self):
        """Set up the currency tests."""
        self.dh = DateHelper()
        super().setUp()
        self.tables = [
            OCPGCPCostLineItemDailySummaryP,
            OCPGCPCostSummaryByAccountP,
            OCPGCPCostSummaryByServiceP,
            OCPGCPCostSummaryP,
            OCPGCPComputeSummaryP,
            OCPGCPStorageSummaryP,
        ]
        self.neg_ten = self.dh.n_days_ago(self.dh.today, 10)
        self.currencies = ["USD", "CAD", "AUD"]
        self.ten_days_ago = self.dh.n_days_ago(self.dh.today, 9)
        dates = self.dh.list_days(self.ten_days_ago, self.dh.today)
        with tenant_context(self.tenant):
            for table in self.tables:
                kwargs = table.objects.filter(usage_start__gt=self.dh.last_month_end).values().first()
                for date in dates:
                    kwargs["usage_start"] = date
                    kwargs["usage_end"] = date
                    for currency in ["AUD", "CAD"]:
                        if table == OCPGCPCostLineItemDailySummaryP:
                            kwargs["uuid"] = uuid4()
                        else:
                            kwargs["id"] = uuid4()
                        kwargs["currency"] = currency
                        table.objects.create(**kwargs)
        self.exchange_dictionary = {
            "USD": {"USD": Decimal(1.0), "AUD": Decimal(2.0), "CAD": Decimal(3.0)},
            "AUD": {"USD": Decimal(0.5), "AUD": Decimal(1.0), "CAD": Decimal(0.67)},
            "CAD": {"USD": Decimal(0.33), "AUD": Decimal(1.5), "CAD": Decimal(1.0)},
        }

    def test_multiple_base_currencies(self):
        """Test that our dummy data has multiple base currencies."""
        with tenant_context(self.tenant):
            for table in self.tables:
                currencies = table.objects.values_list("currency", flat=True).distinct()
                self.assertGreater(len(currencies), 1)

    @patch("api.report.queries.ExchangeRateDictionary")
    def test_total_cost(self, mock_exchange):
        """Test overall cost"""
        for desired_currency in self.currencies:
            with self.subTest(desired_currency=desired_currency):
                expected_total = []
                url = f"?currency={desired_currency}"
                mock_exchange.objects.first().currency_exchange_dictionary = self.exchange_dictionary
                query_params = self.mocked_query_params(url, OCPGCPCostView)
                handler = OCPGCPReportQueryHandler(query_params)
                with tenant_context(self.tenant):
                    for currency in self.currencies:
                        filters = {
                            "usage_start__gte": self.ten_days_ago,
                            "invoice_month__in": self.dh.gcp_find_invoice_months_in_date_range(
                                self.ten_days_ago, self.dh.today
                            ),
                            "currency": currency,
                        }
                        aggregates = handler._mapper.report_type_map.get("aggregates")
                        querysets = OCPGCPCostSummaryP.objects.filter(**filters).aggregate(**aggregates)
                        rate = self.exchange_dictionary[currency][desired_currency]
                        expected_total.append(rate * querysets["cost_total"])
                query_output = handler.execute_query()
                total = query_output.get("total")
                total_value = total.get("cost").get("total").get("value")
                self.assertAlmostEqual(total_value, sum(expected_total))
