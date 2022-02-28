#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""OCP-on-GCP Tag Query Handling."""
from copy import deepcopy

from django.db.models import Exists
from django.db.models import OuterRef

from api.models import Provider
from api.report.gcp.openshift.provider_map import OCPGCPProviderMap
from api.tags.gcp.queries import GCPTagQueryHandler
from api.tags.ocp.queries import OCPTagQueryHandler
from api.tags.queries import TagQueryHandler
from reporting.models import OCPGCPTagsSummary
from reporting.provider.gcp.models import GCPEnabledTagKeys
from reporting.provider.gcp.openshift.models import OCPGCPTagsValues
from reporting.provider.ocp.models import OCPEnabledTagKeys


class OCPGCPTagQueryHandler(GCPTagQueryHandler, OCPTagQueryHandler):
    """Handles tag queries and responses for OCP-on-GCP."""

    provider = Provider.OCP_GCP
    data_sources = [
        {
            "db_table": OCPGCPTagsSummary,
            "db_column_period": "cost_entry_bill__billing_period",
            "annotations": {"enabled": Exists(GCPEnabledTagKeys.objects.filter(key=OuterRef("key")))},
        },
        {
            "db_table": OCPGCPTagsSummary,
            "db_column_period": "cost_entry_bill__billing_period",
            "annotations": {"enabled": Exists(OCPEnabledTagKeys.objects.filter(key=OuterRef("key")))},
        },
    ]
    TAGS_VALUES_SOURCE = [{"db_table": OCPGCPTagsValues, "fields": ["key"]}]
    SUPPORTED_FILTERS = GCPTagQueryHandler.SUPPORTED_FILTERS + OCPTagQueryHandler.SUPPORTED_FILTERS

    def __init__(self, parameters):
        """Establish GCP report query handler.

        Args:
            parameters    (QueryParameters): parameter object for query

        """
        self._parameters = parameters
        self._mapper = OCPGCPProviderMap(provider=self.provider, report_type=parameters.report_type)
        if parameters.get_filter("enabled") is None:
            parameters.set_filter(**{"enabled": True})
        # super() needs to be called after _mapper is set
        super().__init__(parameters)

    @property
    def filter_map(self):
        """Establish which filter map to use based on tag API."""
        filter_map = deepcopy(TagQueryHandler.FILTER_MAP)
        if self._parameters.get_filter("value"):
            filter_map.update(
                {
                    "account": {"field": "account_ids", "operation": "icontains"},
                    "project": {"field": "namespaces", "operation": "icontains"},
                    "cluster": [
                        {"field": "cluster_ids", "operation": "icontains", "composition_key": "cluster_filter"},
                        {"field": "cluster_aliases", "operation": "icontains", "composition_key": "cluster_filter"},
                    ],
                    "enabled": {"field": "enabled", "operation": "exact", "parameter": True},
                }
            )
        else:
            filter_map.update(
                {
                    "account": {"field": "account_id", "operation": "icontains"},
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
                    "enabled": {"field": "enabled", "operation": "exact", "parameter": True},
                }
            )
        return filter_map
