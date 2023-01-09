#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View for running_celery_task collect_hcs_report_finalization endpoint."""
import datetime
import logging
import uuid

from django.views.decorators.cache import never_cache
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.decorators import permission_classes
from rest_framework.decorators import renderer_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.settings import api_settings

from api.utils import DateHelper
from hcs.tasks import collect_hcs_report_finalization
from hcs.tasks import HCS_QUEUE

LOG = logging.getLogger(__name__)


@never_cache
@api_view(http_method_names=["GET"])
@permission_classes((AllowAny,))
@renderer_classes(tuple(api_settings.DEFAULT_RENDERER_CLASSES))
def hcs_report_finalization(request):
    """Generate HCS finalized for last month(based on 'datetime.date.today')reports."""

    if request.method == "GET":
        params = request.query_params
        accepted_params = ("month", "year", "provider_type", "provider_uuid", "schema_name")

        for param in params:
            if param not in accepted_params:
                errmsg = f"{param}: is not a valid Request parameter. Valid params: {accepted_params}"
                return Response({"Error": errmsg}, status=status.HTTP_400_BAD_REQUEST)

        month = params.get("month")
        year = params.get("year")
        provider_type = params.get("provider_type")
        provider_uuid = params.get("provider_uuid")
        schema_name = params.get("schema_name")
        tracing_id = str(uuid.uuid4())

        async_results = []

        today = datetime.date.today()
        finalization_month = today.replace(day=1)

        if not month and not year:
            finalization_month = finalization_month - datetime.timedelta(days=1)
        elif not month or not year:
            errmsg = "you must provide both 'month' and 'year' together."
            return Response({"Error": errmsg}, status=status.HTTP_400_BAD_REQUEST)
        else:
            finalization_month = finalization_month.replace(month=int(month), year=int(year))

        if finalization_month >= DateHelper().this_month_start.date():
            errmsg = "finalization can only be run on past months"
            return Response({"Error": errmsg}, status=status.HTTP_400_BAD_REQUEST)

        if provider_type is not None and provider_uuid is not None:
            errmsg = "'provider_type' and 'provider_uuid' are not supported in the same request"
            return Response({"Error": errmsg}, status=status.HTTP_400_BAD_REQUEST)

        if schema_name is not None and provider_uuid is not None:
            errmsg = "'schema_name' and 'provider_uuid' are not supported in the same request"
            return Response({"Error": errmsg}, status=status.HTTP_400_BAD_REQUEST)

        report_data_msg_key = "HCS Report Finalization"

        async_result = collect_hcs_report_finalization.s(
            month, year, provider_type, provider_uuid, schema_name, tracing_id
        ).apply_async(queue=HCS_QUEUE)
        async_results.append({"month": finalization_month.strftime("%Y-%m"), "id": str(async_result)})
        return Response({report_data_msg_key: async_results})
