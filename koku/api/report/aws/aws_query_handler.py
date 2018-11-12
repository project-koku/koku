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
"""AWS Query Handling for Reports."""
import copy
import datetime
from collections import OrderedDict
from decimal import Decimal

from dateutil import relativedelta
from django.db.models import (F,
                              Max,
                              Q,
                              Sum,
                              Value,
                              Window)
from django.db.models.functions import (Coalesce,
                                        Concat,
                                        RowNumber)
from tenant_schemas.utils import tenant_context

from api.report.queries import ReportQueryHandler
from api.report.query_filter import QueryFilterCollection

EXPORT_COLUMNS = ['cost_entry_id', 'cost_entry_bill_id',
                  'cost_entry_product_id', 'cost_entry_pricing_id',
                  'cost_entry_reservation_id', 'tags',
                  'invoice_id', 'line_item_type', 'usage_account_id',
                  'usage_start', 'usage_end', 'product_code',
                  'usage_type', 'operation', 'availability_zone',
                  'usage_amount', 'normalization_factor',
                  'normalized_usage_amount', 'currency_code',
                  'unblended_rate', 'unblended_cost', 'blended_rate',
                  'blended_cost', 'tax_type']


class AWSReportQueryHandler(ReportQueryHandler):
    """Handles report queries and responses for AWS."""

    group_by_options = ['service', 'account', 'region', 'avail_zone']

    def __init__(self, query_parameters, url_data,
                 tenant, **kwargs):
        """Establish AWS report query handler.

        Args:
            query_parameters    (Dict): parameters for query
            url_data        (String): URL string to provide order information
            tenant    (String): the tenant to use to access CUR data
            kwargs    (Dict): A dictionary for internal query alteration based on path
        """
        kwargs['provider'] = 'AWS'

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
            'units': Concat(self._mapper.units_key, Value(''))
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
        if self.time_scope_value in [-1, -2]:
            date_delta = relativedelta.relativedelta(months=1)
        elif self.time_scope_value == -30:
            date_delta = datetime.timedelta(days=30)
        else:
            date_delta = datetime.timedelta(days=10)
        # Added deltas for each grouping
        # e.g. date, account, region, availability zone, et cetera
        query_annotations = self._get_annotations()
        previous_sums = previous_query.annotate(**query_annotations)
        aggregate_key = self._mapper._report_type_map.get('aggregate_key')
        previous_sums = previous_sums\
            .values(*query_group_by)\
            .annotate(total=Sum(aggregate_key))

        previous_dict = OrderedDict()
        for row in previous_sums:
            date = self.string_to_date(row['date'])
            date = date + date_delta
            row['date'] = self.date_to_string(date)
            key = tuple((row[key] for key in query_group_by))
            previous_dict[key] = row['total']

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
            current_total = row.get('total', 0)
            row['delta_value'] = current_total - previous_total
            row['delta_percent'] = self._percent_delta(current_total, previous_total)

        # Calculate the delta on the total aggregate
        current_total_sum = Decimal(query_sum.get('value') or 0)
        aggregate_key = self._mapper._report_type_map.get('aggregate_key')
        prev_total_sum = previous_query.aggregate(value=Sum(aggregate_key))
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

            query_group_by = ['date'] + self._get_group_by()

            query_order_by = ('-date', )
            if self.order_field != 'delta':
                query_order_by += (self.order,)

            aggregate_key = self._mapper._report_type_map.get('aggregate_key')
            query_data = query_data.values(*query_group_by)\
                .annotate(total=Sum(aggregate_key))\
                .annotate(units=Max(self._mapper.units_key))

            if 'account' in query_group_by:
                query_data = query_data.annotate(account_alias=Coalesce(
                    F(self._mapper._operation_map.get('alias')), 'usage_account_id'))

            if self._mapper.count:
                # This is a sum because the summary table already
                # has already performed counts
                query_data = query_data.annotate(count=Sum(self._mapper.count))

            if self._limit:
                rank_order = getattr(F(self.order_field), self.order_direction)()
                rank_by_total = Window(
                    expression=RowNumber(),
                    partition_by=F('date'),
                    order_by=rank_order
                )
                query_data = query_data.annotate(rank=rank_by_total)
                query_order_by = query_order_by + ('rank',)

            if self.order_field != 'delta':
                query_data = query_data.order_by(*query_order_by)

            if query.exists():
                units_value = query.values(self._mapper.units_key)\
                                   .first().get(self._mapper.units_key)
                query_sum = self.calculate_total(units_value)

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
        if self.is_sum:
            return self.execute_sum_query()

        query_sum = {'value': 0}
        data = []

        q_table = self._mapper._operation_map.get('tables').get('query')
        with tenant_context(self.tenant):
            query = q_table.objects.filter(self.query_filter)

            query_annotations = self._get_annotations()
            query_data = query.annotate(**query_annotations)

            query_group_by = ['date'] + self._get_group_by()
            query_group_by_with_units = query_group_by + ['units']

            query_order_by = ('-date',)
            query_data = query_data.order_by(*query_order_by)
            values_out = query_group_by_with_units + EXPORT_COLUMNS
            data = list(query_data.values(*values_out))

            if query.exists():
                units_value = query.values(self._mapper.units_key)\
                                   .first().get(self._mapper.units_key)
                query_sum = self.calculate_total(units_value)

        self.query_sum = query_sum
        self.query_data = data
        return self._format_query_response()

    def calculate_total(self, units_value):
        """Calculate aggregated totals for the query.

        Args:
            units_value (str): The unit of the reported total

        Returns:
            (dict) The aggregated totals for the query

        """
        filt_collection = QueryFilterCollection()
        total_filter = self._get_search_filter(filt_collection)

        time_scope_value = self.get_query_param_data('filter',
                                                     'time_scope_value',
                                                     -10)
        time_and_report_filter = Q(time_scope_value=time_scope_value) & \
            Q(report_type=self._report_type)

        if total_filter is None:
            total_filter = time_and_report_filter
        else:
            total_filter = total_filter & time_and_report_filter

        q_table = self._mapper._operation_map.get('tables').get('total')
        total_query = q_table.objects.filter(total_filter)

        aggregate_key = self._mapper._report_type_map.get('aggregate_key')
        if self._mapper.count:
            query_sum = total_query.aggregate(
                value=Sum(aggregate_key),
                # This is a sum because the summary table already
                # has already performed counts
                count=Sum(self._mapper.count)
            )
        else:
            query_sum = total_query.aggregate(value=Sum(aggregate_key))
        query_sum['units'] = units_value

        return query_sum
