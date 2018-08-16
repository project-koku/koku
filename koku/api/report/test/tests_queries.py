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
from decimal import Decimal

from django.db.models import Value
from django.db.models.functions import Concat
from django.test import TestCase
from tenant_schemas.utils import tenant_context

from api.iam.test.iam_test_case import IamTestCase
from api.models import Customer, Tenant
from api.report.queries import ReportQueryHandler
from api.utils import DateHelper
from reporting.models import (AWSCostEntry,
                              AWSCostEntryBill,
                              AWSCostEntryLineItem,
                              AWSCostEntryPricing,
                              AWSCostEntryProduct)


class ReportQueryUtilsTest(TestCase):
    """Test the report query class functions."""

    def test_has_wildcard_yes(self):
        """Test a list has a wildcard."""
        result = ReportQueryHandler.has_wildcard(['abc', '*'])
        self.assertTrue(result)

    def test_has_wildcard_no(self):
        """Test a list doesn't have a wildcard."""
        result = ReportQueryHandler.has_wildcard(['abc', 'def'])
        self.assertFalse(result)

    def test_has_wildcard_none(self):
        """Test an empty list doesn't have a wildcard."""
        result = ReportQueryHandler.has_wildcard([])
        self.assertFalse(result)

    def test_group_data_by_list(self):
        """Test the _group_data_by_list method."""
        group_by = ['account', 'service']
        data = [{'account': 'a1', 'service': 's1', 'units': 'USD', 'total': 4},
                {'account': 'a1', 'service': 's2', 'units': 'USD', 'total': 5},
                {'account': 'a2', 'service': 's1', 'units': 'USD', 'total': 6},
                {'account': 'a2', 'service': 's2', 'units': 'USD', 'total': 5},
                {'account': 'a1', 'service': 's3', 'units': 'USD', 'total': 5}]
        out_data = ReportQueryHandler._group_data_by_list(group_by, 0, data)
        expected = {'a1':
                    {'s1': [{'account': 'a1', 'service': 's1', 'units': 'USD', 'total': 4}],
                     's2': [{'account': 'a1', 'service': 's2', 'units': 'USD', 'total': 5}],
                        's3': [
                        {'account': 'a1', 'service': 's3', 'units': 'USD', 'total': 5}]},
                    'a2':
                    {'s1': [{'account': 'a2', 'service': 's1', 'units': 'USD', 'total': 6}],
                        's2': [{'account': 'a2', 'service': 's2', 'units': 'USD', 'total': 5}]}}
        self.assertEqual(expected, out_data)

    def test_group_data_by_list_missing_units(self):
        """Test the _group_data_by_list method when duplicates occur due to missing units."""
        group_by = ['instance_type']
        data = [{'date': '2018-07-22', 'units': '', 'instance_type': 't2.micro', 'total': 30.0, 'count': 0},
                {'date': '2018-07-22', 'units': 'Hrs', 'instance_type': 't2.small', 'total': 17.0, 'count': 0},
                {'date': '2018-07-22', 'units': 'Hrs', 'instance_type': 't2.micro', 'total': 1.0, 'count': 0}]
        out_data = ReportQueryHandler._group_data_by_list(group_by, 0, data)
        print(out_data)
        expected = {'t2.micro': [
            {'date': '2018-07-22', 'units': 'Hrs', 'instance_type': 't2.micro', 'total': 1.0, 'count': 0},
            {'date': '2018-07-22', 'units': '', 'instance_type': 't2.micro', 'total': 30.0, 'count': 0}],
            't2.small': [
                {'date': '2018-07-22', 'units': 'Hrs', 'instance_type': 't2.small', 'total': 17.0, 'count': 0}]}
        self.assertEqual(expected, out_data)


class ReportQueryTest(IamTestCase):
    """Tests the report queries."""

    current_month_total = Decimal('0')

    def setUp(self):
        """Set up the customer view tests."""
        super().setUp()
        self.create_service_admin()
        customer = self.customer_data[0]
        response = self.create_customer(customer)
        self.assertEqual(response.status_code, 201)
        customer_json = response.json()
        customer_uuid = customer_json.get('uuid')
        customer_obj = Customer.objects.filter(uuid=customer_uuid).get()
        self.current_month_total = Decimal('0')
        self.tenant = Tenant(schema_name=customer_obj.schema_name)
        self.tenant.save()
        self.add_data_to_tenant()

    def create_hourly_instance_usage(self, payer_account_id, bill,
                                     ce_pricing, ce_product, rate,
                                     cost, start, end):
        """Create hourly instance usage."""
        cost_entry = AWSCostEntry(interval_start=start,
                                  interval_end=end,
                                  bill=bill)
        cost_entry.save()
        line_item = AWSCostEntryLineItem(invoice_id=self.fake.sha1(raw_output=False),
                                         line_item_type='Usage',
                                         usage_account_id=payer_account_id,
                                         usage_start=start,
                                         usage_end=end,
                                         product_code='AmazonEC2',
                                         usage_type='BoxUsage:c4.xlarge',
                                         operation='RunInstances',
                                         availability_zone='us-east-1a',
                                         resource_id='i-{}'.format(self.fake.ean8()),
                                         usage_amount=1,
                                         currency_code='USD',
                                         unblended_rate=rate,
                                         unblended_cost=cost,
                                         blended_rate=rate,
                                         blended_cost=cost,
                                         cost_entry=cost_entry,
                                         cost_entry_bill=bill,
                                         cost_entry_product=ce_product,
                                         cost_entry_pricing=ce_pricing)
        line_item.save()

    def _create_product(self,
                        name='Amazon Elastic Compute Cloud',
                        family='Compute Instance',
                        code='AmazonEC2',
                        region='US East (N. Virginia)',
                        instance_type='c4.xlarge',
                        memory=7.5,
                        vcpu=4):
        """Create a AWSCostEntryProduct."""
        # pylint: disable=no-member
        sku = self.fake.pystr(min_chars=12, max_chars=12).upper()
        ce_product = AWSCostEntryProduct(sku=sku,
                                         product_name=name,
                                         product_family=family,
                                         service_code=code,
                                         region=region,
                                         instance_type=instance_type,
                                         memory=memory,
                                         vcpu=vcpu)
        ce_product.save()
        return ce_product

    def _create_bill(self, account, bill_start, bill_end,
                     bill_type='Anniversary'):
        """Create an AWSCostEntryBill."""
        bill = AWSCostEntryBill(bill_type='Anniversary',
                                payer_account_id=account,
                                billing_period_start=bill_start,
                                billing_period_end=bill_end)
        bill.save()
        return bill

    def _create_pricing(self, term='OnDemand', unit='Hrs'):
        """Create an AWSCostEntryPricing."""
        ce_pricing = AWSCostEntryPricing(term=term, unit=unit)
        ce_pricing.save()
        return ce_pricing

    def add_data_to_tenant(self, rate=Decimal('0.199'), amount=1,
                           bill_start=DateHelper().this_month_start,
                           bill_end=DateHelper().this_month_end,
                           data_start=DateHelper().yesterday,
                           data_end=DateHelper().today):
        """Populate tenant with data."""
        payer_account_id = self.fake.ean(length=13)  # pylint: disable=no-member
        self.payer_account_id = payer_account_id

        with tenant_context(self.tenant):
            bill = AWSCostEntryBill(bill_type='Anniversary',
                                    payer_account_id=payer_account_id,
                                    billing_period_start=bill_start,
                                    billing_period_end=bill_end)
            bill.save()
            cost = rate * amount
            bill = self._create_bill(payer_account_id, bill_start, bill_end)
            ce_product = self._create_product()
            ce_pricing = self._create_pricing(cost, rate)

            current = data_start
            while current < data_end:
                if current.month == DateHelper().this_month_start.month:
                    self.current_month_total += cost
                end_hour = current + DateHelper().one_hour
                self.create_hourly_instance_usage(payer_account_id, bill,
                                                  ce_pricing, ce_product, rate,
                                                  cost, current, end_hour)
                current = end_hour

    def test_has_filter_no_filter(self):
        """Test the has_filter method with no filter in the query params."""
        handler = ReportQueryHandler({}, '', self.tenant, 'unblended_cost',
                                     'currency_code')
        self.assertFalse(handler.check_query_params('filter', 'time_scope_value'))

    def test_has_filter_with_filter(self):
        """Test the has_filter method with filter in the query params."""
        query_params = {'filter':
                        {'resolution': 'monthly', 'time_scope_value': -1}}
        handler = ReportQueryHandler(query_params, '', self.tenant, 'unblended_cost',
                                     'currency_code')
        self.assertIsNotNone(handler.check_query_params('filter', 'time_scope_value'))

    def test_get_group_by_no_data(self):
        """Test the get_group_by_data method with no data in the query params."""
        handler = ReportQueryHandler({}, '', self.tenant, 'unblended_cost',
                                     'currency_code')
        self.assertFalse(handler.get_query_param_data('group_by', 'service'))

    def test_get_group_by_with_service_list(self):
        """Test the get_group_by_data method with no data in the query params."""
        expected = ['a', 'b']
        query_string = '?group_by[service]=a&group_by[service]=b'
        handler = ReportQueryHandler({'group_by':
                                      {'service': expected}},
                                     query_string,
                                     self.tenant,
                                     'unblended_cost',
                                     'currency_code')
        service = handler.get_query_param_data('group_by', 'service')
        self.assertEqual(expected, service)

    def test_get_resolution_empty_default(self):
        """Test get_resolution returns default when query params are empty."""
        query_params = {}
        handler = ReportQueryHandler(query_params, '', self.tenant, 'unblended_cost',
                                     'currency_code')
        self.assertEqual(handler.get_resolution(), 'daily')
        self.assertEqual(handler.get_resolution(), 'daily')

    def test_get_resolution_empty_month_time_scope(self):
        """Test get_resolution returns default when time_scope is month."""
        query_params = {'filter': {'time_scope_value': -1}}
        handler = ReportQueryHandler(query_params, '', self.tenant, 'unblended_cost',
                                     'currency_code')
        self.assertEqual(handler.get_resolution(), 'monthly')

    def test_get_resolution_empty_day_time_scope(self):
        """Test get_resolution returns default when time_scope is month."""
        query_params = {'filter': {'time_scope_value': -10}}
        handler = ReportQueryHandler(query_params, '', self.tenant, 'unblended_cost',
                                     'currency_code')
        self.assertEqual(handler.get_resolution(), 'daily')

    def test_get_time_scope_units_empty_default(self):
        """Test get_time_scope_units returns default when query params are empty."""
        query_params = {}
        handler = ReportQueryHandler(query_params, '', self.tenant, 'unblended_cost',
                                     'currency_code')
        self.assertEqual(handler.get_time_scope_units(), 'day')
        self.assertEqual(handler.get_time_scope_units(), 'day')

    def test_get_time_scope_units_empty_month_time_scope(self):
        """Test get_time_scope_units returns default when time_scope is month."""
        query_params = {'filter': {'time_scope_value': -1}}
        handler = ReportQueryHandler(query_params, '', self.tenant, 'unblended_cost',
                                     'currency_code')
        self.assertEqual(handler.get_time_scope_units(), 'month')

    def test_get_time_scope_units_empty_day_time_scope(self):
        """Test get_time_scope_units returns default when time_scope is month."""
        query_params = {'filter': {'time_scope_value': -10}}
        handler = ReportQueryHandler(query_params, '', self.tenant, 'unblended_cost',
                                     'currency_code')
        self.assertEqual(handler.get_time_scope_units(), 'day')

    def test_get_time_scope_value_empty_default(self):
        """Test get_time_scope_value returns default when query params are empty."""
        query_params = {}
        handler = ReportQueryHandler(query_params, '', self.tenant, 'unblended_cost',
                                     'currency_code')
        self.assertEqual(handler.get_time_scope_value(), -10)
        self.assertEqual(handler.get_time_scope_value(), -10)

    def test_get_time_scope_value_empty_month_time_scope(self):
        """Test get_time_scope_value returns default when time_scope is month."""
        query_params = {'filter': {'time_scope_units': 'month'}}
        handler = ReportQueryHandler(query_params, '', self.tenant, 'unblended_cost',
                                     'currency_code')
        self.assertEqual(handler.get_time_scope_value(), -1)

    def test_get_time_scope_value_empty_day_time_scope(self):
        """Test get_time_scope_value returns default when time_scope is month."""
        query_params = {'filter': {'time_scope_units': 'day'}}
        handler = ReportQueryHandler(query_params, '', self.tenant, 'unblended_cost',
                                     'currency_code')
        self.assertEqual(handler.get_time_scope_value(), -10)

    def test_get_time_frame_filter_current_month(self):
        """Test _get_time_frame_filter for current month."""
        query_params = {'filter':
                        {'resolution': 'daily',
                         'time_scope_value': -1,
                         'time_scope_units': 'month'}}
        handler = ReportQueryHandler(query_params, '', self.tenant, 'unblended_cost',
                                     'currency_code')
        start = handler.start_datetime
        end = handler.end_datetime
        interval = handler.time_interval
        self.assertEqual(start, DateHelper().this_month_start)
        self.assertEqual(end, DateHelper().this_month_end)
        self.assertIsInstance(interval, list)
        self.assertTrue(len(interval) >= 28)

    def test_get_time_frame_filter_previous_month(self):
        """Test _get_time_frame_filter for previous month."""
        query_params = {'filter':
                        {'resolution': 'daily',
                         'time_scope_value': -2,
                         'time_scope_units': 'month'}}
        handler = ReportQueryHandler(query_params, '', self.tenant, 'unblended_cost',
                                     'currency_code')
        start = handler.start_datetime
        end = handler.end_datetime
        interval = handler.time_interval
        self.assertEqual(start, DateHelper().last_month_start)
        self.assertEqual(end, DateHelper().last_month_end)
        self.assertIsInstance(interval, list)
        self.assertTrue(len(interval) >= 28)

    def test_get_time_frame_filter_last_ten(self):
        """Test _get_time_frame_filter for last ten days."""
        query_params = {'filter':
                        {'resolution': 'daily',
                         'time_scope_value': -10,
                         'time_scope_units': 'day'}}
        handler = ReportQueryHandler(query_params, '', self.tenant, 'unblended_cost',
                                     'currency_code')
        dh = DateHelper()
        ten_days_ago = dh.n_days_ago(dh.today, 10)
        start = handler.start_datetime.replace(hour=0, minute=0, second=0, microsecond=0)
        end = handler.end_datetime.replace(hour=0, minute=0, second=0, microsecond=0)
        interval = handler.time_interval
        self.assertEqual(start, ten_days_ago)
        self.assertEqual(end, dh.today)
        self.assertIsInstance(interval, list)
        self.assertTrue(len(interval) == 11)

    def test_get_time_frame_filter_last_thirty(self):
        """Test _get_time_frame_filter for last thirty days."""
        query_params = {'filter':
                        {'resolution': 'daily',
                         'time_scope_value': -30,
                         'time_scope_units': 'day'}}
        handler = ReportQueryHandler(query_params, '', self.tenant, 'unblended_cost',
                                     'currency_code')
        dh = DateHelper()
        thirty_days_ago = dh.n_days_ago(dh.today, 30)
        start = handler.start_datetime.replace(hour=0, minute=0, second=0, microsecond=0)
        end = handler.end_datetime.replace(hour=0, minute=0, second=0, microsecond=0)
        interval = handler.time_interval
        self.assertEqual(start, thirty_days_ago)
        self.assertEqual(end, dh.today)
        self.assertIsInstance(interval, list)
        self.assertTrue(len(interval) == 31)

    def test_execute_query_current_month_daily(self):
        """Test execute_query for current month on daily breakdown."""
        query_params = {'filter':
                        {'resolution': 'daily', 'time_scope_value': -1,
                         'time_scope_units': 'month'}}
        handler = ReportQueryHandler(query_params, '', self.tenant, 'unblended_cost',
                                     'currency_code')
        query_output = handler.execute_query()
        self.assertIsNotNone(query_output.get('data'))
        self.assertIsNotNone(query_output.get('total'))
        total = query_output.get('total')
        self.assertIsNotNone(total.get('value'))
        self.assertEqual(total.get('value'), self.current_month_total)

    def test_execute_query_current_month_monthly(self):
        """Test execute_query for current month on monthly breakdown."""
        query_params = {'filter':
                        {'resolution': 'monthly', 'time_scope_value': -1,
                         'time_scope_units': 'month'}}
        handler = ReportQueryHandler(query_params, '', self.tenant, 'unblended_cost',
                                     'currency_code')
        query_output = handler.execute_query()
        self.assertIsNotNone(query_output.get('data'))
        self.assertIsNotNone(query_output.get('total'))
        total = query_output.get('total')
        self.assertIsNotNone(total.get('value'))
        self.assertEqual(total.get('value'), self.current_month_total)

    def test_execute_query_current_month_by_service(self):
        """Test execute_query for current month on monthly breakdown by service."""
        query_params = {'filter':
                        {'resolution': 'monthly', 'time_scope_value': -1,
                         'time_scope_units': 'month'},
                        'group_by': {'service': ['*']}}
        handler = ReportQueryHandler(query_params, '?group_by[service]=*',
                                     self.tenant, 'unblended_cost',
                                     'currency_code')
        query_output = handler.execute_query()
        data = query_output.get('data')
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get('total'))
        total = query_output.get('total')
        self.assertIsNotNone(total.get('value'))
        self.assertEqual(total.get('value'), self.current_month_total)

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
        query_params = {'filter':
                        {'resolution': 'monthly', 'time_scope_value': -1,
                         'time_scope_units': 'month'},
                        'group_by': {'service': ['AmazonEC2']}}
        handler = ReportQueryHandler(query_params, '?group_by[service]=AmazonEC2',
                                     self.tenant, 'unblended_cost',
                                     'currency_code')
        query_output = handler.execute_query()
        data = query_output.get('data')
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get('total'))
        total = query_output.get('total')
        self.assertIsNotNone(total.get('value'))
        self.assertEqual(total.get('value'), self.current_month_total)

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
        query_params = {'filter':
                        {'resolution': 'monthly', 'time_scope_value': -1,
                         'time_scope_units': 'month'},
                        'group_by': {'account': ['*']}}
        handler = ReportQueryHandler(query_params, '?group_by[account]=*',
                                     self.tenant, 'unblended_cost',
                                     'currency_code')
        query_output = handler.execute_query()
        data = query_output.get('data')
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get('total'))
        total = query_output.get('total')
        self.assertIsNotNone(total.get('value'))
        self.assertEqual(total.get('value'), self.current_month_total)

        cmonth_str = DateHelper().this_month_start.strftime('%Y-%m')
        for data_item in data:
            month_val = data_item.get('date')
            month_data = data_item.get('accounts')
            self.assertEqual(month_val, cmonth_str)
            self.assertIsInstance(month_data, list)
            for month_item in month_data:
                account = month_item.get('account')
                self.assertEqual(account, self.payer_account_id)
                self.assertIsInstance(month_item.get('values'), list)

    def test_execute_query_by_account_by_service(self):
        """Test execute_query for current month breakdown by account by service."""
        query_params = {'filter':
                        {'resolution': 'monthly', 'time_scope_value': -1,
                         'time_scope_units': 'month'},
                        'group_by': {'account': ['*'],
                                     'service': ['*']}}
        query_string = '?group_by[account]=*&group_by[service]=AmazonEC2'
        handler = ReportQueryHandler(query_params, query_string,
                                     self.tenant, 'unblended_cost',
                                     'currency_code')
        query_output = handler.execute_query()
        data = query_output.get('data')
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get('total'))
        total = query_output.get('total')
        self.assertIsNotNone(total.get('value'))
        self.assertEqual(total.get('value'), self.current_month_total)

        cmonth_str = DateHelper().this_month_start.strftime('%Y-%m')
        for data_item in data:
            month_val = data_item.get('date')
            month_data = data_item.get('accounts')
            self.assertEqual(month_val, cmonth_str)
            self.assertIsInstance(month_data, list)
            for month_item in month_data:
                account = month_item.get('account')
                self.assertEqual(account, self.payer_account_id)
                self.assertIsInstance(month_item.get('services'), list)

    def test_execute_query_with_counts(self):
        """Test execute_query for with counts of unique resources."""
        dh = DateHelper()
        self.add_data_to_tenant(rate=Decimal('0.299'),
                                data_start=dh.today,
                                data_end=dh.tomorrow)

        with tenant_context(self.tenant):
            instance_type = AWSCostEntryProduct.objects.first().instance_type

        expected = {
            dh.today.strftime('%Y-%m-%d'): dh.this_hour.hour,
            dh.yesterday.strftime('%Y-%m-%d'): 24
        }

        query_params = {'filter':
                        {'resolution': 'daily', 'time_scope_value': -1,
                         'time_scope_units': 'day'}}
        query_string = '?filter[time_scope_value]=-1&filter[resolution]=daily'
        annotations = {'instance_type':
                       Concat('cost_entry_product__instance_type', Value(''))}
        extras = {'count': 'resource_id',
                  'group_by': ['instance_type'],
                  'annotations': annotations,
                  'filter': {'cost_entry_product__instance_type__isnull': False}}
        handler = ReportQueryHandler(query_params, query_string,
                                     self.tenant, 'usage_amount',
                                     'cost_entry_pricing__unit',
                                     **extras)
        query_output = handler.execute_query()

        data = query_output.get('data')
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get('total'))

        total = query_output.get('total')
        self.assertIsNotNone(total.get('count'))
        self.assertEqual(total.get('count'), sum(expected.values()))

        for data_item in data:
            instance_types = data_item.get('instance_types')
            for it in instance_types:
                if it['instance_type'] == instance_type:
                    actual_count = it['values'][0].get('count')
                    self.assertEqual(expected.get(data_item['date']), actual_count)

    def test_execute_query_curr_month_by_account_w_limit(self):
        """Test execute_query for current month on monthly breakdown by account with limit."""
        self.add_data_to_tenant(rate=Decimal('0.299'))
        self.add_data_to_tenant(rate=Decimal('0.399'))
        self.add_data_to_tenant(rate=Decimal('0.099'))
        self.add_data_to_tenant(rate=Decimal('0.999'))
        self.add_data_to_tenant(rate=Decimal('0.699'))

        query_params = {'filter':
                        {'resolution': 'monthly', 'time_scope_value': -1,
                         'time_scope_units': 'month', 'limit': 2},
                        'group_by': {'account': ['*']}}
        handler = ReportQueryHandler(query_params, '?group_by[account]=*&filter[limit]=2',
                                     self.tenant, 'unblended_cost',
                                     'currency_code')
        query_output = handler.execute_query()
        data = query_output.get('data')
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get('total'))
        total = query_output.get('total')
        self.assertIsNotNone(total.get('value'))
        self.assertEqual(total.get('value'), self.current_month_total)

        cmonth_str = DateHelper().this_month_start.strftime('%Y-%m')
        for data_item in data:
            month_val = data_item.get('date')
            month_data = data_item.get('accounts')
            self.assertEqual(month_val, cmonth_str)
            self.assertIsInstance(month_data, list)
            self.assertEqual(3, len(month_data))
            for month_item in month_data:
                self.assertIsInstance(month_item.get('account'), str)
                self.assertIsInstance(month_item.get('values'), list)

    def test_execute_query_curr_month_by_account_w_order(self):
        """Test execute_query for current month on monthly breakdown by account with asc order."""
        self.add_data_to_tenant(rate=Decimal('0.299'))
        self.add_data_to_tenant(rate=Decimal('0.099'))
        self.add_data_to_tenant(rate=Decimal('0.999'))

        query_params = {'filter':
                        {'resolution': 'monthly', 'time_scope_value': -1,
                         'time_scope_units': 'month'},
                        'group_by': {'account': ['*']},
                        'order_by': {'cost': 'asc'}}
        handler = ReportQueryHandler(query_params, '?group_by[account]=*',
                                     self.tenant, 'unblended_cost',
                                     'currency_code')
        query_output = handler.execute_query()
        data = query_output.get('data')
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get('total'))
        total = query_output.get('total')
        self.assertIsNotNone(total.get('value'))
        self.assertEqual(total.get('value'), self.current_month_total)

        cmonth_str = DateHelper().this_month_start.strftime('%Y-%m')
        for data_item in data:
            month_val = data_item.get('date')
            month_data = data_item.get('accounts')
            self.assertEqual(month_val, cmonth_str)
            self.assertIsInstance(month_data, list)
            self.assertEqual(4, len(month_data))
            current_total = 0
            for month_item in month_data:
                self.assertIsInstance(month_item.get('account'), str)
                self.assertIsInstance(month_item.get('values'), list)
                self.assertIsNotNone(month_item.get('values')[0].get('total'))
                data_point_total = month_item.get('values')[0].get('total')
                self.assertLess(current_total, data_point_total)
                current_total = data_point_total

    def test_execute_query_curr_month_by_region(self):
        """Test execute_query for current month on monthly breakdown by region."""
        query_params = {'filter':
                        {'resolution': 'monthly', 'time_scope_value': -1,
                         'time_scope_units': 'month'},
                        'group_by': {'region': ['*']}}
        handler = ReportQueryHandler(query_params, '?group_by[region]=*',
                                     self.tenant, 'unblended_cost',
                                     'currency_code')
        query_output = handler.execute_query()
        data = query_output.get('data')
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get('total'))
        total = query_output.get('total')
        self.assertIsNotNone(total.get('value'))
        self.assertEqual(total.get('value'), self.current_month_total)

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
                self.assertIsNotNone(month_item.get('values')[0].get('total'))

    def test_execute_query_curr_month_by_filtered_region(self):
        """Test execute_query for current month on monthly breakdown by filtered region."""
        query_params = {'filter':
                        {'resolution': 'monthly', 'time_scope_value': -1,
                         'time_scope_units': 'month'},
                        'group_by': {'region': ['us-east-1']}}
        handler = ReportQueryHandler(query_params, '?group_by[region]=us-east-1',
                                     self.tenant, 'unblended_cost',
                                     'currency_code')
        query_output = handler.execute_query()
        data = query_output.get('data')
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get('total'))
        total = query_output.get('total')
        self.assertIsNotNone(total.get('value'))
        self.assertEqual(total.get('value'), 0)

        cmonth_str = DateHelper().this_month_start.strftime('%Y-%m')
        for data_item in data:
            month_val = data_item.get('date')
            month_data = data_item.get('regions')
            self.assertEqual(month_val, cmonth_str)
            self.assertIsInstance(month_data, list)
            for month_item in month_data:
                self.assertIsInstance(month_item.get('region'), str)
                self.assertIsInstance(month_item.get('values'), list)
                self.assertIsNotNone(month_item.get('values')[0].get('total'))

    def test_execute_query_curr_month_by_avail_zone(self):
        """Test execute_query for current month on monthly breakdown by avail_zone."""
        query_params = {'filter':
                        {'resolution': 'monthly', 'time_scope_value': -1,
                         'time_scope_units': 'month'},
                        'group_by': {'avail_zone': ['*']}}
        handler = ReportQueryHandler(query_params, '?group_by[avail_zone]=*',
                                     self.tenant, 'unblended_cost',
                                     'currency_code')
        query_output = handler.execute_query()
        data = query_output.get('data')
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get('total'))
        total = query_output.get('total')
        self.assertIsNotNone(total.get('value'))
        self.assertEqual(total.get('value'), self.current_month_total)

        cmonth_str = DateHelper().this_month_start.strftime('%Y-%m')
        for data_item in data:
            month_val = data_item.get('date')
            month_data = data_item.get('avail_zones')
            self.assertEqual(month_val, cmonth_str)
            self.assertIsInstance(month_data, list)
            self.assertEqual(1, len(month_data))
            for month_item in month_data:
                self.assertIsInstance(month_item.get('avail_zone'), str)
                self.assertIsInstance(month_item.get('values'), list)
                self.assertIsNotNone(month_item.get('values')[0].get('total'))

    def test_execute_query_curr_month_by_filtered_avail_zone(self):
        """Test execute_query for current month on monthly breakdown by filtered avail_zone."""
        query_params = {'filter':
                        {'resolution': 'monthly', 'time_scope_value': -1,
                         'time_scope_units': 'month'},
                        'group_by': {'avail_zone': ['us-east-1a']}}
        handler = ReportQueryHandler(query_params, '?group_by[avail_zone]=us-east-1a',
                                     self.tenant, 'unblended_cost',
                                     'currency_code')
        query_output = handler.execute_query()
        data = query_output.get('data')
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get('total'))
        total = query_output.get('total')
        self.assertIsNotNone(total.get('value'))
        self.assertEqual(total.get('value'), self.current_month_total)

        cmonth_str = DateHelper().this_month_start.strftime('%Y-%m')
        for data_item in data:
            month_val = data_item.get('date')
            month_data = data_item.get('avail_zones')
            self.assertEqual(month_val, cmonth_str)
            self.assertIsInstance(month_data, list)
            self.assertEqual(1, len(month_data))
            for month_item in month_data:
                self.assertIsInstance(month_item.get('avail_zone'), str)
                self.assertIsInstance(month_item.get('values'), list)
                self.assertIsNotNone(month_item.get('values')[0].get('total'))

    def test_execute_query_current_month_filter_account(self):
        """Test execute_query for current month on monthly filtered by account."""
        query_params = {'filter':
                        {'resolution': 'monthly', 'time_scope_value': -1,
                         'time_scope_units': 'month',
                         'account': [self.payer_account_id]}}
        handler = ReportQueryHandler(query_params, '',
                                     self.tenant, 'unblended_cost',
                                     'currency_code')
        query_output = handler.execute_query()
        data = query_output.get('data')
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get('total'))
        total = query_output.get('total')
        self.assertIsNotNone(total.get('value'))
        self.assertEqual(total.get('value'), self.current_month_total)

        cmonth_str = DateHelper().this_month_start.strftime('%Y-%m')
        for data_item in data:
            month_val = data_item.get('date')
            month_data = data_item.get('values')
            self.assertEqual(month_val, cmonth_str)
            self.assertIsInstance(month_data, list)

    def test_execute_query_current_month_filter_service(self):
        """Test execute_query for current month on monthly filtered by service."""
        query_params = {'filter':
                        {'resolution': 'monthly', 'time_scope_value': -1,
                         'time_scope_units': 'month',
                         'service': ['AmazonEC2']}}
        handler = ReportQueryHandler(query_params, '',
                                     self.tenant, 'unblended_cost',
                                     'currency_code')
        query_output = handler.execute_query()

        data = query_output.get('data')
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get('total'))

        total = query_output.get('total')
        self.assertIsNotNone(total.get('value'))
        self.assertEqual(total.get('value'), self.current_month_total)

        cmonth_str = DateHelper().this_month_start.strftime('%Y-%m')
        for data_item in data:
            month_val = data_item.get('date')
            month_data = data_item.get('values')
            self.assertEqual(month_val, cmonth_str)
            self.assertIsInstance(month_data, list)

    def test_execute_query_current_month_filter_region(self):
        """Test execute_query for current month on monthly filtered by region."""
        query_params = {'filter':
                        {'resolution': 'monthly', 'time_scope_value': -1,
                         'time_scope_units': 'month',
                         'region': ['us-east-1']}}
        handler = ReportQueryHandler(query_params, '',
                                     self.tenant, 'unblended_cost',
                                     'currency_code')
        query_output = handler.execute_query()
        data = query_output.get('data')
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get('total'))
        total = query_output.get('total')
        self.assertIsNotNone(total.get('value'))
        self.assertEqual(total.get('value'), 0)

        cmonth_str = DateHelper().this_month_start.strftime('%Y-%m')
        for data_item in data:
            month_val = data_item.get('date')
            month_data = data_item.get('values')
            self.assertEqual(month_val, cmonth_str)
            self.assertIsInstance(month_data, list)

    def test_execute_query_current_month_filter_avail_zone(self):
        """Test execute_query for current month on monthly filtered by avail_zone."""
        query_params = {'filter':
                        {'resolution': 'monthly', 'time_scope_value': -1,
                         'time_scope_units': 'month',
                         'avail_zone': ['us-east-1a']}}
        handler = ReportQueryHandler(query_params, '',
                                     self.tenant, 'unblended_cost',
                                     'currency_code')
        query_output = handler.execute_query()
        data = query_output.get('data')
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get('total'))
        total = query_output.get('total')
        self.assertIsNotNone(total.get('value'))
        self.assertEqual(total.get('value'), self.current_month_total)

        cmonth_str = DateHelper().this_month_start.strftime('%Y-%m')
        for data_item in data:
            month_val = data_item.get('date')
            month_data = data_item.get('values')
            self.assertEqual(month_val, cmonth_str)
            self.assertIsInstance(month_data, list)

    def test_execute_query_current_month_filter_avail_zone_csv(self):
        """Test execute_query for current month on monthly filtered by avail_zone for csv."""
        query_params = {'filter':
                        {'resolution': 'monthly', 'time_scope_value': -1,
                         'time_scope_units': 'month',
                         'avail_zone': ['us-east-1a']}}
        handler = ReportQueryHandler(query_params, '',
                                     self.tenant, 'unblended_cost',
                                     'currency_code',
                                     **{'accept_type': 'text/csv'})
        query_output = handler.execute_query()
        data = query_output.get('data')
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get('total'))
        total = query_output.get('total')
        self.assertIsNotNone(total.get('value'))
        self.assertEqual(total.get('value'), self.current_month_total)

        cmonth_str = DateHelper().this_month_start.strftime('%Y-%m')
        self.assertEqual(len(data), 1)
        for data_item in data:
            month_val = data_item.get('date')
            self.assertEqual(month_val, cmonth_str)

    def test_execute_query_current_month_export_json(self):
        """Test execute_query for current month on monthly export raw json data."""
        query_params = {'filter':
                        {'resolution': 'monthly', 'time_scope_value': -1,
                         'time_scope_units': 'month'},
                        'operation': 'none'}
        handler = ReportQueryHandler(query_params, '',
                                     self.tenant, 'unblended_cost',
                                     'currency_code')
        query_output = handler.execute_query()

        data = query_output.get('data')
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get('total'))

        total = query_output.get('total')
        self.assertIsNotNone(total.get('value'))
        self.assertEqual(total.get('value'), self.current_month_total)

        cmonth_str = DateHelper().this_month_start.strftime('%Y-%m')
        self.assertEqual(len(data), 24)
        for data_item in data:
            month = data_item.get('date')
            self.assertEqual(month, cmonth_str)

    def test_execute_query_current_month_export_csv(self):
        """Test execute_query for current month on monthly export raw csv data."""
        query_params = {'filter':
                        {'resolution': 'monthly', 'time_scope_value': -1,
                         'time_scope_units': 'month'},
                        'operation': 'none'}
        handler = ReportQueryHandler(query_params, '',
                                     self.tenant, 'unblended_cost',
                                     'currency_code',
                                     **{'accept_type': 'text/csv'})
        query_output = handler.execute_query()

        data = query_output.get('data')
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get('total'))

        total = query_output.get('total')
        self.assertIsNotNone(total.get('value'))
        self.assertEqual(total.get('value'), self.current_month_total)

        cmonth_str = DateHelper().this_month_start.strftime('%Y-%m')
        self.assertEqual(len(data), 24)
        for data_item in data:
            month = data_item.get('date')
            self.assertEqual(month, cmonth_str)

    def test_execute_query_curr_month_by_account_w_limit_csv(self):
        """Test execute_query for current month on monthly by account with limt as csv."""
        self.add_data_to_tenant(rate=Decimal('0.299'))
        self.add_data_to_tenant(rate=Decimal('0.399'))
        self.add_data_to_tenant(rate=Decimal('0.099'))
        self.add_data_to_tenant(rate=Decimal('0.999'))
        self.add_data_to_tenant(rate=Decimal('0.699'))
        query_params = {'filter':
                        {'resolution': 'monthly', 'time_scope_value': -1,
                         'time_scope_units': 'month', 'limit': 2},
                        'group_by': {'account': ['*']}}
        handler = ReportQueryHandler(query_params, '?group_by[account]=*&filter[limit]=2',
                                     self.tenant, 'unblended_cost',
                                     'currency_code',
                                     **{'accept_type': 'text/csv'})
        query_output = handler.execute_query()
        data = query_output.get('data')
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get('total'))
        total = query_output.get('total')
        self.assertIsNotNone(total.get('value'))
        self.assertEqual(total.get('value'), self.current_month_total)

        cmonth_str = DateHelper().this_month_start.strftime('%Y-%m')
        self.assertEqual(len(data), 3)
        for data_item in data:
            month = data_item.get('date')
            self.assertEqual(month, cmonth_str)

    def test_execute_query_w_delta_bad_choice(self):
        """Test invalid delta value."""
        query_params = {'filter':
                        {'resolution': 'monthly',
                         'time_scope_value': -1,
                         'time_scope_units': 'month',
                         'limit': 2},
                        'group_by': {'account': ['*']},
                        'delta': 'Invalid'}
        handler = ReportQueryHandler(query_params,
                                     '?group_by[account]=*&filter[limit]=2&delta=Invalid',
                                     self.tenant,
                                     'unblended_cost',
                                     'currency_code')
        with self.assertRaises(NotImplementedError):
            handler.execute_query()

    def test_execute_query_w_delta_month(self):
        """Test execute_query for current month on monthly breakdown by account with limit."""
        dh = DateHelper()

        # generate data for 5 days in last month
        self.add_data_to_tenant(rate=Decimal('0.5'),
                                bill_start=dh.last_month_start,
                                bill_end=dh.last_month_end,
                                data_start=dh.last_month_start,
                                data_end=dh.last_month_start.replace(day=5))

        # generate data for first 5 days in this month
        self.add_data_to_tenant(rate=Decimal('1.0'),
                                bill_start=dh.this_month_start,
                                bill_end=dh.this_month_end,
                                data_start=dh.this_month_start,
                                data_end=dh.this_month_start.replace(day=5))

        query_params = {'filter':
                        {'resolution': 'monthly',
                         'time_scope_value': -1,
                         'time_scope_units': 'month',
                         'limit': 2},
                        'group_by': {'account': ['*']},
                        'delta': 'month'}
        handler = ReportQueryHandler(query_params,
                                     '?group_by[account]=*&filter[limit]=2&delta=month',
                                     self.tenant,
                                     'unblended_cost',
                                     'currency_code')
        query_output = handler.execute_query()
        data = query_output.get('data')
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get('total'))

        total = query_output.get('total')
        self.assertIsNotNone(total.get('value'))
        self.assertEqual(total.get('value'), self.current_month_total)

        delta = query_output.get('delta')
        self.assertIsNotNone(delta.get('value'))
        self.assertIsNotNone(delta.get('percent'))
        self.assertTrue(delta.get('percent') > Decimal(100))
