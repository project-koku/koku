#
# Copyright 2024 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View for data validation endpoint."""
import logging

from django.views.decorators.cache import never_cache
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.decorators import permission_classes
from rest_framework.decorators import renderer_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.settings import api_settings

from api.models import Provider
from common.queues import get_customer_queue
from common.queues import PriorityQueue
from common.queues import QUEUE_LIST
from masu.processor.tasks import validate_daily_data

LOG = logging.getLogger(__name__)
REPORT_DATA_KEY = "Report Data Task IDs"


@never_cache
@api_view(http_method_names=["GET"])
@permission_classes((AllowAny,))
@renderer_classes(tuple(api_settings.DEFAULT_RENDERER_CLASSES))
def validate_cost_data(request):  # noqa: C901
    """Masu endpoint to trigger cost validation for a provider"""
    if request.method == "GET":
        async_results = []
        params = request.query_params
        async_result = None
        provider_uuid = params.get("provider_uuid")
        ocp_on_cloud_type = params.get("ocp_on_cloud_type", None)
        start_date = params.get("start_date")
        end_date = params.get("end_date")
        if start_date is None:
            errmsg = "start_date is a required parameter."
            return Response({"Error": errmsg}, status=status.HTTP_400_BAD_REQUEST)
        if end_date is None:
            errmsg = "end_date is a required parameter."
            return Response({"Error": errmsg}, status=status.HTTP_400_BAD_REQUEST)
        if provider_uuid is None:
            errmsg = "provider_uuid must be supplied as a parameter."
            return Response({"Error": errmsg}, status=status.HTTP_400_BAD_REQUEST)

        try:
            provider = Provider.objects.get(uuid=provider_uuid)
            provider_schema = provider.account.get("schema_name")
        except Provider.DoesNotExist:
            errmsg = f"provider_uuid {provider_uuid} does not exist."
            return Response({"Error": errmsg}, status=status.HTTP_400_BAD_REQUEST)
        provider_schema = provider.account.get("schema_name")

        if ocp_on_cloud_type:
            if provider.type != Provider.PROVIDER_OCP:
                errmsg = "ocp_on_cloud_type must by used with an ocp provider."
                return Response({"Error": errmsg}, status=status.HTTP_400_BAD_REQUEST)
            supported_types = [Provider.PROVIDER_AWS, Provider.PROVIDER_AZURE, Provider.PROVIDER_GCP]
            if ocp_on_cloud_type not in supported_types:
                errmsg = f"ocp on cloud type must match: {supported_types}"
                return Response({"Error": errmsg}, status=status.HTTP_400_BAD_REQUEST)

        fallback_queue = get_customer_queue(provider_schema, PriorityQueue)
        queue_name = params.get("queue") or fallback_queue

        if queue_name not in QUEUE_LIST:
            errmsg = f"'queue' must be one of {QUEUE_LIST}."
            return Response({"Error": errmsg}, status=status.HTTP_400_BAD_REQUEST)
        context = {"tracing_id": "running provider validation via masu"}

        async_result = validate_daily_data.s(
            provider_schema,
            start_date,
            end_date,
            provider_uuid,
            ocp_on_cloud_type,
            context=context,
        ).apply_async(queue=queue_name)
        async_results.append(str(async_result))
    return Response({REPORT_DATA_KEY: async_results})
