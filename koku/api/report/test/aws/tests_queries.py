#
# Copyright 2019 Red Hat, Inc.
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
"""Test the Report Queries."""
import copy
from collections import OrderedDict, defaultdict
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import PropertyMock, patch

from django.db.models import Count, F, Sum
from django.urls import reverse
from rest_framework.exceptions import ValidationError
from tenant_schemas.utils import tenant_context

from api.iam.test.iam_test_case import IamTestCase
from api.models import Provider
from api.provider.test import create_generic_provider
from api.report.aws.query_handler import AWSReportQueryHandler
from api.report.aws.view import AWSCostView, AWSInstanceTypeView, AWSStorageView
from api.report.queries import strip_tag_prefix
from api.report.test import FakeAWSCostData
from api.report.test.aws.helpers import AWSReportDataGenerator
from api.tags.aws.queries import AWSTagQueryHandler
from api.tags.aws.view import AWSTagView
from api.utils import DateHelper
from reporting.models import AWSCostEntryLineItemDaily, AWSCostEntryLineItemDailySummary, AWSCostEntryProduct


class AWSReportQueryTest(IamTestCase):
    """Tests the report queries."""

    def setUp(self):
        """Set up the customer view tests."""
        self.dh = DateHelper()
        super().setUp()
        _, self.provider = create_generic_provider(Provider.PROVIDER_AWS, self.headers)
        self.fake_aws = FakeAWSCostData(self.provider)
        self.generator = AWSReportDataGenerator(self.tenant)
        self.generator.add_data_to_tenant(self.fake_aws)

    def test_apply_group_null_label(self):
        """Test adding group label for null values."""
        url = '?'
        query_params = self.mocked_query_params(url, AWSCostView)
        handler = AWSReportQueryHandler(query_params)
        groups = ['region']
        data = {'region': None, 'units': 'USD'}
        expected = {'region': 'no-region', 'units': 'USD'}
        out_data = handler._apply_group_null_label(data, groups)
        self.assertEqual(expected, out_data)

        data = {'region': 'us-east', 'units': 'USD'}
        expected = {'region': 'us-east', 'units': 'USD'}
        out_data = handler._apply_group_null_label(data, groups)
        self.assertEqual(expected, out_data)

        groups = []
        out_data = handler._apply_group_null_label(data, groups)
        self.assertEqual(expected, out_data)

    def test_transform_null_group(self):
        """Test transform data with null group value."""
        url = '?'
        query_params = self.mocked_query_params(url, AWSCostView)
        handler = AWSReportQueryHandler(query_params)
        groups = ['region']
        group_index = 0
        data = {None: [{'region': 'no-region', 'units': 'USD'}]}
        expected = [
            {'region': 'no-region', 'values': [{'region': 'no-region', 'units': 'USD'}]}
        ]
        out_data = handler._transform_data(groups, group_index, data)
        self.assertEqual(expected, out_data)

        data = {'us-east': [{'region': 'us-east', 'units': 'USD'}]}
        expected = [
            {'region': 'us-east', 'values': [{'region': 'us-east', 'units': 'USD'}]}
        ]
        out_data = handler._transform_data(groups, group_index, data)
        self.assertEqual(expected, out_data)

        data = {None: {'region': 'no-region', 'units': 'USD'}}
        expected = [{'region': 'no-region', 'values': {'region': 'no-region', 'units': 'USD'}}]
        out_data = handler._transform_data(groups, group_index, data)
        self.assertEqual(expected, out_data)

    def test_get_group_by_with_group_by_and_limit_params(self):
        """Test the _get_group_by method with limit and group by params."""
        expected = ['account']
        url = '?group_by[account]=*&filter[limit]=1'
        query_params = self.mocked_query_params(url, AWSInstanceTypeView)
        handler = AWSReportQueryHandler(query_params)
        group_by = handler._get_group_by()
        self.assertEqual(expected, group_by)

    def test_get_group_by_with_group_by_and_no_limit_params(self):
        """Test the _get_group_by method with group by params."""
        expected = ['account', 'instance_type']
        url = '?group_by[account]=*'
        query_params = self.mocked_query_params(url, AWSInstanceTypeView)
        handler = AWSReportQueryHandler(query_params)
        group_by = handler._get_group_by()
        self.assertEqual(expected, group_by)

    def test_get_group_by_with_limit_and_no_group_by_params(self):
        """Test the _get_group_by method with limit params."""
        expected = ['instance_type']
        url = '?filter[limit]=1'
        query_params = self.mocked_query_params(url, AWSInstanceTypeView)
        handler = AWSReportQueryHandler(query_params)
        group_by = handler._get_group_by()
        self.assertEqual(expected, group_by)

    def test_get_resolution_empty_day_time_scope(self):
        """Test get_resolution returns default when time_scope is month."""
        url = '?filter[time_scope_value]=-10'
        query_params = self.mocked_query_params(url, AWSCostView)
        handler = AWSReportQueryHandler(query_params)
        self.assertEqual(handler.get_resolution(), 'daily')

    def test_get_time_scope_units_empty_default(self):
        """Test get_time_scope_units returns default when query params are empty."""
        url = '?'
        query_params = self.mocked_query_params(url, AWSCostView)
        handler = AWSReportQueryHandler(query_params)
        self.assertEqual(handler.get_time_scope_units(), 'day')

    def test_get_time_scope_units_existing_value(self):
        """Test get_time_scope_units returns month when time_scope is month."""
        url = '?filter[time_scope_units]=month'
        query_params = self.mocked_query_params(url, AWSCostView)
        handler = AWSReportQueryHandler(query_params)
        self.assertEqual(handler.get_time_scope_units(), 'month')

    def test_get_time_scope_value_empty_default(self):
        """Test get_time_scope_value returns default when query params are empty."""
        url = '?'
        query_params = self.mocked_query_params(url, AWSCostView)
        handler = AWSReportQueryHandler(query_params)
        self.assertEqual(handler.get_time_scope_value(), -10)

    def test_get_time_scope_value_existing_value(self):
        """Test validationerror for invalid time_scope_value."""
        url = '?filter[time_scope_value]=9999'
        with self.assertRaises(ValidationError):
            self.mocked_query_params(url, AWSCostView)

    def test_get_time_frame_filter_current_month(self):
        """Test _get_time_frame_filter for current month."""
        url = '?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=daily'
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
        url = '?filter[time_scope_units]=month&filter[time_scope_value]=-2&filter[resolution]=daily'
        query_params = self.mocked_query_params(url, AWSCostView)
        handler = AWSReportQueryHandler(query_params)
        start = handler.start_datetime
        end = handler.end_datetime
        interval = handler.time_interval
        self.assertEqual(start, DateHelper().last_month_start)
        self.assertEqual(end, DateHelper().last_month_end)
        self.assertIsInstance(interval, list)
        self.assertTrue(len(interval) >= 28)

    def test_get_time_frame_filter_last_ten(self):
        """Test _get_time_frame_filter for last ten days."""
        url = '?filter[time_scope_units]=day&filter[time_scope_value]=-10&filter[resolution]=daily'
        query_params = self.mocked_query_params(url, AWSCostView)
        handler = AWSReportQueryHandler(query_params)
        dh = DateHelper()
        nine_days_ago = dh.n_days_ago(dh.today, 9)
        start = handler.start_datetime.replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        end = handler.end_datetime.replace(hour=0, minute=0, second=0, microsecond=0)
        interval = handler.time_interval
        self.assertEqual(start, nine_days_ago)
        self.assertEqual(end, dh.today)
        self.assertIsInstance(interval, list)
        self.assertTrue(len(interval) == 10)

    def test_get_time_frame_filter_last_thirty(self):
        """Test _get_time_frame_filter for last thirty days."""
        url = '?filter[time_scope_units]=day&filter[time_scope_value]=-30&filter[resolution]=daily'
        query_params = self.mocked_query_params(url, AWSCostView)
        handler = AWSReportQueryHandler(query_params)
        dh = DateHelper()
        twenty_nine_days_ago = dh.n_days_ago(dh.today, 29)
        start = handler.start_datetime.replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        end = handler.end_datetime.replace(hour=0, minute=0, second=0, microsecond=0)
        interval = handler.time_interval
        self.assertEqual(start, twenty_nine_days_ago)
        self.assertEqual(end, dh.today)
        self.assertIsInstance(interval, list)
        self.assertTrue(len(interval) == 30)

    def test_execute_take_defaults(self):
        """Test execute_query for current month on daily breakdown."""
        url = '?'
        query_params = self.mocked_query_params(url, AWSCostView)
        handler = AWSReportQueryHandler(query_params)
        query_output = handler.execute_query()
        self.assertIsNotNone(query_output.get('data'))
        self.assertIsNotNone(query_output.get('total'))
        total = query_output.get('total')
        self.assertIsNotNone(total.get('cost'))

    def test_execute_query_current_month_daily(self):
        """Test execute_query for current month on daily breakdown."""
        url = '?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=daily'
        query_params = self.mocked_query_params(url, AWSCostView)
        handler = AWSReportQueryHandler(query_params)
        query_output = handler.execute_query()
        self.assertIsNotNone(query_output.get('data'))
        self.assertIsNotNone(query_output.get('total'))
        total = query_output.get('total')
        self.assertIsNotNone(total.get('cost'))
        self.assertAlmostEqual(
            total.get('cost', {}).get('value'), self.generator.current_month_total, 6
        )

    def test_execute_query_current_month_monthly(self):
        """Test execute_query for current month on monthly breakdown."""
        url = '?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly'
        query_params = self.mocked_query_params(url, AWSCostView)
        handler = AWSReportQueryHandler(query_params)
        query_output = handler.execute_query()
        self.assertIsNotNone(query_output.get('data'))
        self.assertIsNotNone(query_output.get('total'))
        total = query_output.get('total')
        self.assertIsNotNone(total.get('cost'))
        self.assertAlmostEqual(
            total.get('cost', {}).get('value'), self.generator.current_month_total, 6
        )

    def test_execute_query_current_month_by_service(self):
        """Test execute_query for current month on monthly breakdown by service."""
        url = '?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&group_by[service]=*'  # noqa: E501
        query_params = self.mocked_query_params(url, AWSCostView)
        handler = AWSReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get('data')
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get('total'))
        total = query_output.get('total')
        self.assertIsNotNone(total.get('cost'))
        self.assertAlmostEqual(
            total.get('cost', {}).get('value'), self.generator.current_month_total, 6
        )

        cmonth_str = DateHelper().this_month_start.strftime('%Y-%m')
        for data_item in data:
            month_val = data_item.get('date')
            month_data = data_item.get('services')
            self.assertEqual(month_val, cmonth_str)
            self.assertIsInstance(month_data, list)
            for month_item in month_data:
                compute = month_item.get('service')
                self.assertEqual(compute, 'AmazonEC2')
                self.assertIsInstance(month_item.get('values'), list)

    def test_execute_query_by_filtered_service(self):
        """Test execute_query monthly breakdown by filtered service."""
        url = '?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&group_by[service]=AmazonEC2'  # noqa: E501
        query_params = self.mocked_query_params(url, AWSCostView)
        handler = AWSReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get('data')
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get('total'))
        total = query_output.get('total')
        self.assertIsNotNone(total.get('cost'))
        self.assertAlmostEqual(
            total.get('cost', {}).get('value'), self.generator.current_month_total, 6
        )

        cmonth_str = DateHelper().this_month_start.strftime('%Y-%m')
        for data_item in data:
            month_val = data_item.get('date')
            month_data = data_item.get('services')
            self.assertEqual(month_val, cmonth_str)
            self.assertIsInstance(month_data, list)
            for month_item in month_data:
                compute = month_item.get('service')
                self.assertEqual(compute, 'AmazonEC2')
                self.assertIsInstance(month_item.get('values'), list)

    def test_query_by_partial_filtered_service(self):
        """Test execute_query monthly breakdown by filtered service."""
        url = '?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&group_by[service]=eC2'  # noqa: E501
        query_params = self.mocked_query_params(url, AWSCostView)
        handler = AWSReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get('data')
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get('total'))
        total = query_output.get('total')
        self.assertIsNotNone(total.get('cost'))
        self.assertAlmostEqual(
            total.get('cost', {}).get('value'), self.generator.current_month_total, 6
        )

        cmonth_str = DateHelper().this_month_start.strftime('%Y-%m')
        for data_item in data:
            month_val = data_item.get('date')
            month_data = data_item.get('services')
            self.assertEqual(month_val, cmonth_str)
            self.assertIsInstance(month_data, list)
            for month_item in month_data:
                compute = month_item.get('service')
                self.assertEqual(compute, 'AmazonEC2')
                self.assertIsInstance(month_item.get('values'), list)

    def test_execute_query_current_month_by_account(self):
        """Test execute_query for current month on monthly breakdown by account."""
        url = '?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&group_by[account]=*'  # noqa: E501
        query_params = self.mocked_query_params(url, AWSCostView)
        handler = AWSReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get('data')
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get('total'))
        total = query_output.get('total')
        self.assertIsNotNone(total.get('cost'))
        self.assertAlmostEqual(
            total.get('cost', {}).get('value'), self.generator.current_month_total, 6
        )

        cmonth_str = DateHelper().this_month_start.strftime('%Y-%m')
        for data_item in data:
            month_val = data_item.get('date')
            month_data = data_item.get('accounts')
            self.assertEqual(month_val, cmonth_str)
            self.assertIsInstance(month_data, list)
            for month_item in month_data:
                account = month_item.get('account')
                self.assertEqual(account, self.fake_aws.account_id)
                self.assertIsInstance(month_item.get('values'), list)

    def test_execute_query_by_account_by_service(self):
        """Test execute_query for current month breakdown by account by service."""
        url = '?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&group_by[account]=*&group_by[service]=*'  # noqa: E501
        query_params = self.mocked_query_params(url, AWSCostView)
        handler = AWSReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get('data')
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get('total'))
        total = query_output.get('total')
        self.assertIsNotNone(total.get('cost'))
        self.assertAlmostEqual(
            total.get('cost', {}).get('value'), self.generator.current_month_total, 6
        )

        cmonth_str = DateHelper().this_month_start.strftime('%Y-%m')
        for data_item in data:
            month_val = data_item.get('date')
            month_data = data_item.get('accounts')
            self.assertEqual(month_val, cmonth_str)
            self.assertIsInstance(month_data, list)
            for month_item in month_data:
                account = month_item.get('account')
                self.assertEqual(account, self.fake_aws.account_id)
                self.assertIsInstance(month_item.get('services'), list)

    def test_execute_query_with_counts(self):
        """Test execute_query for with counts of unique resources."""
        with tenant_context(self.tenant):
            instance_type = AWSCostEntryProduct.objects.first().instance_type

        url = '?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=daily&group_by[instance_type]=*'  # noqa: E501
        query_params = self.mocked_query_params(url, AWSInstanceTypeView)
        handler = AWSReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get('data')
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get('total'))

        total = query_output.get('total')
        self.assertIsNotNone(total.get('count'))
        self.assertEqual(total.get('count', {}).get('value'), 24)

        annotations = {
            'date': F('usage_start'),
            'count': Count('resource_id', distinct=True)
        }

        expected_counts = AWSCostEntryLineItemDaily.objects.values(**annotations)
        count_dict = defaultdict(int)
        for item in expected_counts:
            count_dict[str(item['date'].date())] += item['count']

        for data_item in data:
            instance_types = data_item.get('instance_types')
            expected_count = count_dict.get(data_item.get('date'))
            for it in instance_types:
                if it['instance_type'] == instance_type:
                    actual_count = it['values'][0].get('count', {}).get('value')
                    self.assertEqual(actual_count, expected_count)

    def test_execute_query_curr_month_by_account_w_limit(self):
        """Test execute_query for current month on monthly breakdown by account with limit."""
        self.generator.add_data_to_tenant(FakeAWSCostData(self.provider))

        url = '?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&filter[limit]=2&group_by[account]=*'  # noqa: E501
        query_params = self.mocked_query_params(url, AWSCostView)
        handler = AWSReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get('data')
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get('total'))
        total = query_output.get('total')
        self.assertIsNotNone(total.get('cost'))
        self.assertAlmostEqual(
            total.get('cost', {}).get('value'), self.generator.current_month_total, 6
        )

        cmonth_str = DateHelper().this_month_start.strftime('%Y-%m')
        for data_item in data:
            month_val = data_item.get('date')
            month_data = data_item.get('accounts')
            self.assertEqual(month_val, cmonth_str)
            self.assertIsInstance(month_data, list)
            self.assertEqual(2, len(month_data))
            for month_item in month_data:
                self.assertIsInstance(month_item.get('account'), str)
                self.assertIsInstance(month_item.get('values'), list)

    def test_execute_query_curr_month_by_account_w_order(self):
        """Test execute_query for current month on monthly breakdown by account with asc order."""
        self.generator.add_data_to_tenant(FakeAWSCostData(self.provider))

        url = '?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&group_by[account]=*&order_by[cost]=asc'  # noqa: E501
        query_params = self.mocked_query_params(url, AWSCostView)
        handler = AWSReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get('data')
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get('total'))
        total = query_output.get('total')
        self.assertIsNotNone(total.get('cost'))
        self.assertAlmostEqual(
            total.get('cost', {}).get('value'), self.generator.current_month_total, 6
        )

        cmonth_str = DateHelper().this_month_start.strftime('%Y-%m')
        for data_item in data:
            month_val = data_item.get('date')
            month_data = data_item.get('accounts')
            self.assertEqual(month_val, cmonth_str)
            self.assertIsInstance(month_data, list)
            self.assertEqual(len(month_data), 2)
            current_total = 0
            for month_item in month_data:
                self.assertIsInstance(month_item.get('account'), str)
                self.assertIsInstance(month_item.get('values'), list)
                self.assertIsNotNone(
                    month_item.get('values')[0].get('cost', {}).get('value')
                )
                data_point_total = (
                    month_item.get('values')[0].get('cost', {}).get('value')
                )
                self.assertLess(current_total, data_point_total)
                current_total = data_point_total

    def test_execute_query_curr_month_by_account_w_order_by_account_alias(self):
        """Test execute_query for current month on monthly breakdown by account with asc order."""
        self.generator.add_data_to_tenant(FakeAWSCostData(self.provider))

        url = '?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&group_by[account]=*&order_by[account_alias]=asc'  # noqa: E501
        query_params = self.mocked_query_params(url, AWSCostView)
        handler = AWSReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get('data')
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get('total'))
        total = query_output.get('total')
        self.assertIsNotNone(total.get('cost'))
        self.assertAlmostEqual(
            total.get('cost', {}).get('value'), self.generator.current_month_total, 6
        )

        cmonth_str = DateHelper().this_month_start.strftime('%Y-%m')
        for data_item in data:
            month_val = data_item.get('date')
            month_data = data_item.get('accounts')
            self.assertEqual(month_val, cmonth_str)
            self.assertIsInstance(month_data, list)
            self.assertEqual(len(month_data), 2)
            current = ''
            for month_item in month_data:
                self.assertIsInstance(month_item.get('account'), str)
                self.assertIsInstance(month_item.get('values'), list)
                self.assertIsNotNone(month_item.get('values')[0].get('account'))
                data_point = month_item.get('values')[0].get('account_alias')
                self.assertLess(current, data_point)
                current = data_point

    def test_execute_query_curr_month_by_region(self):
        """Test execute_query for current month on monthly breakdown by region."""
        url = '?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&group_by[region]=*'  # noqa: E501
        query_params = self.mocked_query_params(url, AWSCostView)
        handler = AWSReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get('data')
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get('total'))
        total = query_output.get('total')
        self.assertIsNotNone(total.get('cost'))
        self.assertAlmostEqual(
            total.get('cost', {}).get('value'), self.generator.current_month_total, 6
        )

        cmonth_str = DateHelper().this_month_start.strftime('%Y-%m')
        for data_item in data:
            month_val = data_item.get('date')
            month_data = data_item.get('regions')
            self.assertEqual(month_val, cmonth_str)
            self.assertIsInstance(month_data, list)
            self.assertEqual(1, len(month_data))
            for month_item in month_data:
                self.assertIsInstance(month_item.get('region'), str)
                self.assertIsInstance(month_item.get('values'), list)
                self.assertIsNotNone(month_item.get('values')[0].get('cost'))

    def test_execute_query_curr_month_by_filtered_region(self):
        """Test execute_query for current month on monthly breakdown by filtered region."""
        url = f'?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&group_by[region]={self.fake_aws.region}'  # noqa: E501
        query_params = self.mocked_query_params(url, AWSCostView)
        handler = AWSReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get('data')
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get('total'))
        total = query_output.get('total')
        self.assertIsNotNone(total.get('cost'))
        self.assertGreater(total.get('cost', {}).get('value'), 0)

        cmonth_str = DateHelper().this_month_start.strftime('%Y-%m')
        for data_item in data:
            month_val = data_item.get('date')
            month_data = data_item.get('regions')
            self.assertEqual(month_val, cmonth_str)
            self.assertIsInstance(month_data, list)
            for month_item in month_data:
                self.assertIsInstance(month_item.get('region'), str)
                self.assertIsInstance(month_item.get('values'), list)
                self.assertIsNotNone(month_item.get('values')[0].get('cost'))

    def test_execute_query_curr_month_by_avail_zone(self):
        """Test execute_query for current month on monthly breakdown by avail_zone."""
        url = '?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&group_by[az]=*'  # noqa: E501
        query_params = self.mocked_query_params(url, AWSCostView)
        handler = AWSReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get('data')
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get('total'))
        total = query_output.get('total')
        self.assertIsNotNone(total.get('cost'))
        self.assertAlmostEqual(
            total.get('cost', {}).get('value'), self.generator.current_month_total, 6
        )

        cmonth_str = DateHelper().this_month_start.strftime('%Y-%m')
        for data_item in data:
            month_val = data_item.get('date')
            month_data = data_item.get('azs')
            self.assertEqual(month_val, cmonth_str)
            self.assertIsInstance(month_data, list)
            self.assertEqual(len(month_data), 1)
            for month_item in month_data:
                self.assertIsInstance(month_item.get('az'), str)
                self.assertIsInstance(month_item.get('values'), list)
                self.assertIsNotNone(month_item.get('values')[0].get('cost'))

    def test_execute_query_curr_month_by_filtered_avail_zone(self):
        """Test execute_query for current month on monthly breakdown by filtered avail_zone."""
        url = f'?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&group_by[az]={self.fake_aws.availability_zone}'  # noqa: E501
        query_params = self.mocked_query_params(url, AWSCostView)
        handler = AWSReportQueryHandler(query_params)
        query_output = handler.execute_query()

        data = query_output.get('data')
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get('total'))
        total = query_output.get('total')
        self.assertIsNotNone(total.get('cost'))

        cmonth_str = DateHelper().this_month_start.strftime('%Y-%m')
        for data_item in data:
            month_val = data_item.get('date')
            month_data = data_item.get('azs')
            self.assertEqual(month_val, cmonth_str)
            self.assertIsInstance(month_data, list)
            self.assertEqual(1, len(month_data))
            for month_item in month_data:
                self.assertIsInstance(month_item.get('az'), str)
                self.assertIsInstance(month_item.get('values'), list)
                self.assertIsNotNone(month_item.get('values')[0].get('cost'))

    def test_execute_query_current_month_filter_account(self):
        """Test execute_query for current month on monthly filtered by account."""
        url = f'?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&filter[account]={self.fake_aws.account_alias}'  # noqa: E501
        query_params = self.mocked_query_params(url, AWSCostView)
        handler = AWSReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get('data')
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get('total'))
        total = query_output.get('total')
        self.assertIsNotNone(total.get('cost'))
        self.assertAlmostEqual(
            total.get('cost', {}).get('value'), self.generator.current_month_total, 6
        )

        cmonth_str = DateHelper().this_month_start.strftime('%Y-%m')
        for data_item in data:
            month_val = data_item.get('date')
            month_data = data_item.get('values')
            self.assertEqual(month_val, cmonth_str)
            self.assertIsInstance(month_data, list)

    def test_execute_query_current_month_filter_service(self):
        """Test execute_query for current month on monthly filtered by service."""
        url = '?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&filter[service]=AmazonEC2'  # noqa: E501
        query_params = self.mocked_query_params(url, AWSCostView)
        handler = AWSReportQueryHandler(query_params)
        query_output = handler.execute_query()

        data = query_output.get('data')
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get('total'))

        total = query_output.get('total')
        self.assertIsNotNone(total.get('cost'))
        self.assertAlmostEqual(
            total.get('cost', {}).get('value'), self.generator.current_month_total, 6
        )

        cmonth_str = DateHelper().this_month_start.strftime('%Y-%m')
        for data_item in data:
            month_val = data_item.get('date')
            month_data = data_item.get('values')
            self.assertEqual(month_val, cmonth_str)
            self.assertIsInstance(month_data, list)

    def test_execute_query_current_month_filter_region(self):
        """Test execute_query for current month on monthly filtered by region."""
        url = f'?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&filter[region]={self.fake_aws.region}'  # noqa: E501
        query_params = self.mocked_query_params(url, AWSCostView)
        handler = AWSReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get('data')
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get('total'))
        total = query_output.get('total')
        self.assertIsNotNone(total.get('cost'))
        self.assertGreater(total.get('cost', {}).get('value'), 0)

        cmonth_str = DateHelper().this_month_start.strftime('%Y-%m')
        for data_item in data:
            month_val = data_item.get('date')
            month_data = data_item.get('values')
            self.assertEqual(month_val, cmonth_str)
            self.assertIsInstance(month_data, list)

    def test_execute_query_current_month_filter_avail_zone(self):
        """Test execute_query for current month on monthly filtered by avail_zone."""
        url = f'?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&filter[az]={self.fake_aws.availability_zone}'  # noqa: E501
        query_params = self.mocked_query_params(url, AWSCostView)
        handler = AWSReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get('data')
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get('total'))
        total = query_output.get('total')
        self.assertIsNotNone(total.get('cost'))
        self.assertAlmostEqual(
            total.get('cost', {}).get('value'), self.generator.current_month_total, 6
        )

        cmonth_str = DateHelper().this_month_start.strftime('%Y-%m')
        for data_item in data:
            month_val = data_item.get('date')
            month_data = data_item.get('values')
            self.assertEqual(month_val, cmonth_str)
            self.assertIsInstance(month_data, list)

    @patch('api.query_params.QueryParameters.accept_type', new_callable=PropertyMock)
    def test_execute_query_current_month_filter_avail_zone_csv(self, mock_accept):
        """Test execute_query for current month on monthly filtered by avail_zone for csv."""
        mock_accept.return_value = 'text/csv'
        url = f'?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&filter[az]={self.fake_aws.availability_zone}'  # noqa: E501
        query_params = self.mocked_query_params(url, AWSCostView)
        handler = AWSReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get('data')
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get('total'))
        total = query_output.get('total')
        self.assertIsNotNone(total.get('cost'))
        self.assertAlmostEqual(
            total.get('cost', {}).get('value'), self.generator.current_month_total, 6
        )

        cmonth_str = DateHelper().this_month_start.strftime('%Y-%m')
        self.assertEqual(len(data), 1)
        for data_item in data:
            month_val = data_item.get('date')
            self.assertEqual(month_val, cmonth_str)

    @patch('api.query_params.QueryParameters.accept_type', new_callable=PropertyMock)
    def test_execute_query_curr_month_by_account_w_limit_csv(self, mock_accept):
        """Test execute_query for current month on monthly by account with limt as csv."""
        mock_accept.return_value = 'text/csv'
        self.generator.add_data_to_tenant(FakeAWSCostData(self.provider))

        url = '?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&filter[limit]=2&group_by[account]=*'  # noqa: E501
        query_params = self.mocked_query_params(url, AWSCostView)
        handler = AWSReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get('data')

        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get('total'))
        total = query_output.get('total')
        self.assertIsNotNone(total.get('cost'))
        self.assertAlmostEqual(
            total.get('cost', {}).get('value'), self.generator.current_month_total, 6
        )

        cmonth_str = DateHelper().this_month_start.strftime('%Y-%m')
        self.assertEqual(len(data), 2)
        for data_item in data:
            month = data_item.get('date')
            self.assertEqual(month, cmonth_str)

    def test_execute_query_w_delta(self):
        """Test grouped by deltas."""
        dh = DateHelper()
        current_total = Decimal(0)
        prev_total = Decimal(0)

        previous_data = copy.deepcopy(self.fake_aws)
        previous_data.billing_period_end = dh.last_month_end
        previous_data.billing_period_start = dh.last_month_start
        previous_data.usage_end = dh.last_month_start + dh.one_day
        previous_data.usage_start = dh.last_month_start

        # add some current data.
        self.generator.add_data_to_tenant(self.fake_aws)
        # add some previous data.
        self.generator.add_data_to_tenant(previous_data)

        # fetch the expected sums from the DB.
        with tenant_context(self.tenant):
            curr = AWSCostEntryLineItemDailySummary.objects.filter(
                usage_start__gte=dh.this_month_start, usage_end__lte=dh.this_month_end
            ).aggregate(value=Sum(F('unblended_cost') + F('markup_cost')))
            current_total = Decimal(curr.get('value'))

            prev = AWSCostEntryLineItemDailySummary.objects.filter(
                usage_start__gte=dh.last_month_start, usage_end__lte=dh.last_month_end
            ).aggregate(value=Sum(F('unblended_cost') + F('markup_cost')))
            prev_total = Decimal(prev.get('value'))

        expected_delta_value = Decimal(current_total - prev_total)
        expected_delta_percent = Decimal(
            (current_total - prev_total) / prev_total * 100
        )

        url = '?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&group_by[account]=*&delta=cost'  # noqa: E501
        path = reverse('reports-aws-costs')
        query_params = self.mocked_query_params(url, AWSCostView, path)
        handler = AWSReportQueryHandler(query_params)

        # test the calculations
        query_output = handler.execute_query()
        data = query_output.get('data')
        self.assertIsNotNone(data)

        values = data[0].get('accounts', [])[0].get('values', [])[0]
        self.assertIn('delta_value', values)
        self.assertIn('delta_percent', values)
        self.assertEqual(values.get('delta_value'), expected_delta_value)
        self.assertEqual(values.get('delta_percent'), expected_delta_percent)

        delta = query_output.get('delta')
        self.assertIsNotNone(delta.get('value'))
        self.assertIsNotNone(delta.get('percent'))
        self.assertEqual(delta.get('value'), expected_delta_value)
        self.assertEqual(delta.get('percent'), expected_delta_percent)

    def test_execute_query_w_delta_no_previous_data(self):
        """Test deltas with no previous data."""
        expected_delta_value = Decimal(self.generator.current_month_total)
        expected_delta_percent = None

        url = '?filter[time_scope_value]=-1&delta=cost'
        path = reverse('reports-aws-costs')
        query_params = self.mocked_query_params(url, AWSCostView, path)
        handler = AWSReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get('data')
        self.assertIsNotNone(data)

        delta = query_output.get('delta')
        self.assertIsNotNone(delta.get('value'))
        self.assertIsNone(delta.get('percent'))
        self.assertAlmostEqual(delta.get('value'), expected_delta_value, 6)
        self.assertEqual(delta.get('percent'), expected_delta_percent)

    def test_execute_query_orderby_delta(self):
        """Test execute_query with ordering by delta ascending."""
        dh = DateHelper()
        current_data = FakeAWSCostData(self.provider)
        previous_data = copy.deepcopy(current_data)
        previous_data.billing_period_end = dh.last_month_end
        previous_data.billing_period_start = dh.last_month_start
        previous_data.usage_end = dh.last_month_start + timedelta(days=1)
        previous_data.usage_start = dh.last_month_start + timedelta(days=1)

        # add some current data.
        self.generator.add_data_to_tenant(self.fake_aws)
        # add some previous data.
        self.generator.add_data_to_tenant(previous_data)

        # create another account id for the next loop
        current_data = FakeAWSCostData(self.provider)
        previous_data = copy.deepcopy(current_data)
        previous_data.billing_period_end = dh.last_month_end
        previous_data.billing_period_start = dh.last_month_start
        previous_data.usage_end = dh.last_month_start + timedelta(days=1)
        previous_data.usage_start = dh.last_month_start + timedelta(days=1)

        url = '?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&order_by[delta]=asc&group_by[account]=*&delta=cost'  # noqa: E501
        path = reverse('reports-openshift-aws-costs')
        query_params = self.mocked_query_params(url, AWSCostView, path)
        handler = AWSReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get('data')
        self.assertIsNotNone(data)

        cmonth_str = DateHelper().this_month_start.strftime('%Y-%m')
        for data_item in data:
            month_val = data_item.get('date')
            month_data = data_item.get('accounts')
            self.assertEqual(month_val, cmonth_str)
            self.assertIsInstance(month_data, list)
            for month_item in month_data:
                self.assertIsInstance(month_item.get('account'), str)
                self.assertIsInstance(month_item.get('values'), list)
                self.assertIsNone(month_item.get('values')[0].get('delta_percent'))

    def test_execute_query_with_account_alias(self):
        """Test execute_query when account alias is avaiable."""
        url = '?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&filter[limit]=2&group_by[account]=*'  # noqa: E501
        query_params = self.mocked_query_params(url, AWSCostView)
        handler = AWSReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get('data')

        account_alias = data[0].get('accounts')[0].get('values')[0].get('account_alias')
        self.assertEqual(account_alias, self.fake_aws.account_alias)

    def test_execute_query_orderby_alias(self):
        """Test execute_query when account alias is avaiable."""
        # generate test data
        expected = {self.fake_aws.account_alias: self.fake_aws.account_id}
        fake_data = FakeAWSCostData(self.provider)
        expected[fake_data.account_alias] = fake_data.account_id
        self.generator.add_data_to_tenant(fake_data)
        expected = OrderedDict(sorted(expected.items()))

        # execute query
        url = '?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&group_by[account]=*&order_by[account_alias]=asc'  # noqa: E501
        query_params = self.mocked_query_params(url, AWSCostView)
        handler = AWSReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get('data')

        # test query output
        actual = OrderedDict()
        for datum in data:
            for account in datum.get('accounts'):
                for value in account.get('values'):
                    actual[value.get('account_alias')] = value.get('account')

        self.assertEqual(actual, expected)

    def test_calculate_total(self):
        """Test that calculated totals return correctly."""
        url = '?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly'
        query_params = self.mocked_query_params(url, AWSCostView)
        handler = AWSReportQueryHandler(query_params)
        expected_units = 'USD'
        with tenant_context(self.tenant):
            result = handler.calculate_total(**{'cost_units': expected_units})

        self.assertAlmostEqual(
            result.get('cost', {}).get('value'), self.generator.current_month_total, 6
        )
        self.assertEqual(result.get('cost', {}).get('units'), expected_units)

    def test_percent_delta(self):
        """Test _percent_delta() utility method."""
        url = '?'
        query_params = self.mocked_query_params(url, AWSCostView)
        handler = AWSReportQueryHandler(query_params)
        self.assertEqual(handler._percent_delta(10, 5), 100)

    def test_rank_list(self):
        """Test rank list limit with account alias."""
        url = '?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&filter[limit]=2&group_by[account]=*'  # noqa: E501
        query_params = self.mocked_query_params(url, AWSCostView)
        handler = AWSReportQueryHandler(query_params)
        data_list = [
            {'account': '1', 'account_alias': '1', 'total': 5, 'rank': 1},
            {'account': '2', 'account_alias': '2', 'total': 4, 'rank': 2},
            {'account': '3', 'account_alias': '3', 'total': 3, 'rank': 3},
            {'account': '4', 'account_alias': '4', 'total': 2, 'rank': 4},
        ]
        expected = [
            {'account': '1', 'account_alias': '1', 'total': 5, 'rank': 1},
            {'account': '2', 'account_alias': '2', 'total': 4, 'rank': 2},
            {
                'account': '2 Others',
                'account_alias': '2 Others',
                'cost': 0,
                'markup_cost': 0,
                'derived_cost': 0,
                'infrastructure_cost': 0,
                'total': 5,
                'rank': 3,
            },
        ]
        ranked_list = handler._ranked_list(data_list)
        self.assertEqual(ranked_list, expected)

    def test_rank_list_no_account(self):
        """Test rank list limit with out account alias."""
        url = '?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&filter[limit]=2&group_by[service]=*'  # noqa: E501
        query_params = self.mocked_query_params(url, AWSCostView)
        handler = AWSReportQueryHandler(query_params)
        data_list = [
            {'service': '1', 'total': 5, 'rank': 1},
            {'service': '2', 'total': 4, 'rank': 2},
            {'service': '3', 'total': 3, 'rank': 3},
            {'service': '4', 'total': 2, 'rank': 4},
        ]
        expected = [
            {'service': '1', 'total': 5, 'rank': 1},
            {'service': '2', 'total': 4, 'rank': 2},
            {
                'cost': 0,
                'derived_cost': 0,
                'infrastructure_cost': 0,
                'markup_cost': 0,
                'service': '2 Others',
                'total': 5,
                'rank': 3,
            },
        ]
        ranked_list = handler._ranked_list(data_list)
        self.assertEqual(ranked_list, expected)

    def test_rank_list_with_offset(self):
        """Test rank list limit and offset with account alias."""
        url = '?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&filter[limit]=1&filter[offset]=1&group_by[account]=*'  # noqa: E501
        query_params = self.mocked_query_params(url, AWSCostView)
        handler = AWSReportQueryHandler(query_params)
        data_list = [
            {'account': '1', 'account_alias': '1', 'total': 5, 'rank': 1},
            {'account': '2', 'account_alias': '2', 'total': 4, 'rank': 2},
            {'account': '3', 'account_alias': '3', 'total': 3, 'rank': 3},
            {'account': '4', 'account_alias': '4', 'total': 2, 'rank': 4},
        ]
        expected = [{'account': '2', 'account_alias': '2', 'total': 4, 'rank': 2}]
        ranked_list = handler._ranked_list(data_list)
        self.assertEqual(ranked_list, expected)

    def test_query_costs_with_totals(self):
        """Test execute_query() - costs with totals.

        Query for instance_types, validating that cost totals are present.
        """
        self.generator.add_data_to_tenant(FakeAWSCostData(self.provider), product='ec2')
        self.generator.add_data_to_tenant(FakeAWSCostData(self.provider), product='ebs')

        url = '?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&group_by[account]=*'  # noqa: E501
        query_params = self.mocked_query_params(url, AWSCostView)
        handler = AWSReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get('data')
        self.assertIsNotNone(data)

        for data_item in data:
            accounts = data_item.get('accounts')
            for account in accounts:
                self.assertIsNotNone(account.get('values'))
                self.assertGreater(len(account.get('values')), 0)
                for value in account.get('values'):
                    self.assertIsInstance(value.get('cost', {}).get('value'), Decimal)
                    self.assertGreater(value.get('cost', {}).get('value'), Decimal(0))

    def test_query_instance_types_with_totals(self):
        """Test execute_query() - instance types with totals.

        Query for instance_types, validating that cost totals are present.
        """
        self.generator.add_data_to_tenant(FakeAWSCostData(self.provider), product='ec2')

        url = '?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&group_by[instance_type]=*'  # noqa: E501
        query_params = self.mocked_query_params(url, AWSInstanceTypeView)
        handler = AWSReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get('data')
        self.assertIsNotNone(data)

        for data_item in data:
            instance_types = data_item.get('instance_types')
            for it in instance_types:
                self.assertIsNotNone(it.get('values'))
                self.assertGreater(len(it.get('values')), 0)
                for value in it.get('values'):
                    self.assertIsInstance(value.get('cost', {}).get('value'), Decimal)
                    self.assertGreater(value.get('cost', {}).get('value'), Decimal(0))
                    self.assertIsInstance(value.get('usage', {}).get('value'), Decimal)
                    self.assertGreater(value.get('usage', {}).get('value'), Decimal(0))

    def test_query_storage_with_totals(self):
        """Test execute_query() - storage with totals.

        Query for storage, validating that cost totals are present.
        """
        self.generator.add_data_to_tenant(FakeAWSCostData(self.provider), product='ebs')

        url = '?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&group_by[service]=*'  # noqa: E501
        query_params = self.mocked_query_params(url, AWSStorageView)
        handler = AWSReportQueryHandler(query_params)
        query_output = handler.execute_query()
        data = query_output.get('data')
        self.assertIsNotNone(data)

        for data_item in data:
            services = data_item.get('services')
            self.assertIsNotNone(services)
            for srv in services:
                # EBS is filed under the 'AmazonEC2' service.
                if srv.get('service') == 'AmazonEC2':
                    self.assertIsNotNone(srv.get('values'))
                    self.assertGreater(len(srv.get('values')), 0)
                    for value in srv.get('values'):
                        self.assertIsInstance(
                            value.get('cost', {}).get('value'), Decimal
                        )
                        self.assertGreater(
                            value.get('cost', {}).get('value'), Decimal(0)
                        )
                        self.assertIsInstance(
                            value.get('usage', {}).get('value'), Decimal
                        )
                        self.assertGreater(
                            value.get('usage', {}).get('value'), Decimal(0)
                        )

    def test_order_by(self):
        """Test that order_by returns properly sorted data."""
        today = datetime.utcnow()
        yesterday = today - timedelta(days=1)
        url = '?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly'  # noqa: E501
        query_params = self.mocked_query_params(url, AWSCostView)
        handler = AWSReportQueryHandler(query_params)

        unordered_data = [
            {'date': today, 'delta_percent': 8, 'total': 6.2, 'rank': 2},
            {'date': yesterday, 'delta_percent': 4, 'total': 2.2, 'rank': 1},
            {'date': today, 'delta_percent': 7, 'total': 8.2, 'rank': 1},
            {'date': yesterday, 'delta_percent': 4, 'total': 2.2, 'rank': 2},
        ]

        order_fields = ['date', 'rank']
        expected = [
            {'date': yesterday, 'delta_percent': 4, 'total': 2.2, 'rank': 1},
            {'date': yesterday, 'delta_percent': 4, 'total': 2.2, 'rank': 2},
            {'date': today, 'delta_percent': 7, 'total': 8.2, 'rank': 1},
            {'date': today, 'delta_percent': 8, 'total': 6.2, 'rank': 2},
        ]

        ordered_data = handler.order_by(unordered_data, order_fields)
        self.assertEqual(ordered_data, expected)

        order_fields = ['date', '-delta']
        expected = [
            {'date': yesterday, 'delta_percent': 4, 'total': 2.2, 'rank': 1},
            {'date': yesterday, 'delta_percent': 4, 'total': 2.2, 'rank': 2},
            {'date': today, 'delta_percent': 8, 'total': 6.2, 'rank': 2},
            {'date': today, 'delta_percent': 7, 'total': 8.2, 'rank': 1},
        ]

        ordered_data = handler.order_by(unordered_data, order_fields)
        self.assertEqual(ordered_data, expected)

    def test_strip_tag_prefix(self):
        """Verify that our tag prefix is stripped from a string."""
        tag_str = 'tag:project'
        result = strip_tag_prefix(tag_str)
        self.assertEqual(result, tag_str.replace('tag:', ''))

    def test_execute_query_with_wildcard_tag_filter(self):
        """Test that data is filtered to include entries with tag key."""
        url = '?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly'  # noqa: E501
        query_params = self.mocked_query_params(url, AWSTagView)
        handler = AWSTagQueryHandler(query_params)
        tag_keys = handler.get_tag_keys()
        filter_key = tag_keys[0]
        tag_keys = ['tag:' + tag for tag in tag_keys]

        with tenant_context(self.tenant):
            totals = (
                AWSCostEntryLineItemDailySummary.objects.filter(
                    usage_start__gte=self.dh.this_month_start
                )
                .aggregate(**{'cost': Sum(F('unblended_cost') + F('markup_cost'))})
            )

        url = f'?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&filter[tag:{filter_key}]=*'  # noqa: E501
        query_params = self.mocked_query_params(url, AWSCostView)
        handler = AWSReportQueryHandler(query_params)
        data = handler.execute_query()
        data_totals = data.get('total', {})
        for key in totals:
            result = data_totals.get(key, {}).get('value')
            self.assertEqual(result, totals[key])

    def test_execute_query_with_tag_group_by(self):
        """Test that data is grouped by tag key."""
        url = '?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly'  # noqa: E501
        query_params = self.mocked_query_params(url, AWSTagView)
        handler = AWSTagQueryHandler(query_params)
        tag_keys = handler.get_tag_keys()
        group_by_key = tag_keys[0]
        tag_keys = ['tag:' + tag for tag in tag_keys]

        with tenant_context(self.tenant):
            totals = (
                AWSCostEntryLineItemDailySummary.objects.filter(
                    usage_start__gte=self.dh.this_month_start
                )
                .aggregate(**{'cost': Sum(F('unblended_cost') + F('markup_cost'))})
            )

        url = f'?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&group_by[tag:{group_by_key}]=*'  # noqa: E501
        query_params = self.mocked_query_params(url, AWSCostView)
        handler = AWSReportQueryHandler(query_params)

        data = handler.execute_query()
        data_totals = data.get('total', {})
        data = data.get('data', [])
        expected_keys = ['date', group_by_key + 's']
        for entry in data:
            self.assertEqual(list(entry.keys()), expected_keys)
        for key in totals:
            result = data_totals.get(key, {}).get('value')
            self.assertEqual(result, totals[key])

    def test_execute_query_return_others_with_tag_group_by(self):
        """Test that data is grouped by tag key."""
        url = f'?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly'  # noqa: E501
        query_params = self.mocked_query_params(url, AWSTagView)
        handler = AWSTagQueryHandler(query_params)
        tag_keys = handler.get_tag_keys()
        group_by_key = tag_keys[0]
        tag_keys = ['tag:' + tag for tag in tag_keys]

        with tenant_context(self.tenant):
            totals = (
                AWSCostEntryLineItemDailySummary.objects.filter(
                    usage_start__gte=self.dh.this_month_start
                )
                .filter(**{'tags__has_key': group_by_key})
                .aggregate(**{'cost': Sum(F('unblended_cost') + F('markup_cost'))})
            )
            others_totals = (
                AWSCostEntryLineItemDailySummary.objects.filter(
                    usage_start__gte=self.dh.this_month_start
                )
                .exclude(**{'tags__has_key': group_by_key})
                .aggregate(**{'cost': Sum(F('unblended_cost') + F('markup_cost'))})
            )

        url = f'?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&group_by[or:tag:{group_by_key}]=*'  # noqa: E501
        query_params = self.mocked_query_params(url, AWSCostView)
        handler = AWSReportQueryHandler(query_params)

        data = handler.execute_query()
        data_totals = data.get('total', {})
        data = data.get('data', [])
        expected_keys = ['date', group_by_key + 's']
        for entry in data:
            self.assertEqual(list(entry.keys()), expected_keys)
        for key in totals:
            result = data_totals.get(key, {}).get('value')
            self.assertAlmostEqual(result, (totals[key] + others_totals[key]), 6)

    def test_execute_query_with_tag_filter(self):
        """Test that data is filtered by tag key."""
        url = f'?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly'  # noqa: E501
        query_params = self.mocked_query_params(url, AWSTagView)
        handler = AWSTagQueryHandler(query_params)
        tag_keys = handler.get_tag_keys()
        filter_key = tag_keys[0]
        tag_keys = ['tag:' + tag for tag in tag_keys]

        with tenant_context(self.tenant):
            labels = (
                AWSCostEntryLineItemDailySummary.objects.filter(
                    usage_start__gte=self.dh.this_month_start
                )
                .filter(tags__has_key=filter_key)
                .values(*['tags'])
                .all()
            )
            label_of_interest = labels[0]
            filter_value = label_of_interest.get('tags', {}).get(filter_key)

            totals = (
                AWSCostEntryLineItemDailySummary.objects.filter(
                    usage_start__gte=self.dh.this_month_start
                )
                .filter(**{f'tags__{filter_key}': filter_value})
                .aggregate(**{'cost': Sum(F('unblended_cost') + F('markup_cost'))})
            )

        url = f'?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&group_by[tag:{filter_key}]={filter_value}'  # noqa: E501
        query_params = self.mocked_query_params(url, AWSCostView)
        handler = AWSReportQueryHandler(query_params)

        data = handler.execute_query()
        data_totals = data.get('total', {})
        for key in totals:
            result = data_totals.get(key, {}).get('value')
            self.assertEqual(result, totals[key])


class AWSReportQueryLogicalAndTest(IamTestCase):
    """Tests the report queries."""

    def setUp(self):
        """Set up the customer view tests."""
        self.dh = DateHelper()
        super().setUp()
        _, self.provider = create_generic_provider(Provider.PROVIDER_AWS, self.headers)
        self.fake_aws = FakeAWSCostData(self.provider)
        self.generator = AWSReportDataGenerator(self.tenant)

    def test_prefixed_logical_and(self):
        """Test prefixed logical AND."""
        # Create Test Accounts
        account_ab_fake_aws = FakeAWSCostData(self.provider, account_alias='ab')
        self.generator.add_data_to_tenant(account_ab_fake_aws, product='ec2')

        account_ac_fake_aws = FakeAWSCostData(self.provider, account_alias='ac')
        self.generator.add_data_to_tenant(account_ac_fake_aws, product='ec2')

        # Query 1 - a AND b
        query_1_url = "?group_by[and:account]=a&group_by[and:account]=b&filter[time_scope_value]=-1&filter[time_scope_units]=month"  # noqa
        query_1_params = self.mocked_query_params(query_1_url, AWSCostView)
        query_1_handler = AWSReportQueryHandler(query_1_params)
        query_1_output = query_1_handler.execute_query()
        query_1_total = query_1_output.get('total').get('cost').get('value', 0)

        # Query 2 - ab
        query_2_url = "?group_by[account]=ab&filter[time_scope_value]=-1&filter[time_scope_units]=month"  # noqa
        query_2_params = self.mocked_query_params(query_2_url, AWSCostView)
        query_2_handler = AWSReportQueryHandler(query_2_params)
        query_2_output = query_2_handler.execute_query()
        query_2_total = query_2_output.get('total').get('cost').get('value', 1)
        with self.subTest('query1 vs query2'):
            self.assertEqual(query_1_total, query_2_total)

        # Query 3 - (a AND b AND c) == 0
        query_3_url = "?group_by[and:account]=a&group_by[and:account]=b&group_by[and:account]=c&filter[time_scope_value]=-1&filter[time_scope_units]=month"  # noqa
        query_3_params = self.mocked_query_params(query_3_url, AWSCostView)
        query_3_handler = AWSReportQueryHandler(query_3_params)
        query_3_output = query_3_handler.execute_query()
        query_3_total = query_3_output.get('total').get('cost').get('value', 2)
        with self.subTest('query3 vs 0'):
            self.assertEqual(0, query_3_total)

        # Query 4 - (a OR b) > (a AND b)
        query_4_url = "?group_by[account]=a&group_by[account]=b&filter[time_scope_value]=-1&filter[time_scope_units]=month"  # noqa
        query_4_params = self.mocked_query_params(query_4_url, AWSCostView)
        query_4_handler = AWSReportQueryHandler(query_4_params)
        query_4_output = query_4_handler.execute_query()
        query_4_total = query_4_output.get('total').get('cost').get('value', 0)
        with self.subTest('query4 vs query1'):
            self.assertGreater(query_4_total, query_1_total)


class AWSQueryHandlerTest(IamTestCase):
    """Test the report queries."""

    def setUp(self):
        """Set up the customer view tests."""
        self.dh = DateHelper()
        super().setUp()
        _, self.provider = create_generic_provider('AWS', self.headers)
        self.fake_aws = FakeAWSCostData(self.provider)
        self.generator = AWSReportDataGenerator(self.tenant)
        self.generator.add_data_to_tenant(self.fake_aws)

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
        self.generator.add_data_to_tenant(FakeAWSCostData(self.provider), product='ec2')
        self.generator.add_data_to_tenant(FakeAWSCostData(self.provider, region='eu-west-3'), product='ec2')
        self.generator.add_data_to_tenant(FakeAWSCostData(self.provider, region='us-west-1'), product='ec2')

        # First Request:
        url = '?group_by[region]=*&filter[region]=eu-west-3&group_by[service]=AmazonEC2'
        query_params = self.mocked_query_params(url, AWSInstanceTypeView)
        handler = AWSReportQueryHandler(query_params)
        data = handler.execute_query()
        # Second Request:
        url2 = '?group_by[region]=eu-west-3&group_by[service]=AmazonEC2'
        query_params2 = self.mocked_query_params(url2, AWSInstanceTypeView)
        handler2 = AWSReportQueryHandler(query_params2)
        data2 = handler2.execute_query()
        # Assert the second request contains only eu-west-3 region
        for region_dict in data2['data']:
            # For each date, assert that the region is eu-west-3
            for list_item in region_dict['regions']:
                self.assertEquals('eu-west-3', list_item['region'])
        # Assert the first request contains only eu-west-3
        for region_dict in data['data']:
            # For each date, assert that the region is eu-west-3
            for list_item in region_dict['regions']:
                self.assertEquals('eu-west-3', list_item['region'])

    def test_filter_to_group_by(self):
        """Test the filter_to_group_by method."""
        url = '?group_by[region]=*&filter[region]=eu-west-3&group_by[service]=AmazonEC2'
        query_params = self.mocked_query_params(url, AWSInstanceTypeView)
        handler = AWSReportQueryHandler(query_params)
        query_params = handler.filter_to_order_by(query_params)

        self.assertEqual(['eu-west-3'], query_params._parameters['group_by']['region'])

    def test_filter_to_group_by_3(self):
        """Test group_by[service]=something AND group_by[service]=*."""
        url = '?group_by[region]=*&filter[region]=eu-west-3&group_by[service]=AmazonEC2&group_by[service]=*&filter[service]=AmazonEC2' # noqa
        query_params = self.mocked_query_params(url, AWSInstanceTypeView)
        handler = AWSReportQueryHandler(query_params)
        query_params = handler.filter_to_order_by(query_params)

        self.assertEqual(['eu-west-3'], query_params._parameters['group_by']['region'])
        self.assertEqual(['AmazonEC2'], query_params._parameters['group_by']['service'])

    def test_filter_to_group_by_star(self):
        """Test group_by star."""
        url = '?group_by[region]=*&group_by[service]=*'
        query_params = self.mocked_query_params(url, AWSInstanceTypeView)
        handler = AWSReportQueryHandler(query_params)
        query_params = handler.filter_to_order_by(query_params)
        self.assertEqual(['*'], query_params._parameters['group_by']['region'])
        self.assertEqual(['*'], query_params._parameters['group_by']['service'])

    def test_two_filters_and_group_by_star(self):
        """
        Test two filters for the same category.

        For example, group_by[service]=*&filter[service]=X&filter[service]=Y
        """
        url = '?group_by[region]=*&filter[region]=eu-west-3&filter[region]=us-west-1'
        query_params = self.mocked_query_params(url, AWSInstanceTypeView)
        handler = AWSReportQueryHandler(query_params)
        query_params = handler.filter_to_order_by(query_params)
        region_1_exists = False
        region_2_exists = False
        if 'eu-west-3' in query_params._parameters['group_by']['region']:
            region_1_exists = True
        if 'us-west-1' in query_params._parameters['group_by']['region']:
            region_2_exists = True
        # Both regions should be in the resulting group_by list.
        self.assertTrue(region_1_exists)
        self.assertTrue(region_2_exists)
