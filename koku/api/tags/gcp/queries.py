#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""GCP Tag Query Handling."""
import logging
from copy import deepcopy

from django.db.models import Exists
from django.db.models import OuterRef

from api.models import Provider
from api.report.gcp.provider_map import GCPProviderMap
from api.tags.queries import TagQueryHandler
from reporting.models import GCPTagsSummary
from reporting.provider.gcp.models import GCPEnabledTagKeys
from reporting.provider.gcp.models import GCPTagsValues


LOG = logging.getLogger(__name__)


class GCPTagQueryHandler(TagQueryHandler):
    """Handles tag queries and responses for GCP."""

    provider = Provider.PROVIDER_GCP
    enabled = GCPEnabledTagKeys.objects.filter(key=OuterRef("key"))
    data_sources = [
        {
            "db_table": GCPTagsSummary,
            "db_column_period": "cost_entry_bill__billing_period",
            "annotations": {"enabled": Exists(enabled)},
        }
    ]
    TAGS_VALUES_SOURCE = [{"db_table": GCPTagsValues, "fields": ["key"]}]
    # TODO: COST-1986
    # SUPPORTED_FILTERS, filter_map.update
    SUPPORTED_FILTERS = TagQueryHandler.SUPPORTED_FILTERS + ["account", "project", "gcp_project", "enabled"]

    def __init__(self, parameters):
        """Establish GCP report query handler.

        Args:
            parameters    (QueryParameters): parameter object for query

        """
        self._parameters = parameters
        if not hasattr(self, "_mapper"):
            self._mapper = GCPProviderMap(provider=self.provider, report_type=parameters.report_type)
        if parameters.get_filter("enabled") is None:
            parameters.set_filter(**{"enabled": True})
        # super() needs to be called after _mapper is set
        super().__init__(parameters)

    @property
    def filter_map(self):
        """Establish which filter map to use based on tag API."""
        enabled_parameter = self._parameters.get_filter("enabled") in (None, True)
        filter_map = deepcopy(TagQueryHandler.FILTER_MAP)
        if self._parameters.get_filter("value"):
            filter_map.update(
                {
                    "account": [
                        {"field": "account_ids", "operation": "icontains", "composition_key": "account_filter"}
                    ],
                    "project": [
                        {"field": "project_ids", "operation": "icontains", "composition_key": "project_filter"},
                        {"field": "project_names", "operation": "icontains", "composition_key": "project_filter"},
                    ],
                    "gcp_project": [
                        {"field": "project_ids", "operation": "icontains", "composition_key": "project_filter"},
                        {"field": "project_names", "operation": "icontains", "composition_key": "project_filter"},
                    ],
                    "enabled": {"field": "enabled", "operation": "exact", "parameter": enabled_parameter},
                }
            )
        else:
            filter_map.update(
                {
                    "account": [
                        {"field": "account_id", "operation": "icontains", "composition_key": "account_filter"}
                    ],
                    "project": [
                        {"field": "project_id", "operation": "icontains", "composition_key": "project_filter"},
                        {"field": "project_name", "operation": "icontains", "composition_key": "project_filter"},
                    ],
                    "gcp_project": [
                        {"field": "project_ids", "operation": "icontains", "composition_key": "project_filter"},
                        {"field": "project_names", "operation": "icontains", "composition_key": "project_filter"},
                    ],
                    "enabled": {"field": "enabled", "operation": "exact", "parameter": enabled_parameter},
                }
            )
        return filter_map
