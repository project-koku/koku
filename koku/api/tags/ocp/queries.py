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
from copy import deepcopy

from django.db.models import Exists
from django.db.models import OuterRef

from api.models import Provider
from api.query_filter import QueryFilter
from api.query_filter import QueryFilterCollection
from api.report.ocp.provider_map import OCPProviderMap
from api.tags.queries import TagQueryHandler
from reporting.models import OCPEnabledTagKeys
from reporting.models import OCPStorageVolumeLabelSummary
from reporting.models import OCPUsagePodLabelSummary
from reporting.provider.ocp.models import OCPTagsValues


class OCPTagQueryHandler(TagQueryHandler):
    """Handles tag queries and responses for OCP."""

    provider = Provider.PROVIDER_OCP
    enabled = OCPEnabledTagKeys.objects.filter(key=OuterRef("key"))
    data_sources = [
        {
            "db_table": OCPUsagePodLabelSummary,
            "db_column_period": "report_period__report_period",
            "type": "pod",
            "annotations": {"enabled": Exists(enabled)},
            "db_values": OCPTagsValues,
        },
        {
            "db_table": OCPStorageVolumeLabelSummary,
            "db_column_period": "report_period__report_period",
            "type": "storage",
            "annotations": {"enabled": Exists(enabled)},
            "db_values": OCPTagsValues,
        },
    ]
    SUPPORTED_FILTERS = TagQueryHandler.SUPPORTED_FILTERS + ["project", "enabled", "cluster"]
    FILTER_MAP = deepcopy(TagQueryHandler.FILTER_MAP)
    FILTER_MAP.update(
        {
            "project": {"field": "namespace", "operation": "icontains"},
            "enabled": {"field": "enabled", "operation": "exact", "parameter": True},
            "cluster": [
                {"field": "report_period__cluster_id", "operation": "icontains", "composition_key": "cluster_filter"},
                {
                    "field": "report_period__cluster_alias",
                    "operation": "icontains",
                    "composition_key": "cluster_filter",
                },
            ],
        }
    )

    def __init__(self, parameters):
        """Establish AWS report query handler.

        Args:
            parameters    (QueryParameters): parameter object for query

        """
        if not hasattr(self, "_mapper"):
            self._mapper = OCPProviderMap(provider=self.provider, report_type=parameters.report_type)

        if parameters.get_filter("enabled") is None:
            parameters.set_filter(**{"enabled": True})
        # super() needs to be called after _mapper is set
        super().__init__(parameters)

    def _get_key_filter(self):
        """
        Add new `exact` QueryFilter that filters on the key name.
        If filtering on value, uses the tags summary table to find the key,
        has to check both possible tables
        """
        filters = QueryFilterCollection()
        if self.parameters.get_filter("value"):
            filters.add(
                QueryFilter(
                    field="ocpusagepodlabelsummary__key",
                    operation="exact",
                    parameter=self.key,
                    composition_key="tag_filter",
                )
            )
            filters.add(
                QueryFilter(
                    field="ocpstoragevolumelabelsummary__key",
                    operation="exact",
                    parameter=self.key,
                    composition_key="tag_filter",
                )
            )
        else:
            filters.add(QueryFilter(field="key", operation="exact", parameter=self.key))
        return self.query_filter & filters.compose()
