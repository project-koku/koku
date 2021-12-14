#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""AWS Tag Query Handling."""
from copy import deepcopy

from django.db.models import Exists
from django.db.models import OuterRef

from api.models import Provider
from api.report.aws.provider_map import AWSProviderMap
from api.tags.queries import TagQueryHandler
from koku.settings import KOKU_DEFAULT_COST_TYPE
from reporting.models import AWSTagsSummary
from reporting.provider.aws.models import AWSEnabledTagKeys
from reporting.provider.aws.models import AWSTagsValues


class AWSTagQueryHandler(TagQueryHandler):
    """Handles tag queries and responses for AWS."""

    provider = Provider.PROVIDER_AWS
    enabled = AWSEnabledTagKeys.objects.filter(key=OuterRef("key")).filter(enabled=True)
    data_sources = [
        {
            "db_table": AWSTagsSummary,
            "db_column_period": "cost_entry_bill__billing_period",
            "annotations": {"enabled": Exists(enabled)},
        }
    ]
    TAGS_VALUES_SOURCE = [{"db_table": AWSTagsValues, "fields": ["key"]}]
    SUPPORTED_FILTERS = TagQueryHandler.SUPPORTED_FILTERS + ["account", "enabled"]

    def __init__(self, parameters):
        """Establish AWS report query handler.

        Args:
            parameters    (QueryParameters): parameter object for query

        """
        self._parameters = parameters
        if not hasattr(self, "_mapper"):
            self._mapper = AWSProviderMap(
                provider=self.provider,
                report_type=parameters.report_type,
                cost_type=parameters.parameters.get("cost_type", KOKU_DEFAULT_COST_TYPE),
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
                    "account": [
                        {"field": "account_aliases", "operation": "icontains", "composition_key": "account_filter"},
                        {"field": "usage_account_ids", "operation": "icontains", "composition_key": "account_filter"},
                    ],
                    "enabled": {"field": "enabled", "operation": "exact", "parameter": enabled_parameter},
                }
            )
        else:
            filter_map.update(
                {
                    "account": [
                        {
                            "field": "account_alias__account_alias",
                            "operation": "icontains",
                            "composition_key": "account_filter",
                        },
                        {"field": "usage_account_id", "operation": "icontains", "composition_key": "account_filter"},
                    ],
                    "enabled": {"field": "enabled", "operation": "exact", "parameter": enabled_parameter},
                }
            )
        return filter_map
