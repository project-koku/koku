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

from django.db.models import Sum
from tenant_schemas.utils import tenant_context

from api.report.ocp.ocp_query_handler import OCPReportQueryHandler
from api.report.test.ocp.test_ocp_query_handler_base import OCPReportQueryHandlerBaseTest
from reporting.models import OCPUsageLineItemDailySummary


class OCPReportQueryHandlerTest(OCPReportQueryHandlerBaseTest):
    """Tests for the report query handler."""

    def get_totals_by_time_scope(self, filter=None):
        """Return the total aggregates for a time period."""
        if filter is None:
            filter = self.ten_day_filter
        with tenant_context(self.tenant):
            return OCPUsageLineItemDailySummary.objects\
                .filter(**filter)\
                .aggregate(
                    usage=Sum('pod_usage_cpu_core_hours'),
                    request=Sum('pod_request_cpu_core_hours'),
                    charge=Sum('pod_charge_cpu_cores')
                )

    def test_execute_sum_query(self):
        """Test that the sum query runs properly."""
        current_totals = self.get_totals_by_time_scope()
        query_params = {}
        handler = OCPReportQueryHandler(
            query_params,
            '',
            self.tenant,
            **{'report_type': 'cpu'}
        )
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
