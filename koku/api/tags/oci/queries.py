#
# Copyright 2022 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""OCI Tag Query Handling."""
from copy import deepcopy

from django.db.models import Exists
from django.db.models import OuterRef

from api.models import Provider
from api.report.oci.provider_map import OCIProviderMap
from api.tags.queries import TagQueryHandler
from reporting.models import OCITagsSummary
from reporting.provider.all.models import EnabledTagKeys
from reporting.provider.oci.models import OCITagsValues


class OCITagQueryHandler(TagQueryHandler):
    """Handles tag queries and responses for OCI."""

    provider = Provider.PROVIDER_OCI
    enabled = EnabledTagKeys.objects.filter(provider_type=Provider.PROVIDER_OCI).filter(key=OuterRef("key"))
    data_sources = [
        {
            "db_table": OCITagsSummary,
            "db_column_period": "cost_entry_bill__billing_period",
            "annotations": {"enabled": Exists(enabled)},
        }
    ]
    TAGS_VALUES_SOURCE = [{"db_table": OCITagsValues, "fields": ["key"]}]
    #  filter_map.update
    SUPPORTED_FILTERS = TagQueryHandler.SUPPORTED_FILTERS + ["payer_tenant_id", "enabled"]

    def __init__(self, parameters):
        """Establish OCI report query handler.

        Args:
            parameters    (QueryParameters): parameter object for query

        """
        self._parameters = parameters
        if not hasattr(self, "_mapper"):
            self._mapper = OCIProviderMap(
                provider=self.provider, report_type=parameters.report_type, schema_name=parameters.tenant.schema_name
            )
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
                    "payer_tenant_id": [
                        {"field": "payer_tenant_ids", "operation": "icontains", "composition_key": "account_filter"}
                    ],
                    "enabled": {"field": "enabled", "operation": "exact", "parameter": enabled_parameter},
                }
            )
        else:
            filter_map.update(
                {
                    "payer_tenant_id": [
                        {"field": "payer_tenant_id", "operation": "icontains", "composition_key": "account_filter"}
                    ],
                    "enabled": {"field": "enabled", "operation": "exact", "parameter": enabled_parameter},
                }
            )
        return filter_map
