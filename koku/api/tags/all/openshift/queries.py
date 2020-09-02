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
"""OCP-on-All Tag Query Handling."""
from copy import deepcopy

from django.db.models import DecimalField
from django.db.models import F
from django.db.models import Value

from api.models import Provider
from api.report.all.openshift.provider_map import OCPAllProviderMap
from api.tags.queries import TagQueryHandler
from reporting.models import OCPAWSTagsSummary
from reporting.models import OCPAzureTagsSummary
from reporting.provider.aws.openshift.models import OCPAWSTagsValues
from reporting.provider.azure.openshift.models import OCPAzureTagsValues


class OCPAllTagQueryHandler(TagQueryHandler):
    """Handles tag queries and responses for OCP-on-All."""

    provider = Provider.OCP_ALL
    data_sources = [
        {"db_table": OCPAWSTagsSummary, "db_column_period": "cost_entry_bill__billing_period"},
        {
            "db_table": OCPAzureTagsSummary,
            "db_column_period": "cost_entry_bill__billing_period",
            "annotations": {
                "usage_account_id": F("subscription_guid"),
                "account_alias__account_alias": Value(0, output_field=DecimalField()),
            },
        },
    ]
    TAGS_VALUES_SOURCE = [
        {"db_table": OCPAzureTagsValues, "fields": ["ocpazuretagssummary__key"]},
        {"db_table": OCPAWSTagsValues, "fields": ["ocpawstagssummary__key"]},
    ]
    SUPPORTED_FILTERS = TagQueryHandler.SUPPORTED_FILTERS + ["account", "cluster"]
    FILTER_MAP = deepcopy(TagQueryHandler.FILTER_MAP)
    FILTER_MAP.update(
        {
            "account": [
                {
                    "field": "account_alias__account_alias",
                    "operation": "icontains",
                    "composition_key": "account_filter",
                },
                {"field": "usage_account_id", "operation": "icontains", "composition_key": "account_filter"},
            ],
            "cluster": [
                {"field": "cluster_id", "operation": "icontains", "composition_key": "cluster_filter"},
                {"field": "cluster_alias", "operation": "icontains", "composition_key": "cluster_filter"},
            ],
        }
    )

    def __init__(self, parameters):
        """Establish OCP on All infrastructure tag query handler.

        Args:
            parameters    (QueryParameters): parameter object for query

        """
        self._mapper = OCPAllProviderMap(provider=self.provider, report_type=parameters.report_type)
        # super() needs to be called after _mapper is set
        super().__init__(parameters)
