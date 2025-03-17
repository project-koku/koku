#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View for report_data endpoint."""
# flake8: noqa
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
from api.utils import get_months_in_date_range
from common.queues import get_customer_queue
from common.queues import PriorityQueue
from common.queues import QUEUE_LIST
from masu.processor import is_managed_ocp_cloud_summary_enabled
from masu.processor.tasks import process_openshift_on_cloud_trino
from masu.processor.tasks import update_summary_tables

LOG = logging.getLogger(__name__)
REPORT_DATA_KEY = "Report Data Task IDs"


@never_cache
@api_view(http_method_names=["GET"])
@permission_classes((AllowAny,))
@renderer_classes(tuple(api_settings.DEFAULT_RENDERER_CLASSES))
def report_data(request):
    """Update report summary tables in the database."""
    if request.method == "GET":
        async_results = []
        params = request.query_params
        async_result = None
        provider_uuid = params.get("provider_uuid")
        schema_name = params.get("schema")
        start_date = params.get("start_date")
        end_date = params.get("end_date")
        invoice_month = params.get("invoice_month")
        # Set boolean for ocp_on_cloud based on param string
        ocp_on_cloud = params.get("ocp_on_cloud", "true").lower() == "true"

        fallback_queue = get_customer_queue(schema_name, PriorityQueue)
        queue_name = params.get("queue") or fallback_queue

        if provider_uuid is None:
            errmsg = "provider_uuid must be supplied as a parameter."
            return Response({"Error": errmsg}, status=status.HTTP_400_BAD_REQUEST)
        if schema_name is None:
            errmsg = "schema is a required parameter."
            return Response({"Error": errmsg}, status=status.HTTP_400_BAD_REQUEST)
        if queue_name not in QUEUE_LIST:
            errmsg = f"'queue' must be one of {QUEUE_LIST}."
            return Response({"Error": errmsg}, status=status.HTTP_400_BAD_REQUEST)
        if start_date is None:
            errmsg = "start_date is a required parameter."
            return Response({"Error": errmsg}, status=status.HTTP_400_BAD_REQUEST)

        try:
            provider = Provider.objects.get(uuid=provider_uuid)
            provider_schema = provider.account.get("schema_name")
            provider_type = provider.type
        except Provider.DoesNotExist:
            errmsg = f"provider_uuid {provider_uuid} does not exist"
            return Response({"Error": errmsg}, status=status.HTTP_400_BAD_REQUEST)
        if provider_schema != schema_name:
            errmsg = f"provider_uuid {provider_uuid} is not associated with schema {schema_name}."
            return Response({"Error": errmsg}, status=status.HTTP_400_BAD_REQUEST)

        # For GCP invoice month summary periods
        if not invoice_month:
            if provider_type in [Provider.PROVIDER_GCP, Provider.PROVIDER_GCP_LOCAL]:
                if end_date:
                    invoice_month = end_date[0:4] + end_date[5:7]
                else:
                    invoice_month = start_date[0:4] + start_date[5:7]

        months = get_months_in_date_range(start=start_date, end=end_date, invoice_month=invoice_month)

        for month in months:
            async_result = update_summary_tables.s(
                schema_name,
                provider_type,
                provider_uuid,
                month[0],
                month[1],
                invoice_month=month[2],
                queue_name=queue_name,
                ocp_on_cloud=ocp_on_cloud,
            ).apply_async(queue=queue_name or fallback_queue)
            async_results.append({str(month): str(async_result)})
            # If managed flow is enabled trigger trino managed processing
            if is_managed_ocp_cloud_summary_enabled(schema_name, provider_type):
                tracing_id = str(async_result)
                report = {
                    "schema_name": schema_name,
                    "provider_type": provider_type,
                    "provider_uuid": provider_uuid,
                    "tracing_id": tracing_id,
                    "start": month[0],
                    "end": month[1],
                    "invoice_month": month[2],
                }
                ocp_async = process_openshift_on_cloud_trino.s(
                    [report], provider_type, schema_name, provider_uuid, tracing_id, masu_api_trigger=True
                ).apply_async(queue=queue_name or fallback_queue)
                async_results.append({f"Managed OCP on Cloud {str(month)}": str(ocp_async)})
        return Response({REPORT_DATA_KEY: async_results})
