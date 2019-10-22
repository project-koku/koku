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
from decimal import Decimal, DivisionByZero, InvalidOperation

from django.db.models import F, Value, Window
from django.db.models.functions import Coalesce, Concat, RowNumber
from tenant_schemas.utils import tenant_context

from api.report.ocp.provider_map import OCPProviderMap
from api.report.queries import ReportQueryHandler


class OCPReportQueryHandler(ReportQueryHandler):
    """Handles report queries and responses for OCP."""

    provider = 'OCP'

    def __init__(self, parameters):
        """Establish OCP report query handler.

        Args:
            parameters    (QueryParameters): parameter object for query

        """
        self._mapper = OCPProviderMap(provider=self.provider,
                                      report_type=parameters.report_type)
        self.group_by_options = self._mapper.provider_map.get('group_by_options')
        self._limit = parameters.get_filter('limit')

        # super() needs to be called after _mapper and _limit is set
        super().__init__(parameters)
        # super() needs to be called before _get_group_by is called

        # Update which field is used to calculate cost by group by param.
        group_by = self._get_group_by()
        if (group_by and 'project' in group_by
                or 'project' in parameters.get('filter', {}).keys()) \
                and parameters.report_type == 'costs':
            self._report_type = parameters.report_type + '_by_project'
            self._mapper = OCPProviderMap(provider=self.provider,
                                          report_type=parameters.report_type)

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
        fields = self._mapper.provider_map.get('annotations')
        for q_param, db_field in fields.items():
            annotations[q_param] = Concat(db_field, Value(''))
        return annotations

    @property
    def report_annotations(self):
        """Return annotations with the correct capacity field."""
        group_by_value = self._get_group_by()
        annotations = copy.deepcopy(self._mapper.report_type_map.get('annotations'))
        if 'capacity' not in annotations:
            return annotations
        for group in group_by_value:
            if group in ('project', 'cluster', 'node'):
                annotations['capacity'] = annotations['capacity'].get('cluster')
                return annotations

        for filt in self.parameters.get('filter', {}).keys():
            if filt in ('project', 'cluster', 'node'):
                annotations['capacity'] = annotations['capacity'].get('cluster')
                return annotations

        annotations['capacity'] = annotations['capacity'].get('total')
        return annotations

    def _format_query_response(self):
        """Format the query response with data.

        Returns:
            (Dict): Dictionary response of query params, data, and total

        """
        output = copy.deepcopy(self.parameters.parameters)
        output['data'] = self.query_data
        self.query_sum = self._pack_data_object(self.query_sum, **self._mapper.PACK_DEFINITIONS)
        output['total'] = self.query_sum

        if self._delta:
            output['delta'] = self.query_delta

        return output

    def execute_query(self):
        """Execute query and return provided data.

        Returns:
            (Dict): Dictionary response of query params, data, and total

        """
        query_sum = self.initialize_totals()
        data = []

        q_table = self._mapper.query_table
        with tenant_context(self.tenant):
            query = q_table.objects.filter(self.query_filter)
            if self.query_exclusions:
                query = query.exclude(self.query_exclusions)
            query_data = query.annotate(**self.annotations)
            group_by_value = self._get_group_by()

            query_group_by = ['date'] + group_by_value
            query_order_by = ['-date']
            query_order_by.extend([self.order])
            clustered_group_by = self._get_cluster_group_by(query_group_by)

            query_data = query_data.values(*clustered_group_by).annotate(**self.report_annotations)

            if 'cluster' in query_group_by or 'cluster' in self.query_filter:
                query_data = query_data.annotate(cluster_alias=Coalesce('cluster_alias',
                                                                        'cluster_id'))

            if self._limit and group_by_value:
                rank_by_total = self.get_rank_window_function(group_by_value)
                query_data = query_data.annotate(rank=rank_by_total)
                query_order_by.insert(1, 'rank')
                query_data = self._ranked_list(query_data)

            # Populate the 'total' section of the API response
            if query.exists():
                aggregates = self._mapper.report_type_map.get('aggregates')
                metric_sum = query.aggregate(**aggregates)
                query_sum = {key: metric_sum.get(key) for key in aggregates}

            query_data, total_capacity = self.get_cluster_capacity(query_data)
            if total_capacity:
                query_sum.update(total_capacity)

            if self._delta:
                query_data = self.add_deltas(query_data, query_sum)
            is_csv_output = self.parameters.accept_type and 'text/csv' in self.parameters.accept_type

            query_data, query_group_by = self.strip_label_column_name(
                query_data,
                query_group_by
            )
            query_data = self.order_by(query_data, query_order_by)

            if is_csv_output:
                if self._limit:
                    data = self._ranked_list(list(query_data))
                else:
                    data = list(query_data)
            else:
                # Pass in a copy of the group by without the added
                # tag column name prefix
                groups = copy.deepcopy(query_group_by)
                groups.remove('date')
                data = self._apply_group_by(list(query_data), groups)
                data = self._transform_data(query_group_by, 0, data)

        sum_init = {'cost_units': self._mapper.cost_units_key}
        if self._mapper.usage_units_key:
            sum_init['usage_units'] = self._mapper.usage_units_key
        query_sum.update(sum_init)

        ordered_total = {total_key: query_sum[total_key]
                         for total_key in self.report_annotations.keys() if total_key in query_sum}
        ordered_total.update(query_sum)

        self.query_sum = ordered_total
        self.query_data = data
        return self._format_query_response()

    def get_rank_window_function(self, group_by_value):
        """Generate a limit ranking window function."""
        tag_column = self._mapper.tag_column
        rank_orders = []
        rank_field = group_by_value.pop()
        default_ordering = self._mapper.report_type_map.get('default_ordering')

        if self.order_field == 'delta' and '__' in self._delta:
            delta_field_one, delta_field_two = self._delta.split('__')
            rank_orders.append(
                getattr(
                    F(delta_field_one) / F(delta_field_two),
                    self.order_direction
                )()
            )
        elif self.parameters.get('order_by', default_ordering):
            rank_orders.append(
                getattr(F(self.order_field), self.order_direction)()
            )
        if tag_column in rank_field:
            rank_orders.append(self.get_tag_order_by(rank_field))
        else:
            rank_orders.append(
                getattr(F(rank_field), self.order_direction)()
            )

        return Window(
            expression=RowNumber(),
            partition_by=F('date'),
            order_by=rank_orders
        )

    def get_cluster_capacity(self, query_data):
        """Calculate cluster capacity for all nodes over the date range."""
        annotations = self._mapper.report_type_map.get('capacity_aggregate')
        if not annotations:
            return query_data, {}

        cap_key = list(annotations.keys())[0]
        total_capacity = Decimal(0)
        capacity_by_cluster = defaultdict(Decimal)

        q_table = self._mapper.query_table
        query = q_table.objects.filter(self.query_filter)
        query_group_by = ['usage_start', 'cluster_id']

        with tenant_context(self.tenant):
            cap_data = query.values(*query_group_by).annotate(**annotations)
            for entry in cap_data:
                cluster_id = entry.get('cluster_id', '')
                capacity_by_cluster[cluster_id] += entry.get(cap_key, 0)
                total_capacity += entry.get(cap_key, 0)

        if self.resolution == 'monthly':
            for row in query_data:
                cluster_id = row.get('cluster')
                if cluster_id:
                    row[cap_key] = capacity_by_cluster.get(cluster_id, Decimal(0))
                else:
                    row[cap_key] = total_capacity

        return query_data, {cap_key: total_capacity}

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
            delta_value = (Decimal(row.get(delta_field_one, 0)) -  # noqa: W504
                           Decimal(row.get(delta_field_two, 0)))

            row['delta_value'] = delta_value
            try:
                row['delta_percent'] = (row.get(delta_field_one, 0) /  # noqa: W504
                                        row.get(delta_field_two, 0) * 100)
            except (DivisionByZero, ZeroDivisionError, InvalidOperation):
                row['delta_percent'] = None

        total_delta = (Decimal(query_sum.get(delta_field_one, 0)) -  # noqa: W504
                       Decimal(query_sum.get(delta_field_two, 0)))
        try:
            total_delta_percent = (query_sum.get(delta_field_one, 0) /  # noqa: W504
                                   query_sum.get(delta_field_two, 0) * 100)
        except (DivisionByZero, ZeroDivisionError, InvalidOperation):
            total_delta_percent = None

        self.query_delta = {
            'value': total_delta,
            'percent': total_delta_percent
        }

        return query_data
