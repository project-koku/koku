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
from collections import defaultdict
from decimal import Decimal
from unittest.mock import patch
from urllib.parse import quote_plus, urlencode

from django.db.models import Max
from django.db.models.expressions import OrderBy
from tenant_schemas.utils import tenant_context

from api.iam.test.iam_test_case import IamTestCase
from api.query_filter import QueryFilterCollection
from api.report.ocp.ocp_query_handler import OCPReportQueryHandler
from api.report.test.ocp.helpers import OCPReportDataGenerator
from api.tags.ocp.ocp_tag_query_handler import OCPTagQueryHandler
from api.utils import DateHelper
from reporting.models import OCPUsageLineItemDailySummary


class OCPReportQueryHandlerTest(IamTestCase):
    """Tests for the OCP report query handler."""

    @classmethod
    def setUpClass(cls):
        """Set up the test class."""
        super().setUpClass()
        cls.dh = DateHelper()

        cls.this_month_filter = {'usage_start__gte': cls.dh.this_month_start}
        cls.ten_day_filter = {'usage_start__gte': cls.dh.n_days_ago(cls.dh.today, 9)}
        cls.thirty_day_filter = {'usage_start__gte': cls.dh.n_days_ago(cls.dh.today, 29)}
        cls.last_month_filter = {'usage_start__gte': cls.dh.last_month_start,
                                 'usage_end__lte': cls.dh.last_month_end}

    def setUp(self):
        """Set up the customer view tests."""
        super().setUp()
        OCPReportDataGenerator(self.tenant).add_data_to_tenant()

    def get_totals_by_time_scope(self, aggregates, filter=None):
        """Return the total aggregates for a time period."""
        if filter is None:
            filter = self.ten_day_filter
        with tenant_context(self.tenant):
            return OCPUsageLineItemDailySummary.objects\
                .filter(**filter)\
                .aggregate(**aggregates)

    def test_execute_sum_query(self):
        """Test that the sum query runs properly."""
        query_params = {}
        handler = OCPReportQueryHandler(
            query_params,
            '',
            self.tenant,
            **{'report_type': 'cpu'}
        )

        aggregates = handler._mapper.report_type_map.get('aggregates')
        current_totals = self.get_totals_by_time_scope(aggregates)
        query_output = handler.execute_query()
        self.assertIsNotNone(query_output.get('data'))
        self.assertIsNotNone(query_output.get('total'))
        total = query_output.get('total')
        self.assertEqual(total.get('usage', {}).get('value').quantize(Decimal('0.001')),
                         current_totals.get('usage').quantize(Decimal('0.001')))
        self.assertEqual(total.get('request', {}).get('value').quantize(Decimal('0.001')),
                         current_totals.get('request').quantize(Decimal('0.001')))
        self.assertEqual(total.get('cost', {}).get('value').quantize(Decimal('0.001')),
                         current_totals.get('cost').quantize(Decimal('0.001')))
        self.assertEqual(total.get('limit', {}).get('value').quantize(Decimal('0.001')),
                         current_totals.get('limit').quantize(Decimal('0.001')))

    def test_execute_sum_query_charge(self):
        """Test that the sum query runs properly for the charge endpoint."""
        query_params = {}
        handler = OCPReportQueryHandler(
            query_params,
            '',
            self.tenant,
            **{'report_type': 'charge'}
        )
        aggregates = handler._mapper.report_type_map.get('aggregates')
        current_totals = self.get_totals_by_time_scope(aggregates)
        query_output = handler.execute_query()
        self.assertIsNotNone(query_output.get('data'))
        self.assertIsNotNone(query_output.get('total'))
        total = query_output.get('total')
        self.assertEqual(total.get('cost', {}).get('value').quantize(Decimal('0.001')),
                         current_totals.get('cost').quantize(Decimal('0.001')))

    def test_get_cluster_capacity_monthly_resolution(self):
        """Test that cluster capacity returns a full month's capacity."""
        query_params = {'filter': {'resolution': 'monthly',
                                   'time_scope_value': -1,
                                   'time_scope_units': 'month'},
                        }
        query_string = '?filter[resolution]=monthly&' + \
                       'filter[time_scope_value]=-1&' + \
                       'filter[time_scope_units]=month&'

        handler = OCPReportQueryHandler(
            query_params,
            query_string,
            self.tenant,
            **{'report_type': 'cpu'}
        )
        query_data = [{'row': 1}]
        query_data, total_capacity = handler.get_cluster_capacity(query_data)
        self.assertTrue('capacity' in total_capacity)
        self.assertTrue(isinstance(total_capacity['capacity'], Decimal))
        self.assertTrue('capacity' in query_data[0])
        self.assertEqual(query_data[0].get('capacity'),
                         total_capacity.get('capacity'))

    def test_get_cluster_capacity_monthly_resolution_group_by_cluster(self):
        """Test that cluster capacity returns capacity by cluster."""
        # Add data for a second cluster
        OCPReportDataGenerator(self.tenant).add_data_to_tenant()

        query_params = {'filter': {'resolution': 'monthly',
                                   'time_scope_value': -1,
                                   'time_scope_units': 'month'},
                        'group_by': {'cluster': ['*']},
                        }
        query_string = '?filter[resolution]=monthly&' + \
                       'filter[time_scope_value]=-1&' + \
                       'filter[time_scope_units]=month&' + \
                       'group_by[cluster]=*'

        handler = OCPReportQueryHandler(
            query_params,
            query_string,
            self.tenant,
            **{'report_type': 'cpu'}
        )

        query_data = handler.execute_query()

        capacity_by_cluster = defaultdict(Decimal)
        total_capacity = Decimal(0)
        query_filter = handler.query_filter
        query_group_by = ['usage_start', 'cluster_id']
        annotations = {'capacity': Max('cluster_capacity_cpu_core_hours')}
        cap_key = list(annotations.keys())[0]

        q_table = handler._mapper.provider_map.get('tables').get('query')
        query = q_table.objects.filter(query_filter)

        with tenant_context(self.tenant):
            cap_data = query.values(*query_group_by).annotate(**annotations)
            for entry in cap_data:
                cluster_id = entry.get('cluster_id', '')
                capacity_by_cluster[cluster_id] += entry.get(cap_key, 0)
                total_capacity += entry.get(cap_key, 0)

        for entry in query_data.get('data', []):
            for cluster in entry.get('clusters', []):
                cluster_name = cluster.get('cluster', '')
                capacity = cluster.get('values')[0].get('capacity', {}).get('value')
                self.assertEqual(capacity, capacity_by_cluster[cluster_name])

        self.assertEqual(query_data.get('total', {}).get('capacity', {}).get('value'),
                         total_capacity)

    def test_get_cluster_capacity_daily_resolution(self):
        """Test that total capacity is returned daily resolution."""
        query_params = {
            'filter': {
                'resolution': 'daily',
                'time_scope_value': -1,
                'time_scope_units': 'month'
            }
        }
        handler = OCPReportQueryHandler(
            query_params,
            '',
            self.tenant,
            **{'report_type': 'cpu'}
        )

        query_data = handler.execute_query()

        daily_capacity = defaultdict(Decimal)
        total_capacity = Decimal(0)
        query_filter = handler.query_filter
        query_group_by = ['usage_start']
        annotations = {'capacity': Max('total_capacity_cpu_core_hours')}
        cap_key = list(annotations.keys())[0]

        q_table = handler._mapper.provider_map.get('tables').get('query')
        query = q_table.objects.filter(query_filter)

        with tenant_context(self.tenant):
            cap_data = query.values(*query_group_by).annotate(**annotations)
            for entry in cap_data:
                date = handler.date_to_string(entry.get('usage_start'))
                daily_capacity[date] += entry.get(cap_key, 0)
            # This is a hack because the total capacity in the test data
            # is artificial but the total should still be a sum of
            # cluster capacities
            annotations = {'capacity': Max('cluster_capacity_cpu_core_hours')}
            cap_data = query.values(*query_group_by).annotate(**annotations)
            for entry in cap_data:
                total_capacity += entry.get(cap_key, 0)

        self.assertEqual(query_data.get('total', {}).get('capacity', {}).get('value'), total_capacity)
        for entry in query_data.get('data', []):
            date = entry.get('date')
            values = entry.get('values')
            if values:
                capacity = values[0].get('capacity', {}).get('value')
                self.assertEqual(capacity, daily_capacity[date])

    def test_get_cluster_capacity_daily_resolution_group_by_clusters(self):
        """Test that cluster capacity returns daily capacity by cluster."""
        query_params = {'filter': {'resolution': 'daily',
                                   'time_scope_value': -1,
                                   'time_scope_units': 'month'},
                        'group_by': {'cluster': ['*']},
                        }
        query_string = '?filter[resolution]=daily&' + \
                       'filter[time_scope_value]=-1&' + \
                       'filter[time_scope_units]=month&' + \
                       'group_by[cluster]=*'

        handler = OCPReportQueryHandler(
            query_params,
            query_string,
            self.tenant,
            **{'report_type': 'cpu'}
        )

        query_data = handler.execute_query()

        daily_capacity_by_cluster = defaultdict(dict)
        total_capacity = Decimal(0)
        query_filter = handler.query_filter
        query_group_by = ['usage_start', 'cluster_id']
        annotations = {'capacity': Max('cluster_capacity_cpu_core_hours')}
        cap_key = list(annotations.keys())[0]

        q_table = handler._mapper.query_table
        query = q_table.objects.filter(query_filter)

        with tenant_context(self.tenant):
            cap_data = query.values(*query_group_by).annotate(**annotations)
            for entry in cap_data:
                date = handler.date_to_string(entry.get('usage_start'))
                cluster_id = entry.get('cluster_id', '')
                if cluster_id in daily_capacity_by_cluster[date]:
                    daily_capacity_by_cluster[date][cluster_id] += entry.get(cap_key, 0)
                else:
                    daily_capacity_by_cluster[date][cluster_id] = entry.get(cap_key, 0)
                total_capacity += entry.get(cap_key, 0)

        for entry in query_data.get('data', []):
            date = entry.get('date')
            for cluster in entry.get('clusters', []):
                cluster_name = cluster.get('cluster', '')
                capacity = cluster.get('values')[0].get('capacity', {}).get('value')
                self.assertEqual(capacity, daily_capacity_by_cluster[date][cluster_name])

        self.assertEqual(query_data.get('total', {}).get('capacity', {}).get('value'),
                         total_capacity)

    @patch('api.report.ocp.ocp_query_handler.ReportQueryHandler.add_deltas')
    @patch('api.report.ocp.ocp_query_handler.OCPReportQueryHandler.add_current_month_deltas')
    def test_add_deltas_current_month(self, mock_current_deltas, mock_deltas):
        """Test that the current month method is called for deltas."""
        query_params = {}
        handler = OCPReportQueryHandler(
            query_params,
            '',
            self.tenant,
            **{'report_type': 'cpu'}
        )
        handler._delta = 'usage__request'

        handler.add_deltas([], [])

        mock_current_deltas.assert_called()
        mock_deltas.assert_not_called()

    @patch('api.report.ocp.ocp_query_handler.ReportQueryHandler.add_deltas')
    @patch('api.report.ocp.ocp_query_handler.OCPReportQueryHandler.add_current_month_deltas')
    def test_add_deltas_super_delta(self, mock_current_deltas, mock_deltas):
        """Test that the super delta method is called for deltas."""
        query_params = {}
        handler = OCPReportQueryHandler(
            query_params,
            '',
            self.tenant,
            **{'report_type': 'cpu'}
        )
        handler._delta = 'usage'

        handler.add_deltas([], [])

        mock_current_deltas.assert_not_called()
        mock_deltas.assert_called()

    def test_add_current_month_deltas(self):
        """Test that current month deltas are calculated."""
        query_params = {}
        handler = OCPReportQueryHandler(
            query_params,
            '',
            self.tenant,
            **{'report_type': 'cpu'}
        )
        handler._delta = 'usage__request'

        q_table = handler._mapper.provider_map.get('tables').get('query')
        with tenant_context(self.tenant):
            query = q_table.objects.filter(handler.query_filter)
            query_data = query.annotate(**handler.annotations)
            group_by_value = handler._get_group_by()
            query_group_by = ['date'] + group_by_value
            query_order_by = ('-date', )
            query_order_by += (handler.order,)

            annotations = handler.report_annotations
            query_data = query_data.values(*query_group_by).annotate(**annotations)

            aggregates = handler._mapper.report_type_map.get('aggregates')
            metric_sum = query.aggregate(**aggregates)
            query_sum = {key: metric_sum.get(key) for key in aggregates}

            result = handler.add_current_month_deltas(query_data, query_sum)

            delta_field_one, delta_field_two = handler._delta.split('__')
            field_one_total = Decimal(0)
            field_two_total = Decimal(0)
            for entry in result:
                field_one_total += entry.get(delta_field_one, 0)
                field_two_total += entry.get(delta_field_two, 0)
                delta_percent = entry.get('delta_percent')
                expected = (entry.get(delta_field_one, 0) / entry.get(delta_field_two, 0) * 100) \
                    if entry.get(delta_field_two) else 0
                self.assertEqual(delta_percent, expected)

            expected_total = field_one_total / field_two_total * 100 if field_two_total != 0 else 0

            self.assertEqual(handler.query_delta.get('percent'), expected_total)

    def test_add_current_month_deltas_no_previous_data_wo_query_data(self):
        """Test that current month deltas are calculated with no previous month data."""
        OCPReportDataGenerator(self.tenant).remove_data_from_tenant()
        OCPReportDataGenerator(self.tenant, current_month_only=True).add_data_to_tenant()

        query_params = {'filter': {'resolution': 'monthly',
                                   'time_scope_value': -2,
                                   'limit': 1},
                        }
        query_string = '?filter[resolution]=monthly&' + \
                       'filter[time_scope_value]=-2&' + \
                       'filter[limit]=1'

        handler = OCPReportQueryHandler(
            query_params,
            query_string,
            self.tenant,
            **{'report_type': 'cpu'}
        )
        handler._delta = 'usage__request'

        q_table = handler._mapper.provider_map.get('tables').get('query')
        with tenant_context(self.tenant):
            query = q_table.objects.filter(handler.query_filter)
            query_data = query.annotate(**handler.annotations)
            group_by_value = handler._get_group_by()
            query_group_by = ['date'] + group_by_value
            query_order_by = ('-date', )
            query_order_by += (handler.order,)

            annotations = annotations = handler.report_annotations
            query_data = query_data.values(*query_group_by).annotate(**annotations)

            aggregates = handler._mapper.report_type_map.get('aggregates')
            metric_sum = query.aggregate(**aggregates)
            query_sum = {key: metric_sum.get(key) if metric_sum.get(key) else Decimal(0) for key in aggregates}

            result = handler.add_current_month_deltas(query_data, query_sum)

            self.assertEqual(result, query_data)
            self.assertEqual(handler.query_delta['value'], Decimal(0))
            self.assertIsNone(handler.query_delta['percent'])

    def test_add_current_month_deltas_no_previous_data_w_query_data(self):
        """Test that current month deltas are calculated with no previous data for field two."""
        OCPReportDataGenerator(self.tenant).remove_data_from_tenant()
        OCPReportDataGenerator(self.tenant, current_month_only=True).add_data_to_tenant()

        query_params = {'filter': {'resolution': 'monthly',
                                   'time_scope_value': -1,
                                   'limit': 1},
                        }
        query_string = '?filter[resolution]=monthly&' + \
                       'filter[time_scope_value]=-1&' + \
                       'filter[limit]=1'

        handler = OCPReportQueryHandler(
            query_params,
            query_string,
            self.tenant,
            **{'report_type': 'cpu'}
        )
        handler._delta = 'usage__foo'

        q_table = handler._mapper.provider_map.get('tables').get('query')
        with tenant_context(self.tenant):
            query = q_table.objects.filter(handler.query_filter)
            query_data = query.annotate(**handler.annotations)
            group_by_value = handler._get_group_by()
            query_group_by = ['date'] + group_by_value
            query_order_by = ('-date', )
            query_order_by += (handler.order,)

            annotations = annotations = handler.report_annotations
            query_data = query_data.values(*query_group_by).annotate(**annotations)

            aggregates = handler._mapper.report_type_map.get('aggregates')
            metric_sum = query.aggregate(**aggregates)
            query_sum = {key: metric_sum.get(key) if metric_sum.get(key) else Decimal(0) for key in aggregates}

            result = handler.add_current_month_deltas(query_data, query_sum)

            self.assertEqual(result, query_data)
            self.assertIsNotNone(handler.query_delta['value'])
            self.assertIsNone(handler.query_delta['percent'])

    def test_strip_label_column_name(self):
        """Test that the tag column name is stripped from results."""
        query_params = {}
        handler = OCPReportQueryHandler(
            query_params,
            '',
            self.tenant,
            **{'report_type': 'cpu'}
        )
        tag_column = handler._mapper.provider_map.get('tag_column')
        data = [
            {f'{tag_column}__tag_key1': 'value'},
            {f'{tag_column}__tag_key2': 'value'}
        ]
        group_by = ['date', f'{tag_column}__tag_key1', f'{tag_column}__tag_key2']

        expected_data = [
            {'tag_key1': 'value'},
            {'tag_key2': 'value'}
        ]
        expected_group_by = ['date', 'tag_key1', 'tag_key2']

        result_data, result_group_by = handler.strip_label_column_name(
            data, group_by
        )

        self.assertEqual(result_data, expected_data)
        self.assertEqual(result_group_by, expected_group_by)

    def test_get_tag_filter_keys(self):
        """Test that filter params with tag keys are returned."""
        handler = OCPTagQueryHandler('', {}, self.tenant)
        tag_keys = handler.get_tag_keys(filters=False)

        key_of_interest = tag_keys[0]

        query_params = {
            'filter': {
                'resolution': 'monthly',
                'time_scope_value': -1,
                'time_scope_units': 'month',
                key_of_interest: ['']
            }
        }
        handler = OCPReportQueryHandler(
            query_params,
            f'?filter[{key_of_interest}]=\'\'',
            self.tenant,
            **{
                'report_type': 'cpu',
                'tag_keys': tag_keys
            }
        )

        results = handler.get_tag_filter_keys()

        self.assertEqual(results, [key_of_interest])

    def test_get_tag_group_by_keys(self):
        """Test that group_by params with tag keys are returned."""
        handler = OCPTagQueryHandler('', {}, self.tenant)
        tag_keys = handler.get_tag_keys(filters=False)

        key_of_interest = tag_keys[0]

        query_params = {
            'group_by': {
                key_of_interest: ['']
            }
        }
        handler = OCPReportQueryHandler(
            query_params,
            f'?filter[{key_of_interest}]=\'\'',
            self.tenant,
            **{
                'report_type': 'cpu',
                'tag_keys': tag_keys
            }
        )

        results = handler.get_tag_group_by_keys()

        self.assertEqual(results, [key_of_interest])

    def test_set_tag_filters(self):
        """Test that tag filters are created properly."""
        filters = QueryFilterCollection()

        handler = OCPTagQueryHandler('', {}, self.tenant)
        tag_keys = handler.get_tag_keys(filters=False)

        filter_key = tag_keys[0]

        filter_value = 'filter'
        group_by_key = tag_keys[1]

        group_by_value = 'group_By'

        query_params = {
            'filter': {filter_key: [filter_value]},
            'group_by': {group_by_key: [group_by_value]}
        }

        handler = OCPReportQueryHandler(
            query_params,
            '',
            self.tenant,
            **{
                'report_type': 'cpu',
                'tag_keys': tag_keys
            }
        )

        filters = handler._set_tag_filters(filters)

        expected = f"""<class 'api.query_filter.QueryFilterCollection'>: (AND: ('pod_labels__{filter_key}__icontains', '{filter_value}')), (AND: ('pod_labels__{group_by_key}__icontains', '{group_by_value}')), """  # noqa: E501

        self.assertEqual(repr(filters), expected)

    def test_get_exclusions(self):
        """Test that exclusions are properly set."""
        handler = OCPTagQueryHandler('', {}, self.tenant)
        tag_keys = handler.get_tag_keys(filters=False)

        group_by_key = tag_keys[0]

        group_by_value = 'group_By'
        query_params = {
            'group_by': {group_by_key: [group_by_value]}
        }

        handler = OCPReportQueryHandler(
            query_params,
            '',
            self.tenant,
            **{
                'report_type': 'cpu',
                'tag_keys': tag_keys
            }
        )

        exclusions = handler._get_exclusions()
        expected = f"<Q: (AND: ('pod_labels__{group_by_key}__isnull', True))>"
        self.assertEqual(repr(exclusions), expected)

    def test_get_tag_group_by(self):
        """Test that tag based group bys work."""
        handler = OCPTagQueryHandler('', {}, self.tenant)
        tag_keys = handler.get_tag_keys(filters=False)

        group_by_key = tag_keys[0]

        group_by_value = 'group_by'
        query_params = {
            'group_by': {group_by_key: [group_by_value]}
        }

        param_string = urlencode(query_params, quote_via=quote_plus)

        handler = OCPReportQueryHandler(
            query_params,
            param_string,
            self.tenant,
            **{
                'report_type': 'cpu',
                'tag_keys': tag_keys
            }
        )

        group_by = handler._get_tag_group_by()
        group = group_by[0]
        expected = 'pod_labels__' + group_by_key
        self.assertEqual(len(group_by), 1)
        self.assertEqual(group[0], expected)

    def test_get_tag_order_by(self):
        """Verify that a propery order by is returned."""
        tag = 'pod_labels__key'

        expected_param = (tag.split('__')[1], )

        query_params = {}
        handler = OCPReportQueryHandler(
            query_params,
            '',
            self.tenant,
            **{'report_type': 'cpu'}
        )
        result = handler.get_tag_order_by(tag)
        expression = result.expression

        self.assertIsInstance(result, OrderBy)
        self.assertEqual(expression.sql, 'pod_labels -> %s')
        self.assertEqual(expression.params, expected_param)
