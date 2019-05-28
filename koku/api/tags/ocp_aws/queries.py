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

"""OCP-on-AWS Tag Query Handling."""
from django.core.exceptions import FieldError
from tenant_schemas.utils import tenant_context

from api.functions import JSONBObjectKeys
from api.tags.aws.queries import AWSTagQueryHandler
from api.tags.ocp.queries import OCPTagQueryHandler

import logging
LOG = logging.getLogger(__name__)


class OCPAWSTagQueryHandler(AWSTagQueryHandler, OCPTagQueryHandler):
    """Handles tag queries and responses for OCP-on-AWS."""

    def get_tag_keys(self, filters=True):
        """Get a list of tag keys to validate filters.

        This is overridden to provide the intersection of AWS and OCP keys

        """
        tag_keys = []
        with tenant_context(self.tenant):
            # queries = {'AWS': [], 'OCP': []}
            queries = {src.get('provider'): [] for src in self.data_sources}
            for src in self.data_sources:
                if filters:
                    query = src.get('db_table').objects.filter(self.query_filter)
                else:
                    query = src.get('db_table').objects

                type_filter = self.parameter_filter.get('type')
                if type_filter and type_filter != src.get('type'):
                    continue

                query = query.annotate(tag_keys=JSONBObjectKeys(
                    src.get('db_column'))).values('tag_keys').distinct().all()

                queries[src.get('provider')].append(query)

            # assumption: there should only be one AWS data source.
            tag_keys_query = queries.get('AWS')[0].intersection(*queries.get('OCP'))
            for tag_key in [tag.get('tag_keys') for tag in tag_keys_query]:
                tag_keys.append(tag_key)

        return tag_keys

    def get_tags(self):
        """Get a list of tags and values to validate filters.

        This is overridden to provide the intersection of AWS and OCP keys

        """
        merged_data = []
        tag_keys = []

        with tenant_context(self.tenant):

            # queries = {'AWS': [], 'OCP': []}
            queries = {src.get('provider'): [] for src in self.data_sources}

            # loop through data_sources, filtering out parameter_filter, if any
            type_filter = self.parameter_filter.get('type', 'no-filter')
            for src in filter(lambda x: type_filter in (x.get('type'), 'no-filter'),
                              self.data_sources):
                try:
                    query = src.get('db_table').objects\
                        .filter(self.query_filter)\
                        .values(src.get('db_column'))\
                        .distinct()\
                        .all()
                    queries[src.get('provider')].append(query)
                except FieldError:
                    # this field isn't on this table. skip it.
                    continue

            # assumption: there should only be one AWS data source.
            LOG.debug('XXX: %s', queries)
            tag_keys_query = queries.get('AWS')[0].intersection(*queries.get('OCP'))
            for tag_key in [tag.get('tag_keys') for tag in tag_keys_query]:
                tag_keys.append(tag_key)

        for src in self.data_sources:
            for item in tag_keys:
                for key, value in item.items():
                    key_dict = OCPAWSTagQueryHandler._get_dictionary_for_key(merged_data, key)
                    if key_dict:
                        if value not in key_dict.get('values'):
                            key_dict['values'].append(value)
                            key_dict['values'].sort()
                    else:
                        merged_data.append({'key': key,
                                            'values': [value],
                                            'type': src.get('type')})
        return merged_data
