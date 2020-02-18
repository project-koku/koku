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
from api.models import Provider
from api.report.all.openshift.provider_map import OCPAllProviderMap
from api.tags.queries import TagQueryHandler
from reporting.models import OCPAllCostLineItemDailySummary


class OCPAllTagQueryHandler(TagQueryHandler):
    """Handles tag queries and responses for OCP-on-All."""

    data_sources = [{"db_table": OCPAllCostLineItemDailySummary, "db_column": "tags"}]
    provider = Provider.OCP_ALL

    def __init__(self, parameters):
        """Establish OCP on All infrastructure tag query handler.

        Args:
            parameters    (QueryParameters): parameter object for query

        """
        self._mapper = OCPAllProviderMap(provider=self.provider, report_type=parameters.report_type)
        # super() needs to be called after _mapper is set
        super().__init__(parameters)
