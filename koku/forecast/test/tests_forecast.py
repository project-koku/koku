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
from datetime import date
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
        # super().__init()

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
            fake_yesterday = dh.this_month_start
            fake_today = dh.this_month_start + timedelta(days=1)
            mock_dh.today = fake_today
            mock_dh.this_month_start = dh.this_month_start
            mock_dh.this_month_end = dh.this_month_end
            mock_dh.last_month_start = dh.last_month_start
            mock_dh.last_month_end = dh.last_month_end
            forecast = AWSForecast(params)
            self.assertEqual(forecast.forecast_days_required, dh.this_month_end.day - fake_yesterday.day)

    def test_query_range(self):
        """Test that we select the correct range based on day of month."""
        dh = DateHelper()
        params = self.mocked_query_params("?", AWSCostForecastView)

        with patch("forecast.forecast.Forecast.dh") as mock_dh:
            mock_dh.today = dh.this_month_start + timedelta(days=AWSForecast.MINIMUM - 1)
            mock_dh.this_month_start = dh.this_month_start
            mock_dh.this_month_end = dh.this_month_end
            mock_dh.last_month_start = dh.last_month_start
            mock_dh.last_month_end = dh.last_month_end
            expected = (dh.last_month_start, dh.last_month_end)
            forecast = AWSForecast(params)
            self.assertEqual(forecast.query_range, expected)

        with patch("forecast.forecast.Forecast.dh") as mock_dh:
            mock_dh.today = dh.this_month_start + timedelta(days=(AWSForecast.MINIMUM))
            mock_dh.this_month_start = dh.this_month_start
            mock_dh.this_month_end = dh.this_month_end
            mock_dh.last_month_start = dh.last_month_start
            mock_dh.last_month_end = dh.last_month_end
            expected = (dh.this_month_start, dh.this_month_start + timedelta(days=AWSForecast.MINIMUM - 1))
            forecast = AWSForecast(params)
            self.assertEqual(forecast.query_range, expected)

    def test_add_additional_data_points(self):
        """Test that we fill in data to the end of the month."""
        dh = DateHelper()
        params = self.mocked_query_params("?", AWSCostForecastView)
        last_day_of_data = dh.last_month_start + timedelta(days=10)
        with patch("forecast.forecast.Forecast.dh") as mock_dh:
            mock_dh.today = dh.this_month_start
            mock_dh.this_month_end = dh.this_month_end
            mock_dh.last_month_start = dh.last_month_start
            mock_dh.last_month_end = last_day_of_data
            forecast = AWSForecast(params)
            results = forecast.predict()

            self.assertEqual(len(results), dh.this_month_end.day)
            for i, result in enumerate(results):
                self.assertEqual(result.get("date"), dh.this_month_start.date() + timedelta(days=i))
                for val in result.get("values", []):
                    cost = val.get("cost", {}).get("total", {}).get("value")
                    self.assertNotEqual(cost, 0)

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

        for result in results:
            for val in result.get("values", []):
                self.assertIsInstance(val.get("date"), date)

                item = val.get("cost")
                self.assertAlmostEqual(float(item.get("total").get("value")), 5, delta=0.0001)
                self.assertAlmostEqual(float(item.get("confidence_max").get("value")), 5, delta=0.0001)
                self.assertAlmostEqual(float(item.get("confidence_min").get("value")), 5, delta=0.0001)
                self.assertAlmostEqual(float(item.get("rsquared").get("value")), 1, delta=0.0001)
                self.assertGreaterEqual(float(item.get("pvalues").get("value")), 0)

    def test_predict_increasing(self):
        """Test that predict() returns expected values for increasing costs."""
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

        for result in results:
            for val in result.get("values", []):
                self.assertIsInstance(val.get("date"), date)

                item = val.get("cost")
                self.assertGreaterEqual(float(item.get("total").get("value")), 0)
                self.assertGreaterEqual(float(item.get("confidence_max").get("value")), 0)
                self.assertGreaterEqual(float(item.get("confidence_min").get("value")), 0)
                self.assertGreaterEqual(float(item.get("rsquared").get("value")), 0)
                self.assertGreaterEqual(float(item.get("pvalues").get("value")), 0)

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
                if number == 1:
                    # forecasting isn't possible with only 1 data point.
                    with self.assertLogs(logger="forecast.forecast", level=logging.WARNING):
                        results = instance.predict()
                        self.assertEqual(results, [])
                else:
                    with self.assertLogs(logger="forecast.forecast", level=logging.WARNING):
                        results = instance.predict()
                        for result in results:
                            for val in result.get("values", []):
                                self.assertIsInstance(val.get("date"), date)

                                item = val.get("cost")
                                self.assertGreaterEqual(float(item.get("total").get("value")), 0)
                                self.assertGreaterEqual(float(item.get("confidence_max").get("value")), 0)
                                self.assertGreaterEqual(float(item.get("confidence_min").get("value")), 0)
                                self.assertGreaterEqual(float(item.get("rsquared").get("value")), 0)
                                self.assertGreaterEqual(float(item.get("pvalues").get("value")), 0)
                        # test that the results always stop at the end of the month.
                        self.assertEqual(results[-1].get("date"), dh.this_month_end.date())

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


class AzureForecastTest(IamTestCase):
    """Tests the AzureForecast class."""

    def test_predict_flat(self):
        """Test that predict() returns expected values for flat costs."""
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

        params = self.mocked_query_params("?", AzureCostForecastView)
        instance = AzureForecast(params)

        instance.cost_summary_table = mocked_table

        results = instance.predict()

        for result in results:
            for val in result.get("values", []):
                self.assertIsInstance(val.get("date"), date)

                item = val.get("cost")
                self.assertAlmostEqual(float(item.get("total").get("value")), 5, delta=0.0001)
                self.assertAlmostEqual(float(item.get("confidence_max").get("value")), 5, delta=0.0001)
                self.assertAlmostEqual(float(item.get("confidence_min").get("value")), 5, delta=0.0001)
                self.assertAlmostEqual(float(item.get("rsquared").get("value")), 1, delta=0.0001)
                self.assertGreaterEqual(float(item.get("pvalues").get("value")), 0)


class OCPForecastTest(IamTestCase):
    """Tests the OCPForecast class."""

    def test_predict_flat(self):
        """Test that predict() returns expected values for flat costs."""
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

        params = self.mocked_query_params("?", OCPCostForecastView)
        instance = OCPForecast(params)

        instance.cost_summary_table = mocked_table

        results = instance.predict()

        for result in results:
            for val in result.get("values", []):
                self.assertIsInstance(val.get("date"), date)

                item = val.get("cost")
                self.assertAlmostEqual(float(item.get("total").get("value")), 5, delta=0.0001)
                self.assertAlmostEqual(float(item.get("confidence_max").get("value")), 5, delta=0.0001)
                self.assertAlmostEqual(float(item.get("confidence_min").get("value")), 5, delta=0.0001)
                self.assertAlmostEqual(float(item.get("rsquared").get("value")), 1, delta=0.0001)
                self.assertGreaterEqual(float(item.get("pvalues").get("value")), 0)

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

        params = self.mocked_query_params("?", OCPAllCostForecastView)
        instance = OCPAllForecast(params)

        instance.cost_summary_table = mocked_table

        results = instance.predict()

        for result in results:
            for val in result.get("values", []):
                self.assertIsInstance(val.get("date"), date)

                item = val.get("cost")
                self.assertAlmostEqual(float(item.get("total").get("value")), 5, delta=0.0001)
                self.assertAlmostEqual(float(item.get("confidence_max").get("value")), 5, delta=0.0001)
                self.assertAlmostEqual(float(item.get("confidence_min").get("value")), 5, delta=0.0001)
                self.assertAlmostEqual(float(item.get("rsquared").get("value")), 1, delta=0.0001)
                self.assertGreaterEqual(float(item.get("pvalues").get("value")), 0)


class OCPAWSForecastTest(IamTestCase):
    """Tests the OCPAWSForecast class."""

    def test_predict_flat(self):
        """Test that predict() returns expected values for flat costs."""
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

        params = self.mocked_query_params("?", OCPAWSCostForecastView)
        instance = OCPAWSForecast(params)

        instance.cost_summary_table = mocked_table

        results = instance.predict()

        for result in results:
            for val in result.get("values", []):
                self.assertIsInstance(val.get("date"), date)

                item = val.get("cost")
                self.assertAlmostEqual(float(item.get("total").get("value")), 5, delta=0.0001)
                self.assertAlmostEqual(float(item.get("confidence_max").get("value")), 5, delta=0.0001)
                self.assertAlmostEqual(float(item.get("confidence_min").get("value")), 5, delta=0.0001)
                self.assertAlmostEqual(float(item.get("rsquared").get("value")), 1, delta=0.0001)
                self.assertGreaterEqual(float(item.get("pvalues").get("value")), 0)


class OCPAzureForecastTest(IamTestCase):
    """Tests the OCPAzureForecast class."""

    def test_predict_flat(self):
        """Test that predict() returns expected values for flat costs."""
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

        params = self.mocked_query_params("?", OCPAzureCostForecastView)
        instance = OCPAzureForecast(params)

        instance.cost_summary_table = mocked_table

        results = instance.predict()

        for result in results:
            for val in result.get("values", []):
                self.assertIsInstance(val.get("date"), date)

                item = val.get("cost")
                self.assertAlmostEqual(float(item.get("total").get("value")), 5, delta=0.0001)
                self.assertAlmostEqual(float(item.get("confidence_max").get("value")), 5, delta=0.0001)
                self.assertAlmostEqual(float(item.get("confidence_min").get("value")), 5, delta=0.0001)
                self.assertAlmostEqual(float(item.get("rsquared").get("value")), 1, delta=0.0001)
                self.assertGreaterEqual(float(item.get("pvalues").get("value")), 0)


class LinearForecastResultTest(IamTestCase):
    """Tests the LinearForecastResult class."""

    @patch("forecast.forecast.wls_prediction_std", return_value=(1, 2, 3))
    def test_constructor_logging(self, _):
        """Test that the constructor logs messages."""
        fake_results = Mock(summary=Mock(side_effect=ValueWarning("test")))

        with self.assertLogs(logger="forecast.forecast", level=logging.WARNING):
            LinearForecastResult(fake_results)

    @patch("forecast.forecast.wls_prediction_std", return_value=(1, 2, 3))
    def test_pvalues_slope_single(self, _):
        """Test the slope and pvalues properties."""
        fake_results = Mock(
            summary=Mock(return_value="test"),
            pvalues=Mock(tolist=Mock(return_value=["test_pvalues"])),
            params=["test_slope"],
        )

        lfr = LinearForecastResult(fake_results)

        self.assertEqual(lfr.pvalues, "test_pvalues")
        self.assertEqual(lfr.slope, "test_slope")

    @patch("forecast.forecast.wls_prediction_std", return_value=(1, 2, 3))
    def test_pvalues_slope_list(self, _):
        """Test the slope and pvalues properties."""
        fake_results = Mock(
            summary=Mock(return_value="test"), pvalues=Mock(tolist=Mock(return_value=[0, 1, 2])), params=[3, 4, 5]
        )

        lfr = LinearForecastResult(fake_results)

        self.assertEqual(lfr.pvalues, [0, 1, 2])
        self.assertEqual(lfr.slope, [3, 4, 5])
