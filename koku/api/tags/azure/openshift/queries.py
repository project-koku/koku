#
# Copyright 2019 Red Hat, Inc.
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
            "annotations": {"enabled": Exists(AzureEnabledTagKeys.objects.filter(key=OuterRef("key")))},
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
                {
                    "subscription_guid": {"field": "subscription_guids", "operation": "icontains"},
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
                    "subscription_guid": {"field": "subscription_guid", "operation": "icontains"},
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
