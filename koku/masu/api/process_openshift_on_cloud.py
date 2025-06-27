#
# Copyright 2022 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View for report_data endpoint."""
import logging
from uuid import uuid4

import ciso8601
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
from api.utils import get_months_in_date_range
from common.queues import DownloadQueue
from common.queues import get_customer_queue
from common.queues import QUEUE_LIST
from masu.processor.tasks import process_daily_openshift_on_cloud as process_daily_openshift_on_cloud_task
from masu.processor.tasks import process_openshift_on_cloud as process_openshift_on_cloud_task

LOG = logging.getLogger(__name__)
REPORT_DATA_KEY = "process_openshift_on_cloud Task IDs"


@never_cache
@api_view(http_method_names=["GET"])
@permission_classes((AllowAny,))
@renderer_classes(tuple(api_settings.DEFAULT_RENDERER_CLASSES))
def process_openshift_on_cloud(request):  # noqa: C901
    """Update OCP on Cloud report summary tables in the database."""
    async_results = []
    params = request.query_params
    cloud_provider_uuid = params.get("provider_uuid")
    schema_name = params.get("schema")
    start_date = params.get("start_date")
    end_date = params.get("end_date")
    fallback_queue = get_customer_queue(schema_name, DownloadQueue)
    queue_name = params.get("queue") or fallback_queue

    if cloud_provider_uuid is None:
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
        provider = Provider.objects.get(uuid=cloud_provider_uuid)
    except Provider.DoesNotExist:
        errmsg = f"provider_uuid: {cloud_provider_uuid} does not exist."
        return Response({"Error": errmsg}, status=status.HTTP_400_BAD_REQUEST)

    if provider.type not in Provider.OPENSHIFT_ON_CLOUD_PROVIDER_LIST:
        errmsg = f"You must provide a cloud provider UUID from {Provider.OPENSHIFT_ON_CLOUD_PROVIDER_LIST}."
        return Response({"Error": errmsg}, status=status.HTTP_400_BAD_REQUEST)

    dh = DateHelper()
    if provider.type in [Provider.PROVIDER_GCP, Provider.PROVIDER_GCP_LOCAL]:
        invoice_month = dh.invoice_month_from_bill_date(start_date)
        months = get_months_in_date_range(start=start_date, end=end_date, invoice_month=invoice_month)
    else:
        months = get_months_in_date_range(start=start_date, end=end_date)

    bill_dates = [month[0].replace(day=1) for month in months]

    for bill_date in bill_dates:
        tracing_id = str(uuid4())
        params = {
            "schema_name": schema_name,
            "provider_uuid": cloud_provider_uuid,
            "bill_date": bill_date,
            "tracing_id": tracing_id,
        }
        if provider.type in (Provider.PROVIDER_GCP, Provider.PROVIDER_GCP_LOCAL):
            bill_end = dh.month_end(bill_date).date()
            bill_start = dh.month_start(bill_date).date()
            start = ciso8601.parse_datetime(start_date).date()
            end = ciso8601.parse_datetime(end_date).date() if end_date else bill_end
            params["start_date"] = max(start, bill_start)
            params["end_date"] = min(bill_end, end)
            LOG.info("Triggering process_daily_openshift_on_cloud task with params:")
            LOG.info(params)
            LOG.info("on queue: %s", queue_name)
            async_result = process_daily_openshift_on_cloud_task.s(**params).apply_async(queue=queue_name)
        else:
            LOG.info("Triggering process_openshift_on_cloud task with params:")
            LOG.info(params)
            LOG.info("on queue: %s", queue_name)
            async_result = process_openshift_on_cloud_task.s(**params).apply_async(queue=queue_name)
        async_results.append({str(bill_date): str(async_result)})
    return Response({REPORT_DATA_KEY: async_results})
