#
# Copyright 2018 Red Hat, Inc.
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

"""OCP-on-AWS Tag Query Handling."""
from api.report.ocp_aws.provider_map import OCPAWSProviderMap
from api.tags.aws.queries import AWSTagQueryHandler
from api.tags.ocp.queries import OCPTagQueryHandler
from reporting.models import OCPAWSCostLineItemDailySummary


class OCPAWSTagQueryHandler(AWSTagQueryHandler, OCPTagQueryHandler):
    """Handles tag queries and responses for OCP-on-AWS."""

    data_sources = [{'db_table': OCPAWSCostLineItemDailySummary,
                     'db_column': 'tags'}]
    provider = 'OCP_AWS'

    def __init__(self, parameters):
        """Establish AWS report query handler.

        Args:
            parameters    (QueryParameters): parameter object for query

        """
        self._mapper = OCPAWSProviderMap(provider=self.provider,
                                         report_type=parameters.report_type)
        # super() needs to be called after _mapper is set
        super().__init__(parameters)
