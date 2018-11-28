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
