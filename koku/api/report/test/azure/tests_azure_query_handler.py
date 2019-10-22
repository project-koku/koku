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
"""Test the Azure Provider query handler."""

import random
from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID

from django.db.models import F, Sum
from tenant_schemas.utils import tenant_context

from api.iam.test.iam_test_case import IamTestCase
from api.query_filter import QueryFilter
from api.report.azure.query_handler import AzureReportQueryHandler
from api.report.test import FakeQueryParameters
from api.report.test.azure.helpers import (AZURE_SERVICES,
                                           AzureReportDataGenerator)
from api.tags.azure.queries import AzureTagQueryHandler
from api.utils import DateHelper
from reporting.models import (AzureCostEntryLineItemDailySummary,
                              AzureCostEntryProductService)


class AzureReportQueryHandlerTest(IamTestCase):
    """Azure report view test cases."""

    def setUp(self):
        """Set up the customer view tests."""
        super().setUp()
        self.dh = DateHelper()
        self.this_month_filter = {'usage_start__gte': self.dh.this_month_start}
        self.ten_day_filter = {'usage_start__gte': self.dh.n_days_ago(self.dh.today, 9)}
        self.thirty_day_filter = {'usage_start__gte': self.dh.n_days_ago(self.dh.today, 29)}
        self.last_month_filter = {'usage_start__gte': self.dh.last_month_start,
                                  'usage_start__lte': self.dh.last_month_end}
        self.generator = AzureReportDataGenerator(self.tenant)
        self.generator.add_data_to_tenant()

    def get_totals_by_time_scope(self, aggregates, filters=None):
        """Return the total aggregates for a time period."""
        if filters is None:
            filters = self.ten_day_filter
        with tenant_context(self.tenant):
            return AzureCostEntryLineItemDailySummary.objects\
                .filter(**filters)\
                .aggregate(**aggregates)

    def get_totals_costs_by_time_scope(self, aggregates, filters=None):
        """Return the total costs aggregates for a time period."""
        if filters is None:
            filters = self.this_month_filter
        with tenant_context(self.tenant):
            return AzureCostEntryLineItemDailySummary.objects\
                .filter(**filters)\
                .aggregate(**aggregates)

    def test_execute_sum_query(self):
        """Test that the sum query runs properly."""
        for _ in range(0, 3):
            AzureReportDataGenerator(self.tenant, config=self.generator.config).add_data_to_tenant()

        # '?'
        query_params = FakeQueryParameters({}, report_type='instance_type', tenant=self.tenant)
        handler = AzureReportQueryHandler(query_params.mock_qp)

        aggregates = handler._mapper.report_type_map.get('aggregates')
        filters = self.ten_day_filter
        for filt in handler._mapper.report_type_map.get('filter'):
            qf = QueryFilter(**filt)
            filters.update({qf.composed_query_string(): qf.parameter})
        current_totals = self.get_totals_costs_by_time_scope(aggregates, filters)
        query_output = handler.execute_query()

        self.assertIsNotNone(query_output.get('data'))
        self.assertIsNotNone(query_output.get('total'))
        total = query_output.get('total')

        # FIXME: usage doesn't have units yet. waiting on MSFT
        # self.assertEqual(total.get('usage', {}).get('value'), current_totals.get('usage'))
        self.assertEqual(total.get('usage', {}), current_totals.get('usage'))
        self.assertEqual(total.get('request', {}).get('value'), current_totals.get('request'))
        self.assertEqual(total.get('cost', {}).get('value'), current_totals.get('cost'))
        self.assertEqual(total.get('limit', {}).get('value'), current_totals.get('limit'))

    def test_execute_sum_query_costs(self):
        """Test that the sum query runs properly for the costs endpoint."""
        # '?
        query_params = FakeQueryParameters({}, tenant=self.tenant)
        handler = AzureReportQueryHandler(query_params.mock_qp)
        aggregates = handler._mapper.report_type_map.get('aggregates')
        current_totals = self.get_totals_costs_by_time_scope(aggregates, self.ten_day_filter)
        query_output = handler.execute_query()
        self.assertIsNotNone(query_output.get('data'))
        self.assertIsNotNone(query_output.get('total'))
        total = query_output.get('total')
        self.assertEqual(total.get('cost', {}).get('value'), current_totals.get('cost'))

    def test_execute_take_defaults(self):
        """Test execute_query for current month on daily breakdown."""
        # '?
        query_params = FakeQueryParameters({}, tenant=self.tenant)
        handler = AzureReportQueryHandler(query_params.mock_qp)
        query_output = handler.execute_query()
        self.assertIsNotNone(query_output.get('data'))
        self.assertIsNotNone(query_output.get('total'))
        total = query_output.get('total')
        self.assertIsNotNone(total.get('cost'))

    def test_execute_query_current_month_daily(self):
        """Test execute_query for current month on daily breakdown."""
        # '?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=daily'
        params = {'filter': {'resolution': 'daily',
                             'time_scope_value': -1,
                             'time_scope_units': 'month'}}
        query_params = FakeQueryParameters(params, tenant=self.tenant)
        handler = AzureReportQueryHandler(query_params.mock_qp)
        query_output = handler.execute_query()
        self.assertIsNotNone(query_output.get('data'))
        self.assertIsNotNone(query_output.get('total'))
        total = query_output.get('total')
        aggregates = handler._mapper.report_type_map.get('aggregates')
        current_totals = self.get_totals_costs_by_time_scope(aggregates, self.this_month_filter)
        self.assertIsNotNone(total.get('cost'))
        self.assertEqual(total.get('cost', {}).get('value'),
                         current_totals.get('cost'))

    def test_execute_query_current_month_monthly(self):
        """Test execute_query for current month on monthly breakdown."""
        # '?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=daily'
        params = {'filter': {'resolution': 'daily',
                             'time_scope_value': -1,
                             'time_scope_units': 'month'}}
        query_params = FakeQueryParameters(params, tenant=self.tenant)
        handler = AzureReportQueryHandler(query_params.mock_qp)
        query_output = handler.execute_query()
        self.assertIsNotNone(query_output.get('data'))
        self.assertIsNotNone(query_output.get('total'))
        total = query_output.get('total')
        aggregates = handler._mapper.report_type_map.get('aggregates')
        current_totals = self.get_totals_costs_by_time_scope(aggregates, self.this_month_filter)
        self.assertIsNotNone(total.get('cost'))
        self.assertEqual(total.get('cost', {}).get('value'),
                         current_totals.get('cost'))

    def test_execute_query_current_month_by_service(self):
        """Test execute_query for current month on monthly breakdown by service."""
        for _ in range(0, 3):
            AzureReportDataGenerator(self.tenant).add_data_to_tenant()

        valid_services = list(AZURE_SERVICES.keys())
        # '?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&group_by[service_name]=*'
        params = {'filter': {'resolution': 'monthly',
                             'time_scope_value': -1,
                             'time_scope_units': 'month'},
                  'group_by': {'service_name': ['*']}}
        query_params = FakeQueryParameters(params, tenant=self.tenant)
        handler = AzureReportQueryHandler(query_params.mock_qp)
        query_output = handler.execute_query()
        data = query_output.get('data')
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get('total'))
        total = query_output.get('total')
        aggregates = handler._mapper.report_type_map.get('aggregates')
        current_totals = self.get_totals_costs_by_time_scope(aggregates, self.this_month_filter)
        self.assertIsNotNone(total.get('cost'))
        self.assertEqual(total.get('cost', {}).get('value'),
                         current_totals.get('cost'))

        cmonth_str = self.dh.this_month_start.strftime('%Y-%m')
        for data_item in data:
            month_val = data_item.get('date')
            month_data = data_item.get('service_names')
            self.assertEqual(month_val, cmonth_str)
            self.assertIsInstance(month_data, list)
            for month_item in month_data:
                name = month_item.get('service_name')
                self.assertIn(name, valid_services)
                self.assertIsInstance(month_item.get('values'), list)

    def test_execute_query_by_filtered_service(self):
        """Test execute_query monthly breakdown by filtered service."""
        for _ in range(0, 3):
            config = self.generator.config
            generator = AzureReportDataGenerator(self.tenant,
                                                 current_month_only=True,
                                                 config=config)
            generator.add_data_to_tenant(fixed_fields=['subscription_guid',
                                                       'resource_location',
                                                       'tags',
                                                       'service_name'])

        valid_services = list(AZURE_SERVICES.keys())
        service = self.generator.config.service_name
        # '?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&group_by[service_name]=some_service'
        params = {'filter': {'resolution': 'monthly',
                             'time_scope_value': -1,
                             'time_scope_units': 'month'},
                  'group_by': {'service_name': [service]}}
        query_params = FakeQueryParameters(params, tenant=self.tenant)
        handler = AzureReportQueryHandler(query_params.mock_qp)
        query_output = handler.execute_query()
        data = query_output.get('data')
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get('total'))
        total = query_output.get('total')
        aggregates = handler._mapper.report_type_map.get('aggregates')
        filters = {**self.this_month_filter,
                   'service_name__icontains': service}
        for filt in handler._mapper.report_type_map.get('filter'):
            if filt:
                qf = QueryFilter(**filt)
                filters.update({qf.composed_query_string(): qf.parameter})
        current_totals = self.get_totals_costs_by_time_scope(aggregates, filters)
        self.assertIsNotNone(total.get('cost'))
        self.assertEqual(total.get('cost', {}).get('value'),
                         current_totals.get('cost'))

        cmonth_str = self.dh.this_month_start.strftime('%Y-%m')
        for data_item in data:
            month_val = data_item.get('date')
            month_data = data_item.get('service_names')
            self.assertEqual(month_val, cmonth_str)
            self.assertIsInstance(month_data, list)
            for month_item in month_data:
                name = month_item.get('service_name')
                self.assertIn(name, valid_services)
                self.assertIsInstance(month_item.get('values'), list)

    def test_query_by_partial_filtered_service(self):
        """Test execute_query monthly breakdown by filtered service."""
        for _ in range(0, 3):
            config = self.generator.config
            generator = AzureReportDataGenerator(self.tenant,
                                                 current_month_only=True,
                                                 config=config)
            generator.add_data_to_tenant(fixed_fields=['subscription_guid',
                                                       'resource_location',
                                                       'tags',
                                                       'service_name'])

        valid_services = list(AZURE_SERVICES.keys())
        selected_range = random.randrange(2, len(self.generator.config.service_name))
        service = self.generator.config.service_name[0: selected_range]
        # '?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&group_by[service_name]=some_service'
        params = {'filter': {'resolution': 'monthly',
                             'time_scope_value': -1,
                             'time_scope_units': 'month'},
                  'group_by': {'service_name': [service]}}
        query_params = FakeQueryParameters(params, tenant=self.tenant)
        handler = AzureReportQueryHandler(query_params.mock_qp)
        query_output = handler.execute_query()
        data = query_output.get('data')
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get('total'))
        total = query_output.get('total')
        aggregates = handler._mapper.report_type_map.get('aggregates')
        filters = {**self.this_month_filter, 'service_name__icontains': service}
        for filt in handler._mapper.report_type_map.get('filter'):
            if filt:
                qf = QueryFilter(**filt)
                filters.update({qf.composed_query_string(): qf.parameter})
        current_totals = self.get_totals_costs_by_time_scope(aggregates, filters)
        self.assertIsNotNone(total.get('cost'))
        self.assertEqual(total.get('cost', {}).get('value'),
                         current_totals.get('cost'))

        cmonth_str = self.dh.this_month_start.strftime('%Y-%m')
        for data_item in data:
            month_val = data_item.get('date')
            month_data = data_item.get('service_names')
            self.assertEqual(month_val, cmonth_str)
            self.assertIsInstance(month_data, list)
            for month_item in month_data:
                name = month_item.get('service_name')
                self.assertIn(name, valid_services)
                self.assertIsInstance(month_item.get('values'), list)

    def test_execute_query_current_month_by_subscription_guid(self):
        """Test execute_query for current month on monthly breakdown by subscription_guid."""
        # '?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&group_by[subscription_guid]=*'
        params = {'filter': {'resolution': 'monthly',
                             'time_scope_value': -1,
                             'time_scope_units': 'month'},
                  'group_by': {'subscription_guid': ['*']}}
        query_params = FakeQueryParameters(params, tenant=self.tenant)
        handler = AzureReportQueryHandler(query_params.mock_qp)
        query_output = handler.execute_query()
        data = query_output.get('data')
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get('total'))
        total = query_output.get('total')
        aggregates = handler._mapper.report_type_map.get('aggregates')
        current_totals = self.get_totals_costs_by_time_scope(aggregates, self.this_month_filter)
        self.assertIsNotNone(total.get('cost'))
        self.assertEqual(total.get('cost', {}).get('value'),
                         current_totals.get('cost'))

        cmonth_str = self.dh.this_month_start.strftime('%Y-%m')
        for data_item in data:
            month_val = data_item.get('date')
            month_data = data_item.get('subscription_guids')
            self.assertEqual(month_val, cmonth_str)
            self.assertIsInstance(month_data, list)
            for month_item in month_data:
                try:
                    UUID(month_item.get('subscription_guid'), version=4)
                except ValueError as exc:
                    self.fail(exc)
                self.assertIsInstance(month_item.get('values'), list)

    def test_execute_query_by_subscription_guid_by_service(self):
        """Test execute_query for current month breakdown by subscription_guid by service."""
        # '?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&group_by[subscription_guid]=*&group_by[service_name]=*'
        params = {'filter': {'resolution': 'monthly',
                             'time_scope_value': -1,
                             'time_scope_units': 'month'},
                  'group_by': {'subscription_guid': ['*'],
                               'service_name': ['*']}}
        query_params = FakeQueryParameters(params, tenant=self.tenant)
        handler = AzureReportQueryHandler(query_params.mock_qp)
        query_output = handler.execute_query()
        data = query_output.get('data')
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get('total'))
        total = query_output.get('total')
        aggregates = handler._mapper.report_type_map.get('aggregates')
        current_totals = self.get_totals_costs_by_time_scope(aggregates, self.this_month_filter)
        self.assertIsNotNone(total.get('cost'))
        self.assertEqual(total.get('cost', {}).get('value'),
                         current_totals.get('cost'))

        cmonth_str = DateHelper().this_month_start.strftime('%Y-%m')
        for data_item in data:
            month_val = data_item.get('date')
            month_data = data_item.get('subscription_guids')
            self.assertEqual(month_val, cmonth_str)
            self.assertIsInstance(month_data, list)
            for month_item in month_data:
                try:
                    UUID(month_item.get('subscription_guid'), version=4)
                except ValueError as exc:
                    self.fail(exc)
                self.assertIsInstance(month_item.get('service_names'), list)

    def test_execute_query_with_counts(self):
        """Test execute_query for with counts of unique resources."""
        with tenant_context(self.tenant):
            instance_type = AzureCostEntryProductService.objects\
                                                        .filter(service_name='Virtual Machines')\
                                                        .first()
        # '?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=daily&group_by[instance_type]=*'
        params = {'filter': {'resolution': 'daily',
                             'time_scope_value': -1,
                             'time_scope_units': 'month'},
                  'group_by': {'instance_type': ['*']}}
        query_params = FakeQueryParameters(params, report_type='instance_type', tenant=self.tenant)
        handler = AzureReportQueryHandler(query_params.mock_qp)
        query_output = handler.execute_query()
        data = query_output.get('data')
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get('total'))

        total = query_output.get('total')
        aggregates = handler._mapper.report_type_map.get('aggregates')
        current_totals = self.get_totals_costs_by_time_scope(aggregates, self.this_month_filter)
        self.assertIsNotNone(total.get('cost'))
        self.assertEqual(total.get('cost', {}).get('value'),
                         current_totals.get('cost'))

        for data_item in data:
            instance_types = data_item.get('instance_types')
            for it in instance_types:
                if it['instance_type'] == instance_type:
                    actual_count = it['values'][0].get('count', {}).get('value')
                    self.assertEqual(actual_count, 1)

    def test_execute_query_curr_month_by_subscription_guid_w_limit(self):
        """Test execute_query for current month on monthly breakdown by subscription_guid with limit."""
        for _ in range(3):
            AzureReportDataGenerator(self.tenant).add_data_to_tenant()

        # '?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&filter[limit]=2&group_by[subscription_guid]=*'
        params = {'filter': {'resolution': 'monthly',
                             'time_scope_value': -1,
                             'time_scope_units': 'month',
                             'limit': 2},
                  'group_by': {'subscription_guid': ['*']}}
        query_params = FakeQueryParameters(params, tenant=self.tenant)
        handler = AzureReportQueryHandler(query_params.mock_qp)
        query_output = handler.execute_query()
        data = query_output.get('data')
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get('total'))
        total = query_output.get('total')
        aggregates = handler._mapper.report_type_map.get('aggregates')
        current_totals = self.get_totals_costs_by_time_scope(aggregates, self.this_month_filter)
        self.assertIsNotNone(total.get('cost'))
        self.assertEqual(total.get('cost', {}).get('value'),
                         current_totals.get('cost'))

        cmonth_str = DateHelper().this_month_start.strftime('%Y-%m')
        for data_item in data:
            month_val = data_item.get('date')
            month_data = data_item.get('subscription_guids')
            self.assertEqual(month_val, cmonth_str)
            self.assertIsInstance(month_data, list)
            self.assertEqual(3, len(month_data))
            for month_item in month_data:
                self.assertIsInstance(month_item.get('subscription_guid'), str)
                self.assertIsInstance(month_item.get('values'), list)

    def test_execute_query_curr_month_by_subscription_guid_w_order(self):
        """Test execute_query for current month on monthly breakdown by subscription_guid with asc order."""
        for _ in range(3):
            AzureReportDataGenerator(self.tenant).add_data_to_tenant()

        # '?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&order_by[cost]=asc&group_by[subscription_guid]=*'
        params = {'filter': {'resolution': 'monthly',
                             'time_scope_value': -1,
                             'time_scope_units': 'month',
                             'limit': 3},
                  'group_by': {'subscription_guid': ['*']},
                  'order_by': {'cost': 'asc'}}
        query_params = FakeQueryParameters(params, tenant=self.tenant)
        handler = AzureReportQueryHandler(query_params.mock_qp)
        query_output = handler.execute_query()
        data = query_output.get('data')
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get('total'))
        total = query_output.get('total')
        aggregates = handler._mapper.report_type_map.get('aggregates')
        current_totals = self.get_totals_costs_by_time_scope(aggregates, self.this_month_filter)
        self.assertIsNotNone(total.get('cost'))
        self.assertEqual(total.get('cost', {}).get('value'),
                         current_totals.get('cost'))

        cmonth_str = self.dh.this_month_start.strftime('%Y-%m')
        for data_item in data:
            month_val = data_item.get('date')
            month_data = data_item.get('subscription_guids')
            self.assertEqual(month_val, cmonth_str)
            self.assertIsInstance(month_data, list)
            self.assertEqual(len(month_data), 4)
            current_total = 0
            for month_item in month_data:
                self.assertIsInstance(month_item.get('subscription_guid'), str)
                self.assertIsInstance(month_item.get('values'), list)
                self.assertIsNotNone(month_item.get('values')[0].get('cost', {}).get('value'))
                data_point_total = month_item.get('values')[0].get('cost', {}).get('value')
                self.assertLess(current_total, data_point_total)
                current_total = data_point_total

    def test_execute_query_curr_month_by_subscription_guid_w_order_by_subscription_guid(self):
        """Test execute_query for current month on monthly breakdown by subscription_guid with asc order."""
        for _ in range(3):
            AzureReportDataGenerator(self.tenant).add_data_to_tenant()

        # '?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&order_by[subscription_guid]=asc&group_by[subscription_guid]=*'
        params = {'filter': {'resolution': 'monthly',
                             'time_scope_value': -1,
                             'time_scope_units': 'month',
                             'limit': 3},
                  'group_by': {'subscription_guid': ['*']},
                  'order_by': {'subscription_guid': 'asc'}}
        query_params = FakeQueryParameters(params, tenant=self.tenant)
        handler = AzureReportQueryHandler(query_params.mock_qp)
        query_output = handler.execute_query()
        data = query_output.get('data')
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get('total'))
        total = query_output.get('total')
        aggregates = handler._mapper.report_type_map.get('aggregates')
        current_totals = self.get_totals_costs_by_time_scope(aggregates, self.this_month_filter)
        self.assertIsNotNone(total.get('cost'))
        self.assertEqual(total.get('cost', {}).get('value'),
                         current_totals.get('cost'))

        cmonth_str = self.dh.this_month_start.strftime('%Y-%m')
        for data_item in data:
            month_val = data_item.get('date')
            month_data = data_item.get('subscription_guids')
            self.assertEqual(month_val, cmonth_str)
            self.assertIsInstance(month_data, list)
            self.assertEqual(len(month_data), 4)
            current = '0'
            for month_item in month_data:
                self.assertIsInstance(month_item.get('subscription_guid'), str)
                self.assertIsInstance(month_item.get('values'), list)
                self.assertIsNotNone(month_item.get('values')[0].get('subscription_guid'))
                data_point = month_item.get('values')[0].get('subscription_guid')
                if data_point == '1 Other':
                    continue
                self.assertLess(current, data_point)
                current = data_point

    def test_execute_query_curr_month_by_resource_location(self):
        """Test execute_query for current month on monthly breakdown by resource_location."""
        # '?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&group_by[resource_location]=*'
        params = {'filter': {'resolution': 'monthly',
                             'time_scope_value': -1,
                             'time_scope_units': 'month'},
                  'group_by': {'resource_location': ['*']}}
        query_params = FakeQueryParameters(params, tenant=self.tenant)
        handler = AzureReportQueryHandler(query_params.mock_qp)
        query_output = handler.execute_query()
        data = query_output.get('data')
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get('total'))
        total = query_output.get('total')
        aggregates = handler._mapper.report_type_map.get('aggregates')
        current_totals = self.get_totals_costs_by_time_scope(aggregates, self.this_month_filter)
        self.assertIsNotNone(total.get('cost'))
        self.assertEqual(total.get('cost', {}).get('value'),
                         current_totals.get('cost'))

        cmonth_str = DateHelper().this_month_start.strftime('%Y-%m')
        for data_item in data:
            month_val = data_item.get('date')
            month_data = data_item.get('resource_locations')
            self.assertEqual(month_val, cmonth_str)
            self.assertIsInstance(month_data, list)
            self.assertEqual(1, len(month_data))
            for month_item in month_data:
                self.assertIsInstance(month_item.get('resource_location'), str)
                self.assertIsInstance(month_item.get('values'), list)
                self.assertIsNotNone(month_item.get('values')[0].get('cost'))

    def test_execute_query_curr_month_by_filtered_resource_location(self):
        """Test execute_query for current month on monthly breakdown by filtered resource_location."""
        location = self.generator.config.resource_location
        # '?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&group_by[resource_location]=some_location'
        params = {'filter': {'resolution': 'monthly',
                             'time_scope_value': -1,
                             'time_scope_units': 'month'},
                  'group_by': {'resource_location': [location]}}
        query_params = FakeQueryParameters(params, tenant=self.tenant)
        handler = AzureReportQueryHandler(query_params.mock_qp)
        query_output = handler.execute_query()
        data = query_output.get('data')
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get('total'))
        total = query_output.get('total')
        aggregates = handler._mapper.report_type_map.get('aggregates')
        current_totals = self.get_totals_costs_by_time_scope(aggregates, self.this_month_filter)
        self.assertIsNotNone(total.get('cost'))
        self.assertEqual(total.get('cost', {}).get('value'),
                         current_totals.get('cost'))

        cmonth_str = DateHelper().this_month_start.strftime('%Y-%m')
        for data_item in data:
            month_val = data_item.get('date')
            month_data = data_item.get('resource_locations')
            self.assertEqual(month_val, cmonth_str)
            self.assertIsInstance(month_data, list)
            for month_item in month_data:
                self.assertIsInstance(month_item.get('resource_location'), str)
                self.assertIsInstance(month_item.get('values'), list)
                self.assertIsNotNone(month_item.get('values')[0].get('cost'))

    def test_execute_query_current_month_filter_subscription_guid(self):
        """Test execute_query for current month on monthly filtered by subscription_guid."""
        # '?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&filter[subscription_guid]=11111111-2222-3333-4444-555555555555'
        params = {'filter': {'resolution': 'monthly',
                             'time_scope_value': -1,
                             'time_scope_units': 'month',
                             'subscription_guid': [self.generator.config.subscription_guid]}}
        query_params = FakeQueryParameters(params, tenant=self.tenant)
        handler = AzureReportQueryHandler(query_params.mock_qp)
        query_output = handler.execute_query()
        data = query_output.get('data')
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get('total'))
        total = query_output.get('total')
        aggregates = handler._mapper.report_type_map.get('aggregates')
        current_totals = self.get_totals_costs_by_time_scope(aggregates, self.this_month_filter)
        self.assertIsNotNone(total.get('cost'))
        self.assertEqual(total.get('cost', {}).get('value'),
                         current_totals.get('cost'))

        cmonth_str = self.dh.this_month_start.strftime('%Y-%m')
        for data_item in data:
            month_val = data_item.get('date')
            month_data = data_item.get('values')
            self.assertEqual(month_val, cmonth_str)
            self.assertIsInstance(month_data, list)

    def test_execute_query_current_month_filter_service(self):
        """Test execute_query for current month on monthly filtered by service."""
        for _ in range(0, 3):
            config = self.generator.config
            generator = AzureReportDataGenerator(self.tenant,
                                                 current_month_only=True,
                                                 config=config)
            generator.add_data_to_tenant(fixed_fields=['subscription_guid',
                                                       'resource_location',
                                                       'tags',
                                                       'service_name'])

        service = self.generator.config.service_name
        # '?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&filter[service]=some_service'
        params = {'filter': {'resolution': 'monthly',
                             'time_scope_value': -1,
                             'time_scope_units': 'month',
                             'service_name': [self.generator.config.service_name]}}
        query_params = FakeQueryParameters(params, tenant=self.tenant)
        handler = AzureReportQueryHandler(query_params.mock_qp)
        query_output = handler.execute_query()

        data = query_output.get('data')
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get('total'))

        total = query_output.get('total')
        aggregates = handler._mapper.report_type_map.get('aggregates')
        filters = {**self.this_month_filter, 'service_name__icontains': service}
        for filt in handler._mapper.report_type_map.get('filter'):
            if filt:
                qf = QueryFilter(**filt)
                filters.update({qf.composed_query_string(): qf.parameter})
        current_totals = self.get_totals_costs_by_time_scope(aggregates, filters)
        self.assertIsNotNone(total.get('cost'))
        self.assertEqual(total.get('cost', {}).get('value'),
                         current_totals.get('cost'))

        cmonth_str = self.dh.this_month_start.strftime('%Y-%m')
        for data_item in data:
            month_val = data_item.get('date')
            month_data = data_item.get('values')
            self.assertEqual(month_val, cmonth_str)
            self.assertIsInstance(month_data, list)

    def test_execute_query_current_month_filter_resource_location(self):
        """Test execute_query for current month on monthly filtered by resource_location."""
        # '?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&filter[resource_location]=some_location'
        params = {'filter': {'resolution': 'monthly',
                             'time_scope_value': -1,
                             'time_scope_units': 'month',
                             'resource_location': [self.generator.config.resource_location]}}
        query_params = FakeQueryParameters(params, tenant=self.tenant)
        handler = AzureReportQueryHandler(query_params.mock_qp)
        query_output = handler.execute_query()
        data = query_output.get('data')
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get('total'))
        total = query_output.get('total')
        aggregates = handler._mapper.report_type_map.get('aggregates')
        current_totals = self.get_totals_costs_by_time_scope(aggregates, self.this_month_filter)
        self.assertIsNotNone(total.get('cost'))
        self.assertEqual(total.get('cost', {}).get('value'),
                         current_totals.get('cost'))

        cmonth_str = DateHelper().this_month_start.strftime('%Y-%m')
        for data_item in data:
            month_val = data_item.get('date')
            month_data = data_item.get('values')
            self.assertEqual(month_val, cmonth_str)
            self.assertIsInstance(month_data, list)

    def test_execute_query_current_month_filter_resource_location_csv(self):
        """Test execute_query on monthly filtered by resource_location for csv."""
        # '?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&filter[resource_location]=some_location'
        params = {'filter': {'resolution': 'monthly',
                             'time_scope_value': -1,
                             'time_scope_units': 'month',
                             'resource_location': [self.generator.config.resource_location]}}
        query_params = FakeQueryParameters(params, accept_type='text/csv', tenant=self.tenant)
        handler = AzureReportQueryHandler(query_params.mock_qp)
        query_output = handler.execute_query()
        data = query_output.get('data')
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get('total'))
        total = query_output.get('total')
        aggregates = handler._mapper.report_type_map.get('aggregates')
        current_totals = self.get_totals_costs_by_time_scope(aggregates, self.this_month_filter)
        self.assertIsNotNone(total.get('cost'))
        self.assertEqual(total.get('cost', {}).get('value'),
                         current_totals.get('cost'))

        cmonth_str = DateHelper().this_month_start.strftime('%Y-%m')
        self.assertEqual(len(data), 1)
        for data_item in data:
            month_val = data_item.get('date')
            self.assertEqual(month_val, cmonth_str)

    def test_execute_query_curr_month_by_subscription_guid_w_limit_csv(self):
        """Test execute_query for current month on monthly by subscription_guid with limt as csv."""
        for _ in range(3):
            AzureReportDataGenerator(self.tenant).add_data_to_tenant()

        # '?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=daily&filter[resource_location]=some_location'
        params = {'filter': {'resolution': 'monthly',
                             'time_scope_value': -1,
                             'time_scope_units': 'month',
                             'limit': 2},
                  'group_by': {'subscription_guid': ['*']}}
        query_params = FakeQueryParameters(params, accept_type=['text/csv'], tenant=self.tenant)
        handler = AzureReportQueryHandler(query_params.mock_qp)
        query_output = handler.execute_query()
        data = query_output.get('data')

        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get('total'))
        total = query_output.get('total')
        aggregates = handler._mapper.report_type_map.get('aggregates')
        current_totals = self.get_totals_costs_by_time_scope(aggregates, self.this_month_filter)
        self.assertIsNotNone(total.get('cost'))
        self.assertEqual(total.get('cost', {}).get('value'),
                         current_totals.get('cost'))

        cmonth_str = self.dh.this_month_start.strftime('%Y-%m')
        self.assertEqual(len(data), 3)
        for data_item in data:
            month = data_item.get('date')
            self.assertEqual(month, cmonth_str)

    def test_execute_query_w_delta(self):
        """Test grouped by deltas."""
        for _ in range(0, 3):
            AzureReportDataGenerator(self.tenant).add_data_to_tenant()

        query_params = {'filter':
                        {'resolution': 'monthly',
                         'time_scope_value': -1,
                         'time_scope_units': 'month'},
                        'group_by': {'subscription_guid': ['*']},
                        'delta': 'cost'}
        # '?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&group_by[subscription_guid]=*&delta=cost'
        params = {'filter': {'resolution': 'monthly',
                             'time_scope_value': -1,
                             'time_scope_units': 'month'},
                  'group_by': {'subscription_guid': ['*']},
                  'delta': 'cost'}
        query_params = FakeQueryParameters(params, tenant=self.tenant)
        handler = AzureReportQueryHandler(query_params.mock_qp)
        # test the calculations
        query_output = handler.execute_query()
        data = query_output.get('data')
        self.assertIsNotNone(data)

        subs = data[0].get('subscription_guids', [{}])
        for sub in subs:
            current_total = Decimal(0)
            prev_total = Decimal(0)

            # fetch the expected sums from the DB.
            with tenant_context(self.tenant):
                curr = AzureCostEntryLineItemDailySummary.objects.filter(
                    usage_start__gte=self.dh.this_month_start,
                    usage_start__lte=self.dh.today,
                    subscription_guid=sub.get('subscription_guid')).aggregate(
                        value=Sum(F('pretax_cost') + F('markup_cost')))
                current_total = Decimal(curr.get('value'))

                prev = AzureCostEntryLineItemDailySummary.objects.filter(
                    usage_start__gte=self.dh.last_month_start,
                    usage_start__lte=self.dh.today.replace(month=self.dh.today.month - 1),
                    subscription_guid=sub.get('subscription_guid')).aggregate(
                        value=Sum(F('pretax_cost') + F('markup_cost')))
                prev_total = Decimal(prev.get('value'))

            expected_delta_value = Decimal(current_total - prev_total)
            expected_delta_percent = Decimal(
                (current_total - prev_total) / prev_total * 100
            )

            values = sub.get('values', [{}])[0]
            self.assertIn('delta_value', values)
            self.assertIn('delta_percent', values)
            self.assertEqual(values.get('delta_value'), expected_delta_value)
            self.assertEqual(values.get('delta_percent'), expected_delta_percent)

        current_total = Decimal(0)
        prev_total = Decimal(0)

        # fetch the expected sums from the DB.
        with tenant_context(self.tenant):
            curr = AzureCostEntryLineItemDailySummary.objects.filter(
                usage_start__gte=self.dh.this_month_start,
                usage_start__lte=self.dh.today).aggregate(value=Sum(F('pretax_cost') + F('markup_cost')))
            current_total = Decimal(curr.get('value'))

            prev = AzureCostEntryLineItemDailySummary.objects.filter(
                usage_start__gte=self.dh.last_month_start,
                usage_start__lte=self.dh.today.replace(month=self.dh.today.month - 1))\
                .aggregate(value=Sum(F('pretax_cost') + F('markup_cost')))
            prev_total = Decimal(prev.get('value'))

        expected_delta_value = Decimal(current_total - prev_total)
        expected_delta_percent = Decimal(
            (current_total - prev_total) / prev_total * 100
        )

        delta = query_output.get('delta')
        self.assertIsNotNone(delta.get('value'))
        self.assertIsNotNone(delta.get('percent'))
        self.assertEqual(delta.get('value'), expected_delta_value)
        self.assertEqual(delta.get('percent'), expected_delta_percent)

    def test_execute_query_w_delta_no_previous_data(self):
        """Test deltas with no previous data."""
        self.generator.remove_data_from_tenant()
        generator = AzureReportDataGenerator(self.tenant,
                                             current_month_only=True)
        generator.add_data_to_tenant()

        # ?filter[time_scope_value=-1&delta=cost]
        params = {'filter': {'time_scope_value': -1},
                  'delta': 'cost'}
        query_params = FakeQueryParameters(params, tenant=self.tenant)
        handler = AzureReportQueryHandler(query_params.mock_qp)
        query_output = handler.execute_query()
        data = query_output.get('data')
        self.assertIsNotNone(data)
        total_cost = query_output.get('total', {}).get('cost', {}).get('value')
        delta = query_output.get('delta')
        self.assertIsNotNone(delta.get('value'))
        self.assertIsNone(delta.get('percent'))
        self.assertEqual(delta.get('value'), total_cost)
        self.assertEqual(delta.get('percent'), None)

    def test_execute_query_orderby_delta(self):
        """Test execute_query with ordering by delta ascending."""
        for _ in range(0, 3):
            AzureReportDataGenerator(self.tenant).add_data_to_tenant()

        # '?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&order_by[delta]=asc&group_by[subscription_guid]=*&delta=cost'
        params = {'filter': {'resolution': 'monthly',
                             'time_scope_value': -1,
                             'time_scope_units': 'month'},
                  'order_by': {'delta': 'asc'},
                  'group_by': {'subscription_guid': ['*']},
                  'delta': 'cost'}
        query_params = FakeQueryParameters(params, tenant=self.tenant)
        handler = AzureReportQueryHandler(query_params.mock_qp)
        query_output = handler.execute_query()
        data = query_output.get('data')
        self.assertIsNotNone(data)

        cmonth_str = self.dh.this_month_start.strftime('%Y-%m')
        for data_item in data:
            month_val = data_item.get('date')
            month_data = data_item.get('subscription_guids')
            self.assertEqual(month_val, cmonth_str)
            self.assertIsInstance(month_data, list)
            for month_item in month_data:
                self.assertIsInstance(month_item.get('subscription_guid'), str)
                self.assertIsInstance(month_item.get('values'), list)
                self.assertIsInstance(month_item.get('values')[0].get('delta_percent'),
                                      Decimal)

    def test_calculate_total(self):
        """Test that calculated totals return correctly."""
        # '?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly'
        params = {'filter': {'resolution': 'monthly',
                             'time_scope_value': -1,
                             'time_scope_units': 'month'}}
        query_params = FakeQueryParameters(params, tenant=self.tenant)
        handler = AzureReportQueryHandler(query_params.mock_qp)
        expected_units = 'USD'
        with tenant_context(self.tenant):
            result = handler.calculate_total(**{'cost_units': expected_units})

        aggregates = handler._mapper.report_type_map.get('aggregates')
        current_totals = self.get_totals_costs_by_time_scope(aggregates, self.this_month_filter)
        self.assertEqual(result.get('cost', {}).get('value'),
                         current_totals.get('cost'))
        self.assertEqual(result.get('cost', {}).get('units'), expected_units)

    def test_percent_delta(self):
        """Test _percent_delta() utility method."""
        # '?'
        query_params = FakeQueryParameters({})
        handler = AzureReportQueryHandler(query_params.mock_qp)
        self.assertEqual(handler._percent_delta(10, 5), 100)

    def test_rank_list_by_subscription_guid(self):
        """Test rank list limit with subscription_guid alias."""
        query_params = {'filter':
                        {'resolution': 'monthly', 'time_scope_value': -1,
                         'time_scope_units': 'month', 'limit': 2},
                        'group_by': {'subscription_guid': ['*']}}
        # '?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly'
        params = {'filter': {'resolution': 'monthly',
                             'time_scope_value': -1,
                             'time_scope_units': 'month',
                             'limit': 2},
                  'group_by': {'subscription_guid': ['*']}}
        query_params = FakeQueryParameters(params, tenant=self.tenant)
        handler = AzureReportQueryHandler(query_params.mock_qp)
        data_list = [
            {'subscription_guid': '1', 'total': 5, 'rank': 1},
            {'subscription_guid': '2', 'total': 4, 'rank': 2},
            {'subscription_guid': '3', 'total': 3, 'rank': 3},
            {'subscription_guid': '4', 'total': 2, 'rank': 4}
        ]
        expected = [
            {'subscription_guid': '1', 'total': 5, 'rank': 1},
            {'subscription_guid': '2', 'total': 4, 'rank': 2},
            {'subscription_guid': '2 Others', 'cost': 0, 'markup_cost': 0,
             'derived_cost': 0, 'infrastructure_cost': 0, 'total': 5, 'rank': 3}
        ]
        ranked_list = handler._ranked_list(data_list)
        self.assertEqual(ranked_list, expected)

    def test_rank_list_by_service_name(self):
        """Test rank list limit with service_name grouping."""
        # '?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&filter[limit]=2&group_by[service_name]=*'
        params = {'filter': {'resolution': 'monthly',
                             'time_scope_value': -1,
                             'time_scope_units': 'month',
                             'limit': 2},
                  'group_by': {'service_name': ['*']}}
        query_params = FakeQueryParameters(params, tenant=self.tenant)
        handler = AzureReportQueryHandler(query_params.mock_qp)
        data_list = [
            {'service_name': '1', 'total': 5, 'rank': 1},
            {'service_name': '2', 'total': 4, 'rank': 2},
            {'service_name': '3', 'total': 3, 'rank': 3},
            {'service_name': '4', 'total': 2, 'rank': 4}
        ]
        expected = [
            {'service_name': '1', 'total': 5, 'rank': 1},
            {'service_name': '2', 'total': 4, 'rank': 2},
            {'cost': 0, 'derived_cost': 0, 'infrastructure_cost': 0,
             'markup_cost': 0, 'service_name': '2 Others', 'total': 5, 'rank': 3}
        ]
        ranked_list = handler._ranked_list(data_list)
        self.assertEqual(ranked_list, expected)

    def test_rank_list_with_offset(self):
        # '?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&filter[limit]=2&filter[offset]=2&group_by[service_name]=*'
        """Test rank list limit and offset with subscription_guid alias."""
        params = {'filter': {'resolution': 'monthly',
                             'time_scope_value': -1,
                             'time_scope_units': 'month',
                             'limit': 1,
                             'offset': 1},
                  'group_by': {'subscription_guid': ['*']}}
        query_params = FakeQueryParameters(params, tenant=self.tenant)
        handler = AzureReportQueryHandler(query_params.mock_qp)
        data_list = [
            {'subscription_guid': '1', 'total': 5, 'rank': 1},
            {'subscription_guid': '2', 'total': 4, 'rank': 2},
            {'subscription_guid': '3', 'total': 3, 'rank': 3},
            {'subscription_guid': '4', 'total': 2, 'rank': 4}
        ]
        expected = [
            {'subscription_guid': '2', 'total': 4, 'rank': 2},
        ]
        ranked_list = handler._ranked_list(data_list)
        self.assertEqual(ranked_list, expected)

    def test_query_costs_with_totals(self):
        """Test execute_query() - costs with totals.

        Query for instance_types, validating that cost totals are present.

        """
        for _ in range(0, 3):
            AzureReportDataGenerator(self.tenant).add_data_to_tenant()

        # '?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly'
        params = {'filter': {'resolution': 'monthly',
                             'time_scope_value': -1,
                             'time_scope_units': 'month'},
                  'group_by': {'subscription_guid': ['*']}}
        query_params = FakeQueryParameters(params, tenant=self.tenant)
        handler = AzureReportQueryHandler(query_params.mock_qp)
        query_output = handler.execute_query()
        data = query_output.get('data')
        self.assertIsNotNone(data)

        for data_item in data:
            subscription_guids = data_item.get('subscription_guids')
            for subscription_guid in subscription_guids:
                self.assertIsNotNone(subscription_guid.get('values'))
                self.assertGreater(len(subscription_guid.get('values')), 0)
                for value in subscription_guid.get('values'):
                    self.assertIsInstance(value.get('cost', {}).get('value'), Decimal)
                    self.assertGreater(value.get('cost', {}).get('value'), Decimal(0))

    def test_query_instance_types_with_totals(self):
        """Test execute_query() - instance types with totals.

        Query for instance_types, validating that cost totals are present.

        """
        for _ in range(0, 3):
            AzureReportDataGenerator(self.tenant).add_data_to_tenant()

        # '?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&group_by[instance_type]=*'
        params = {'filter': {'resolution': 'monthly',
                             'time_scope_value': -1,
                             'time_scope_units': 'month'},
                  'group_by': {'instance_type': ['*']}}
        query_params = FakeQueryParameters(params, report_type='instance_type', tenant=self.tenant)
        handler = AzureReportQueryHandler(query_params.mock_qp)
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
                    self.assertGreaterEqual(value.get('cost',
                                                      {}).get('value').quantize(
                        Decimal('.0001'), ROUND_HALF_UP), Decimal(0))
                    # FIXME: usage doesn't have units yet. waiting on MSFT
                    # self.assertIsInstance(value.get('usage', {}).get('value'), Decimal)
                    # self.assertGreater(value.get('usage', {}).get('value'), Decimal(0))
                    self.assertIsInstance(value.get('usage', {}), dict)
                    self.assertGreaterEqual(value.get('usage', {}).get('value', {}).quantize(
                        Decimal('.0001'), ROUND_HALF_UP), Decimal(0))

    def test_query_storage_with_totals(self):
        """Test execute_query() - storage with totals.

        Query for storage, validating that cost totals are present.

        """
        for _ in range(0, 3):
            AzureReportDataGenerator(self.tenant).add_data_to_tenant()

        # '?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&group_by[service_name]=*'
        params = {'filter': {'resolution': 'monthly',
                             'time_scope_value': -1,
                             'time_scope_units': 'month'},
                  'group_by': {'service_name': ['*']}}
        query_params = FakeQueryParameters(params, report_type='storage', tenant=self.tenant)
        handler = AzureReportQueryHandler(query_params.mock_qp)
        query_output = handler.execute_query()
        data = query_output.get('data')
        self.assertIsNotNone(data)

        for data_item in data:
            services = data_item.get('service_names')
            self.assertIsNotNone(services)
            for srv in services:
                self.assertIsNotNone(srv.get('values'))
                self.assertGreater(len(srv.get('values')), 0)
                for value in srv.get('values'):
                    self.assertIsInstance(value.get('cost', {}).get('value'), Decimal)
                    self.assertGreater(value.get('cost', {}).get('value'), Decimal(0))
                    # FIXME: usage doesn't have units yet. waiting on MSFT
                    # self.assertIsInstance(value.get('usage', {}).get('value'), Decimal)
                    # self.assertGreater(value.get('usage', {}).get('value'), Decimal(0))
                    self.assertIsInstance(value.get('usage', {}), dict)
                    self.assertGreater(value.get('usage', {}).get('value', {}), Decimal(0))

    def test_order_by(self):
        """Test that order_by returns properly sorted data."""
        # '?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly'
        params = {'filter': {'resolution': 'monthly',
                             'time_scope_value': -1,
                             'time_scope_units': 'month'}}
        query_params = FakeQueryParameters(params, tenant=self.tenant)
        handler = AzureReportQueryHandler(query_params.mock_qp)

        unordered_data = [{'date': self.dh.today,
                           'delta_percent': 8,
                           'total': 6.2,
                           'rank': 2},
                          {'date': self.dh.yesterday,
                           'delta_percent': 4,
                           'total': 2.2,
                           'rank': 1},
                          {'date': self.dh.today,
                           'delta_percent': 7,
                           'total': 8.2,
                           'rank': 1},
                          {'date': self.dh.yesterday,
                           'delta_percent': 4,
                           'total': 2.2,
                           'rank': 2}]

        order_fields = ['date', 'rank']
        expected = [{'date': self.dh.yesterday,
                     'delta_percent': 4,
                     'total': 2.2,
                     'rank': 1},
                    {'date': self.dh.yesterday,
                     'delta_percent': 4,
                     'total': 2.2,
                     'rank': 2},
                    {'date': self.dh.today,
                     'delta_percent': 7,
                     'total': 8.2,
                     'rank': 1},
                    {'date': self.dh.today,
                     'delta_percent': 8,
                     'total': 6.2,
                     'rank': 2}]

        ordered_data = handler.order_by(unordered_data, order_fields)
        self.assertEqual(ordered_data, expected)

        order_fields = ['date', '-delta']
        expected = [{'date': self.dh.yesterday,
                     'delta_percent': 4,
                     'total': 2.2,
                     'rank': 1},
                    {'date': self.dh.yesterday,
                     'delta_percent': 4,
                     'total': 2.2,
                     'rank': 2},
                    {'date': self.dh.today,
                     'delta_percent': 8,
                     'total': 6.2,
                     'rank': 2},
                    {'date': self.dh.today,
                     'delta_percent': 7,
                     'total': 8.2,
                     'rank': 1}]

        ordered_data = handler.order_by(unordered_data, order_fields)
        self.assertEqual(ordered_data, expected)

    def test_order_by_null_values(self):
        """Test that order_by returns properly sorted data with null data."""
        # '?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly'
        params = {'filter': {'resolution': 'monthly',
                             'time_scope_value': -1,
                             'time_scope_units': 'month'}}
        query_params = FakeQueryParameters(params, tenant=self.tenant)
        handler = AzureReportQueryHandler(query_params.mock_qp)

        unordered_data = [{'node': None,
                           'cluster': 'cluster-1'},
                          {'node': 'alpha',
                           'cluster': 'cluster-2'},
                          {'node': 'bravo',
                           'cluster': 'cluster-3'},
                          {'node': 'oscar',
                           'cluster': 'cluster-4'}]

        order_fields = ['node']
        expected = [{'node': 'alpha',
                     'cluster': 'cluster-2'},
                    {'node': 'bravo',
                     'cluster': 'cluster-3'},
                    {'node': 'no-node',
                     'cluster': 'cluster-1'},
                    {'node': 'oscar',
                     'cluster': 'cluster-4'}]
        ordered_data = handler.order_by(unordered_data, order_fields)
        self.assertEqual(ordered_data, expected)

    def test_execute_query_with_tag_filter(self):
        """Test that data is filtered by tag key."""
        # '?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly'
        params = {'filter': {'resolution': 'monthly',
                             'time_scope_value': -1,
                             'time_scope_units': 'month'}}
        query_params = FakeQueryParameters(params, tenant=self.tenant)
        handler = AzureTagQueryHandler(query_params.mock_qp)
        tag_keys = handler.get_tag_keys()
        filter_key = tag_keys[0]
        tag_keys = ['tag:' + tag for tag in tag_keys]

        with tenant_context(self.tenant):
            labels = AzureCostEntryLineItemDailySummary.objects\
                .filter(usage_start__gte=self.dh.this_month_start)\
                .filter(tags__has_key=filter_key)\
                .values(*['tags'])\
                .all()
            label_of_interest = labels[0]
            filter_value = label_of_interest.get('tags', {}).get(filter_key)

            totals = AzureCostEntryLineItemDailySummary.objects\
                .filter(usage_start__gte=self.dh.this_month_start)\
                .filter(**{f'tags__{filter_key}': filter_value})\
                .aggregate(**{'cost': Sum(F('pretax_cost') + F('markup_cost'))})

        # '?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&filter[tag:some_tag]=some_key'
        params = {'filter': {'resolution': 'monthly',
                             'time_scope_value': -1,
                             'time_scope_units': 'month',
                             f'tag:{filter_key}': [filter_value]}}
        query_params = FakeQueryParameters(params, tag_keys=tag_keys, tenant=self.tenant)
        handler = AzureReportQueryHandler(query_params.mock_qp)

        data = handler.execute_query()
        data_totals = data.get('total', {})
        for key in totals:
            result = data_totals.get(key, {}).get('value')
            self.assertAlmostEqual(result, totals[key], 6)

    def test_execute_query_with_wildcard_tag_filter(self):
        """Test that data is filtered to include entries with tag key."""
        # Pick tags for the same month we query on later
        # '?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly'
        params = {'filter': {'resolution': 'monthly',
                             'time_scope_value': -1,
                             'time_scope_units': 'month'}}
        query_params = FakeQueryParameters(params, tenant=self.tenant)
        handler = AzureTagQueryHandler(query_params.mock_qp)
        tag_keys = handler.get_tag_keys()
        filter_key = tag_keys[0]
        tag_keys = ['tag:' + tag for tag in tag_keys]

        with tenant_context(self.tenant):
            totals = AzureCostEntryLineItemDailySummary.objects\
                .filter(usage_start__gte=self.dh.this_month_start)\
                .filter(**{'tags__has_key': filter_key})\
                .aggregate(
                    **{'cost': Sum(F('pretax_cost') + F('markup_cost'))})

        # '?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&filter[tag:some_tag]=*'
        params = {'filter': {'resolution': 'monthly',
                             'time_scope_value': -1,
                             'time_scope_units': 'month',
                             f'tag:{filter_key}': ['*']}}
        query_params = FakeQueryParameters(params, tag_keys=tag_keys, tenant=self.tenant)
        handler = AzureReportQueryHandler(query_params.mock_qp)

        data = handler.execute_query()
        data_totals = data.get('total', {})
        for key in totals:
            result = data_totals.get(key, {}).get('value')
            self.assertAlmostEqual(result, totals[key], 6)

    def test_execute_query_with_tag_group_by(self):
        """Test that data is grouped by tag key."""
        # Pick tags for the same month we query on later
        params = {'filter': {'resolution': 'monthly',
                             'time_scope_value': -1,
                             'time_scope_units': 'month'}}
        query_params = FakeQueryParameters(params, tenant=self.tenant)
        handler = AzureTagQueryHandler(query_params.mock_qp)
        tag_keys = handler.get_tag_keys()
        group_by_key = tag_keys[0]
        tag_keys = ['tag:' + tag for tag in tag_keys]

        with tenant_context(self.tenant):
            totals = AzureCostEntryLineItemDailySummary.objects\
                .filter(usage_start__gte=self.dh.this_month_start)\
                .filter(**{'tags__has_key': group_by_key})\
                .aggregate(
                    **{'cost': Sum(F('pretax_cost') + F('markup_cost'))})

        # '?filter[time_scope_units]=month&filter[time_scope_value]=-1&filter[resolution]=monthly&group_by[tag:some_tag]=*'
        params = {'filter': {'resolution': 'monthly',
                             'time_scope_value': -1,
                             'time_scope_units': 'month'},
                  'group_by': {f'tag:{group_by_key}': ['*']}}
        query_params = FakeQueryParameters(params, tag_keys=tag_keys, tenant=self.tenant)
        handler = AzureReportQueryHandler(query_params.mock_qp)

        data = handler.execute_query()
        data_totals = data.get('total', {})
        data = data.get('data', [])
        expected_keys = ['date', group_by_key + 's']
        for entry in data:
            self.assertEqual(list(entry.keys()), expected_keys)
        for key in totals:
            result = data_totals.get(key, {}).get('value')
            self.assertAlmostEqual(result, totals[key], 6)
