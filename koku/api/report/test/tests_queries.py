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
import random
from collections import Iterable, OrderedDict
from datetime import timedelta
from decimal import Decimal

from django.db.models import (CharField, Count, DateTimeField, IntegerField,
                              Max, Q, Sum, Value)
from django.db.models.functions import Cast, Concat
from django.test import TestCase
from faker import Faker
from tenant_schemas.utils import tenant_context

from api.iam.test.iam_test_case import IamTestCase
from api.report.aws.queries import AWSReportQueryHandler
from api.report.query_filter import QueryFilter, QueryFilterCollection
from api.utils import DateHelper
from reporting.models import (AWSAccountAlias,
                              AWSCostEntry,
                              AWSCostEntryBill,
                              AWSCostEntryLineItem,
                              AWSCostEntryLineItemAggregates,
                              AWSCostEntryLineItemDaily,
                              AWSCostEntryLineItemDailySummary,
                              AWSCostEntryPricing,
                              AWSCostEntryProduct)


class QueryFilterTest(TestCase):
    """Test the QueryFilter class."""

    fake = Faker()

    def test_composed_string_all(self):
        """Test composed_query_string() method using all parameters."""
        table = self.fake.word()
        field = self.fake.word()
        operation = self.fake.word()
        parameter = self.fake.word()
        filt = QueryFilter(table, field, operation, parameter)
        expected = f'{table}__{field}__{operation}'
        self.assertEqual(filt.composed_query_string(), expected)

    def test_composed_string_table_op(self):
        """Test composed_query_string() method using table and operation parameters."""
        table = self.fake.word()
        operation = self.fake.word()
        filt = QueryFilter(table=table, operation=operation)
        expected = f'{table}__{operation}'
        self.assertEqual(filt.composed_query_string(), expected)

    def test_composed_dict_all(self):
        """Test composed_dict() method with all parameters."""
        table = self.fake.word()
        field = self.fake.word()
        operation = self.fake.word()
        parameter = self.fake.word()

        filt = QueryFilter(table, field, operation, parameter)
        expected_dict = {f'{table}__{field}__{operation}': parameter}
        expected = Q(**expected_dict)
        self.assertEqual(filt.composed_Q(), expected)

    def test_composed_dict_field(self):
        """Test composed_dict() method without a Table parameter."""
        field = self.fake.word()
        operation = self.fake.word()
        parameter = self.fake.word()
        filt = QueryFilter(field=field, operation=operation,
                           parameter=parameter)
        expected_dict = {f'{field}__{operation}': parameter}
        expected = Q(**expected_dict)
        self.assertEqual(filt.composed_Q(), expected)

    def test_from_string_all(self):
        """Test from_string() method with all parts."""
        table = self.fake.word()
        field = self.fake.word()
        operation = self.fake.word()
        SEP = QueryFilter.SEP
        test_string = table + SEP + field + SEP + operation
        filt = QueryFilter().from_string(test_string)

        self.assertEqual(filt.table, table)
        self.assertEqual(filt.field, field)
        self.assertEqual(filt.operation, operation)
        self.assertEqual(filt.composed_query_string(), test_string)

    def test_from_string_two_parts(self):
        """Test from_string() method with two parts."""
        table = self.fake.word()
        operation = self.fake.word()
        SEP = QueryFilter.SEP
        test_string = table + SEP + operation
        filt = QueryFilter().from_string(test_string)

        self.assertEqual(filt.table, table)
        self.assertEqual(filt.operation, operation)
        self.assertEqual(filt.composed_query_string(), test_string)

    def test_from_string_wrong_parts_few(self):
        """Test from_string() method with too few parts."""
        test_string = self.fake.word()
        with self.assertRaises(TypeError):
            QueryFilter().from_string(test_string)

    def test_from_string_wrong_parts_more(self):
        """Test from_string() method with too many parts."""
        SEP = QueryFilter.SEP
        test_string = self.fake.word() + SEP + \
            self.fake.word() + SEP + \
            self.fake.word() + SEP + \
            self.fake.word()

        with self.assertRaises(TypeError):
            QueryFilter().from_string(test_string)


class QueryFilterCollectionTest(TestCase):
    """Test the QueryFilterCollection class."""

    fake = Faker()

    def test_constructor(self):
        """Test the constructor using valid QueryFilter instances."""
        filters = []
        for _ in range(0, 3):
            filt = QueryFilter(table=self.fake.word(), field=self.fake.word(),
                               operation=self.fake.word(), parameter=self.fake.word())
            filters.append(filt)
        qf_coll = QueryFilterCollection(filters)
        self.assertEqual(qf_coll._filters, filters)

    def test_constructor_bad_type(self):
        """Test the constructor using an invalid object type."""
        with self.assertRaises(TypeError):
            QueryFilterCollection(dict())

    def test_constructor_bad_elements(self):
        """Test the constructor using invalid values."""
        bad_list = [self.fake.word(), self.fake.word()]

        with self.assertRaises(TypeError):
            QueryFilterCollection(bad_list)

    def test_add_filter(self):
        """Test the add() method using a QueryFilter instance."""
        filters = []
        qf_coll = QueryFilterCollection()
        for _ in range(0, 3):
            filt = QueryFilter(self.fake.word(), self.fake.word(),
                               self.fake.word(), self.fake.word())
            filters.append(filt)
            qf_coll.add(query_filter=filt)
        self.assertEqual(qf_coll._filters, filters)

    def test_add_params(self):
        """Test the add() method using parameters."""
        table = self.fake.word()
        field = self.fake.word()
        operation = self.fake.word()
        parameter = self.fake.word()
        filt = QueryFilter(table=table, field=field, operation=operation,
                           parameter=parameter)
        qf_coll = QueryFilterCollection()
        qf_coll.add(table=table, field=field, operation=operation,
                    parameter=parameter)
        self.assertEqual(qf_coll._filters[0], filt)

    def test_add_bad(self):
        """Test the add() method using invalid values."""
        qf_coll = QueryFilterCollection()

        with self.assertRaises(AttributeError):
            qf_coll.add(self.fake.word(), self.fake.word(), self.fake.word())

    def test_compose(self):
        """Test the compose() method."""
        qf_coll = QueryFilterCollection()
        table = self.fake.word()
        field = self.fake.word()
        operation = self.fake.word()
        parameter = self.fake.word()
        filt = QueryFilter(table=table, field=field, operation=operation,
                           parameter=parameter)
        expected = filt.composed_Q()
        qf_coll.add(table=table, field=field, operation=operation, parameter=parameter)
        self.assertEqual(qf_coll.compose(), expected)

    def test_contains_with_filter(self):
        """Test the __contains__() method using a QueryFilter."""
        qf = QueryFilter(table=self.fake.word(), field=self.fake.word(),
                         parameter=self.fake.word())
        qf_coll = QueryFilterCollection([qf])
        self.assertIn(qf, qf_coll)

    def test_contains_with_dict(self):
        """Test the __contains__() method using a dict to get a fuzzy match."""
        table = self.fake.word()
        field = self.fake.word()
        operation = self.fake.word()
        parameter = self.fake.word()
        qf = QueryFilter(table=table, field=field, operation=operation,
                         parameter=parameter)
        qf_coll = QueryFilterCollection([qf])
        self.assertIn({'table': table, 'parameter': parameter}, qf_coll)

    def test_contains_fail(self):
        """Test the __contains__() method fails with a non-matching filter."""
        qf1 = QueryFilter(table=self.fake.word(), field=self.fake.word(),
                          parameter=self.fake.word())
        qf2 = QueryFilter(table=self.fake.word(), field=self.fake.word(),
                          parameter=self.fake.word())
        qf_coll = QueryFilterCollection([qf1])
        self.assertNotIn(qf2, qf_coll)
        self.assertFalse(qf2 in qf_coll)

    def test_delete_filter(self):
        """Test the delete() method works with QueryFilters."""
        qf1 = QueryFilter(table=self.fake.word(), field=self.fake.word(),
                          parameter=self.fake.word())
        qf2 = QueryFilter(table=self.fake.word(), field=self.fake.word(),
                          parameter=self.fake.word())
        qf_coll = QueryFilterCollection([qf1, qf2])

        qf_coll.delete(qf1)
        self.assertEqual([qf2], qf_coll._filters)
        self.assertNotIn(qf1, qf_coll)

    def test_delete_fail(self):
        """Test the delete() method works with QueryFilters."""
        qf1 = QueryFilter(table=self.fake.word(), field=self.fake.word(),
                          parameter=self.fake.word())
        qf2 = QueryFilter(table=self.fake.word(), field=self.fake.word(),
                          parameter=self.fake.word())
        qf_coll = QueryFilterCollection([qf1, qf2])

        q_dict = {'table': self.fake.word(),
                  'field': self.fake.word(),
                  'parameter': self.fake.word()}

        with self.assertRaises(AttributeError):
            qf_coll.delete(qf1, **q_dict)

    def test_delete_params(self):
        """Test the delete() method works with parameters."""
        qf1 = QueryFilter(table=self.fake.word(), field=self.fake.word(),
                          parameter=self.fake.word())
        qf2 = QueryFilter(table=self.fake.word(), field=self.fake.word(),
                          parameter=self.fake.word())
        qf_coll = QueryFilterCollection([qf1, qf2])

        qf_coll.delete(table=qf1.table, field=qf1.field,
                       parameter=qf1.parameter)
        self.assertEqual([qf2], qf_coll._filters)
        self.assertNotIn(qf1, qf_coll)

    def test_get_fail(self):
        """Test the get() method fails when no match is found."""
        qf1 = QueryFilter(table=self.fake.word(), field=self.fake.word(),
                          parameter=self.fake.word())
        qf2 = QueryFilter(table=self.fake.word(), field=self.fake.word(),
                          parameter=self.fake.word())
        qf_coll = QueryFilterCollection([qf1, qf2])

        response = qf_coll.get({'table': self.fake.word(),
                                'field': self.fake.word(),
                                'parameter': self.fake.word()})
        self.assertIsNone(response)

    def test_iterable(self):
        """Test the __iter__() method returns an iterable."""
        qf1 = QueryFilter(table=self.fake.word(), field=self.fake.word(),
                          parameter=self.fake.word())
        qf2 = QueryFilter(table=self.fake.word(), field=self.fake.word(),
                          parameter=self.fake.word())
        qf_coll = QueryFilterCollection([qf1, qf2])

        self.assertIsInstance(qf_coll.__iter__(), Iterable)

    def test_indexing(self):
        """Test that __getitem__() allows array slicing."""
        qf1 = QueryFilter(table=self.fake.word(), field=self.fake.word(),
                          parameter=self.fake.word())
        qf2 = QueryFilter(table=self.fake.word(), field=self.fake.word(),
                          parameter=self.fake.word())
        qf_coll = QueryFilterCollection([qf1, qf2])

        self.assertEqual(qf_coll[0], qf1)
        self.assertEqual(qf_coll[1], qf2)
        self.assertEqual(qf_coll[-1], qf2)
        self.assertEqual(qf_coll[-2], qf1)


class ReportQueryUtilsTest(TestCase):
    """Test the report query class functions."""

    def test_has_wildcard_yes(self):
        """Test a list has a wildcard."""
        result = AWSReportQueryHandler.has_wildcard(['abc', '*'])
        self.assertTrue(result)

    def test_has_wildcard_no(self):
        """Test a list doesn't have a wildcard."""
        result = AWSReportQueryHandler.has_wildcard(['abc', 'def'])
        self.assertFalse(result)

    def test_has_wildcard_none(self):
        """Test an empty list doesn't have a wildcard."""
        result = AWSReportQueryHandler.has_wildcard([])
        self.assertFalse(result)

    def test_group_data_by_list(self):
        """Test the _group_data_by_list method."""
        group_by = ['account', 'service']
        data = [{'account': 'a1', 'service': 's1', 'units': 'USD', 'total': 4},
                {'account': 'a1', 'service': 's2', 'units': 'USD', 'total': 5},
                {'account': 'a2', 'service': 's1', 'units': 'USD', 'total': 6},
                {'account': 'a2', 'service': 's2', 'units': 'USD', 'total': 5},
                {'account': 'a1', 'service': 's3', 'units': 'USD', 'total': 5}]
        out_data = AWSReportQueryHandler._group_data_by_list(group_by, 0, data)
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
        out_data = AWSReportQueryHandler._group_data_by_list(group_by, 0, data)
        print(out_data)
        expected = {'t2.micro': [
            {'date': '2018-07-22', 'units': 'Hrs', 'instance_type': 't2.micro', 'total': 1.0, 'count': 0},
            {'date': '2018-07-22', 'units': '', 'instance_type': 't2.micro', 'total': 30.0, 'count': 0}],
            't2.small': [
                {'date': '2018-07-22', 'units': 'Hrs', 'instance_type': 't2.small', 'total': 17.0, 'count': 0}]}
        self.assertEqual(expected, out_data)


class ReportQueryTest(IamTestCase):
    """Tests the report queries."""

    def setUp(self):
        """Set up the customer view tests."""
        super().setUp()
        self.current_month_total = Decimal(0)
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
                        region='us-east-1',
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
        bill, _ = AWSCostEntryBill.objects.get_or_create(
            bill_type='Anniversary',
            payer_account_id=account,
            billing_period_start=bill_start,
            billing_period_end=bill_end
        )
        return bill

    def _create_pricing(self, term='OnDemand', unit='Hrs'):
        """Create an AWSCostEntryPricing."""
        ce_pricing, _ = AWSCostEntryPricing.objects.get_or_create(
            term=term,
            unit=unit
        )
        return ce_pricing

    def _populate_daily_table(self):
        included_fields = [
            'cost_entry_product_id',
            'cost_entry_pricing_id',
            'cost_entry_reservation_id',
            'line_item_type',
            'usage_account_id',
            'usage_type',
            'operation',
            'availability_zone',
            'resource_id',
            'tax_type',
            'product_code',
            'tags'
        ]
        annotations = {
            'usage_start': Cast('usage_start', DateTimeField()),
            'usage_end': Cast('usage_start', DateTimeField()),
            'usage_amount': Sum('usage_amount'),
            'normalization_factor': Max('normalization_factor'),
            'normalized_usage_amount': Sum('normalized_usage_amount'),
            'currency_code': Max('currency_code'),
            'unblended_rate': Max('unblended_rate'),
            'unblended_cost': Sum('unblended_cost'),
            'blended_rate': Max('blended_rate'),
            'blended_cost': Sum('blended_cost'),
            'public_on_demand_cost': Sum('public_on_demand_cost'),
            'public_on_demand_rate': Max('public_on_demand_rate')
        }

        entries = AWSCostEntryLineItem.objects\
            .values(*included_fields)\
            .annotate(**annotations)
        for entry in entries:
            daily = AWSCostEntryLineItemDaily(**entry)
            daily.save()

    def _populate_daily_summary_table(self):
        included_fields = [
            'usage_start',
            'usage_end',
            'usage_account_id',
            'availability_zone'
        ]
        annotations = {
            'product_family': Concat('cost_entry_product__product_family', Value('')),
            'product_code': Concat('cost_entry_product__service_code', Value('')),
            'region': Concat('cost_entry_product__region', Value('')),
            'instance_type': Concat('cost_entry_product__instance_type', Value('')),
            'unit': Concat('cost_entry_pricing__unit', Value('')),
            'usage_amount': Sum('usage_amount'),
            'normalization_factor': Max('normalization_factor'),
            'normalized_usage_amount': Sum('normalized_usage_amount'),
            'currency_code': Max('currency_code'),
            'unblended_rate': Max('unblended_rate'),
            'unblended_cost': Sum('unblended_cost'),
            'blended_rate': Max('blended_rate'),
            'blended_cost': Sum('blended_cost'),
            'public_on_demand_cost': Sum('public_on_demand_cost'),
            'public_on_demand_rate': Max('public_on_demand_rate'),
            'resource_count': Count('resource_id', distinct=True)
        }

        entries = AWSCostEntryLineItemDaily.objects\
            .values(*included_fields)\
            .annotate(**annotations)
        for entry in entries:
            alias = AWSAccountAlias.objects.filter(account_id=entry['usage_account_id'])
            summary = AWSCostEntryLineItemDailySummary(**entry,
                                                       account_alias=list(alias).pop())
            summary.save()
            self.current_month_total += entry['blended_cost']

    def _populate_aggregates_table(self):
        dh = DateHelper()
        this_month_filter = {'usage_start__gte': dh.this_month_start}
        ten_day_filter = {'usage_start__gte': dh.n_days_ago(dh.today, 10)}
        last_month_filter = {'usage_start__gte': dh.last_month_start,
                             'usage_end__lte': dh.last_month_end}

        report_types = ['costs', 'instance_type', 'storage']
        time_scopes = [
            (-1, this_month_filter),
            (-2, last_month_filter),
            (-10, ten_day_filter)
        ]

        for r_type in report_types:
            included_fields = [
                'usage_account_id',
                'product_code',
                'availability_zone'
            ]
            annotations = {
                'region': Concat('cost_entry_product__region', Value('')),
                'usage_amount': Sum('usage_amount'),
                'unblended_cost': Sum('unblended_cost'),
                'resource_count': Count('resource_id', distinct=True),
                'report_type': Value(r_type, CharField())
            }
            if r_type == 'costs':
                annotations.pop('usage_amount')

            for value, query_filter in time_scopes:
                annotations.update(
                    {'time_scope_value': Value(value, IntegerField())}
                )
                if r_type == 'instance_type':
                    query_filter.update(
                        {'cost_entry_product__instance_type__isnull': False}
                    )
                elif r_type == 'storage':
                    query_filter.update(
                        {'cost_entry_product__product_family': 'Storage'}
                    )
                entries = AWSCostEntryLineItemDaily.objects\
                    .filter(**query_filter)\
                    .values(*included_fields)\
                    .annotate(**annotations)
                for entry in entries:
                    alias = AWSAccountAlias.objects.filter(account_id=entry['usage_account_id'])
                    agg = AWSCostEntryLineItemAggregates(**entry, account_alias=list(alias).pop())
                    agg.save()

    def add_data_to_tenant(self, rate=Decimal(random.random()), amount=1,
                           bill_start=DateHelper().this_month_start,
                           bill_end=DateHelper().this_month_end,
                           data_start=DateHelper().this_month_start,
                           data_end=DateHelper().this_month_start + DateHelper().one_day,
                           account_id=None,
                           account_alias=None):
        """Populate tenant with data."""
        self.payer_account_id = account_id
        if account_id is None:
            self.payer_account_id = self.fake.ean(length=13)  # pylint: disable=no-member

        self.account_alias = account_alias
        if account_alias is None:
            self.account_alias = self.fake.company()

        with tenant_context(self.tenant):
            alias = list(AWSAccountAlias.objects.filter(
                account_id=self.payer_account_id))
            if not alias:
                alias = AWSAccountAlias(account_id=self.payer_account_id,
                                        account_alias=self.account_alias)
                alias.save()

            cost = rate * amount
            bill = self._create_bill(self.payer_account_id, bill_start, bill_end)
            ce_product = self._create_product()
            ce_pricing = self._create_pricing()

            current = data_start
            while current < data_end:
                end_hour = current + DateHelper().one_hour
                self.create_hourly_instance_usage(self.payer_account_id, bill,
                                                  ce_pricing, ce_product, rate,
                                                  cost, current, end_hour)
                current = end_hour
            self._populate_daily_table()
            self._populate_daily_summary_table()
            self._populate_aggregates_table()

    def test_has_filter_no_filter(self):
        """Test the has_filter method with no filter in the query params."""
        handler = AWSReportQueryHandler({}, '', self.tenant,
                                        **{'report_type': 'costs'})
        self.assertFalse(handler.check_query_params('filter', 'time_scope_value'))

    def test_has_filter_with_filter(self):
        """Test the has_filter method with filter in the query params."""
        query_params = {'filter':
                        {'resolution': 'monthly', 'time_scope_value': -1}}
        handler = AWSReportQueryHandler(query_params, '', self.tenant,
                                        **{'report_type': 'costs'})
        self.assertIsNotNone(handler.check_query_params('filter', 'time_scope_value'))

    def test_get_group_by_no_data(self):
        """Test the get_group_by_data method with no data in the query params."""
        handler = AWSReportQueryHandler({}, '', self.tenant,
                                        **{'report_type': 'costs'})
        self.assertFalse(handler.get_query_param_data('group_by', 'service'))

    def test_get_group_by_with_service_list(self):
        """Test the get_group_by_data method with no data in the query params."""
        expected = ['a', 'b']
        query_string = '?group_by[service]=a&group_by[service]=b'
        handler = AWSReportQueryHandler({'group_by':
                                        {'service': expected}},
                                        query_string,
                                        self.tenant,
                                        **{'report_type': 'costs'})
        service = handler.get_query_param_data('group_by', 'service')
        self.assertEqual(expected, service)

    def test_get_resolution_empty_default(self):
        """Test get_resolution returns default when query params are empty."""
        query_params = {}
        handler = AWSReportQueryHandler(query_params, '', self.tenant,
                                        **{'report_type': 'costs'})
        self.assertEqual(handler.get_resolution(), 'daily')
        self.assertEqual(handler.get_resolution(), 'daily')

    def test_get_resolution_empty_month_time_scope(self):
        """Test get_resolution returns default when time_scope is month."""
        query_params = {'filter': {'time_scope_value': -1}}
        handler = AWSReportQueryHandler(query_params, '', self.tenant,
                                        **{'report_type': 'costs'})
        self.assertEqual(handler.get_resolution(), 'monthly')

    def test_get_resolution_empty_day_time_scope(self):
        """Test get_resolution returns default when time_scope is month."""
        query_params = {'filter': {'time_scope_value': -10}}
        handler = AWSReportQueryHandler(query_params, '', self.tenant,
                                        **{'report_type': 'costs'})
        self.assertEqual(handler.get_resolution(), 'daily')

    def test_get_time_scope_units_empty_default(self):
        """Test get_time_scope_units returns default when query params are empty."""
        query_params = {}
        handler = AWSReportQueryHandler(query_params, '', self.tenant,
                                        **{'report_type': 'costs'})
        self.assertEqual(handler.get_time_scope_units(), 'day')
        self.assertEqual(handler.get_time_scope_units(), 'day')

    def test_get_time_scope_units_empty_month_time_scope(self):
        """Test get_time_scope_units returns default when time_scope is month."""
        query_params = {'filter': {'time_scope_value': -1}}
        handler = AWSReportQueryHandler(query_params, '', self.tenant,
                                        **{'report_type': 'costs'})
        self.assertEqual(handler.get_time_scope_units(), 'month')

    def test_get_time_scope_units_empty_day_time_scope(self):
        """Test get_time_scope_units returns default when time_scope is month."""
        query_params = {'filter': {'time_scope_value': -10}}
        handler = AWSReportQueryHandler(query_params, '', self.tenant,
                                        **{'report_type': 'costs'})
        self.assertEqual(handler.get_time_scope_units(), 'day')

    def test_get_time_scope_value_empty_default(self):
        """Test get_time_scope_value returns default when query params are empty."""
        query_params = {}
        handler = AWSReportQueryHandler(query_params, '', self.tenant,
                                        **{'report_type': 'costs'})
        self.assertEqual(handler.get_time_scope_value(), -10)
        self.assertEqual(handler.get_time_scope_value(), -10)

    def test_get_time_scope_value_empty_month_time_scope(self):
        """Test get_time_scope_value returns default when time_scope is month."""
        query_params = {'filter': {'time_scope_units': 'month'}}
        handler = AWSReportQueryHandler(query_params, '', self.tenant,
                                        **{'report_type': 'costs'})
        self.assertEqual(handler.get_time_scope_value(), -1)

    def test_get_time_scope_value_empty_day_time_scope(self):
        """Test get_time_scope_value returns default when time_scope is month."""
        query_params = {'filter': {'time_scope_units': 'day'}}
        handler = AWSReportQueryHandler(query_params, '', self.tenant,
                                        **{'report_type': 'costs'})
        self.assertEqual(handler.get_time_scope_value(), -10)

    def test_get_time_frame_filter_current_month(self):
        """Test _get_time_frame_filter for current month."""
        query_params = {'filter':
                        {'resolution': 'daily',
                         'time_scope_value': -1,
                         'time_scope_units': 'month'}}
        handler = AWSReportQueryHandler(query_params, '', self.tenant,
                                        **{'report_type': 'costs'})
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
        handler = AWSReportQueryHandler(query_params, '', self.tenant,
                                        **{'report_type': 'costs'})
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
        handler = AWSReportQueryHandler(query_params, '', self.tenant,
                                        **{'report_type': 'costs'})
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
        handler = AWSReportQueryHandler(query_params, '', self.tenant,
                                        **{'report_type': 'costs'})
        dh = DateHelper()
        thirty_days_ago = dh.n_days_ago(dh.today, 30)
        start = handler.start_datetime.replace(hour=0, minute=0, second=0, microsecond=0)
        end = handler.end_datetime.replace(hour=0, minute=0, second=0, microsecond=0)
        interval = handler.time_interval
        self.assertEqual(start, thirty_days_ago)
        self.assertEqual(end, dh.today)
        self.assertIsInstance(interval, list)
        self.assertTrue(len(interval) == 31)

    def test_execute_take_defaults(self):
        """Test execute_query for current month on daily breakdown."""
        query_params = {}
        handler = AWSReportQueryHandler(query_params, '', self.tenant,
                                        **{'report_type': 'costs'})
        query_output = handler.execute_query()
        self.assertIsNotNone(query_output.get('data'))
        self.assertIsNotNone(query_output.get('total'))
        total = query_output.get('total')
        self.assertIsNotNone(total.get('value'))

    def test_execute_query_current_month_daily(self):
        """Test execute_query for current month on daily breakdown."""
        query_params = {'filter':
                        {'resolution': 'daily', 'time_scope_value': -1,
                         'time_scope_units': 'month'}}
        handler = AWSReportQueryHandler(query_params, '', self.tenant,
                                        **{'report_type': 'costs'})
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
        handler = AWSReportQueryHandler(query_params, '', self.tenant,
                                        **{'report_type': 'costs'})
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
        handler = AWSReportQueryHandler(query_params, '?group_by[service]=*',
                                        self.tenant,
                                        **{'report_type': 'costs'})
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
        handler = AWSReportQueryHandler(query_params, '?group_by[service]=AmazonEC2',
                                        self.tenant,
                                        **{'report_type': 'costs'})
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

    def test_query_by_partial_filtered_service(self):
        """Test execute_query monthly breakdown by filtered service."""
        query_params = {'filter':
                        {'resolution': 'monthly', 'time_scope_value': -1,
                         'time_scope_units': 'month'},
                        'group_by': {'service': ['eC2']}}
        handler = AWSReportQueryHandler(query_params, '?group_by[service]=eC2',
                                        self.tenant,
                                        **{'report_type': 'costs'})
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
        handler = AWSReportQueryHandler(query_params, '?group_by[account]=*',
                                        self.tenant,
                                        **{'report_type': 'costs'})
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
        handler = AWSReportQueryHandler(query_params, query_string,
                                        self.tenant,
                                        **{'report_type': 'costs'})
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

        with tenant_context(self.tenant):
            instance_type = AWSCostEntryProduct.objects.first().instance_type

        # this may need some additional work, but I think this covers most cases.
        expected = {
            dh.this_month_start.strftime('%Y-%m'): 24,
        }

        query_params = {'filter':
                        {'resolution': 'monthly', 'time_scope_value': -1,
                         'time_scope_units': 'month'}}
        query_string = '?filter[time_scope_value]=-1&filter[resolution]=monthly'
        annotations = {'instance_type':
                       Concat('cost_entry_product__instance_type', Value(''))}
        extras = {'count': 'resource_count',
                  'report_type': 'instance_type',
                  'group_by': ['instance_type'],
                  'annotations': annotations,
                  'filter': {'instance_type__isnull': False}}
        handler = AWSReportQueryHandler(query_params, query_string,
                                        self.tenant,
                                        **extras)
        query_output = handler.execute_query()
        data = query_output.get('data')
        self.assertIsNotNone(data)
        self.assertIsNotNone(query_output.get('total'))

        total = query_output.get('total')
        self.assertIsNotNone(total.get('count'))
        self.assertEqual(total.get('count'), 24)

        for data_item in data:
            instance_types = data_item.get('instance_types')
            for it in instance_types:
                if it['instance_type'] == instance_type:
                    actual_count = it['values'][0].get('count')
                    self.assertEqual(expected.get(data_item['date']), actual_count)

    def test_execute_query_curr_month_by_account_w_limit(self):
        """Test execute_query for current month on monthly breakdown by account with limit."""
        for _ in range(3):
            self.add_data_to_tenant()

        query_params = {'filter':
                        {'resolution': 'monthly', 'time_scope_value': -1,
                         'time_scope_units': 'month', 'limit': 2},
                        'group_by': {'account': ['*']}}
        handler = AWSReportQueryHandler(query_params, '?group_by[account]=*&filter[limit]=2',
                                        self.tenant,
                                        **{'report_type': 'costs'})
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
                        'order_by': {'total': 'asc'}}
        handler = AWSReportQueryHandler(query_params, '?group_by[account]=*',
                                        self.tenant,
                                        **{'report_type': 'costs'})
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

    def test_execute_query_curr_month_by_account_w_order_by_account(self):
        """Test execute_query for current month on monthly breakdown by account with asc order."""
        self.add_data_to_tenant(rate=Decimal('0.299'))
        self.add_data_to_tenant(rate=Decimal('0.099'))
        self.add_data_to_tenant(rate=Decimal('0.999'))

        query_params = {'filter':
                        {'resolution': 'monthly', 'time_scope_value': -1,
                         'time_scope_units': 'month'},
                        'group_by': {'account': ['*']},
                        'order_by': {'account': 'asc'}}
        handler = AWSReportQueryHandler(query_params, '?group_by[account]=*',
                                        self.tenant,
                                        **{'report_type': 'costs'})
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
            current = '0'
            for month_item in month_data:
                self.assertIsInstance(month_item.get('account'), str)
                self.assertIsInstance(month_item.get('values'), list)
                self.assertIsNotNone(month_item.get('values')[0].get('account'))
                data_point = month_item.get('values')[0].get('account')
                self.assertLess(current, data_point)
                current = data_point

    def test_execute_query_curr_month_by_region(self):
        """Test execute_query for current month on monthly breakdown by region."""
        query_params = {'filter':
                        {'resolution': 'monthly', 'time_scope_value': -1,
                         'time_scope_units': 'month'},
                        'group_by': {'region': ['*']}}
        handler = AWSReportQueryHandler(query_params, '?group_by[region]=*',
                                        self.tenant,
                                        **{'report_type': 'costs'})
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
                        'group_by': {'region': ['us-east-2']}}
        handler = AWSReportQueryHandler(query_params, '?group_by[region]=us-east-2',
                                        self.tenant,
                                        **{'report_type': 'costs'})
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
        handler = AWSReportQueryHandler(query_params, '?group_by[avail_zone]=*',
                                        self.tenant,
                                        **{'report_type': 'costs'})
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
        handler = AWSReportQueryHandler(query_params, '?group_by[avail_zone]=us-east-1a',
                                        self.tenant,
                                        **{'report_type': 'costs'})
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
                         'account': [self.account_alias]}}
        handler = AWSReportQueryHandler(query_params, '',
                                        self.tenant,
                                        **{'report_type': 'costs'})
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
        handler = AWSReportQueryHandler(query_params, '',
                                        self.tenant,
                                        **{'report_type': 'costs'})
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
                         'region': ['us-east-2']}}
        handler = AWSReportQueryHandler(query_params, '',
                                        self.tenant,
                                        **{'report_type': 'costs'})
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
        handler = AWSReportQueryHandler(query_params, '',
                                        self.tenant,
                                        **{'report_type': 'costs'})
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
        handler = AWSReportQueryHandler(query_params, '',
                                        self.tenant,
                                        **{'accept_type': 'text/csv',
                                            'report_type': 'costs'})
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
        handler = AWSReportQueryHandler(query_params, '',
                                        self.tenant,
                                        **{'report_type': 'costs'})
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
        handler = AWSReportQueryHandler(query_params, '',
                                        self.tenant,
                                        **{'accept_type': 'text/csv',
                                            'report_type': 'costs'})
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
        handler = AWSReportQueryHandler(query_params, '?group_by[account]=*&filter[limit]=2',
                                        self.tenant,
                                        **{'accept_type': 'text/csv',
                                            'report_type': 'costs'})
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

    def test_execute_query_w_delta(self):
        """Test grouped by deltas."""
        dh = DateHelper()
        current_total = Decimal(0)
        prev_total = Decimal(0)

        account_id = self.payer_account_id
        account_alias = self.account_alias

        kwargs = {'account_id': account_id,
                  'account_alias': account_alias,
                  'bill_start': dh.last_month_start,
                  'bill_end': dh.last_month_end,
                  'data_start': dh.last_month_start,
                  'data_end': dh.last_month_start + timedelta(days=1)}

        for _ in range(0, 3):
            # add some current data.
            self.add_data_to_tenant(account_id=account_id,
                                    account_alias=account_alias)
            # add some previous data.
            self.add_data_to_tenant(**kwargs)

        # fetch the expected sums from the DB.
        with tenant_context(self.tenant):
            curr = AWSCostEntryLineItemDailySummary.objects.filter(
                usage_start__gte=dh.this_month_start,
                usage_end__lte=dh.this_month_end).aggregate(value=Sum('unblended_cost'))
            current_total = Decimal(curr.get('value'))

            prev = AWSCostEntryLineItemDailySummary.objects.filter(
                usage_start__gte=dh.last_month_start,
                usage_end__lte=dh.last_month_end).aggregate(value=Sum('unblended_cost'))
            prev_total = Decimal(prev.get('value'))

        expected_delta_value = Decimal(current_total - prev_total)
        expected_delta_percent = Decimal(
            (current_total - prev_total) / prev_total * 100
        )

        query_params = {'filter':
                        {'resolution': 'monthly',
                         'time_scope_value': -1,
                         'time_scope_units': 'month'},
                        'group_by': {'account': ['*']},
                        'delta': True}
        handler = AWSReportQueryHandler(query_params,
                                        '?group_by[account]=*&delta=True',
                                        self.tenant,
                                        **{'report_type': 'costs'})

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
        expected_delta_value = Decimal(self.current_month_total)
        expected_delta_percent = Decimal(0)

        query_params = {
            'filter': {'time_scope_value': -1},
            'delta': True
        }

        handler = AWSReportQueryHandler(query_params,
                                        '?filter[time_scope_value]=-10&delta=True',
                                        self.tenant,
                                        **{'report_type': 'costs'})
        query_output = handler.execute_query()
        data = query_output.get('data')
        self.assertIsNotNone(data)

        delta = query_output.get('delta')
        self.assertIsNotNone(delta.get('value'))
        self.assertIsNotNone(delta.get('percent'))
        self.assertEqual(delta.get('value'), expected_delta_value)
        self.assertEqual(delta.get('percent'), expected_delta_percent)

    def test_execute_query_orderby_delta(self):
        """Test execute_query with ordering by delta ascending."""
        account_id = self.payer_account_id
        kwargs = {'account_id': account_id,
                  'bill_start': DateHelper().last_month_start,
                  'bill_end': DateHelper().last_month_end,
                  'data_start': DateHelper().last_month_start,
                  'data_end': DateHelper().last_month_start + timedelta(days=1)}

        for _ in range(0, 3):
            # add some current data.
            self.add_data_to_tenant(rate=Decimal(random.random()),
                                    account_id=account_id)
            self.add_data_to_tenant(rate=Decimal(random.random()),
                                    account_id=account_id)
            self.add_data_to_tenant(rate=Decimal(random.random()),
                                    account_id=account_id)

            # add some past data.
            self.add_data_to_tenant(rate=Decimal(random.random()), **kwargs)
            self.add_data_to_tenant(rate=Decimal(random.random()), **kwargs)
            self.add_data_to_tenant(rate=Decimal(random.random()), **kwargs)

            # create another account id for the next loop
            account_id = self.fake.ean(length=13)  # pylint: disable=no-member
            kwargs['account_id'] = account_id

        query_params = {'filter':
                        {'resolution': 'monthly',
                         'time_scope_value': -1,
                         'time_scope_units': 'month'},
                        'order_by': {'delta': 'asc'},
                        'group_by': {'account': ['*']},
                        'delta': True}
        handler = AWSReportQueryHandler(query_params,
                                        '?group_by[account]=*&order_by[delta]=asc&delta=True',
                                        self.tenant,
                                        **{'report_type': 'costs'})
        query_output = handler.execute_query()
        data = query_output.get('data')
        self.assertIsNotNone(data)

        cmonth_str = DateHelper().this_month_start.strftime('%Y-%m')
        for data_item in data:
            month_val = data_item.get('date')
            month_data = data_item.get('accounts')
            self.assertEqual(month_val, cmonth_str)
            self.assertIsInstance(month_data, list)
            current_delta = Decimal(-9000)
            for month_item in month_data:
                self.assertIsInstance(month_item.get('account'), str)
                self.assertIsInstance(month_item.get('values'), list)
                self.assertIsNotNone(month_item.get('values')[0].get('delta_percent'))
                data_point_delta = month_item.get('values')[0].get('delta_percent')
                self.assertLessEqual(current_delta, data_point_delta)
                current_delta = data_point_delta

    def test_execute_query_with_account_alias(self):
        """Test execute_query when account alias is avaiable."""
        query_params = {'filter':
                        {'resolution': 'monthly',
                         'time_scope_value': -1,
                         'time_scope_units': 'month',
                         'limit': 2},
                        'group_by': {'account': ['*']},
                        'delta': 'month'}
        handler = AWSReportQueryHandler(query_params,
                                        '?group_by[account]=*&filter[limit]=2&delta=month',
                                        self.tenant,
                                        **{'report_type': 'costs'})
        query_output = handler.execute_query()
        data = query_output.get('data')

        account_alias = data[0].get('accounts')[0].get('values')[0].get('account_alias')
        self.assertEqual(account_alias, self.account_alias)

    def test_execute_query_orderby_alias(self):
        """Test execute_query when account alias is avaiable."""
        # generate test data
        expected = {self.account_alias: self.payer_account_id}
        for _ in range(0, 3):
            account_id = self.fake.ean(length=13)
            account_alias = self.fake.company()
            expected[account_alias] = account_id

            self.add_data_to_tenant(rate=Decimal(random.random()),
                                    account_id=account_id,
                                    account_alias=account_alias)
        expected = OrderedDict(sorted(expected.items()))

        # execute query
        query_params = {'filter':
                        {'resolution': 'monthly',
                         'time_scope_value': -1,
                         'time_scope_units': 'month'},
                        'group_by': {'account': ['*']},
                        'order_by': {'account_alias': 'asc'}}
        handler = AWSReportQueryHandler(query_params,
                                        '?group_by[account]=[*]&order_by[account_alias]=asc',
                                        self.tenant,
                                        **{'report_type': 'costs'})
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
        query_params = {
            'filter': {
                'resolution': 'monthly',
                'time_scope_value': -1,
                'time_scope_units': 'month'
            }
        }
        handler = AWSReportQueryHandler(
            query_params,
            '',
            self.tenant,
            **{'report_type': 'costs'}
        )
        expected_units = 'USD'
        with tenant_context(self.tenant):
            result = handler.calculate_total(expected_units)

        self.assertEqual(result.get('value'), self.current_month_total)
        self.assertEqual(result.get('units'), expected_units)

    def test_percent_delta(self):
        """Test _percent_delta() utility method."""
        args = [{}, '', self.tenant]
        rqh = AWSReportQueryHandler(*args, **{'report_type': 'costs'})
        self.assertEqual(rqh._percent_delta(10, 5), 100)

    def test_rank_list(self):
        """Test rank list limit with account alias."""
        query_params = {'filter':
                        {'resolution': 'monthly', 'time_scope_value': -1,
                         'time_scope_units': 'month', 'limit': 2},
                        'group_by': {'account': ['*']}}
        handler = AWSReportQueryHandler(query_params, '?group_by[account]=*&filter[limit]=2',
                                        self.tenant,
                                        **{'report_type': 'costs'})
        data_list = [
            {'account': '1', 'account_alias': '1', 'total': 5, 'rank': 1},
            {'account': '2', 'account_alias': '2', 'total': 4, 'rank': 2},
            {'account': '3', 'account_alias': '3', 'total': 3, 'rank': 3},
            {'account': '4', 'account_alias': '4', 'total': 2, 'rank': 4}
        ]
        expected = [
            {'account': '1', 'account_alias': '1', 'total': 5},
            {'account': '2', 'account_alias': '2', 'total': 4},
            {'account': 'Other', 'account_alias': 'Other', 'total': 5}
        ]
        ranked_list = handler._ranked_list(data_list)
        self.assertEqual(ranked_list, expected)

    def test_rank_list_no_account(self):
        """Test rank list limit with out account alias."""
        query_params = {'filter':
                        {'resolution': 'monthly', 'time_scope_value': -1,
                         'time_scope_units': 'month', 'limit': 2},
                        'group_by': {'service': ['*']}}
        handler = AWSReportQueryHandler(query_params, '?group_by[service]=*&filter[limit]=2',
                                        self.tenant,
                                        **{'report_type': 'costs'})
        data_list = [
            {'service': '1', 'total': 5, 'rank': 1},
            {'service': '2', 'total': 4, 'rank': 2},
            {'service': '3', 'total': 3, 'rank': 3},
            {'service': '4', 'total': 2, 'rank': 4}
        ]
        expected = [
            {'service': '1', 'total': 5},
            {'service': '2', 'total': 4},
            {'service': 'Other', 'total': 5}
        ]
        ranked_list = handler._ranked_list(data_list)
        self.assertEqual(ranked_list, expected)
