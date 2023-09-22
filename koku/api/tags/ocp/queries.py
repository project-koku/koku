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
from reporting.models import OCPStorageVolumeLabelSummary
from reporting.models import OCPUsagePodLabelSummary
from reporting.provider.all.models import EnabledTagKeys
from reporting.provider.ocp.models import OCPTagsValues


class OCPTagQueryHandler(TagQueryHandler):
    """Handles tag queries and responses for OCP."""

    provider = Provider.PROVIDER_OCP
    enabled = (
        EnabledTagKeys.objects.filter(provider_type=Provider.PROVIDER_OCP)
        .filter(key=OuterRef("key"))
        .filter(enabled=True)
    )
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
    SUPPORTED_FILTERS = TagQueryHandler.SUPPORTED_FILTERS + ["project", "enabled", "cluster", "node"]
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
            "node": {"field": "node", "operation": "icontains"},
        }
    )

    def __init__(self, parameters):
        """Establish AWS report query handler.

        Args:
            parameters    (QueryParameters): parameter object for query

        """
        self._parameters = parameters
        if not hasattr(self, "_mapper"):
            self._mapper = OCPProviderMap(**parameters.provider_map_kwargs)

        if parameters.get_filter("enabled") is None:
            parameters.set_filter(**{"enabled": True})
        # super() needs to be called after _mapper is set
        super().__init__(parameters)

    @property
    def filter_map(self):
        """Establish which filter map to use based on tag API."""
        filter_map = deepcopy(TagQueryHandler.FILTER_MAP)
        enabled_parameter = self._parameters.get_filter("enabled") in (None, True)
        if self._parameters.get_filter("value"):
            filter_map.update(
                {
                    "project": {"field": "namespaces", "operation": "contained_by"},
                    "enabled": {"field": "enabled", "operation": "exact", "parameter": enabled_parameter},
                    "cluster": [
                        {"field": "cluster_ids", "operation": "contained_by", "composition_key": "cluster_filter"},
                        {"field": "cluster_aliases", "operation": "contained_by", "composition_key": "cluster_filter"},
                    ],
                    "node": {"field": "nodes", "operation": "contained_by"},
                }
            )
        else:
            filter_map.update(
                {
                    "project": {"field": "namespace", "operation": "icontains"},
                    "enabled": {"field": "enabled", "operation": "exact", "parameter": enabled_parameter},
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
                }
            )
        return filter_map
