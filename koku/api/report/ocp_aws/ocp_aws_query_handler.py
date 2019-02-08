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

from django.db.models import F, Max, Sum, Value, Window
from django.db.models.functions import (Coalesce, Concat, RowNumber)
from tenant_schemas.utils import tenant_context

from api.report.aws.aws_query_handler import AWSReportQueryHandler
from api.report.queries import ProviderMap
from reporting.models import OCPAWSCostLineItemDailySummary



class OCPAWSProviderMap(ProviderMap):
    """OCP Provider Map."""

    mapping = {
        'provider': 'OCP_AWS',
        'annotations': {'cluster': 'cluster_id',
                        'project': 'namespace',
                        'account': 'usage_account_id',
                        'service': 'product_code',
                        'az': 'availability_zone'},
        'end_date': 'usage_end',
        'filters': {
            'project': {'field': 'namespace',
                        'operation': 'icontains'},
            'cluster': [{'field': 'cluster_alias',
                        'operation': 'icontains',
                        'composition_key': 'cluster_filter'},
                        {'field': 'cluster_id',
                        'operation': 'icontains',
                        'composition_key': 'cluster_filter'}],
            'node': {'field': 'node',
                        'operation': 'icontains'},
            'account': [{'field': 'account_alias__account_alias',
                        'operation': 'icontains',
                        'composition_key': 'account_filter'},
                        {'field': 'usage_account_id',
                        'operation': 'icontains',
                        'composition_key': 'account_filter'}],
            'service': {'field': 'product_code',
                        'operation': 'icontains'},
            'az': {'field': 'availability_zone',
                            'operation': 'icontains'},
            'region': {'field': 'region',
                        'operation': 'icontains'}
        },
        'group_by_options': ['account', 'service', 'region', 'cluster', 'project', 'node'],
        'tag_column': 'tags',
        'report_type': {
            'storage': {
                'aggregate': {
                    'value': Sum('usage_amount'),
                    'cost': Sum('unblended_cost')
                },
                'aggregate_key': 'usage_amount',
                'annotations': {'cost': Sum('unblended_cost'),
                                'total': Sum('usage_amount'),
                                'units': Coalesce(Max('unit'),
                                Value('GB-Mo'))},
                'count': None,
                'delta_key': {'total': Sum('usage_amount')},
                'filter': {
                    'field': 'product_family',
                    'operation': 'contains',
                    'parameter': 'Storage'
                },
                'units_key': 'unit',
                'units_fallback': 'GB-Mo',
                'sum_columns': ['total', 'cost'],
                'default_ordering': {'total': 'desc'},
            },
        },
        'start_date': 'usage_start',
        'tables': {'previous_query': OCPAWSCostLineItemDailySummary,
                    'query': OCPAWSCostLineItemDailySummary,
                    'total': OCPAWSCostLineItemDailySummary},
    }

class OCPAWSReportQueryHandler(AWSReportQueryHandler):
    """Handles report queries and responses for OCP on AWS."""

    def __init__(self, query_parameters, url_data,
                 tenant, **kwargs):
        """Establish OCP report query handler.

        Args:
            query_parameters    (Dict): parameters for query
            url_data        (String): URL string to provide order information
            tenant    (String): the tenant to use to access CUR data
            kwargs    (Dict): A dictionary for internal query alteration based on path
        """
        kwargs['provider'] = 'OCP_AWS'
        super().__init__(query_parameters, url_data,
                         tenant, **kwargs)

    def execute_sum_query(self):
        """Execute query and return provided data when self.is_sum == True.

        Returns:
            (Dict): Dictionary response of query params, data, and total

        """
        query_sum = {'value': 0}
        data = []

        q_table = self._mapper._provider_map.get('tables').get('query')
        with tenant_context(self.tenant):
            query = q_table.objects.filter(self.query_filter)
            query_data = query.annotate(**self.annotations)
            query_group_by = ['date'] + self._get_group_by()
            query_order_by = ['-date', ]
            query_order_by.extend([self.order])

            annotations = self._mapper._report_type_map.get('annotations')
            query_data = query_data.values(*query_group_by).annotate(**annotations)

            if 'account' in query_group_by:
                query_data = query_data.annotate(account_alias=Coalesce(
                    F(self._mapper._provider_map.get('alias')), 'usage_account_id'))

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
                units_fallback = self._mapper._report_type_map.get('units_fallback')
                sum_annotations = {
                    'units': Coalesce(self._mapper.units_key, Value(units_fallback))
                }
                sum_query = query.annotate(**sum_annotations)
                units_value = sum_query.values('units').first().get('units')

                aggregates = self._mapper._report_type_map.get('aggregates')
                metric_sum = query.aggregate(**aggregates)
                query_sum = {key: metric_sum.get(key) for key in aggregates}

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
