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
import copy
from collections import defaultdict
from decimal import Decimal, DivisionByZero

from django.db.models import F, Value, Window
from django.db.models.functions import Concat
from django.db.models.functions import RowNumber
from tenant_schemas.utils import tenant_context

from api.report.queries import ReportQueryHandler


class OCPReportQueryHandler(ReportQueryHandler):
    """Handles report queries and responses for OCP."""

    group_by_options = ['cluster', 'project', 'node']

    def __init__(self, query_parameters, url_data,
                 tenant, **kwargs):
        """Establish OCP report query handler.

        Args:
            query_parameters    (Dict): parameters for query
            url_data        (String): URL string to provide order information
            tenant    (String): the tenant to use to access CUR data
            kwargs    (Dict): A dictionary for internal query alteration based on path
        """
        kwargs['provider'] = 'OCP'
        super().__init__(query_parameters, url_data,
                         tenant, self.group_by_options, **kwargs)

    @property
    def annotations(self):
        """Create dictionary for query annotations.

        Args:
            fields (dict): Fields to create annotations for

        Returns:
            (Dict): query annotations dictionary

        """
        annotations = {'date': self.date_trunc('usage_start')}

        # { query_param: database_field_name }
        fields = self._mapper._operation_map.get('annotations')
        for q_param, db_field in fields.items():
            annotations[q_param] = Concat(db_field, Value(''))

        return annotations

    def _format_query_response(self):
        """Format the query response with data.

        Returns:
            (Dict): Dictionary response of query params, data, and total

        """
        output = copy.deepcopy(self.query_parameters)
        output['data'] = self.query_data
        output['total'] = self.query_sum

        if self._delta:
            output['delta'] = self.query_delta

        return output

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
            query_data = query.annotate(**self.annotations)
            group_by_value = self._get_group_by()
            query_group_by = ['date'] + group_by_value
            query_order_by = ('-date', )
            query_order_by += (self.order,)

            annotations = self._mapper._report_type_map.get('annotations')
            query_data = query_data.values(*query_group_by).annotate(**annotations)

            if self._limit and group_by_value:
                rank_order = getattr(F(group_by_value.pop()), self.order_direction)()

                if self.order_field == 'delta' and '__' in self._delta:
                    delta_field_one, delta_field_two = self._delta.split('__')
                    rank_order = getattr(
                        F(delta_field_one) / F(delta_field_two),
                        self.order_direction
                    )()

                rank_by_total = Window(
                    expression=RowNumber(),
                    partition_by=F('date'),
                    order_by=rank_order
                )
                query_data = query_data.annotate(rank=rank_by_total)
                query_order_by = query_order_by + ('rank',)
                query_data = self._ranked_list(query_data)

            # Populate the 'total' section of the API response
            if query.exists():
                aggregates = self._mapper._report_type_map.get('aggregates')
                metric_sum = query.aggregate(**aggregates)
                query_sum = {key: metric_sum.get(key) for key in aggregates}

            if self._delta:
                query_data = self.add_deltas(query_data, query_sum)
            is_csv_output = self._accept_type and 'text/csv' in self._accept_type

            query_data = self.order_by(query_data, query_order_by)

            if is_csv_output:
                if self._limit:
                    data = self._ranked_list(list(query_data))
                else:
                    data = list(query_data)
            else:
                data = self._apply_group_by(list(query_data))
                data = self._transform_data(query_group_by, 0, data)

        total_capacity = self.get_cluster_capacity()
        if total_capacity:
            query_sum.update(total_capacity)
        query_sum.update({'units': self._mapper.units_key})

        self.query_sum = query_sum
        self.query_data = data
        return self._format_query_response()

    def execute_query(self):
        """Execute query and return provided data.

        Returns:
            (Dict): Dictionary response of query params, data, and total

        """
        return self.execute_sum_query()

    def get_cluster_capacity(self):
        """Calculate cluster capacity for all nodes over the date range."""
        annotations = self._mapper._report_type_map.get('capacity_aggregate')
        if not annotations:
            return {}

        cap_key = list(annotations.keys())[0]
        cluster_capacity = defaultdict(Decimal)
        q_table = self._mapper._operation_map.get('tables').get('query')
        query = q_table.objects.filter(self.query_filter)
        query_group_by = ['usage_start']

        with tenant_context(self.tenant):
            query_data = query.values(*query_group_by).annotate(**annotations)
            for entry in query_data:
                date = self.date_to_string(entry.get('usage_start'))
                if entry.get(cap_key):
                    cluster_capacity[date] += entry.get(cap_key)
            total_capacity = Decimal(sum(cluster_capacity.values()))

        return {cap_key: total_capacity}


    def add_deltas(self, query_data, query_sum):
        """Calculate and add cost deltas to a result set.

        Args:
            query_data (list) The existing query data from execute_query
            query_sum (list) The sum returned by calculate_totals

        Returns:
            (dict) query data with new with keys "value" and "percent"

        """
        if '__' in self._delta:
            return self.add_current_month_deltas(query_data, query_sum)
        else:
            return super().add_deltas(query_data, query_sum)

    def add_current_month_deltas(self, query_data, query_sum):
        """Add delta to the resultset using current month comparisons."""
        delta_field_one, delta_field_two = self._delta.split('__')

        for row in query_data:
            delta_value = (Decimal(row.get(delta_field_one, 0))
                           - Decimal(row.get(delta_field_two, 0)))

            row['delta_value'] = delta_value
            try:
                row['delta_percent'] = (row.get(delta_field_one, 0)
                                        / row.get(delta_field_two, 0) * 100)
            except (DivisionByZero, ZeroDivisionError):
                row['delta_percent'] = 0


        total_delta = (Decimal(query_sum.get(delta_field_one, 0))
                           - Decimal(query_sum.get(delta_field_two, 0)))
        try:
            total_delta_percent = (query_sum.get(delta_field_one, 0)
                                   / query_sum.get(delta_field_two, 0) * 100)
        except (DivisionByZero, ZeroDivisionError):
                total_delta_percent = 0

        self.query_delta = {
            'value': total_delta,
            'percent': total_delta_percent
        }

        return query_data
