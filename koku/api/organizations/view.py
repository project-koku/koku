#
# Copyright 2020 Red Hat, Inc.
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
"""View for Organizations."""
import logging

from django.views.decorators.vary import vary_on_headers
from rest_framework import status
from rest_framework.response import Response
from rest_framework.serializers import ValidationError
from rest_framework.views import APIView

from api.common import RH_IDENTITY_HEADER
from api.common.pagination import ReportPagination
from api.common.pagination import ReportRankedPagination
from api.query_params import QueryParameters


LOG = logging.getLogger(__name__)


def get_paginator(filter_query_params, count):
    """Determine which paginator to use based on query params."""
    if "offset" in filter_query_params:
        paginator = ReportRankedPagination()
        paginator.count = count
    else:
        paginator = ReportPagination()
    return paginator


class OrganizationView(APIView):
    """
    A shared view for all koku organizations.

    This view maps the serializer based on self.provider and self.report.
    It providers one GET endpoint for the reports.
    """

    @vary_on_headers(RH_IDENTITY_HEADER)
    def get(self, request):
        """Get Report Data.

        This method is responsible for passing request data to the reporting APIs.

        Args:
            request (Request): The HTTP request object

        Returns:
            (Response): The report in a Response object

        """
        LOG.debug(f"API: {request.path} USER: {request.user.username}")

        try:
            params = QueryParameters(request=request, caller=self)
        except ValidationError as exc:
            return Response(data=exc.detail, status=status.HTTP_400_BAD_REQUEST)
        handler = self.query_handler(params)
        output = handler.execute_query()
        max_rank = handler.max_rank
        paginator = get_paginator(params.parameters.get("filter", {}), max_rank)
        paginated_result = paginator.paginate_queryset(output, request)
        LOG.debug(f"DATA: {output}")
        return paginator.get_paginated_response(paginated_result)
