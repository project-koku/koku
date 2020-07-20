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
"""AWS Tag Query Handling."""
from copy import deepcopy

from tenant_schemas.utils import tenant_context

from api.models import Provider
from api.query_filter import QueryFilter
from api.query_filter import QueryFilterCollection
from api.report.aws.provider_map import AWSProviderMap
from api.tags.queries import TagQueryHandler
from reporting.models import AWSTagsSummary
from reporting.provider.aws.models import AWSTagsValues


class AWSTagQueryHandler(TagQueryHandler):
    """Handles tag queries and responses for AWS."""

    provider = Provider.PROVIDER_AWS
    data_sources = [
        {"db_table": AWSTagsSummary, "db_column_period": "cost_entry_bill__billing_period", "db_values": AWSTagsValues}
    ]
    SUPPORTED_FILTERS = TagQueryHandler.SUPPORTED_FILTERS + ["account"]
    FILTER_MAP = deepcopy(TagQueryHandler.FILTER_MAP)
    FILTER_MAP.update(
        {
            "account": {"field": "accounts", "operation": "icontains", "composition_key": "account_filter"},
            "value": {"field": "value", "operation": "icontains", "composition_key": "value_filter"},
        }
    )

    def __init__(self, parameters):
        """Establish AWS report query handler.

        Args:
            parameters    (QueryParameters): parameter object for query

        """
        if not hasattr(self, "_mapper"):
            self._mapper = AWSProviderMap(provider=self.provider, report_type=parameters.report_type)
        # super() needs to be called after _mapper is set
        super().__init__(parameters)

    def _get_key_filter(self):
        """Add new `exact` QueryFilter that filters on the key name."""
        filters = QueryFilterCollection()
        if self.parameters.get_filter("value"):
            filters.add(QueryFilter(field="awstagssummary__key", operation="exact", parameter=self.key))
        else:
            filters.add(QueryFilter(field="key", operation="exact", parameter=self.key))
        return self.query_filter & filters.compose()

    # def get_tags(self):
    #     """Get a list of tags and values to validate filters.

    #     Return a list of dictionaries containing the tag keys.
    #     If OCP, these dicationaries will return as:
    #         [
    #             {"key": key1, "values": [value1, value2], "type": "storage" (or "pod")},
    #             {"key": key2, "values": [value1, value2], "type": "storage" (or "pod")},
    #             etc.
    #         ]
    #     If cloud provider, dicitonaries will be:
    #         [
    #             {"key": key1, "values": [value1, value2]},
    #             {"key": key2, "values": [value1, value2]},
    #             etc.
    #         ]
    #     """
    #     type_filter = self.parameters.get_filter("type")
    #     type_filter_array = []

    #     # Sort the data_sources so that those with a "type" go first
    #     sources = sorted(self.data_sources, key=lambda dikt: dikt.get("type", ""), reverse=True)

    #     if type_filter and type_filter == "*":
    #         for source in sources:
    #             source_type = source.get("type")
    #             if source_type:
    #                 type_filter_array.append(source_type)
    #     elif type_filter:
    #         type_filter_array.append(type_filter)

    #     final_data = []
    #     with tenant_context(self.tenant):
    #         vals = ["key"]
    #         for source in sources:
    #             if not self.parameters.get_filter("value"):
    #                 if type_filter and source.get("type") not in type_filter_array:
    #                     continue
    #                 tag_keys_query = source.get("db_table").objects
    #                 annotations = source.get("annotations")
    #                 if annotations:
    #                     tag_keys_query = tag_keys_query.annotate(**annotations)
    #                     for annotation_key in annotations.keys():
    #                         vals.append(annotation_key)
    #                 exclusion = self._get_exclusions("key")
    #                 t_keys = list(tag_keys_query.filter(self.query_filter).exclude(exclusion).values_list(*vals).all())
    #                 t_tup = self._get_tag_key_tuple(t_keys, tag_keys_query)
    #                 converted = self._convert_to_dict(t_tup)
    #                 if type_filter and source.get("type"):
    #                     self.append_to_final_data_with_type(final_data, converted, source)
    #                 else:
    #                     self.append_to_final_data_without_type(final_data, converted)
    #             else:
    #                 if type_filter and source.get("type") not in type_filter_array:
    #                     continue
    #                 tag_values_query = source.get("db_values").objects
    #                 exclusion = self._get_exclusions("key")
    #                 t_keys = list(tag_values_query.filter(self.query_filter))
    #                 t_tup = self._value_filter_dict(t_keys)
    #                 converted = self._convert_to_dict(t_tup)
    #                 if type_filter and source.get("type"):
    #                     self.append_to_final_data_with_type(final_data, converted, source)
    #                 else:
    #                     self.append_to_final_data_without_type(final_data, converted)

    #     # sort the values and deduplicate before returning
    #     # self.deduplicate_and_sort(final_data)
    #     return final_data

    def _get_tag_key_tuple(self, t_keys, tag_keys_query):
        t_tup = []
        for tag in t_keys:
            t_vals = list(tag_keys_query.get(key=tag[0]).values.values_list("value", flat=True))
            t_tup.append((tag[0], t_vals))
        return t_tup

    def _value_filter_dict(self, t_keys):
        t_tup = []
        for obj in t_keys:
            t_tup.append((self.key, obj.value))
        return t_tup
