#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View for report_data endpoint."""
# flake8: noqa
import logging
from uuid import uuid4

from celery import chain
from celery import group
from django.views.decorators.cache import never_cache
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.decorators import permission_classes
from rest_framework.decorators import renderer_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.settings import api_settings

from api.provider.models import Provider
from api.utils import get_months_in_date_range
from masu.processor.ocp.ocp_cloud_parquet_summary_updater import DELETE_TABLE
from masu.processor.ocp.ocp_cloud_parquet_summary_updater import OCPCloudParquetReportSummaryUpdater
from masu.processor.tasks import delete_openshift_on_cloud_data
from masu.processor.tasks import PRIORITY_QUEUE
from masu.processor.tasks import QUEUE_LIST
from masu.processor.tasks import update_openshift_on_cloud as update_openshift_on_cloud_task

LOG = logging.getLogger(__name__)
REPORT_DATA_KEY = "Report Data Task IDs"


@never_cache
@api_view(http_method_names=["GET"])
@permission_classes((AllowAny,))
@renderer_classes(tuple(api_settings.DEFAULT_RENDERER_CLASSES))
def update_openshift_on_cloud(request):
    """Update OCP on Cloud report summary tables in the database."""
    if request.method == "GET":
        async_result = None
        async_results = []
        params = request.query_params
        openshift_provider_uuid = params.get("provider_uuid")
        schema_name = params.get("schema")
        start_date = params.get("start_date")
        end_date = params.get("end_date")
        queue_name = params.get("queue") or PRIORITY_QUEUE

        if openshift_provider_uuid is None:
            errmsg = "provider_uuid is a required parameter."
            return Response({"Error": errmsg}, status=status.HTTP_400_BAD_REQUEST)
        if queue_name not in QUEUE_LIST:
            errmsg = f"'queue' must be one of {QUEUE_LIST}."
            return Response({"Error": errmsg}, status=status.HTTP_400_BAD_REQUEST)
        if start_date is None:
            errmsg = "start_date is a required parameter."
            return Response({"Error": errmsg}, status=status.HTTP_400_BAD_REQUEST)
        if schema_name is None:
            errmsg = "schema is a required parameter."
            return Response({"Error": errmsg}, status=status.HTTP_400_BAD_REQUEST)

        try:
            provider = Provider.objects.get(uuid=openshift_provider_uuid)
        except Provider.DoesNotExist:
            errmsg = f"provider_uuid: {openshift_provider_uuid} does not exist."
            return Response({"Error": errmsg}, status=status.HTTP_400_BAD_REQUEST)

        if provider.type != Provider.PROVIDER_OCP:
            errmsg = "You must provider an OpenShift provider UUID."
            return Response({"Error": errmsg}, status=status.HTTP_400_BAD_REQUEST)

        infra_provider_uuid = provider.infrastructure.infrastructure_provider.uuid
        infra_type = provider.infrastructure.infrastructure_type

        months = get_months_in_date_range(start=start_date, end=end_date)
        infra_provider = Provider.objects.get(uuid=infra_provider_uuid)
        updater = OCPCloudParquetReportSummaryUpdater(schema_name, infra_provider, None)
        for month in months:
            tracing_id = uuid4()
            delete_signature_list = []
            trunc_delete_map = updater.determine_truncates_and_deletes(month[0], month[1])
            for table, operation in trunc_delete_map.items():
                delete_params = {
                    "schema_name": schema_name,
                    "infrastructure_provider_uuid": infra_provider_uuid,
                    "start_date": month[0],
                    "end_date": month[1],
                    "table_name": table,
                    "operation": operation,
                    "queue_name": queue_name,
                    "tracing_id": tracing_id,
                }
                delete_signature_list.append(delete_openshift_on_cloud_data.si(**delete_params))
            summary_params = {
                "schema_name": schema_name,
                "openshift_provider_uuid": openshift_provider_uuid,
                "infrastructure_provider_uuid": infra_provider_uuid,
                "infrastructure_provider_type": infra_type,
                "start_date": month[0],
                "end_date": month[1],
                "queue_name": queue_name,
                "tracing_id": tracing_id,
            }
            LOG.info("Triggering update_openshift_on_cloud task with params:")
            LOG.info(params)
            summary_signature = [update_openshift_on_cloud_task.si(**summary_params)]

            deletes = group(delete_signature_list)
            summaries = group(summary_signature)
            c = chain(deletes, summaries)

            async_result = c.apply_async(queue=queue_name or PRIORITY_QUEUE)
            async_results.append({str(month): str(async_result)})

        return Response({REPORT_DATA_KEY: async_results})
