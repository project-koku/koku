#
# Copyright 2020 Red Hat, Inc.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
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

from statsmodels.tools.sm_exceptions import ValueWarning

from api.forecast.views import AWSCostForecastView
from api.forecast.views import AzureCostForecastView
from api.forecast.views import OCPAllCostForecastView
from api.forecast.views import OCPAWSCostForecastView
from api.forecast.views import OCPAzureCostForecastView
from api.forecast.views import OCPCostForecastView
from api.iam.test.iam_test_case import IamTestCase
from api.query_filter import QueryFilter
from api.query_filter import QueryFilterCollection
from api.report.test.tests_queries import assertSameQ
from api.utils import DateHelper
from forecast import AWSForecast
from forecast import AzureForecast
from forecast import OCPAllForecast
from forecast import OCPAWSForecast
from forecast import OCPAzureForecast
from forecast import OCPForecast
from forecast.forecast import LinearForecastResult
from reporting.provider.ocp.models import OCPCostSummary
from reporting.provider.ocp.models import OCPCostSummaryByNode
from reporting.provider.ocp.models import OCPUsageLineItemDailySummary

LOG = logging.getLogger(__name__)


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
        dh = DateHelper()
        params = self.mocked_query_params("?", AWSCostForecastView)
        with patch("forecast.forecast.Forecast.dh") as mock_dh:
            mock_dh.today = dh.this_month_start
            mock_dh.this_month_start = dh.this_month_start
            mock_dh.this_month_end = dh.this_month_end
            mock_dh.last_month_start = dh.last_month_start
            mock_dh.last_month_end = dh.last_month_end
            forecast = AWSForecast(params)
            self.assertEqual(forecast.forecast_days_required, dh.this_month_end.day)

        with patch("forecast.forecast.Forecast.dh") as mock_dh:
            mock_dh.today = datetime(2000, 1, 13, 0, 0, 0, 0)
            mock_dh.yesterday = datetime(2000, 1, 12, 0, 0, 0, 0)
            mock_dh.this_month_start = datetime(2000, 1, 1, 0, 0, 0, 0)
            mock_dh.this_month_end = datetime(2000, 1, 31, 0, 0, 0, 0)
            mock_dh.last_month_start = datetime(1999, 12, 1, 0, 0, 0, 0)
            mock_dh.last_month_end = datetime(1999, 12, 31, 0, 0, 0, 0)
            forecast = AWSForecast(params)
            self.assertEqual(forecast.forecast_days_required, 19)

    def test_query_range(self):
        """Test that we select the correct range based on day of month."""
        dh = DateHelper()
        params = self.mocked_query_params("?", AWSCostForecastView)

        with patch("forecast.forecast.Forecast.dh") as mock_dh:
            mock_dh.today = dh.this_month_start + timedelta(days=AWSForecast.MINIMUM - 1)
            mock_dh.yesterday = dh.this_month_start + timedelta(days=AWSForecast.MINIMUM - 2)
            mock_dh.this_month_start = dh.this_month_start
            mock_dh.this_month_end = dh.this_month_end
            mock_dh.last_month_start = dh.last_month_start
            mock_dh.last_month_end = dh.last_month_end
            expected = (dh.last_month_start, mock_dh.yesterday)
            forecast = AWSForecast(params)
            self.assertEqual(forecast.query_range, expected)

        with patch("forecast.forecast.Forecast.dh") as mock_dh:
            mock_dh.today = dh.this_month_start + timedelta(days=(AWSForecast.MINIMUM))
            mock_dh.yesterday = dh.this_month_start + timedelta(days=AWSForecast.MINIMUM - 1)
            mock_dh.this_month_start = dh.this_month_start
            mock_dh.this_month_end = dh.this_month_end
            mock_dh.last_month_start = dh.last_month_start
            mock_dh.last_month_end = dh.last_month_end
            expected = (dh.this_month_start, dh.this_month_start + timedelta(days=AWSForecast.MINIMUM - 1))
            forecast = AWSForecast(params)
            self.assertEqual(forecast.query_range, expected)

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
            # the test data needs to include some jitter to avoid
            # division-by-zero in the underlying dot-product maths.
            expected.append(
                {
                    "usage_start": (dh.this_month_start + timedelta(days=n)).date(),
                    "total_cost": 5 + random.random(),
                    "infrastructure_cost": 3 + random.random(),
                    "supplementary_cost": 2 + random.random(),
                }
            )
        mock_qset = MockQuerySet(expected)

        mocked_table = Mock()
        mocked_table.objects.filter.return_value.order_by.return_value.values.return_value.annotate.return_value = (  # noqa: E501
            mock_qset
        )
        mocked_table.len = mock_qset.len

        params = self.mocked_query_params("?", AWSCostForecastView)
        instance = AWSForecast(params)

        instance.cost_summary_table = mocked_table

        results = instance.predict()

        for result in results:
            for val in result.get("values", []):
                self.assertIsInstance(val.get("date"), date)

                for item, cost in [
                    (val.get("cost"), 5),
                    (val.get("infrastructure"), 3),
                    (val.get("supplementary"), 2),
                ]:
                    self.assertAlmostEqual(float(item.get("total").get("value")), cost, delta=2.2)
                    self.assertAlmostEqual(float(item.get("confidence_max").get("value")), cost, delta=2.2)
                    self.assertAlmostEqual(float(item.get("confidence_min").get("value")), cost, delta=2.2)
                    self.assertAlmostEqual(float(item.get("rsquared").get("value")), 1, delta=2.2)
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
                    "total_cost": 5 + random.random(),
                    "infrastructure_cost": 3 + random.random(),
                    "supplementary_cost": 2 + random.random(),
                }
            )
        mock_qset = MockQuerySet(expected)

        mocked_table = Mock()
        mocked_table.objects.filter.return_value.order_by.return_value.values.return_value.annotate.return_value = (  # noqa: E501
            mock_qset
        )
        mocked_table.len = mock_qset.len

        params = self.mocked_query_params("?", AWSCostForecastView)
        instance = AWSForecast(params)

        instance.cost_summary_table = mocked_table

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

        mocked_table = Mock()
        mocked_table.objects.filter.return_value.order_by.return_value.values.return_value.annotate.return_value = (  # noqa: E501
            mock_qset
        )
        mocked_table.len = mock_qset.len

        params = self.mocked_query_params("?", AWSCostForecastView)
        instance = AWSForecast(params)

        instance.cost_summary_table = mocked_table

        results = instance.predict()

        for item in results:
            self.assertIsInstance(item.get("date"), date)
            self.assertLessEqual(item.get("date"), dh.this_month_end.date())

    def test_predict_few_values(self):
        """Test that predict() behaves well with a limited data set."""
        dh = DateHelper()

        num_elements = [1, 2, 3, 4, 5]

        for number in num_elements:
            with self.subTest(num_elements=number):
                expected = []
                for n in range(0, number):
                    # the test data needs to include some jitter to avoid
                    # division-by-zero in the underlying dot-product maths.
                    expected.append(
                        {
                            "usage_start": dh.n_days_ago(dh.today, 10 - n).date(),
                            # "usage_start": dh.today.replace(day=n).date(),
                            "total_cost": 5 + random.random(),
                            "infrastructure_cost": 3 + random.random(),
                            "supplementary_cost": 2 + random.random(),
                        }
                    )
                mock_qset = MockQuerySet(expected)

                mocked_table = Mock()
                mocked_table.objects.filter.return_value.order_by.return_value.values.return_value.annotate.return_value = (  # noqa: E501
                    mock_qset
                )
                mocked_table.len = mock_qset.len

                params = self.mocked_query_params("?", AWSCostForecastView)
                instance = AWSForecast(params)

                instance.cost_summary_table = mocked_table
                if number < 3:
                    # forecasting isn't possible with less than 3 data points.
                    with self.assertLogs(logger="forecast.forecast", level=logging.WARNING):
                        results = instance.predict()
                        self.assertEqual(results, [])
                else:
                    with self.assertLogs(logger="forecast.forecast", level=logging.WARNING):
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

    def test_results_never_outside_current_month(self):
        """Test that our results stop at the end of the current month."""
        dh = DateHelper()
        params = self.mocked_query_params("?", AWSCostForecastView)
        forecast = AWSForecast(params)
        forecast.forecast_days_required = 100
        results = forecast.predict()
        dates = [result.get("date") for result in results]
        self.assertNotIn(dh.next_month_start, dates)
        self.assertEqual(dh.this_month_end.date(), max(dates))

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


class AzureForecastTest(IamTestCase):
    """Tests the AzureForecast class."""

    def test_predict_flat(self):
        """Test that predict() returns expected values for flat costs."""
        dh = DateHelper()

        expected = []
        for n in range(0, 10):
            # the test data needs to include some jitter to avoid
            # division-by-zero in the underlying dot-product maths.
            expected.append(
                {
                    "usage_start": (dh.this_month_start + timedelta(days=n)).date(),
                    "total_cost": 5 + random.random(),
                    "infrastructure_cost": 3 + random.random(),
                    "supplementary_cost": 2 + random.random(),
                }
            )
        mock_qset = MockQuerySet(expected)

        mocked_table = Mock()
        mocked_table.objects.filter.return_value.order_by.return_value.values.return_value.annotate.return_value = (  # noqa: E501
            mock_qset
        )
        mocked_table.len = mock_qset.len

        params = self.mocked_query_params("?", AzureCostForecastView)
        instance = AzureForecast(params)

        instance.cost_summary_table = mocked_table

        results = instance.predict()

        for result in results:
            for val in result.get("values", []):
                self.assertIsInstance(val.get("date"), date)

                for item, cost in [
                    (val.get("cost"), 5),
                    (val.get("infrastructure"), 3),
                    (val.get("supplementary"), 2),
                ]:
                    self.assertAlmostEqual(float(item.get("total").get("value")), cost, delta=2.2)
                    self.assertAlmostEqual(float(item.get("confidence_max").get("value")), cost, delta=2.2)
                    self.assertAlmostEqual(float(item.get("confidence_min").get("value")), cost, delta=2.2)
                    self.assertAlmostEqual(float(item.get("rsquared").get("value")), 1, delta=2.2)
                    for pval in item.get("pvalues").get("value"):
                        self.assertGreaterEqual(float(pval), 0)


class OCPForecastTest(IamTestCase):
    """Tests the OCPForecast class."""

    def test_predict_flat(self):
        """Test that predict() returns expected values for flat costs."""
        dh = DateHelper()

        expected = []
        for n in range(0, 10):
            # the test data needs to include some jitter to avoid
            # division-by-zero in the underlying dot-product maths.
            expected.append(
                {
                    "usage_start": (dh.this_month_start + timedelta(days=n)).date(),
                    "total_cost": 5 + random.random(),
                    "infrastructure_cost": 3 + random.random(),
                    "supplementary_cost": 2 + random.random(),
                }
            )
        mock_qset = MockQuerySet(expected)

        mocked_table = Mock()
        mocked_table.objects.filter.return_value.order_by.return_value.values.return_value.annotate.return_value = (  # noqa: E501
            mock_qset
        )
        mocked_table.len = mock_qset.len

        params = self.mocked_query_params("?", OCPCostForecastView)
        instance = OCPForecast(params)

        instance.cost_summary_table = mocked_table

        results = instance.predict()

        for result in results:
            for val in result.get("values", []):
                self.assertIsInstance(val.get("date"), date)

                for item, cost in [
                    (val.get("cost"), 5),
                    (val.get("infrastructure"), 3),
                    (val.get("supplementary"), 2),
                ]:
                    self.assertAlmostEqual(float(item.get("total").get("value")), cost, delta=2.2)
                    self.assertAlmostEqual(float(item.get("confidence_max").get("value")), cost, delta=2.2)
                    self.assertAlmostEqual(float(item.get("confidence_min").get("value")), cost, delta=2.2)
                    self.assertAlmostEqual(float(item.get("rsquared").get("value")), 1, delta=2.2)
                    for pval in item.get("pvalues").get("value"):
                        self.assertGreaterEqual(float(pval), 0)

    def test_cost_summary_table(self):
        """Test that we select a valid table or view."""
        params = self.mocked_query_params("?", OCPCostForecastView)
        forecast = OCPForecast(params)
        self.assertEqual(forecast.cost_summary_table, OCPCostSummary)

        params = self.mocked_query_params("?", OCPCostForecastView, access={"openshift.cluster": {"read": ["1"]}})
        forecast = OCPForecast(params)
        self.assertEqual(forecast.cost_summary_table, OCPCostSummary)

        params = self.mocked_query_params("?", OCPCostForecastView, access={"openshift.node": {"read": ["1"]}})
        forecast = OCPForecast(params)
        self.assertEqual(forecast.cost_summary_table, OCPCostSummaryByNode)

        params = self.mocked_query_params(
            "?", OCPCostForecastView, access={"openshift.cluster": {"read": ["1"]}, "openshift.node": {"read": ["1"]}}
        )
        forecast = OCPForecast(params)
        self.assertEqual(forecast.cost_summary_table, OCPCostSummaryByNode)

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
            # the test data needs to include some jitter to avoid
            # division-by-zero in the underlying dot-product maths.
            expected.append(
                {
                    "usage_start": (dh.this_month_start + timedelta(days=n)).date(),
                    "total_cost": 5 + random.random(),
                    "infrastructure_cost": 3 + random.random(),
                    "supplementary_cost": 2 + random.random(),
                }
            )
        mock_qset = MockQuerySet(expected)

        mocked_table = Mock()
        mocked_table.objects.filter.return_value.order_by.return_value.values.return_value.annotate.return_value = (  # noqa: E501
            mock_qset
        )
        mocked_table.len = mock_qset.len

        params = self.mocked_query_params("?", OCPAllCostForecastView)
        instance = OCPAllForecast(params)

        instance.cost_summary_table = mocked_table

        results = instance.predict()

        for result in results:
            for val in result.get("values", []):
                self.assertIsInstance(val.get("date"), date)

                for item, cost in [
                    (val.get("cost"), 5),
                    (val.get("infrastructure"), 3),
                    (val.get("supplementary"), 2),
                ]:
                    self.assertAlmostEqual(float(item.get("total").get("value")), cost, delta=2.2)
                    self.assertAlmostEqual(float(item.get("confidence_max").get("value")), cost, delta=2.2)
                    self.assertAlmostEqual(float(item.get("confidence_min").get("value")), cost, delta=2.2)
                    self.assertAlmostEqual(float(item.get("rsquared").get("value")), 1, delta=2.2)
                    for pval in item.get("pvalues").get("value"):
                        self.assertGreaterEqual(float(pval), 0)


class OCPAWSForecastTest(IamTestCase):
    """Tests the OCPAWSForecast class."""

    def test_predict_flat(self):
        """Test that predict() returns expected values for flat costs."""
        dh = DateHelper()

        expected = []
        for n in range(0, 10):
            # the test data needs to include some jitter to avoid
            # division-by-zero in the underlying dot-product maths.
            expected.append(
                {
                    "usage_start": (dh.this_month_start + timedelta(days=n)).date(),
                    "total_cost": 5 + random.random(),
                    "infrastructure_cost": 3 + random.random(),
                    "supplementary_cost": 2 + random.random(),
                }
            )
        mock_qset = MockQuerySet(expected)

        mocked_table = Mock()
        mocked_table.objects.filter.return_value.order_by.return_value.values.return_value.annotate.return_value = (  # noqa: E501
            mock_qset
        )
        mocked_table.len = mock_qset.len

        params = self.mocked_query_params("?", OCPAWSCostForecastView)
        instance = OCPAWSForecast(params)

        instance.cost_summary_table = mocked_table

        results = instance.predict()

        for result in results:
            for val in result.get("values", []):
                self.assertIsInstance(val.get("date"), date)

                for item, cost in [
                    (val.get("cost"), 5),
                    (val.get("infrastructure"), 3),
                    (val.get("supplementary"), 2),
                ]:
                    self.assertAlmostEqual(float(item.get("total").get("value")), cost, delta=2.2)
                    self.assertAlmostEqual(float(item.get("confidence_max").get("value")), cost, delta=2.2)
                    self.assertAlmostEqual(float(item.get("confidence_min").get("value")), cost, delta=2.2)
                    self.assertAlmostEqual(float(item.get("rsquared").get("value")), 1, delta=2.2)
                    for pval in item.get("pvalues").get("value"):
                        self.assertGreaterEqual(float(pval), 0)


class OCPAzureForecastTest(IamTestCase):
    """Tests the OCPAzureForecast class."""

    def test_predict_flat(self):
        """Test that predict() returns expected values for flat costs."""
        dh = DateHelper()

        expected = []
        for n in range(0, 10):
            # the test data needs to include some jitter to avoid
            # division-by-zero in the underlying dot-product maths.
            expected.append(
                {
                    "usage_start": (dh.this_month_start + timedelta(days=n)).date(),
                    "total_cost": 5 + random.random(),
                    "infrastructure_cost": 3 + random.random(),
                    "supplementary_cost": 2 + random.random(),
                }
            )
        mock_qset = MockQuerySet(expected)

        mocked_table = Mock()
        mocked_table.objects.filter.return_value.order_by.return_value.values.return_value.annotate.return_value = (  # noqa: E501
            mock_qset
        )

        mocked_table.len = mock_qset.len

        params = self.mocked_query_params("?", OCPAzureCostForecastView)
        instance = OCPAzureForecast(params)

        instance.cost_summary_table = mocked_table

        results = instance.predict()

        for result in results:
            for val in result.get("values", []):
                self.assertIsInstance(val.get("date"), date)

                for item, cost in [
                    (val.get("cost"), 5),
                    (val.get("infrastructure"), 3),
                    (val.get("supplementary"), 2),
                ]:
                    self.assertAlmostEqual(float(item.get("total").get("value")), cost, delta=2.2)
                    self.assertAlmostEqual(float(item.get("confidence_max").get("value")), cost, delta=2.2)
                    self.assertAlmostEqual(float(item.get("confidence_min").get("value")), cost, delta=2.2)
                    self.assertAlmostEqual(float(item.get("rsquared").get("value")), 1, delta=2.2)
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
