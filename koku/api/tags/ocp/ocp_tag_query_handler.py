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
"""OCP Tag Query Handling."""
import copy
from api.tags.queries import TagQueryHandler
from django.db.models import F, Count, Window
from django.db.models.functions import RowNumber
from tenant_schemas.utils import tenant_context

from reporting.models import OCPUsageLineItemDailySummary

class OCPTagQueryHandler(TagQueryHandler):
    """Handles tag queries and responses for OCP."""

    def __init__(self, query_parameters, url_data,
                tenant, **kwargs):
        """Establish OCP report query handler.

        Args:
            query_parameters    (Dict): parameters for query
            url_data        (String): URL string to provide order information
            tenant    (String): the tenant to use to access CUR data
            kwargs    (Dict): A dictionary for internal query alteration based on path
        """
        super().__init__(query_parameters, url_data,
                            tenant, **kwargs)

    def _format_query_response(self):
        """Format the query response with data.

        Returns:
            (Dict): Dictionary response of query params, data, and total

        """
        output = copy.deepcopy(self.query_parameters)
        output['data'] = self.query_data

        return output

    def _transform_data(self, group_index, data):
        """Transform dictionary data points to lists."""

        out_data = []
        label = 'data'
        group_type = groups[group_index]
        next_group_index = (group_index + 1)

        if next_group_index < groups_len:
            label = groups[next_group_index] + 's'

        for group, group_value in data.items():
            cur = {group_type: group,
                   label: self._transform_data(groups, next_group_index,
                                               group_value)}
            out_data.append(cur)

        return out_data

    def execute_query(self):
        """Execute query and return provided data when self.is_sum == True.

        Returns:
            (Dict): Dictionary response of query params, data, and total

        """
        query_sum = {'value': 0}
        data = []

        q_table = OCPUsageLineItemDailySummary
        with tenant_context(self.tenant):
            import pdb; pdb.set_trace()
            query = q_table.objects.filter(self.query_filter)

            query_data = query.values('pod_labels')

            # annotations = self._mapper._report_type_map.get('annotations')
            # query_data = query_data.values(*query_group_by).annotate(**annotations)

            # is_csv_output = self._accept_type and 'text/csv' in self._accept_type

            data = list(query_data)
            data = self._transform_data(0, data)

        query_sum.update({'units': self._mapper.units_key})

        ordered_total = {total_key: query_sum[total_key]
                         for total_key in annotations.keys() if total_key in query_sum}
        ordered_total.update(query_sum)

        self.query_sum = ordered_total
        self.query_data = data
        return self._format_query_response()
