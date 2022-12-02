#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""OCP Tag Query Handling."""
from copy import deepcopy

from django.db.models import Exists
from django.db.models import OuterRef

from api.models import Provider
from api.report.ocp.provider_map import OCPProviderMap
from api.tags.queries import TagQueryHandler
from reporting.models import OCPEnabledTagKeys
from reporting.models import OCPStorageVolumeLabelSummary
from reporting.models import OCPUsagePodLabelSummary
from reporting.provider.ocp.models import OCPTagsValues


filter_map_single = {
    "project": {"field": "namespace", "operation": "icontains"},
    "cluster": [
        {
            "field": "report_period__cluster_id",
            "operation": "icontains",
            "composition_key": "cluster_filter",
        },
        {
            "field": "report_period__cluster_alias",
            "operation": "icontains",
            "composition_key": "cluster_filter",
        },
    ],
    "node": {"field": "node", "operation": "icontains"},
    "category": {"field": "cost_category__name", "operation": "icontains"},
}

filter_map_multi = {
    "project": {"field": "namespaces", "operation": "contained_by"},
    "cluster": [
        {"field": "cluster_ids", "operation": "contained_by", "composition_key": "cluster_filter"},
        {"field": "cluster_aliases", "operation": "contained_by", "composition_key": "cluster_filter"},
    ],
    "node": {"field": "nodes", "operation": "contained_by"},
    "category": {"field": "cost_category__name", "operation": "contained_by"},
}


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
        },
        {
            "db_table": OCPStorageVolumeLabelSummary,
            "db_column_period": "report_period__report_period",
            "type": "storage",
            "annotations": {"enabled": Exists(enabled)},
        },
    ]
    TAGS_VALUES_SOURCE = [{"db_table": OCPTagsValues, "fields": ["key"]}]
    SUPPORTED_FILTERS = TagQueryHandler.SUPPORTED_FILTERS + ["project", "enabled", "cluster", "node", "category"]
    FILTER_MAP_OCP_SINGLE = filter_map_single
    FILTER_MAP_OCP_MULTI = filter_map_multi
    FILTER_MAP = deepcopy(TagQueryHandler.FILTER_MAP)
    FILTER_MAP.update(
        dict({"enabled": {"field": "enabled", "operation": "exact", "parameter": True},}, **filter_map_single)
        )

    def __init__(self, parameters):
        """Establish OCP report query handler.

        Args:
            parameters    (QueryParameters): parameter object for query

        """
        self._parameters = parameters
        if not hasattr(self, "_mapper"):
            self._mapper = OCPProviderMap(provider=self.provider, report_type=parameters.report_type)

        if parameters.get_filter("enabled") is None:
            parameters.set_filter(**{"enabled": True})
        # super() needs to be called after _mapper is set
        super().__init__(parameters)

    @property
    def filter_map(self):
        """Establish which filter map to use based on tag API."""
        filter_map = deepcopy(TagQueryHandler.FILTER_MAP)
        enabled_parameter = self._parameters.get_filter("enabled") in (None, True)
        enabled_filter = {"enabled": {"field": "enabled", "operation": "exact", "parameter": enabled_parameter},}
        if self._parameters.get_filter("value"):
            filter_map.update(dict(enabled_filter, **filter_map_multi))
        else:
            filter_map.update(dict(enabled_filter, **filter_map_single))
        return filter_map
