#
# Copyright 2018 Red Hat, Inc.
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

from tenant_schemas.utils import tenant_context

from api.iam.test.iam_test_case import IamTestCase
from api.report.ocp_aws.query_handler import OCPAWSReportQueryHandler
from api.report.test import FakeQueryParameters
from api.report.test.ocp_aws.helpers import OCPAWSReportDataGenerator
from api.utils import DateHelper
from reporting.models import OCPAWSCostLineItemDailySummary


class OCPAWSQueryHandlerTestNoData(IamTestCase):
    """Tests for the OCP report query handler with no data."""

    def setUp(self):
        """Set up the customer view tests."""
        super().setUp()
        self.dh = DateHelper()

        self.this_month_filter = {'usage_start__gte': self.dh.this_month_start}
        self.ten_day_filter = {'usage_start__gte': self.dh.n_days_ago(self.dh.today, 9)}
        self.thirty_day_filter = {'usage_start__gte': self.dh.n_days_ago(self.dh.today, 29)}
        self.last_month_filter = {'usage_start__gte': self.dh.last_month_start,
                                  'usage_end__lte': self.dh.last_month_end}

    def test_execute_sum_query_instance_types(self):
        """Test that the sum query runs properly for instance-types."""
        # '?'
        query_params = FakeQueryParameters({}, report_type='instance_type', tenant=self.tenant)
        handler = OCPAWSReportQueryHandler(query_params.mock_qp)
        query_output = handler.execute_query()
        self.assertIsNotNone(query_output.get('data'))
        self.assertIsNotNone(query_output.get('total'))
        total = query_output.get('total')
        self.assertIsNotNone(total.get('cost'))
        self.assertIsInstance(total.get('cost'), dict)
        self.assertEqual(total.get('cost').get('value'), 0)
        self.assertEqual(total.get('cost').get('units'), 'USD')
        self.assertIsNotNone(total.get('usage'))
        self.assertIsInstance(total.get('usage'), dict)
        self.assertEqual(total.get('usage').get('value'), 0)
        self.assertEqual(total.get('usage').get('units'), 'Hrs')
        self.assertIsNotNone(total.get('count'))
        self.assertIsInstance(total.get('count'), dict)
        self.assertEqual(total.get('count').get('value'), 0)
        self.assertEqual(total.get('count').get('units'), 'instances')


class OCPAWSQueryHandlerTest(IamTestCase):
    """Tests for the OCP report query handler."""

    def setUp(self):
        """Set up the customer view tests."""
        super().setUp()
        self.dh = DateHelper()

        self.this_month_filter = {'usage_start__gte': self.dh.this_month_start}
        self.ten_day_filter = {'usage_start__gte': self.dh.n_days_ago(self.dh.today, 9)}
        self.thirty_day_filter = {'usage_start__gte': self.dh.n_days_ago(self.dh.today, 29)}
        self.last_month_filter = {'usage_start__gte': self.dh.last_month_start,
                                  'usage_end__lte': self.dh.last_month_end}
        OCPAWSReportDataGenerator(self.tenant).add_data_to_tenant()

    def get_totals_by_time_scope(self, aggregates, filters=None):
        """Return the total aggregates for a time period."""
        if filters is None:
            filters = self.ten_day_filter
        with tenant_context(self.tenant):
            return OCPAWSCostLineItemDailySummary.objects\
                .filter(**filters)\
                .aggregate(**aggregates)

    def test_execute_sum_query_storage(self):
        """Test that the sum query runs properly."""
        # '?'
        query_params = FakeQueryParameters({}, report_type='storage', tenant=self.tenant)
        handler = OCPAWSReportQueryHandler(query_params.mock_qp)
        filt = {'product_family__contains': 'Storage'}
        filt.update(self.ten_day_filter)
        aggregates = handler._mapper.report_type_map.get('aggregates')
        current_totals = self.get_totals_by_time_scope(aggregates, filt)
        query_output = handler.execute_query()
        self.assertIsNotNone(query_output.get('data'))
        self.assertIsNotNone(query_output.get('total'))
        total = query_output.get('total')
        self.assertEqual(total.get('total'), current_totals.get('total'))

    def test_execute_query_current_month_daily(self):
        """Test execute_query for current month on daily breakdown."""
        # '?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=daily'
        params = {'filter': {'resolution': 'daily',
                             'time_scope_value': -1,
                             'time_scope_units': 'month'}}
        query_params = FakeQueryParameters(params, tenant=self.tenant)
        handler = OCPAWSReportQueryHandler(query_params.mock_qp)
        query_output = handler.execute_query()
        self.assertIsNotNone(query_output.get('data'))
        self.assertIsNotNone(query_output.get('total'))
        total = query_output.get('total')
        self.assertIsNotNone(total.get('cost'))

        aggregates = handler._mapper.report_type_map.get('aggregates')
        current_totals = self.get_totals_by_time_scope(aggregates,
                                                       self.this_month_filter)
        self.assertEqual(total.get('cost', {}).get('value'), current_totals.get('cost'))

    def test_execute_query_current_month_monthly(self):
        """Test execute_query for current month on monthly breakdown."""
        # '?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=daily'
        params = {'filter': {'resolution': 'daily',
                             'time_scope_value': -1,
                             'time_scope_units': 'month'}}
        query_params = FakeQueryParameters(params, tenant=self.tenant)
        handler = OCPAWSReportQueryHandler(query_params.mock_qp)
        query_output = handler.execute_query()
        self.assertIsNotNone(query_output.get('data'))
        self.assertIsNotNone(query_output.get('total'))
        total = query_output.get('total')
        self.assertIsNotNone(total.get('cost'))

        aggregates = handler._mapper.report_type_map.get('aggregates')
        current_totals = self.get_totals_by_time_scope(aggregates,
                                                       self.this_month_filter)
        self.assertEqual(total.get('cost', {}).get('value'), current_totals.get('cost'))

    def test_execute_query_current_month_by_service(self):
        """Test execute_query for current month on monthly breakdown by service."""
        # '?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&group_by[service]=*'
        params = {'filter': {'resolution': 'monthly',
                             'time_scope_value': -1,
                             'time_scope_units': 'month'},
                  'group_by': {'service': ['*']}}
        query_params = FakeQueryParameters(params, tenant=self.tenant)
        handler = OCPAWSReportQueryHandler(query_params.mock_qp)
        query_output = handler.execute_query()
        data = query_output.get('data')
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get('total'))
        total = query_output.get('total')
        self.assertIsNotNone(total.get('cost'))

        aggregates = handler._mapper.report_type_map.get('aggregates')
        current_totals = self.get_totals_by_time_scope(aggregates,
                                                       self.this_month_filter)
        self.assertEqual(total.get('cost', {}).get('value'), current_totals.get('cost'))

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
        # '?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&group_by[service]=AmazonEC2'
        params = {'filter': {'resolution': 'monthly',
                             'time_scope_value': -1,
                             'time_scope_units': 'month'},
                  'group_by': {'service': ['AmazonEC2']}}
        query_params = FakeQueryParameters(params, tenant=self.tenant)
        handler = OCPAWSReportQueryHandler(query_params.mock_qp)
        query_output = handler.execute_query()
        data = query_output.get('data')
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get('total'))
        total = query_output.get('total')
        self.assertIsNotNone(total.get('cost'))

        aggregates = handler._mapper.report_type_map.get('aggregates')
        current_totals = self.get_totals_by_time_scope(aggregates,
                                                       self.this_month_filter)
        self.assertEqual(total.get('cost', {}).get('value'), current_totals.get('cost'))

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
        # '?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&group_by[service]=eC2'
        params = {'filter': {'resolution': 'monthly',
                             'time_scope_value': -1,
                             'time_scope_units': 'month'},
                  'group_by': {'service': ['eC2']}}
        query_params = FakeQueryParameters(params, tenant=self.tenant)
        handler = OCPAWSReportQueryHandler(query_params.mock_qp)
        query_output = handler.execute_query()
        data = query_output.get('data')
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get('total'))
        total = query_output.get('total')
        self.assertIsNotNone(total.get('cost'))

        aggregates = handler._mapper.report_type_map.get('aggregates')
        current_totals = self.get_totals_by_time_scope(aggregates,
                                                       self.this_month_filter)
        self.assertEqual(total.get('cost', {}).get('value'), current_totals.get('cost'))

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
        # '?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&group_by[account]=*'
        params = {'filter': {'resolution': 'monthly',
                             'time_scope_value': -1,
                             'time_scope_units': 'month'},
                  'group_by': {'account': ['*']}}
        query_params = FakeQueryParameters(params, tenant=self.tenant)
        handler = OCPAWSReportQueryHandler(query_params.mock_qp)
        query_output = handler.execute_query()
        data = query_output.get('data')
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get('total'))
        total = query_output.get('total')
        self.assertIsNotNone(total.get('cost'))

        aggregates = handler._mapper.report_type_map.get('aggregates')
        current_totals = self.get_totals_by_time_scope(aggregates,
                                                       self.this_month_filter)
        self.assertEqual(total.get('cost', {}).get('value'), current_totals.get('cost'))

        cmonth_str = DateHelper().this_month_start.strftime('%Y-%m')
        for data_item in data:
            month_val = data_item.get('date')
            month_data = data_item.get('accounts')
            self.assertEqual(month_val, cmonth_str)
            self.assertIsInstance(month_data, list)
            for month_item in month_data:
                self.assertIsInstance(month_item.get('values'), list)

    def test_execute_query_by_account_by_service(self):
        """Test execute_query for current month breakdown by account by service."""
        # '?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&group_by[account]=*&group_by[service]=*'
        params = {'filter': {'resolution': 'monthly',
                             'time_scope_value': -1,
                             'time_scope_units': 'month'},
                  'group_by': {'account': ['*'],
                               'service': ['*']}}
        query_params = FakeQueryParameters(params, tenant=self.tenant)
        handler = OCPAWSReportQueryHandler(query_params.mock_qp)
        query_output = handler.execute_query()
        data = query_output.get('data')
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get('total'))
        total = query_output.get('total')
        self.assertIsNotNone(total.get('cost'))

        aggregates = handler._mapper.report_type_map.get('aggregates')
        current_totals = self.get_totals_by_time_scope(aggregates,
                                                       self.this_month_filter)
        self.assertEqual(total.get('cost', {}).get('value'), current_totals.get('cost'))

        cmonth_str = DateHelper().this_month_start.strftime('%Y-%m')
        for data_item in data:
            month_val = data_item.get('date')
            month_data = data_item.get('accounts')
            self.assertEqual(month_val, cmonth_str)
            self.assertIsInstance(month_data, list)
            for month_item in month_data:
                self.assertIsInstance(month_item.get('services'), list)
