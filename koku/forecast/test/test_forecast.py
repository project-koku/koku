#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Forecast unit tests."""
import logging
import random
from datetime import date
from datetime import datetime
from datetime import timedelta
from decimal import Decimal
from unittest.mock import Mock
from unittest.mock import patch
from uuid import uuid4

from statsmodels.tools.sm_exceptions import ValueWarning

from api.forecast.views import AWSCostForecastView
from api.forecast.views import AzureCostForecastView
from api.forecast.views import GCPCostForecastView
from api.forecast.views import OCPAllCostForecastView
from api.forecast.views import OCPAWSCostForecastView
from api.forecast.views import OCPAzureCostForecastView
from api.forecast.views import OCPCostForecastView
from api.iam.test.iam_test_case import IamTestCase
from api.query_filter import QueryFilter
from api.query_filter import QueryFilterCollection
from api.report.test.test_queries import assertSameQ
from api.utils import DateHelper
from forecast import AWSForecast
from forecast import AzureForecast
from forecast import GCPForecast
from forecast import OCPAllForecast
from forecast import OCPAWSForecast
from forecast import OCPAzureForecast
from forecast import OCPForecast
from forecast.forecast import LinearForecastResult
from forecast.forecast import ZERO_RESULT
from reporting.provider.aws.models import AWSCostSummaryByAccountP
from reporting.provider.gcp.models import GCPCostSummaryByAccountP
from reporting.provider.gcp.models import GCPCostSummaryByProjectP
from reporting.provider.gcp.models import GCPCostSummaryP
from reporting.provider.ocp.models import OCPCostSummaryByNodeP
from reporting.provider.ocp.models import OCPCostSummaryP
from reporting.provider.ocp.models import OCPUsageLineItemDailySummary


class MockQuerySet:
    def __init__(self, data):
        """Set the queryset data as a instance variable."""
        self.data = data

    def values(self, *args):
        """Return data for the specified args."""
        results = []
        for row in self.data:
            results.append({arg: row.get(arg) for arg in args})
        return results

    @property
    def len(self):
        """Length of data."""
        return len(self.data)


class AWSForecastTest(IamTestCase):
    """Tests the AWSForecast class."""

    def test_constructor(self):
        """Test the constructor."""
        params = self.mocked_query_params("?", AWSCostForecastView)
        instance = AWSForecast(params)
        self.assertIsInstance(instance, AWSForecast)

    def test_forecast_days_required(self):
        """Test that we accurately select the number of days."""
        params = self.mocked_query_params("?", AWSCostForecastView)

        dh = DateHelper()
        mock_dh = Mock(spec=DateHelper)

        scenarios = [
            {
                "today": dh.today,
                "yesterday": dh.yesterday,
                "this_month_end": dh.this_month_end,
                "expected": max((dh.this_month_end - dh.yesterday).days, 2),
            },
            {
                "today": datetime(2000, 1, 1, 0, 0, 0, 0),
                "yesterday": datetime(1999, 12, 31, 0, 0, 0, 0),
                "this_month_end": datetime(2000, 1, 31, 0, 0, 0, 0),
                "expected": 31,
            },
            {
                "today": datetime(2000, 1, 31, 0, 0, 0, 0),
                "yesterday": datetime(2000, 1, 30, 0, 0, 0, 0),
                "this_month_end": datetime(2000, 1, 31, 0, 0, 0, 0),
                "expected": 2,
            },
        ]

        mock_dh.return_value.n_days_ago = dh.n_days_ago  # pass-thru to real function

        for test in scenarios:
            with self.subTest(scenario=test):
                mock_dh.return_value.today = test["today"]
                mock_dh.return_value.yesterday = test["yesterday"]
                mock_dh.return_value.this_month_end = test["this_month_end"]

                with patch("forecast.forecast.DateHelper", new_callable=lambda: mock_dh) as mock_dh:
                    forecast = AWSForecast(params)
                    self.assertEqual(forecast.forecast_days_required, test["expected"])

    def test_query_range(self):
        """Test that we select the correct range based on day of month."""
        params = self.mocked_query_params("?", AWSCostForecastView)

        dh = DateHelper()
        mock_dh = Mock(spec=DateHelper)

        scenarios = [
            {
                "today": dh.today,
                "yesterday": dh.yesterday,
                "this_month_end": dh.this_month_end,
                "expected": (dh.yesterday + timedelta(days=-30), dh.yesterday),
            },
            {
                "today": datetime(2000, 1, 1, 0, 0, 0, 0),
                "yesterday": datetime(1999, 12, 31, 0, 0, 0, 0),
                "this_month_end": datetime(2000, 1, 31, 0, 0, 0, 0),
                "expected": (
                    datetime(1999, 12, 31, 0, 0, 0, 0) + timedelta(days=-30),
                    datetime(1999, 12, 31, 0, 0, 0, 0),
                ),
            },
            {
                "today": datetime(2000, 1, 31, 0, 0, 0, 0),
                "yesterday": datetime(2000, 1, 30, 0, 0, 0, 0),
                "this_month_end": datetime(2000, 1, 31, 0, 0, 0, 0),
                "expected": (
                    datetime(2000, 1, 30, 0, 0, 0, 0) + timedelta(days=-30),
                    datetime(2000, 1, 30, 0, 0, 0, 0),
                ),
            },
        ]

        mock_dh.return_value.n_days_ago = dh.n_days_ago  # pass-thru to real function

        for test in scenarios:
            with self.subTest(scenario=test):
                mock_dh.return_value.today = test["today"]
                mock_dh.return_value.yesterday = test["yesterday"]
                mock_dh.return_value.this_month_end = test["this_month_end"]

                with patch("forecast.forecast.DateHelper", new_callable=lambda: mock_dh) as mock_dh:
                    forecast = AWSForecast(params)
                    self.assertEqual(forecast.query_range, test["expected"])

    def test_remove_outliers(self):
        """Test that we remove outliers before predicting."""
        params = self.mocked_query_params("?", AWSCostForecastView)
        dh = DateHelper()
        days_in_month = dh.this_month_end.day
        data = {}
        for i in range(days_in_month):
            data[dh.this_month_start + timedelta(days=i)] = Decimal(20)

        outlier = Decimal(100)
        data[dh.this_month_start] = outlier
        forecast = AWSForecast(params)
        result = forecast._remove_outliers(data)

        self.assertNotIn(dh.this_month_start, result.keys())
        self.assertNotIn(outlier, result.values())

    def test_predict_flat(self):
        """Test that predict() returns expected values for flat costs."""
        dh = DateHelper()

        expected = []
        for n in range(0, 10):
            expected.append(
                {
                    "usage_start": (dh.this_month_start + timedelta(days=n)).date(),
                    "total_cost": 5 + (0.01 * n),
                    "infrastructure_cost": 3 + (0.01 * n),
                    "supplementary_cost": 2 + (0.01 * n),
                }
            )
        mock_qset = MockQuerySet(expected)
        params = self.mocked_query_params("?", AWSCostForecastView)
        instance = AWSForecast(params)

        with patch("forecast.forecast.AWSForecast.get_data", return_value=mock_qset):
            results = instance.predict()

        for result in results:
            for val in result.get("values", []):
                with self.subTest(values=val):
                    self.assertIsInstance(val.get("date"), date)

                    for item, cost, delta in [
                        (val.get("cost"), 5, 1),
                        (val.get("infrastructure"), 3, 1),
                        (val.get("supplementary"), 2, 1),
                    ]:
                        with self.subTest(cost=cost, delta=delta, item=item):
                            self.assertAlmostEqual(float(item.get("total").get("value")), cost, delta=delta)
                            self.assertAlmostEqual(float(item.get("confidence_max").get("value")), cost, delta=delta)
                            self.assertAlmostEqual(float(item.get("confidence_min").get("value")), cost, delta=delta)
                            self.assertGreater(float(item.get("rsquared").get("value")), 0)
                            for pval in item.get("pvalues").get("value"):
                                self.assertGreaterEqual(float(pval), 0)

    def test_predict_increasing(self):
        """Test that predict() returns expected values for increasing costs."""
        dh = DateHelper()

        expected = []
        for n in range(0, 10):
            # the test data needs to include some jitter to avoid
            # division-by-zero in the underlying dot-product maths.
            expected.append(
                {
                    "usage_start": dh.n_days_ago(dh.today, 10 - n).date(),
                    "total_cost": 5 + random.random() + n,
                    "infrastructure_cost": 3 + random.random() + n,
                    "supplementary_cost": 2 + random.random() + n,
                }
            )
        mock_qset = MockQuerySet(expected)
        params = self.mocked_query_params("?", AWSCostForecastView)
        instance = AWSForecast(params)

        with patch("forecast.forecast.AWSForecast.get_data", return_value=mock_qset):
            results = instance.predict()

        for result in results:
            for val in result.get("values", []):
                self.assertIsInstance(val.get("date"), date)

                item = val.get("cost")
                self.assertGreaterEqual(float(item.get("total").get("value")), 0)
                self.assertGreaterEqual(float(item.get("confidence_max").get("value")), 0)
                self.assertGreaterEqual(float(item.get("confidence_min").get("value")), 0)
                self.assertGreaterEqual(float(item.get("rsquared").get("value")), 0)
                for pval in item.get("pvalues").get("value"):
                    self.assertGreaterEqual(float(pval), 0)

    def test_predict_response_date(self):
        """Test that predict() returns expected date range."""
        dh = DateHelper()

        expected = []
        for n in range(0, 10):
            expected.append(
                {
                    "usage_start": dh.n_days_ago(dh.today, 10 - n).date(),
                    "total_cost": 5,
                    "infrastructure_cost": 3,
                    "supplementary_cost": 2,
                }
            )
        mock_qset = MockQuerySet(expected)
        params = self.mocked_query_params("?", AWSCostForecastView)
        instance = AWSForecast(params)

        with patch("forecast.forecast.AWSForecast.get_data", return_value=mock_qset):
            results = instance.predict()

        for item in results:
            self.assertIsInstance(item.get("date"), date)
            self.assertLessEqual(item.get("date"), dh.this_month_end.date())

    def test_predict_few_values(self):
        """Test that predict() behaves well with a limited data set."""
        dh = DateHelper()

        num_elements = [AWSForecast.MINIMUM - 1, AWSForecast.MINIMUM, AWSForecast.MINIMUM + 1]

        for number in num_elements:
            with self.subTest(num_elements=number):
                expected = []
                for n in range(0, number):
                    # the test data needs to include some jitter to avoid
                    # division-by-zero in the underlying dot-product maths.
                    expected.append(
                        {
                            "usage_start": dh.n_days_ago(dh.today, 10 - n).date(),
                            "total_cost": 5 + (0.01 * n),
                            "infrastructure_cost": 3 + (0.01 * n),
                            "supplementary_cost": 2 + (0.01 * n),
                        }
                    )
                mock_qset = MockQuerySet(expected)

                params = self.mocked_query_params("?", AWSCostForecastView)
                instance = AWSForecast(params)

                if number < AWSForecast.MINIMUM:
                    # forecasting isn't useful with less than the minimum number of data points.
                    with self.assertLogs(logger="forecast.forecast", level=logging.WARNING):
                        with patch("forecast.forecast.AWSForecast.get_data", return_value=mock_qset):
                            results = instance.predict()
                        self.assertEqual(results, [])
                else:
                    with patch("forecast.forecast.AWSForecast.get_data", return_value=mock_qset):
                        results = instance.predict()

                    self.assertNotEqual(results, [])

                    for result in results:
                        for val in result.get("values", []):
                            self.assertIsInstance(val.get("date"), date)

                            item = val.get("cost")
                            self.assertGreaterEqual(float(item.get("total").get("value")), 0)
                            self.assertGreaterEqual(float(item.get("confidence_max").get("value")), 0)
                            self.assertGreaterEqual(float(item.get("confidence_min").get("value")), 0)
                            self.assertGreaterEqual(float(item.get("rsquared").get("value")), 0)
                            for pval in item.get("pvalues").get("value"):
                                self.assertGreaterEqual(float(pval), 0)
                    # test that the results always stop at the end of the month.
                    self.assertEqual(results[-1].get("date"), dh.this_month_end.date())

    def test_predict_end_of_month(self):
        """COST-1091: Test that predict() returns ZERO_RESULT on the last day of a month."""
        scenario = [(date(2000, 1, 31), 1.5)]

        params = self.mocked_query_params("?", AWSCostForecastView)
        instance = AWSForecast(params)

        out = instance._predict(scenario)
        self.assertEqual(out, ZERO_RESULT)

    def test_set_access_filter_with_list(self):
        """
        Tests that when an access restriction, filters, and a filter list are passed in,
        the correct query filters are added
        """
        # create the elements needed to mock the query handler
        params = self.mocked_query_params("", AWSCostForecastView)
        instance = AWSForecast(params)
        # set filters and access to be used in function
        filters = QueryFilterCollection()
        access = ["589173575009"]
        filt = [
            {"field": "account_alias__account_alias", "operation": "icontains", "composition_key": "account_filter"},
            {"field": "usage_account_id", "operation": "icontains", "composition_key": "account_filter"},
        ]
        expected = QueryFilterCollection(
            filters=[
                QueryFilter(field="account_alias__account_alias", operation="in", composition_key="account_filter"),
                QueryFilter(field="usage_account_id", operation="in", composition_key="account_filter"),
            ]
        )
        instance.set_access_filters(access, filt, filters)
        self.assertIsInstance(filters, QueryFilterCollection)
        assertSameQ(filters.compose(), expected.compose())

    def test_set_access_filter_without_list(self):
        """
        Tests that when an access restriction, filters, and a filter list are passed in,
        the correct query filters are added
        """
        # create the elements needed to mock the query handler
        params = self.mocked_query_params("", AWSCostForecastView)
        instance = AWSForecast(params)
        # set filters and access to be used in function
        filters = QueryFilterCollection()
        access = ["589173575009"]
        filt = {"field": "account_alias__account_alias", "operation": "icontains", "composition_key": "account_filter"}
        expected = QueryFilterCollection(
            filters=[
                QueryFilter(field="account_alias__account_alias", operation="in", composition_key="account_filter")
            ]
        )
        instance.set_access_filters(access, filt, filters)
        self.assertIsInstance(filters, QueryFilterCollection)
        assertSameQ(filters.compose(), expected.compose())

    def test_enumerate_dates(self):
        """Test that the _enumerate_dates() method gives expected results."""
        test_scenarios = [
            {"dates": [date(2000, 1, 1), date(2000, 1, 2), date(2000, 1, 3)], "expected": [0, 1, 2]},
            {"dates": [date(2000, 1, 1), date(2000, 1, 3), date(2000, 1, 5)], "expected": [0, 2, 4]},
            {"dates": [date(2000, 1, 1), date(2000, 1, 2), date(2000, 1, 5)], "expected": [0, 1, 4]},
            {"dates": [date(2000, 1, 1), date(2000, 1, 4), date(2000, 1, 5)], "expected": [0, 3, 4]},
        ]

        params = self.mocked_query_params("?", AWSCostForecastView)
        instance = AWSForecast(params)

        for scenario in test_scenarios:
            with self.subTest(dates=scenario["dates"], expected=scenario["expected"]):
                out = instance._enumerate_dates(scenario["dates"])
                self.assertEqual(out, scenario["expected"])

    def test_summary_table(self):
        """COST-908: Test that the expected summary table is used."""
        mock_access = {"aws.organizational_unit": {"read": ["1234", "5678"]}}
        params = self.mocked_query_params("?", AWSCostForecastView, access=mock_access)
        instance = AWSForecast(params)
        self.assertEqual(instance.cost_summary_table, AWSCostSummaryByAccountP)

    @patch("forecast.forecast.Forecast.format_result", return_value="FAKE RESULTS")
    @patch("forecast.forecast.Forecast._run_forecast")
    @patch("forecast.forecast.Forecast._enumerate_dates", return_value=[0, 1, 2, 3, 4])
    def test_negative_values(self, mock_enumerate_dates, mock_run_forecast, mock_format_result):
        """COST-1110: ensure that the forecast response does not include negative numbers."""
        mock_run_forecast.return_value = Mock(
            prediction=[1, 0, -1, -2, -3], confidence_lower=[2, 1, 0, -1, -2], confidence_upper=[3, 2, 1, 0, -1]
        )
        params = self.mocked_query_params("?", AWSCostForecastView)
        instance = AWSForecast(params)
        instance.predict()

        self.assertIsInstance(mock_format_result.call_args[0][0], dict)
        for key, val_dict in mock_format_result.call_args[0][0].items():
            for inner_key, inner_val in val_dict.items():
                if "cost" in inner_key:
                    self.assertGreaterEqual(inner_val[0]["total_cost"], 0)
                    self.assertGreaterEqual(inner_val[0]["confidence_min"], 0)
                    self.assertGreaterEqual(inner_val[0]["confidence_max"], 0)

    def test__key_results_by_date(self):
        table = [
            {
                "name": "complete data",
                "data": {
                    "total_cost": (
                        {datetime(2022, 4, 28).date(): {"total_cost": 2, "confidence_min": 4, "confidence_max": 6}},
                        0.99,
                        ["0.00000000", "0.00000000"],
                    ),
                    "infrastructure_cost": (
                        {datetime(2022, 4, 28).date(): {"total_cost": 2, "confidence_min": 4, "confidence_max": 6}},
                        0.99,
                        ["0.00000000", "0.00000000"],
                    ),
                    "supplementary_cost": (
                        {datetime(2022, 4, 28).date(): {"total_cost": 2, "confidence_min": 4, "confidence_max": 6}},
                        0.99,
                        ["0.00000000", "0.00000000"],
                    ),
                },
                "expected": {
                    datetime(2022, 4, 28).date(): {
                        "total_cost": (
                            {"total_cost": 2, "confidence_min": 4, "confidence_max": 6},
                            {"rsquared": 0.99},
                            {"pvalues": ["0.00000000", "0.00000000"]},
                        ),
                        "infrastructure_cost": (
                            {"total_cost": 2, "confidence_min": 4, "confidence_max": 6},
                            {"rsquared": 0.99},
                            {"pvalues": ["0.00000000", "0.00000000"]},
                        ),
                        "supplementary_cost": (
                            {"total_cost": 2, "confidence_min": 4, "confidence_max": 6},
                            {"rsquared": 0.99},
                            {"pvalues": ["0.00000000", "0.00000000"]},
                        ),
                    },
                },
            },
            {
                "name": "incomplete data",
                "data": {
                    "total_cost": ({}, 0, ["0.00000000", "0.00000000"]),
                    "infrastructure_cost": (
                        {datetime(2022, 4, 28).date(): {"total_cost": 2, "confidence_min": 4, "confidence_max": 6}},
                        0.99,
                        ["0.00000000", "0.00000000"],
                    ),
                    "supplementary_cost": (
                        {datetime(2022, 4, 28).date(): {"total_cost": 2, "confidence_min": 4, "confidence_max": 6}},
                        0.99,
                        ["0.00000000", "0.00000000"],
                    ),
                },
                "expected": {
                    datetime(2022, 4, 28).date(): {
                        "total_cost": (
                            {"total_cost": 0, "confidence_min": 0, "confidence_max": 0},
                            {"rsquared": 0},
                            {"pvalues": ["0.00000000", "0.00000000"]},
                        ),
                        "infrastructure_cost": (
                            {"total_cost": 2, "confidence_min": 4, "confidence_max": 6},
                            {"rsquared": 0.99},
                            {"pvalues": ["0.00000000", "0.00000000"]},
                        ),
                        "supplementary_cost": (
                            {"total_cost": 2, "confidence_min": 4, "confidence_max": 6},
                            {"rsquared": 0.99},
                            {"pvalues": ["0.00000000", "0.00000000"]},
                        ),
                    },
                },
            },
            {
                "name": " more incomplete data",
                "data": {
                    "total_cost": ({}, 0, ["0.00000000", "0.00000000"]),
                    "infrastructure_cost": ({}, 0, ["0.00000000", "0.00000000"]),
                    "supplementary_cost": (
                        {datetime(2022, 4, 28).date(): {"total_cost": 2, "confidence_min": 4, "confidence_max": 6}},
                        0.99,
                        ["0.00000000", "0.00000000"],
                    ),
                },
                "expected": {
                    datetime(2022, 4, 28).date(): {
                        "total_cost": (
                            {"total_cost": 0, "confidence_min": 0, "confidence_max": 0},
                            {"rsquared": 0},
                            {"pvalues": ["0.00000000", "0.00000000"]},
                        ),
                        "infrastructure_cost": (
                            {"total_cost": 0, "confidence_min": 0, "confidence_max": 0},
                            {"rsquared": 0},
                            {"pvalues": ["0.00000000", "0.00000000"]},
                        ),
                        "supplementary_cost": (
                            {"total_cost": 2, "confidence_min": 4, "confidence_max": 6},
                            {"rsquared": 0.99},
                            {"pvalues": ["0.00000000", "0.00000000"]},
                        ),
                    },
                },
            },
            {
                "name": "another incomplete data",
                "data": {
                    "total_cost": (
                        {datetime(2022, 4, 28).date(): {"total_cost": 2, "confidence_min": 4, "confidence_max": 6}},
                        0.99,
                        ["0.00000000", "0.00000000"],
                    ),
                    "infrastructure_cost": ({}, 0, ["0.00000000", "0.00000000"]),
                    "supplementary_cost": ({}, 0, ["0.00000000", "0.00000000"]),
                },
                "expected": {
                    datetime(2022, 4, 28).date(): {
                        "total_cost": (
                            {"total_cost": 2, "confidence_min": 4, "confidence_max": 6},
                            {"rsquared": 0.99},
                            {"pvalues": ["0.00000000", "0.00000000"]},
                        ),
                        "infrastructure_cost": (
                            {"total_cost": 0, "confidence_min": 0, "confidence_max": 0},
                            {"rsquared": 0},
                            {"pvalues": ["0.00000000", "0.00000000"]},
                        ),
                        "supplementary_cost": (
                            {"total_cost": 0, "confidence_min": 0, "confidence_max": 0},
                            {"rsquared": 0},
                            {"pvalues": ["0.00000000", "0.00000000"]},
                        ),
                    },
                },
            },
        ]
        params = self.mocked_query_params("?", AWSCostForecastView)
        instance = AWSForecast(params)
        for test in table:
            with self.subTest(test=test["name"]):
                result = instance._key_results_by_date(test["data"])
                self.assertDictEqual(result, test["expected"])


class AzureForecastTest(IamTestCase):
    """Tests the AzureForecast class."""

    def test_predict_flat(self):
        """Test that predict() returns expected values for flat costs."""
        dh = DateHelper()

        expected = []
        for n in range(0, 10):
            expected.append(
                {
                    "usage_start": (dh.this_month_start + timedelta(days=n)).date(),
                    "total_cost": 5 + (0.01 * n),
                    "infrastructure_cost": 3 + (0.01 * n),
                    "supplementary_cost": 2 + (0.01 * n),
                }
            )
        mock_qset = MockQuerySet(expected)
        params = self.mocked_query_params("?", AzureCostForecastView)
        instance = AzureForecast(params)

        with patch("forecast.forecast.AzureForecast.get_data", return_value=mock_qset):
            results = instance.predict()

        for result in results:
            for val in result.get("values", []):
                with self.subTest(values=val):
                    self.assertIsInstance(val.get("date"), date)

                    for item, cost, delta in [
                        (val.get("cost"), 5, 1),
                        (val.get("infrastructure"), 3, 1),
                        (val.get("supplementary"), 2, 1),
                    ]:
                        with self.subTest(cost=cost, delta=delta, item=item):
                            self.assertAlmostEqual(float(item.get("total").get("value")), cost, delta=delta)
                            self.assertAlmostEqual(float(item.get("confidence_max").get("value")), cost, delta=delta)
                            self.assertAlmostEqual(float(item.get("confidence_min").get("value")), cost, delta=delta)
                            self.assertGreater(float(item.get("rsquared").get("value")), 0)
                            for pval in item.get("pvalues").get("value"):
                                self.assertGreaterEqual(float(pval), 0)


class GCPForecastTest(IamTestCase):
    """Tests the GCPForecast class."""

    def test_predict_flat(self):
        """Test that predict() returns expected values for flat costs."""
        dh = DateHelper()

        expected = []
        for n in range(0, 10):
            expected.append(
                {
                    "usage_start": (dh.this_month_start + timedelta(days=n)).date(),
                    "total_cost": 5 + (0.01 * n),
                    "infrastructure_cost": 3 + (0.01 * n),
                    "supplementary_cost": 2 + (0.01 * n),
                }
            )
        mock_qset = MockQuerySet(expected)
        params = self.mocked_query_params("?", GCPCostForecastView)
        instance = GCPForecast(params)

        with patch("forecast.forecast.GCPForecast.get_data", return_value=mock_qset):
            results = instance.predict()

        for result in results:
            for val in result.get("values", []):
                with self.subTest(values=val):
                    self.assertIsInstance(val.get("date"), date)

                    for item, cost, delta in [
                        (val.get("cost"), 5, 1),
                        (val.get("infrastructure"), 3, 1),
                        (val.get("supplementary"), 2, 1),
                    ]:
                        with self.subTest(cost=cost, delta=delta, item=item):
                            self.assertAlmostEqual(float(item.get("total").get("value")), cost, delta=delta)
                            self.assertAlmostEqual(float(item.get("confidence_max").get("value")), cost, delta=delta)
                            self.assertAlmostEqual(float(item.get("confidence_min").get("value")), cost, delta=delta)
                            self.assertGreater(float(item.get("rsquared").get("value")), 0)
                            for pval in item.get("pvalues").get("value"):
                                self.assertGreaterEqual(float(pval), 0)

    def test_cost_summary_table(self):
        """Test that we select a valid table or view."""
        params = self.mocked_query_params("?", GCPCostForecastView)
        forecast = GCPForecast(params)
        self.assertEqual(forecast.cost_summary_table, GCPCostSummaryP)

        params = self.mocked_query_params("?", GCPCostForecastView, access={"gcp.account": {"read": ["1"]}})
        forecast = GCPForecast(params)
        self.assertEqual(forecast.cost_summary_table, GCPCostSummaryByAccountP)

        params = self.mocked_query_params("?", GCPCostForecastView, access={"gcp.project": {"read": ["1"]}})
        forecast = GCPForecast(params)
        self.assertEqual(forecast.cost_summary_table, GCPCostSummaryByProjectP)

        params = self.mocked_query_params(
            "?", GCPCostForecastView, access={"gcp.account": {"read": ["1"]}, "gcp.project": {"read": ["1"]}}
        )
        forecast = GCPForecast(params)
        self.assertEqual(forecast.cost_summary_table, GCPCostSummaryByProjectP)

        params = self.mocked_query_params(
            "?", GCPCostForecastView, access={"gcp.account": {"read": ["1"]}, "gcp.project": {"read": ["1"]}}
        )

        forecast = GCPForecast(params)
        self.assertEqual(forecast.cost_summary_table, GCPCostSummaryByProjectP)


class OCPForecastTest(IamTestCase):
    """Tests the OCPForecast class."""

    def test_predict_flat(self):
        """Test that predict() returns expected values for flat costs."""
        dh = DateHelper()

        expected = []
        for n in range(0, 10):
            expected.append(
                {
                    "source_uuid": str(uuid4()),
                    "usage_start": (dh.this_month_start + timedelta(days=n)).date(),
                    "total_cost": 5 + (0.01 * n),
                    "infrastructure_cost": 3 + (0.01 * n),
                    "supplementary_cost": 2 + (0.01 * n),
                }
            )
        mock_qset = MockQuerySet(expected)
        params = self.mocked_query_params("?", OCPCostForecastView)
        instance = OCPForecast(params)

        with patch("forecast.forecast.OCPForecast.get_data", return_value=mock_qset):
            results = instance.predict()

        for result in results:
            for val in result.get("values", []):
                with self.subTest(values=val):
                    self.assertIsInstance(val.get("date"), date)

                    for item, cost, delta in [
                        (val.get("cost"), 5, 1),
                        (val.get("infrastructure"), 3, 1),
                        (val.get("supplementary"), 2, 1),
                    ]:
                        with self.subTest(cost=cost, delta=delta, item=item):
                            self.assertAlmostEqual(float(item.get("total").get("value")), cost, delta=delta)
                            self.assertAlmostEqual(float(item.get("confidence_max").get("value")), cost, delta=delta)
                            self.assertAlmostEqual(float(item.get("confidence_min").get("value")), cost, delta=delta)
                            self.assertGreater(float(item.get("rsquared").get("value")), 0)
                            for pval in item.get("pvalues").get("value"):
                                self.assertGreaterEqual(float(pval), 0)

    def test_cost_summary_table(self):
        """Test that we select a valid table or view."""
        params = self.mocked_query_params("?", OCPCostForecastView)
        forecast = OCPForecast(params)
        self.assertEqual(forecast.cost_summary_table, OCPCostSummaryP)

        params = self.mocked_query_params("?", OCPCostForecastView, access={"openshift.cluster": {"read": ["1"]}})
        forecast = OCPForecast(params)
        self.assertEqual(forecast.cost_summary_table, OCPCostSummaryP)

        params = self.mocked_query_params("?", OCPCostForecastView, access={"openshift.node": {"read": ["1"]}})
        forecast = OCPForecast(params)
        self.assertEqual(forecast.cost_summary_table, OCPCostSummaryByNodeP)

        params = self.mocked_query_params(
            "?", OCPCostForecastView, access={"openshift.cluster": {"read": ["1"]}, "openshift.node": {"read": ["1"]}}
        )
        forecast = OCPForecast(params)
        self.assertEqual(forecast.cost_summary_table, OCPCostSummaryByNodeP)

        params = self.mocked_query_params("?", OCPCostForecastView, access={"openshift.project": {"read": ["1"]}})
        forecast = OCPForecast(params)
        self.assertEqual(forecast.cost_summary_table, OCPUsageLineItemDailySummary)

        params = self.mocked_query_params(
            "?",
            OCPCostForecastView,
            access={"openshift.cluster": {"read": ["1"]}, "openshift.project": {"read": ["1"]}},
        )
        forecast = OCPForecast(params)
        self.assertEqual(forecast.cost_summary_table, OCPUsageLineItemDailySummary)


class OCPAllForecastTest(IamTestCase):
    """Tests the OCPAllForecast class."""

    def test_predict_flat(self):
        """Test that predict() returns expected values for flat costs."""
        dh = DateHelper()

        expected = []
        for n in range(0, 10):
            expected.append(
                {
                    "usage_start": (dh.this_month_start + timedelta(days=n)).date(),
                    "total_cost": 5 + (0.01 * n),
                    "infrastructure_cost": 3 + (0.01 * n),
                    "supplementary_cost": 2 + (0.01 * n),
                }
            )
        mock_qset = MockQuerySet(expected)
        params = self.mocked_query_params("?", OCPAllCostForecastView)
        instance = OCPAllForecast(params)

        with patch("forecast.forecast.OCPAllForecast.get_data", return_value=mock_qset):
            results = instance.predict()

        for result in results:
            for val in result.get("values", []):
                with self.subTest(values=val):
                    self.assertIsInstance(val.get("date"), date)

                    for item, cost, delta in [
                        (val.get("cost"), 5, 1),
                        (val.get("infrastructure"), 3, 1),
                        (val.get("supplementary"), 2, 1),
                    ]:
                        with self.subTest(cost=cost, delta=delta, item=item):
                            self.assertAlmostEqual(float(item.get("total").get("value")), cost, delta=delta)
                            self.assertAlmostEqual(float(item.get("confidence_max").get("value")), cost, delta=delta)
                            self.assertAlmostEqual(float(item.get("confidence_min").get("value")), cost, delta=delta)
                            self.assertGreater(float(item.get("rsquared").get("value")), 0)
                            for pval in item.get("pvalues").get("value"):
                                self.assertGreaterEqual(float(pval), 0)


class OCPAWSForecastTest(IamTestCase):
    """Tests the OCPAWSForecast class."""

    def test_predict_flat(self):
        """Test that predict() returns expected values for flat costs."""
        dh = DateHelper()

        expected = []
        for n in range(0, 10):
            expected.append(
                {
                    "usage_start": (dh.this_month_start + timedelta(days=n)).date(),
                    "total_cost": 5 + (0.01 * n),
                    "infrastructure_cost": 3 + (0.01 * n),
                    "supplementary_cost": 2 + (0.01 * n),
                }
            )
        mock_qset = MockQuerySet(expected)
        params = self.mocked_query_params("?", OCPAWSCostForecastView)
        instance = OCPAWSForecast(params)

        with patch("forecast.forecast.OCPAWSForecast.get_data", return_value=mock_qset):
            results = instance.predict()

        for result in results:
            for val in result.get("values", []):
                with self.subTest(values=val):
                    self.assertIsInstance(val.get("date"), date)

                    for item, cost, delta in [
                        (val.get("cost"), 5, 1),
                        (val.get("infrastructure"), 3, 1),
                        (val.get("supplementary"), 2, 1),
                    ]:
                        with self.subTest(cost=cost, delta=delta, item=item):
                            self.assertAlmostEqual(float(item.get("total").get("value")), cost, delta=delta)
                            self.assertAlmostEqual(float(item.get("confidence_max").get("value")), cost, delta=delta)
                            self.assertAlmostEqual(float(item.get("confidence_min").get("value")), cost, delta=delta)
                            self.assertGreater(float(item.get("rsquared").get("value")), 0)
                            for pval in item.get("pvalues").get("value"):
                                self.assertGreaterEqual(float(pval), 0)


class OCPAzureForecastTest(IamTestCase):
    """Tests the OCPAzureForecast class."""

    def test_predict_flat(self):
        """Test that predict() returns expected values for flat costs."""
        dh = DateHelper()

        expected = []
        for n in range(0, 10):
            expected.append(
                {
                    "usage_start": (dh.this_month_start + timedelta(days=n)).date(),
                    "total_cost": 5 + (0.01 * n),
                    "infrastructure_cost": 3 + (0.01 * n),
                    "supplementary_cost": 2 + (0.01 * n),
                }
            )
        mock_qset = MockQuerySet(expected)
        params = self.mocked_query_params("?", OCPAzureCostForecastView)
        instance = OCPAzureForecast(params)

        with patch("forecast.forecast.OCPAzureForecast.get_data", return_value=mock_qset):
            results = instance.predict()

        for result in results:
            for val in result.get("values", []):
                with self.subTest(values=val):
                    self.assertIsInstance(val.get("date"), date)

                    for item, cost, delta in [
                        (val.get("cost"), 5, 1),
                        (val.get("infrastructure"), 3, 1),
                        (val.get("supplementary"), 2, 1),
                    ]:
                        with self.subTest(cost=cost, delta=delta, item=item):
                            self.assertAlmostEqual(float(item.get("total").get("value")), cost, delta=delta)
                            self.assertAlmostEqual(float(item.get("confidence_max").get("value")), cost, delta=delta)
                            self.assertAlmostEqual(float(item.get("confidence_min").get("value")), cost, delta=delta)
                            self.assertGreater(float(item.get("rsquared").get("value")), 0)
                            for pval in item.get("pvalues").get("value"):
                                self.assertGreaterEqual(float(pval), 0)


class LinearForecastResultTest(IamTestCase):
    """Tests the LinearForecastResult class."""

    @patch("forecast.forecast.wls_prediction_std", return_value=(1, 2, 3))
    def test_constructor_logging(self, _):
        """Test that the constructor logs messages."""
        fake_results = Mock(summary=Mock(side_effect=ValueWarning("test")))

        with self.assertLogs(logger="forecast.forecast", level=logging.WARNING):
            LinearForecastResult(fake_results)

    @patch("forecast.forecast.wls_prediction_std", return_value=(1, 2, 3))
    def test_pvalues_slope_intercept(self, _):
        """Test the slope, intercept, and pvalues properties."""
        fake_results = Mock(
            summary=Mock(return_value="this is a test summary"),
            pvalues=Mock(tolist=Mock(return_value=[99999, 88888])),
            params=[66666, 77777],
        )

        lfr = LinearForecastResult(fake_results)

        self.assertEqual(lfr.pvalues, ["99999.00000000", "88888.00000000"])
        self.assertEqual(lfr.slope, 77777)
        self.assertEqual(lfr.intercept, 66666)
