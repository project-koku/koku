#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View for update_cost_model_costs endpoint."""
import logging

from celery import chain
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
from masu.processor.tasks import PRIORITY_QUEUE
from masu.processor.tasks import QUEUE_LIST
from masu.processor.tasks import refresh_materialized_views
from masu.processor.tasks import update_cost_model_costs as cost_task

LOG = logging.getLogger(__name__)


@never_cache
@api_view(http_method_names=["GET", "DELETE"])
@permission_classes((AllowAny,))
@renderer_classes(tuple(api_settings.DEFAULT_RENDERER_CLASSES))
def update_cost_model_costs(request):
    """Update report summary tables in the database."""
    params = request.query_params

    provider_uuid = params.get("provider_uuid")
    schema_name = params.get("schema")
    default_start_date = DateHelper().this_month_start.strftime("%Y-%m-%d")
    default_end_date = DateHelper().today.strftime("%Y-%m-%d")
    start_date = params.get("start_date", default=default_start_date)
    end_date = params.get("end_date", default=default_end_date)
    queue_name = params.get("queue") or PRIORITY_QUEUE

    if provider_uuid is None or schema_name is None:
        errmsg = "provider_uuid and schema_name are required parameters."
        return Response({"Error": errmsg}, status=status.HTTP_400_BAD_REQUEST)
    if queue_name not in QUEUE_LIST:
        errmsg = f"'queue' must be one of {QUEUE_LIST}."
        return Response({"Error": errmsg}, status=status.HTTP_400_BAD_REQUEST)

    try:
        provider = Provider.objects.get(uuid=provider_uuid)
    except Provider.DoesNotExist:
        return Response({"Error": "Provider does not exist."}, status=status.HTTP_400_BAD_REQUEST)

    LOG.info("Calling update_cost_model_costs async task.")
    async_result = chain(
        cost_task.s(schema_name, provider_uuid, start_date, end_date, queue_name=queue_name).set(queue=queue_name),
        refresh_materialized_views.si(
            schema_name, provider.type, provider_uuid=provider_uuid, queue_name=queue_name
        ).set(queue=queue_name),
    ).apply_async()

    return Response({"Update Cost Model Cost Task ID": str(async_result)})
