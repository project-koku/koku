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
import copy
from decimal import Decimal
from unittest.mock import patch

from tenant_schemas.utils import tenant_context

from api.iam.test.iam_test_case import IamTestCase
from api.report.ocp.ocp_query_handler import OCPReportQueryHandler
from api.report.test.ocp.helpers import OCPReportDataGenerator
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

        aggregates = handler._mapper._report_type_map.get('aggregates')
        current_totals = self.get_totals_by_time_scope(aggregates)
        query_output = handler.execute_query()
        self.assertIsNotNone(query_output.get('data'))
        self.assertIsNotNone(query_output.get('total'))
        total = query_output.get('total')
        self.assertEqual(total.get('usage').quantize(Decimal('0.001')),
                         current_totals.get('usage').quantize(Decimal('0.001')))
        self.assertEqual(total.get('request').quantize(Decimal('0.001')),
                         current_totals.get('request').quantize(Decimal('0.001')))
        self.assertEqual(total.get('charge').quantize(Decimal('0.001')),
                         current_totals.get('charge').quantize(Decimal('0.001')))
        self.assertEqual(total.get('limit').quantize(Decimal('0.001')),
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
        aggregates = handler._mapper._report_type_map.get('aggregates')
        current_totals = self.get_totals_by_time_scope(aggregates)
        query_output = handler.execute_query()
        self.assertIsNotNone(query_output.get('data'))
        self.assertIsNotNone(query_output.get('total'))
        total = query_output.get('total')
        self.assertEqual(total.get('charge').quantize(Decimal('0.001')),
                         current_totals.get('charge').quantize(Decimal('0.001')))

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

    def test_get_cluster_capacity_daily_resolution(self):
        """Test that cluster capacity is unaltered for daily resolution."""
        query_params = {
            'filter': {
                'resolution': 'daily',
                'time_scope_value': -2,
                'time_scope_units': 'month'
            }
        }
        handler = OCPReportQueryHandler(
            query_params,
            '',
            self.tenant,
            **{'report_type': 'cpu'}
        )
        query_data = [{'capacity': -1}]
        expected = copy.deepcopy(query_data)
        query_data, total_capacity = handler.get_cluster_capacity(query_data)
        self.assertTrue('capacity' in total_capacity)
        self.assertTrue(isinstance(total_capacity['capacity'], Decimal))
        self.assertEqual(query_data, expected)

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

        q_table = handler._mapper._operation_map.get('tables').get('query')
        with tenant_context(self.tenant):
            query = q_table.objects.filter(handler.query_filter)
            query_data = query.annotate(**handler.annotations)
            group_by_value = handler._get_group_by()
            query_group_by = ['date'] + group_by_value
            query_order_by = ('-date', )
            query_order_by += (handler.order,)

            annotations = handler._mapper._report_type_map.get('annotations')
            query_data = query_data.values(*query_group_by).annotate(**annotations)

            aggregates = handler._mapper._report_type_map.get('aggregates')
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
