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

from django.db.models import Count
from tenant_schemas.utils import tenant_context

from api.functions import JSONBObjectKeys
from api.tags.queries import TagQueryHandler
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

    def get_tag_keys(self, filters=True):
        """Get a list of tag keys to validate filters."""
        with tenant_context(self.tenant):
            tag_keys = OCPUsageLineItemDailySummary.objects
            if filters is True:
                tag_keys = tag_keys.filter(self.query_filter)

            tag_keys = tag_keys.annotate(tag_keys=JSONBObjectKeys('pod_labels'))\
                .values('tag_keys')\
                .annotate(tag_count=Count('tag_keys'))\
                .all()
            tag_keys = [tag.get('tag_keys') for tag in tag_keys]

        return tag_keys

    def get_tags(self, tenant):
        """Get a list of tag key and values to validate filters."""
        def get_dictionary_for_key(merged_data, key):
            for di in merged_data:
                if key in di.get('key'):
                    return di
            return None

        with tenant_context(tenant):
            tag_keys = OCPUsageLineItemDailySummary.objects\
                .filter(self.query_filter)\
                .values('pod_labels')\
                .all()
            tag_keys = [tag.get('pod_labels') for tag in tag_keys]

            merged_data = []
            for item in tag_keys:
                for key, value in item.items():
                    key_dict = get_dictionary_for_key(merged_data, key)
                    if not key_dict:
                        new_dict = {}
                        new_dict['key'] = key
                        new_dict['values'] = [value]
                        merged_data.append(new_dict)
                    else:
                        if value not in key_dict.get('values'):
                            key_dict['values'].append(value)
                            key_dict['values'].sort()
        return merged_data

    def execute_query(self):
        """Execute query and return provided data.

        Returns:
            (Dict): Dictionary response of query params and data

        """
        if self.query_parameters.get('key_only'):
            tag_keys = self.get_tag_keys()
            query_data = sorted(tag_keys, reverse=self.order_direction == 'desc')
        else:
            tags = self.get_tags(self.tenant)
            query_data = sorted(tags, key=lambda k: k['key'], reverse=self.order_direction == 'desc')

        self.query_data = query_data
        return self._format_query_response()
