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
from collections import OrderedDict
from decimal import Decimal

from django.db.models import (F,
                              Sum,
                              Value,
                              Window)
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

    def _get_annotations(self, fields=None):
        """Create dictionary for query annotations.

        Args:
            fields (dict): Fields to create annotations for

        Returns:
            (Dict): query annotations dictionary

        """
        annotations = {
            'date': self.date_trunc('usage_start'),
            # 'units': Concat(self._mapper.units_key, Value(''))  Try and generalize this
        }
        if self._annotations and not self.is_sum:
            annotations.update(self._annotations)

        # { query_param: database_field_name }
        if not fields:
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

    def _create_previous_totals(self, previous_query, query_group_by):
        """Get totals from the time period previous to the current report.

        Args:
            previous_query (Query): A Django ORM query
            query_group_by (dict): The group by dict for the current report
        Returns:
            (dict) A dictionary keyed off the grouped values for the report

        """
        date_delta = self._get_date_delta()
        # Added deltas for each grouping
        # e.g. date, account, region, availability zone, et cetera
        query_annotations = self._get_annotations()
        previous_sums = previous_query.annotate(**query_annotations)
        delta_field = self._mapper._report_type_map.get('delta_key').get(self._delta)
        delta_annotation = {self._delta: delta_field}
        previous_sums = previous_sums\
            .values(*query_group_by)\
            .annotate(**delta_annotation)
        previous_dict = OrderedDict()
        for row in previous_sums:
            date = self.string_to_date(row['date'])
            date = date + date_delta
            row['date'] = self.date_to_string(date)
            key = tuple((row[key] for key in query_group_by))
            previous_dict[key] = row[self._delta]

        return previous_dict

    def add_deltas(self, query_data, query_sum):
        """Calculate and add cost deltas to a result set.

        Args:
            query_data (list) The existing query data from execute_query
            query_sum (list) The sum returned by calculate_totals

        Returns:
            (dict) query data with new with keys "value" and "percent"

        """
        delta_group_by = ['date'] + self._get_group_by()
        delta_filter = self._get_filter(delta=True)
        q_table = self._mapper._operation_map.get('tables').get('previous_query')
        previous_query = q_table.objects.filter(delta_filter)
        previous_dict = self._create_previous_totals(previous_query,
                                                     delta_group_by)
        for row in query_data:
            key = tuple((row[key] for key in delta_group_by))
            previous_total = previous_dict.get(key, 0)
            current_total = row.get(self._delta, 0)
            row['delta_value'] = current_total - previous_total
            row['delta_percent'] = self._percent_delta(current_total, previous_total)
        # Calculate the delta on the total aggregate
        current_total_sum = Decimal(query_sum.get(self._delta) or 0)
        delta_field = self._mapper._report_type_map.get('delta_key').get(self._delta)
        # aggregate = self._mapper._report_type_map.get('aggregates').get(self._delta)
        prev_total_sum = previous_query.aggregate(value=delta_field)
        prev_total_sum = Decimal(prev_total_sum.get('value') or 0)

        total_delta = current_total_sum - prev_total_sum
        total_delta_percent = self._percent_delta(current_total_sum,
                                                  prev_total_sum)

        self.query_delta = {
            'value': total_delta,
            'percent': total_delta_percent
        }

        if self.order_field == 'delta':
            reverse = True if self.order_direction == 'desc' else False
            query_data = sorted(list(query_data),
                                key=lambda x: x['delta_percent'],
                                reverse=reverse)
        return query_data

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
            annotations = self._mapper._report_type_map.get('annotations')
            query_data = query_data.values(*query_group_by).annotate(**annotations)

            if self._limit and group_by_value:
                rank_order = getattr(F(group_by_value.pop()), self.order_direction)()
                rank_by_total = Window(
                    expression=RowNumber(),
                    partition_by=F('date'),
                    order_by=rank_order
                )
                query_data = query_data.annotate(rank=rank_by_total)
                query_order_by = query_order_by + ('rank',)

            if self.order_field != 'delta':
                query_data = query_data.order_by(*query_order_by)

            # Populate the 'total' section of the API response
            if query.exists():
                aggregates = self._mapper._report_type_map.get('aggregates')
                metric_sum = query.aggregate(**aggregates)
                query_sum = {key: metric_sum.get(key) for key in aggregates}

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

    def execute_query(self):
        """Execute query and return provided data.

        Returns:
            (Dict): Dictionary response of query params, data, and total

        """
        return self.execute_sum_query()
