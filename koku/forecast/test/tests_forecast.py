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
from datetime import datetime
from unittest.mock import Mock
from unittest.mock import patch

import pytz
from django.utils import timezone

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

LOG = logging.getLogger(__name__)


class MockDateHelper(DateHelper):
    """Testing class."""

    def __init__(self, mock_dt=None, utc=False):
        """Initialize when now is."""
        if mock_dt:
            self._now = mock_dt
        else:
            if utc:
                self._now = datetime.datetime.now(tz=pytz.UTC)
            else:
                self._now = timezone.now()

    @property
    def now(self):
        """Return current time at timezone."""
        return self._now


class AWSForecastTest(IamTestCase):
    """Tests the AWSForecast class."""

    def test_constructor(self):
        """Test the constructor."""
        params = self.mocked_query_params("?", AWSCostForecastView)
        instance = AWSForecast(params)
        self.assertIsInstance(instance, AWSForecast)

    def test_constructor_filter_intervals(self):
        """Test the constructor sets the query intervals as expected."""
        test_datetime = datetime(2000, 1, 15, 0, 0, 0, 0)
        mocked_dh = MockDateHelper(mock_dt=test_datetime)

        test_matrix = [
            ("?", (mocked_dh.n_days_ago(mocked_dh.yesterday, 10), mocked_dh.yesterday)),
            (
                "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly",
                (mocked_dh.this_month_start, mocked_dh.yesterday),
            ),
            (
                "?filter[time_scope_units]=month&filter[time_scope_value]=-2&filter[resolution]=monthly",
                (mocked_dh.last_month_start, mocked_dh.yesterday),
            ),
            (
                "?filter[time_scope_units]=day&filter[time_scope_value]=-10&filter[resolution]=daily",
                (mocked_dh.n_days_ago(mocked_dh.yesterday, 10), mocked_dh.yesterday),
            ),
            (
                "?filter[time_scope_units]=day&filter[time_scope_value]=-30&filter[resolution]=daily",
                (mocked_dh.n_days_ago(mocked_dh.yesterday, 30), mocked_dh.yesterday),
            ),
        ]

        with patch.object(AWSForecast, "dh", mocked_dh):
            for url, expected in test_matrix:
                with self.subTest(url=url):
                    params = self.mocked_query_params(url, AWSCostForecastView)
                    instance = AWSForecast(params)
                    self.assertEqual(instance.query_range, expected)

    def test_constructor_filter_intervals_early(self):
        """Test the constructor sets the query intervals as expected."""
        test_datetime = datetime(2000, 1, 3, 0, 0, 0, 0)
        mocked_dh = MockDateHelper(mock_dt=test_datetime)

        test_matrix = [
            ("?", (mocked_dh.n_days_ago(mocked_dh.yesterday, 10), mocked_dh.yesterday)),
            (
                "?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly",
                (mocked_dh.last_month_start, mocked_dh.yesterday),
            ),
            (
                "?filter[time_scope_units]=month&filter[time_scope_value]=-2&filter[resolution]=monthly",
                (mocked_dh.last_month_start, mocked_dh.yesterday),
            ),
            (
                "?filter[time_scope_units]=day&filter[time_scope_value]=-10&filter[resolution]=daily",
                (mocked_dh.n_days_ago(mocked_dh.yesterday, 10), mocked_dh.yesterday),
            ),
            (
                "?filter[time_scope_units]=day&filter[time_scope_value]=-30&filter[resolution]=daily",
                (mocked_dh.n_days_ago(mocked_dh.yesterday, 30), mocked_dh.yesterday),
            ),
        ]

        with patch.object(AWSForecast, "dh", mocked_dh):
            for url, expected in test_matrix:
                with self.subTest(url=url):
                    params = self.mocked_query_params(url, AWSCostForecastView)
                    instance = AWSForecast(params)
                    self.assertEqual(instance.query_range, expected)

    def test_predict_flat(self):
        """Test that predict() returns expected values for flat costs."""
        dh = DateHelper()

        expected = []
        for n in range(0, 10):
            expected.append({"usage_start": dh.n_days_ago(dh.yesterday, 10 - n).date(), "total_cost": 5})

        mocked_table = Mock()
        mocked_table.objects.filter.return_value.order_by.return_value.values.return_value.annotate.return_value = (  # noqa: E501
            expected
        )
        mocked_table.len = len(expected)

        params = self.mocked_query_params("?", AWSCostForecastView)
        instance = AWSForecast(params)

        instance.cost_summary_table = mocked_table

        results = instance.predict()

        for item in results:
            self.assertRegex(item.get("date"), r"\d{4}-\d{2}-\d{2}")
            self.assertAlmostEqual(float(item.get("value")), 5, delta=0.0001)
            self.assertAlmostEqual(float(item.get("confidence_max")), 5, delta=0.0001)
            self.assertAlmostEqual(float(item.get("confidence_min")), 5, delta=0.0001)
            self.assertAlmostEqual(float(item.get("rsquared")), 1, delta=0.0001)
            self.assertGreaterEqual(float(item.get("pvalues")), 0)

    def test_predict_increasing(self):
        """Test that predict() returns expected values for increasing costs."""
        dh = DateHelper()

        expected = []
        for n in range(0, 10):
            expected.append({"usage_start": dh.n_days_ago(dh.yesterday, 10 - n).date(), "total_cost": 5})

        mocked_table = Mock()
        mocked_table.objects.filter.return_value.order_by.return_value.values.return_value.annotate.return_value = (  # noqa: E501
            expected
        )
        mocked_table.len = len(expected)

        params = self.mocked_query_params("?", AWSCostForecastView)
        instance = AWSForecast(params)

        instance.cost_summary_table = mocked_table

        results = instance.predict()

        for item in results:
            self.assertRegex(item.get("date"), r"\d{4}-\d{2}-\d{2}")
            self.assertGreaterEqual(float(item.get("value")), 0)
            self.assertGreaterEqual(float(item.get("confidence_max")), 0)
            self.assertGreaterEqual(float(item.get("confidence_min")), 0)
            self.assertGreaterEqual(float(item.get("rsquared")), 0)
            self.assertGreaterEqual(float(item.get("pvalues")), 0)

    def test_predict_response_date(self):
        """Test that predict() returns expected date range."""
        dh = DateHelper()

        expected = []
        for n in range(0, 10):
            expected.append({"usage_start": dh.n_days_ago(dh.yesterday, 10 - n).date(), "total_cost": 5})

        mocked_table = Mock()
        mocked_table.objects.filter.return_value.order_by.return_value.values.return_value.annotate.return_value = (  # noqa: E501
            expected
        )
        mocked_table.len = len(expected)

        params = self.mocked_query_params("?", AWSCostForecastView)
        instance = AWSForecast(params)

        instance.cost_summary_table = mocked_table

        results = instance.predict()

        for item in results:
            self.assertRegex(item.get("date"), r"\d{4}-\d{2}-\d{2}")
            p_date = datetime.strptime(item.get("date"), "%Y-%m-%d")
            self.assertLessEqual(p_date.date(), dh.this_month_end.date())

    def test_predict_few_values(self):
        """Test that predict() behaves well with a limited data set."""
        dh = DateHelper()

        num_elements = [1, 2, 3, 4, 5]

        for number in num_elements:
            with self.subTest(num_elements=number):
                expected = []
                for n in range(0, number):
                    expected.append({"usage_start": dh.n_days_ago(dh.yesterday, 10 - n).date(), "total_cost": 5})

                mocked_table = Mock()
                mocked_table.objects.filter.return_value.order_by.return_value.values.return_value.annotate.return_value = (  # noqa: E501
                    expected
                )
                mocked_table.len = len(expected)

                params = self.mocked_query_params("?", AWSCostForecastView)
                instance = AWSForecast(params)

                instance.cost_summary_table = mocked_table
                if number == 1:
                    # forecasting isn't possible with only 1 data point.
                    with self.assertLogs(logger="forecast.forecast", level=logging.ERROR):
                        results = instance.predict()
                        self.assertEqual(results, [])
                else:
                    with self.assertLogs(logger="forecast.forecast", level=logging.WARNING):
                        results = instance.predict()

                        for item in results:
                            self.assertRegex(item.get("date"), r"\d{4}-\d{2}-\d{2}")
                            self.assertGreaterEqual(float(item.get("value")), 0)
                            self.assertGreaterEqual(float(item.get("confidence_max")), 0)
                            self.assertGreaterEqual(float(item.get("confidence_min")), 0)
                            self.assertGreaterEqual(float(item.get("rsquared")), 0)
                            self.assertGreaterEqual(float(item.get("pvalues")), 0)

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
            expected.append({"usage_start": dh.n_days_ago(dh.yesterday, 10 - n).date(), "total_cost": 5})

        mocked_table = Mock()
        mocked_table.objects.filter.return_value.order_by.return_value.values.return_value.annotate.return_value = (  # noqa: E501
            expected
        )
        mocked_table.len = len(expected)

        params = self.mocked_query_params("?", AzureCostForecastView)
        instance = AzureForecast(params)

        instance.cost_summary_table = mocked_table

        results = instance.predict()

        for item in results:
            self.assertRegex(item.get("date"), r"\d{4}-\d{2}-\d{2}")
            self.assertAlmostEqual(float(item.get("value")), 5, delta=0.0001)
            self.assertAlmostEqual(float(item.get("confidence_max")), 5, delta=0.0001)
            self.assertAlmostEqual(float(item.get("confidence_min")), 5, delta=0.0001)
            self.assertAlmostEqual(float(item.get("rsquared")), 1, delta=0.0001)
            self.assertGreaterEqual(float(item.get("pvalues")), 0)


class OCPForecastTest(IamTestCase):
    """Tests the OCPForecast class."""

    def test_predict_flat(self):
        """Test that predict() returns expected values for flat costs."""
        dh = DateHelper()

        expected = []
        for n in range(0, 10):
            expected.append({"usage_start": dh.n_days_ago(dh.yesterday, 10 - n).date(), "total_cost": 5})

        mocked_table = Mock()
        mocked_table.objects.filter.return_value.order_by.return_value.values.return_value.annotate.return_value = (  # noqa: E501
            expected
        )
        mocked_table.len = len(expected)

        params = self.mocked_query_params("?", OCPCostForecastView)
        instance = OCPForecast(params)

        instance.cost_summary_table = mocked_table

        results = instance.predict()

        for item in results:
            self.assertRegex(item.get("date"), r"\d{4}-\d{2}-\d{2}")
            self.assertAlmostEqual(float(item.get("value")), 5, delta=0.0001)
            self.assertAlmostEqual(float(item.get("confidence_max")), 5, delta=0.0001)
            self.assertAlmostEqual(float(item.get("confidence_min")), 5, delta=0.0001)
            self.assertAlmostEqual(float(item.get("rsquared")), 1, delta=0.0001)
            self.assertGreaterEqual(float(item.get("pvalues")), 0)


class OCPAllForecastTest(IamTestCase):
    """Tests the OCPAllForecast class."""

    def test_predict_flat(self):
        """Test that predict() returns expected values for flat costs."""
        dh = DateHelper()

        expected = []
        for n in range(0, 10):
            expected.append({"usage_start": dh.n_days_ago(dh.yesterday, 10 - n).date(), "total_cost": 5})

        mocked_table = Mock()
        mocked_table.objects.filter.return_value.order_by.return_value.values.return_value.annotate.return_value = (  # noqa: E501
            expected
        )
        mocked_table.len = len(expected)

        params = self.mocked_query_params("?", OCPAllCostForecastView)
        instance = OCPAllForecast(params)

        instance.cost_summary_table = mocked_table

        results = instance.predict()

        for item in results:
            self.assertRegex(item.get("date"), r"\d{4}-\d{2}-\d{2}")
            self.assertAlmostEqual(float(item.get("value")), 5, delta=0.0001)
            self.assertAlmostEqual(float(item.get("confidence_max")), 5, delta=0.0001)
            self.assertAlmostEqual(float(item.get("confidence_min")), 5, delta=0.0001)
            self.assertAlmostEqual(float(item.get("rsquared")), 1, delta=0.0001)
            self.assertGreaterEqual(float(item.get("pvalues")), 0)


class OCPAWSForecastTest(IamTestCase):
    """Tests the OCPAWSForecast class."""

    def test_predict_flat(self):
        """Test that predict() returns expected values for flat costs."""
        dh = DateHelper()

        expected = []
        for n in range(0, 10):
            expected.append({"usage_start": dh.n_days_ago(dh.yesterday, 10 - n).date(), "total_cost": 5})

        mocked_table = Mock()
        mocked_table.objects.filter.return_value.order_by.return_value.values.return_value.annotate.return_value = (  # noqa: E501
            expected
        )
        mocked_table.len = len(expected)

        params = self.mocked_query_params("?", OCPAWSCostForecastView)
        instance = OCPAWSForecast(params)

        instance.cost_summary_table = mocked_table

        results = instance.predict()

        for item in results:
            self.assertRegex(item.get("date"), r"\d{4}-\d{2}-\d{2}")
            self.assertAlmostEqual(float(item.get("value")), 5, delta=0.0001)
            self.assertAlmostEqual(float(item.get("confidence_max")), 5, delta=0.0001)
            self.assertAlmostEqual(float(item.get("confidence_min")), 5, delta=0.0001)
            self.assertAlmostEqual(float(item.get("rsquared")), 1, delta=0.0001)
            self.assertGreaterEqual(float(item.get("pvalues")), 0)


class OCPAzureForecastTest(IamTestCase):
    """Tests the OCPAzureForecast class."""

    def test_predict_flat(self):
        """Test that predict() returns expected values for flat costs."""
        dh = DateHelper()

        expected = []
        for n in range(0, 10):
            expected.append({"usage_start": dh.n_days_ago(dh.yesterday, 10 - n).date(), "total_cost": 5})

        mocked_table = Mock()
        mocked_table.objects.filter.return_value.order_by.return_value.values.return_value.annotate.return_value = (  # noqa: E501
            expected
        )
        mocked_table.len = len(expected)

        params = self.mocked_query_params("?", OCPAzureCostForecastView)
        instance = OCPAzureForecast(params)

        instance.cost_summary_table = mocked_table

        results = instance.predict()

        for item in results:
            self.assertRegex(item.get("date"), r"\d{4}-\d{2}-\d{2}")
            self.assertAlmostEqual(float(item.get("value")), 5, delta=0.0001)
            self.assertAlmostEqual(float(item.get("confidence_max")), 5, delta=0.0001)
            self.assertAlmostEqual(float(item.get("confidence_min")), 5, delta=0.0001)
            self.assertAlmostEqual(float(item.get("rsquared")), 1, delta=0.0001)
            self.assertGreaterEqual(float(item.get("pvalues")), 0)
