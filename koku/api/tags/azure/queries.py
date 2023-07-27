#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Azure Tag Query Handling."""
from copy import deepcopy

from django.db.models import Exists
from django.db.models import OuterRef

from api.models import Provider
from api.report.azure.provider_map import AzureProviderMap
from api.tags.queries import TagQueryHandler
from reporting.models import AzureTagsSummary
from reporting.provider.all.models import EnabledTagKeys
from reporting.provider.azure.models import AzureTagsValues


class AzureTagQueryHandler(TagQueryHandler):
    """Handles tag queries and responses for Azure."""

    provider = Provider.PROVIDER_AZURE
    enabled = EnabledTagKeys.objects.filter(provider_type=provider).filter(key=OuterRef("key")).filter(enabled=True)
    data_sources = [
        {
            "db_table": AzureTagsSummary,
            "db_column_period": "cost_entry_bill__billing_period",
            "annotations": {"enabled": Exists(enabled)},
        }
    ]
    TAGS_VALUES_SOURCE = [{"db_table": AzureTagsValues, "fields": ["key"]}]
    SUPPORTED_FILTERS = TagQueryHandler.SUPPORTED_FILTERS + ["subscription_guid", "enabled"]

    def __init__(self, parameters):
        """Establish Azure report query handler.

        Args:
            parameters    (QueryParameters): parameter object for query

        """
        self._parameters = parameters
        if not hasattr(self, "_mapper"):
            self._mapper = AzureProviderMap(provider=self.provider, report_type=parameters.report_type)
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
                    "subscription_guid": {"field": "subscription_guids", "operation": "icontains"},
                    "enabled": {"field": "enabled", "operation": "exact", "parameter": enabled_parameter},
                }
            )
        else:
            filter_map.update(
                {
                    "subscription_guid": {"field": "subscription_guid", "operation": "icontains"},
                    "enabled": {"field": "enabled", "operation": "exact", "parameter": enabled_parameter},
                }
            )
        return filter_map
