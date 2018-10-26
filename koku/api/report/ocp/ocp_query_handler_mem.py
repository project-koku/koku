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
"""OCP Query Handling for Reports."""
from django.db.models import (F,
                              Sum,
                              Window)
from django.db.models.functions import DenseRank
from tenant_schemas.utils import tenant_context

from api.report.ocp.ocp_query_handler import OCPReportQueryHandler


class OCPReportQueryHandlerMem(OCPReportQueryHandler):
    """Handles report queries and responses for AWS."""

    default_ordering = {'memory_usage_gigabytes': 'desc'}

    def __init__(self, query_parameters, url_data,
                 tenant, **kwargs):
        """Establish AWS report query handler.

        Args:
            query_parameters    (Dict): parameters for query
            url_data        (String): URL string to provide order information
            tenant    (String): the tenant to use to access CUR data
            kwargs    (Dict): A dictionary for internal query alteration based on path
        """
        super().__init__(query_parameters, url_data,
                         tenant, self.default_ordering, **kwargs)

    @property
    def order_field(self):
        """Order-by field name.

        The default is 'total'
        """
        order_by = self.query_parameters.get('order_by', self.default_ordering)
        if 'usage' in order_by:
            return 'memory_usage_gigabytes'
        return 'memory_requests_gigabytes'

    def execute_sum_query(self):
        """Execute query and return provided data when self.is_sum == True.

        Returns:
            (Dict): Dictionary response of query params, data, and total

        """
        query_sum = {'value': 0}
        data = []

        q_table = self._mapper._operation_map.get('tables').get('query')
        with tenant_context(self.tenant):
            query = q_table.objects.filter(self.query_filter)
            query_annotations = self._get_annotations()
            query_data = query.annotate(**query_annotations)
            group_by_value = self._get_group_by()
            query_group_by = ['date'] + group_by_value

            query_order_by = ('-date', )
            if self.order_field != 'delta':
                query_order_by += (self.order,)

            mem_usage = self._mapper._report_type_map.get('mem_usage')
            mem_request = self._mapper._report_type_map.get('mem_request')
            query_data = query_data.values(*query_group_by)\
                .annotate(memory_usage_gigabytes=Sum(mem_usage))\
                .annotate(memory_requests_gigabytes=Sum(mem_request))

            if self._mapper.count:
                # This is a sum because the summary table already
                # has already performed counts
                query_data = query_data.annotate(count=Sum(self._mapper.count))

            if self._limit and group_by_value:
                rank_order = getattr(F(group_by_value.pop()), self.order_direction)()
                dense_rank_by_total = Window(
                    expression=DenseRank(),
                    partition_by=F('date'),
                    order_by=rank_order
                )
                query_data = query_data.annotate(rank=dense_rank_by_total)
                query_order_by = query_order_by + ('rank',)

            if self.order_field != 'delta':
                query_data = query_data.order_by(*query_order_by)

            if query.exists():
                query_sum = self.calculate_total(mem_usage, mem_request)

            if self._delta:
                query_data = self.add_deltas(query_data, query_sum)

            is_csv_output = self._accept_type and 'text/csv' in self._accept_type

            if is_csv_output:
                if self._limit:
                    data = self._ranked_list(list(query_data))
                else:
                    data = list(query_data)
            else:
                data = self._apply_group_by(list(query_data))
                data = self._transform_data(query_group_by, 0, data)
        self.query_sum = query_sum
        self.query_data = data
        return self._format_query_response()
