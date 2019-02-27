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

from django.db.models import (F, Q, Value, Window)
from django.db.models.functions import Coalesce, Concat, RowNumber
from tenant_schemas.utils import tenant_context

from api.query_filter import QueryFilterCollection
from api.report.queries import ReportQueryHandler

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

    def __init__(self, query_parameters, url_data,
                 tenant, **kwargs):
        """Establish AWS report query handler.

        Args:
            query_parameters    (Dict): parameters for query
            url_data        (String): URL string to provide order information
            tenant    (String): the tenant to use to access CUR data
            kwargs    (Dict): A dictionary for internal query alteration based on path
        """
        if not kwargs.get('provider'):
            kwargs['provider'] = 'AWS'
        super().__init__(query_parameters, url_data,
                         tenant, **kwargs)

    @property
    def annotations(self):
        """Create dictionary for query annotations.

        Returns:
            (Dict): query annotations dictionary

        """
        units_fallback = self._mapper.report_type_map.get('cost_units_fallback')
        annotations = {
            'date': self.date_trunc('usage_start'),
            'cost_units': Coalesce(self._mapper.cost_units_key, Value(units_fallback))
        }
        if self._mapper.usage_units_key:
            units_fallback = self._mapper.report_type_map.get('usage_units_fallback')
            annotations['usage_units'] = Coalesce(self._mapper.usage_units_key, Value(units_fallback))
        # { query_param: database_field_name }
        fields = self._mapper.provider_map.get('annotations')
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
            query_data = query.annotate(**self.annotations)
            query_group_by = ['date'] + self._get_group_by()
            query_order_by = ['-date', ]
            query_order_by.extend([self.order])

            annotations = self._mapper.report_type_map.get('annotations')
            query_data = query_data.values(*query_group_by).annotate(**annotations)

            if 'account' in query_group_by:
                query_data = query_data.annotate(account_alias=Coalesce(
                    F(self._mapper.provider_map.get('alias')), 'usage_account_id'))

            if self._limit:
                rank_order = getattr(F(self.order_field), self.order_direction)()
                rank_by_total = Window(
                    expression=RowNumber(),
                    partition_by=F('date'),
                    order_by=rank_order
                )
                query_data = query_data.annotate(rank=rank_by_total)
                query_order_by.insert(1, 'rank')
                query_data = self._ranked_list(query_data)

            if query.exists():
                units_fallback = self._mapper.report_type_map.get('cost_units_fallback')
                sum_annotations = {
                    'cost_units': Coalesce(self._mapper.cost_units_key, Value(units_fallback))
                }
                if self._mapper.usage_units_key:
                    units_fallback = self._mapper.report_type_map.get('usage_units_fallback')
                    sum_annotations['usage_units'] = Coalesce(self._mapper.usage_units_key, Value(units_fallback))
                sum_query = query.annotate(**sum_annotations)
                units_value = sum_query.values('cost_units').first().get('cost_units')
                sum_units = {'cost_units': units_value}
                if self._mapper.usage_units_key:
                    units_value = sum_query.values('usage_units').first().get('usage_units')
                    sum_units['usage_units'] = units_value
                if self._mapper.report_type_map.get('annotations', {}).get('count_units'):
                    sum_units['count_units'] = 'instances'

                query_sum = self.calculate_total(**sum_units)
            if self._delta:
                query_data = self.add_deltas(query_data, query_sum)

            is_csv_output = self._accept_type and 'text/csv' in self._accept_type

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
                groups = copy.deepcopy(query_group_by)
                groups.remove('date')
                data = self._apply_group_by(list(query_data), groups)
                data = self._transform_data(query_group_by, 0, data)

        key_order = list(['units'] + list(annotations.keys()))
        ordered_total = {total_key: query_sum[total_key]
                         for total_key in key_order if total_key in query_sum}
        ordered_total.update(query_sum)

        self.query_sum = ordered_total
        self.query_data = data
        return self._format_query_response()

    def calculate_total(self, **units):
        """Calculate aggregated totals for the query.

        Args:
            units (dict): The units dictionary

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

        q_table = self._mapper.provider_map.get('tables').get('total')
        aggregates = self._mapper.report_type_map.get('aggregates')
        total_query = q_table.objects.filter(total_filter).aggregate(**aggregates)
        for unit_key, unit_value in units.items():
            total_query[unit_key] = unit_value
        self._pack_data_object(total_query, **self._mapper.PACK_DEFINITIONS)

        return total_query
