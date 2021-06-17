#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
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

        if not key and params.get_filter("value"):
            LOG.debug("Invalid query parameter 'value'.")
            error = {"details": "Invalid query parameter 'value'."}
            raise ValidationError(error)

        handler = self.query_handler(params)
        output = handler.execute_query()
        if key:
            lizt = []
            for dikt in output.get("data"):
                if isinstance(dikt.get("values"), list):
                    for val in dikt.get("values"):
                        lizt.append(val)
                else:
                    lizt.append(dikt.get("values"))
            output["data"] = lizt

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
