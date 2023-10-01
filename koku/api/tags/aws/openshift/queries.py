#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""OCP-on-AWS Tag Query Handling."""
from copy import deepcopy

from django.db.models import Exists
from django.db.models import OuterRef

from api.models import Provider
from api.report.aws.openshift.provider_map import OCPAWSProviderMap
from api.tags.aws.queries import AWSTagQueryHandler
from api.tags.ocp.queries import OCPTagQueryHandler
from api.tags.queries import TagQueryHandler
from reporting.models import OCPAWSTagsSummary
from reporting.provider.all.models import EnabledTagKeys
from reporting.provider.aws.openshift.models import OCPAWSTagsValues


class OCPAWSTagQueryHandler(AWSTagQueryHandler, OCPTagQueryHandler):
    """Handles tag queries and responses for OCP-on-AWS."""

    provider = Provider.OCP_AWS
    data_sources = [
        {
            "db_table": OCPAWSTagsSummary,
            "db_column_period": "cost_entry_bill__billing_period",
            "annotations": {
                "enabled": Exists(
                    EnabledTagKeys.objects.filter(
                        provider_type=Provider.PROVIDER_AWS,
                        key=OuterRef("key"),
                        enabled=True,
                    )
                )
            },
        },
        {
            "db_table": OCPAWSTagsSummary,
            "db_column_period": "cost_entry_bill__billing_period",
            "annotations": {
                "enabled": Exists(
                    EnabledTagKeys.objects.filter(provider_type=Provider.PROVIDER_OCP, key=OuterRef("key"))
                )
            },
        },
    ]
    TAGS_VALUES_SOURCE = [{"db_table": OCPAWSTagsValues, "fields": ["key"]}]
    SUPPORTED_FILTERS = AWSTagQueryHandler.SUPPORTED_FILTERS + OCPTagQueryHandler.SUPPORTED_FILTERS

    def __init__(self, parameters):
        """Establish AWS report query handler.

        Args:
            parameters    (QueryParameters): parameter object for query

        """
        self._parameters = parameters
        self._mapper = OCPAWSProviderMap(parameters)
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
                    "account": [
                        {"field": "account_aliases", "operation": "icontains", "composition_key": "account_filter"},
                        {"field": "usage_account_ids", "operation": "icontains", "composition_key": "account_filter"},
                    ],
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
                    "account": [
                        {
                            "field": "account_alias__account_alias",
                            "operation": "icontains",
                            "composition_key": "account_filter",
                        },
                        {"field": "usage_account_id", "operation": "icontains", "composition_key": "account_filter"},
                    ],
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
