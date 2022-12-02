#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""OCP-on-Azure Tag Query Handling."""
from copy import deepcopy

from django.db.models import Exists
from django.db.models import OuterRef

from api.models import Provider
from api.report.azure.openshift.provider_map import OCPAzureProviderMap
from api.tags.azure.queries import AzureTagQueryHandler
from api.tags.ocp.queries import OCPTagQueryHandler
from api.tags.queries import TagQueryHandler
from reporting.models import OCPAzureTagsSummary
from reporting.provider.azure.models import AzureEnabledTagKeys
from reporting.provider.azure.openshift.models import OCPAzureTagsValues
from reporting.provider.ocp.models import OCPEnabledTagKeys


class OCPAzureTagQueryHandler(AzureTagQueryHandler, OCPTagQueryHandler):
    """Handles tag queries and responses for OCP-on-Azure."""

    provider = Provider.OCP_AZURE
    data_sources = [
        {
            "db_table": OCPAzureTagsSummary,
            "db_column_period": "cost_entry_bill__billing_period",
            "annotations": {
                "enabled": Exists(AzureEnabledTagKeys.objects.filter(key=OuterRef("key")).filter(enabled=True))
            },
        },
        {
            "db_table": OCPAzureTagsSummary,
            "db_column_period": "cost_entry_bill__billing_period",
            "annotations": {"enabled": Exists(OCPEnabledTagKeys.objects.filter(key=OuterRef("key")))},
        },
    ]
    TAGS_VALUES_SOURCE = [{"db_table": OCPAzureTagsValues, "fields": ["key"]}]
    SUPPORTED_FILTERS = AzureTagQueryHandler.SUPPORTED_FILTERS + OCPTagQueryHandler.SUPPORTED_FILTERS

    def __init__(self, parameters):
        """Establish Azure report query handler.

        Args:
            parameters    (QueryParameters): parameter object for query

        """
        self._parameters = parameters
        self._mapper = OCPAzureProviderMap(provider=self.provider, report_type=parameters.report_type)
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
                dict(
                    {
                        "subscription_guid": {"field": "subscription_guids", "operation": "icontains"},
                        "enabled": {"field": "enabled", "operation": "exact", "parameter": True},
                    },
                    **OCPTagQueryHandler.FILTER_MAP_OCP_MULTI
                )
            )
        else:
            filter_map.update(
                dict(
                    {
                        "subscription_guid": {"field": "subscription_guid", "operation": "icontains"},
                        "enabled": {"field": "enabled", "operation": "exact", "parameter": True},
                    },
                    **OCPTagQueryHandler.FILTER_MAP_OCP_SINGLE
                )
            )
        return filter_map
