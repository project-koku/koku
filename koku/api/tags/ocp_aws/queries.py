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
from api.tags.aws.queries import AWSTagQueryHandler
from api.tags.ocp.queries import OCPTagQueryHandler
from reporting.models import OCPAWSCostLineItemDailySummary


class OCPAWSTagQueryHandler(AWSTagQueryHandler, OCPTagQueryHandler):
    """Handles tag queries and responses for OCP-on-AWS."""

    def __init__(self, query_parameters, url_data,
                 tenant, **kwargs):
        """Establish OCP-on-AWS report query handler.

        Args:
            query_parameters    (Dict): parameters for query
            url_data        (String): URL string to provide order information
            tenant    (String): the tenant to use to access CUR data
            kwargs    (Dict): A dictionary for internal query alteration based on path
        """
        super().__init__(query_parameters, url_data, tenant, **kwargs)
        self.data_sources = [{'db_table': OCPAWSCostLineItemDailySummary,
                              'db_column': 'tags'}]
