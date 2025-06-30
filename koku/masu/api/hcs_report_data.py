#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View for running_celery_tasks endpoint."""
import logging
import uuid
from datetime import timedelta

import ciso8601
from django.conf import settings
from django.views.decorators.cache import never_cache
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.decorators import permission_classes
from rest_framework.decorators import renderer_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.settings import api_settings

from api.provider.models import Provider
from api.utils import DateHelper
from hcs.tasks import collect_hcs_report_data
from hcs.tasks import HCS_QUEUE

LOG = logging.getLogger(__name__)


@never_cache
@api_view(http_method_names=["GET"])
@permission_classes((AllowAny,))
@renderer_classes(tuple(api_settings.DEFAULT_RENDERER_CLASSES))
def hcs_report_data(request):
    """Generate HCS report data."""
    params = request.query_params
    end_date = params.get("end_date")
    start_date = params.get("start_date")
    provider_uuid = params.get("provider_uuid")
    provider_type = params.get("provider_type")
    schema_name = params.get("schema")

    async_results = []
    tracing_id = str(uuid.uuid4())

    report_data_msg_key = "HCS Report Data Task ID"
    error_msg_key = "Error"

    if request.method == "GET":
        if provider_uuid is None:
            errmsg = "provider_uuid must be supplied as a parameter"
            return Response({"Error": errmsg}, status=status.HTTP_400_BAD_REQUEST)

        if schema_name is None:
            return Response({error_msg_key: "schema is a required parameter"}, status=status.HTTP_400_BAD_REQUEST)

        if provider_type is None:
            p = Provider.objects.get(uuid=provider_uuid)
            LOG.debug(f"PROVIDER: {p}")
            provider = p.type
        else:
            provider = provider_type

        if provider is None:
            return Response({error_msg_key: "unable to determine provider type"}, status=status.HTTP_400_BAD_REQUEST)

        if provider_type and provider_type != provider:
            return Response(
                {error_msg_key: "provider_uuid and provider_type have mismatched provider types"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        start_date = (
            ciso8601.parse_datetime(start_date).replace(tzinfo=settings.UTC)
            if start_date
            else DateHelper().today - timedelta(days=2)
        )
        end_date = ciso8601.parse_datetime(end_date).replace(tzinfo=settings.UTC) if end_date else DateHelper().today
        months = DateHelper().list_month_tuples(start_date, end_date)

        for month in months:
            async_result = collect_hcs_report_data.s(
                schema_name, provider, provider_uuid, month[0], month[1], tracing_id
            ).apply_async(queue=HCS_QUEUE)
            async_results.append({str(month): str(async_result)})

        return Response({report_data_msg_key: async_results})
