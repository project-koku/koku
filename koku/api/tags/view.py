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
"""View for tags."""
import logging

from django.http import Http404
from django.utils.decorators import method_decorator
from django.views.decorators.vary import vary_on_headers
from rest_framework import status
from rest_framework.response import Response
from rest_framework.serializers import ValidationError

from api.common import CACHE_RH_IDENTITY_HEADER
from api.query_params import QueryParameters
from api.report.view import get_paginator
from api.report.view import ReportView

LOG = logging.getLogger(__name__)


class TagView(ReportView):
    """Base Tag View."""

    report = "tags"

    @method_decorator(vary_on_headers(CACHE_RH_IDENTITY_HEADER))
    def get(self, request, **kwargs):
        """Get Report Data.

        This method is responsible for passing request data to the reporting APIs.

        Args:
            request (Request): The HTTP request object

        Returns:
            (Response): The report in a Response object

        """
        LOG.debug(f"API: {request.path} USER: {request.user.username}")

        key = kwargs.get("key")
        if key and not self.validate_key(key):
            raise Http404

        try:
            params = QueryParameters(request=request, caller=self, **kwargs)
        except ValidationError as exc:
            return Response(data=exc.detail, status=status.HTTP_400_BAD_REQUEST)

        if key and params.get("key_only"):
            LOG.debug("Invalid query parameter 'key_only'.")
            error = {"details": "Invalid query parameter 'key_only'."}
            raise ValidationError(error)

        handler = self.query_handler(params)
        output = handler.execute_query()
        if key:
            output["data"] = [val for dikt in output.get("data") for val in dikt.get("values")]
        max_rank = handler.max_rank

        paginator = get_paginator(params.parameters.get("filter", {}), max_rank)
        paginated_result = paginator.paginate_queryset(output, request)
        LOG.debug(f"DATA: {output}")
        return paginator.get_paginated_response(paginated_result)

    def validate_key(self, key):
        """Validate that tag key exists."""
        count = 0
        for handler in self.tag_handler:
            count += handler.objects.filter(key=key).count()
        return count != 0
