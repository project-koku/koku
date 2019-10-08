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

from django.db.models import F, Window
from django.db.models.functions import (Coalesce, RowNumber)
from tenant_schemas.utils import tenant_context

from api.report.aws.query_handler import AWSReportQueryHandler
from api.report.ocp_aws.provider_map import OCPAWSProviderMap


class OCPAWSReportQueryHandler(AWSReportQueryHandler):
    """Handles report queries and responses for OCP on AWS."""

    provider = 'OCP_AWS'

    def __init__(self, parameters):
        """Establish OCP report query handler.

        Args:
            parameters    (QueryParameters): parameter object for query

        """
        self._mapper = OCPAWSProviderMap(provider=self.provider,
                                         report_type=parameters.report_type)
        self.group_by_options = self._mapper.provider_map.get('group_by_options')
        self._limit = parameters.get_filter('limit')

        # super() needs to be called after _mapper and _limit is set
        super().__init__(parameters)
        # super() needs to be called before _get_group_by is called

        # Update which field is used to calculate cost by group by param.
        group_by = self._get_group_by()
        if (group_by and group_by[0] == 'project') or \
                'project' in self.parameters.get('filter', {}).keys():
            self._report_type = parameters.report_type + '_by_project'
            self._mapper = OCPAWSProviderMap(provider=self.provider,
                                             report_type=parameters.report_type)

    def execute_query(self):  # noqa: C901
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
            group_by_value = self._get_group_by()
            query_group_by = ['date'] + group_by_value
            query_order_by = ['-date', ]
            query_order_by.extend([self.order])
            clustered_group_by = self._get_cluster_group_by(query_group_by)

            annotations = self._mapper.report_type_map.get('annotations')
            query_data = query_data.values(*clustered_group_by).annotate(**annotations)

            if 'account' in query_group_by:
                query_data = query_data.annotate(account_alias=Coalesce(
                    F(self._mapper.provider_map.get('alias')), 'usage_account_id'))
            elif 'cluster' in query_group_by or 'cluster' in self.query_filter:
                query_data = query_data.annotate(cluster_alias=Coalesce('cluster_alias',
                                                                        'cluster_id'))

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
                aggregates = self._mapper.report_type_map.get('aggregates')
                metric_sum = query.aggregate(**aggregates)
                query_sum = {key: metric_sum.get(key) for key in aggregates}

            if self._delta:
                query_data = self.add_deltas(query_data, query_sum)

            is_csv_output = self.parameters.accept_type and 'text/csv' in self.parameters.accept_type

            query_data, query_group_by = self.strip_label_column_name(
                query_data,
                query_group_by
            )
            query_data = self.order_by(query_data, query_order_by)
            cost_units_value = self._mapper.report_type_map.get('cost_units_fallback', 'USD')
            usage_units_value = self._mapper.report_type_map.get('usage_units_fallback')
            count_units_value = self._mapper.report_type_map.get('count_units_fallback')
            if query_data:
                cost_units_value = query_data[0].get('cost_units')
                if self._mapper.usage_units_key:
                    usage_units_value = query_data[0].get('usage_units')
                if self._mapper.report_type_map.get('annotations', {}).get('count_units'):
                    count_units_value = query_data[0].get('count_units')

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

        init_order_keys = []
        query_sum['cost_units'] = cost_units_value
        if self._mapper.usage_units_key and usage_units_value:
            init_order_keys = ['usage_units']
            query_sum['usage_units'] = usage_units_value
        if self._mapper.report_type_map.get('annotations', {}).get('count_units') and count_units_value:
            query_sum['count_units'] = count_units_value
        key_order = list(init_order_keys + list(annotations.keys()))
        ordered_total = {total_key: query_sum[total_key]
                         for total_key in key_order if total_key in query_sum}
        ordered_total.update(query_sum)
        self._pack_data_object(ordered_total, **self._mapper.PACK_DEFINITIONS)

        self.query_sum = ordered_total
        self.query_data = data
        return self._format_query_response()
