#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View for Reports."""
import logging

from django.utils.decorators import method_decorator
from django.views.decorators.vary import vary_on_headers
from rest_framework import status
from rest_framework.response import Response
from rest_framework.serializers import ValidationError
from rest_framework.views import APIView

from api.common import CACHE_RH_IDENTITY_HEADER
from api.common.pagination import AWSEC2ComputePagination
from api.common.pagination import OrgUnitPagination
from api.common.pagination import ReportPagination
from api.common.pagination import ReportRankedPagination
from api.query_params import QueryParameters


LOG = logging.getLogger(__name__)


def get_paginator(filter_query_params, count, group_by_params=False, report_type=None):
    """Determine which paginator to use based on query params."""

    if group_by_params and (
        "group_by[org_unit_id]" in group_by_params or "group_by[or:org_unit_id]" in group_by_params
    ):
        paginator = OrgUnitPagination(filter_query_params)
    else:
        if "offset" in filter_query_params:
            paginator = ReportRankedPagination()
            paginator.count = count
        elif report_type and report_type == "ec2_compute":
            paginator = AWSEC2ComputePagination()
        else:
            paginator = ReportPagination()
    paginator.others = count
    return paginator


class ReportView(APIView):
    """
    A shared view for all koku reports.

    This view maps the serializer based on self.provider and self.report.
    It providers one GET endpoint for the reports.
    """

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

        try:
            params = QueryParameters(request=request, caller=self, **kwargs)
        except ValidationError as exc:
            return Response(data=exc.detail, status=status.HTTP_400_BAD_REQUEST)
        handler = self.query_handler(params)

        output = handler.execute_query()

        # reset the meta when order_by[date] is used
        if output.get("cost_explorer_order_by"):
            order_by_date = output.pop("cost_explorer_order_by")
            output.get("order_by").update(order_by_date)

        max_rank = handler.max_rank

        get_report_type = getattr(handler, "_report_type", None)

        paginator = get_paginator(
            params.parameters.get("filter", {}), max_rank, request.query_params, report_type=get_report_type
        )
        paginated_result = paginator.paginate_queryset(output, request)

        return paginator.get_paginated_response(paginated_result)
