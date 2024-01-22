#
# Copyright 2022 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View for report_data endpoint."""
# flake8: noqa
import logging
from collections import defaultdict
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

from api.common import log_json
from api.provider.models import Provider
from api.utils import DateHelper
from masu.processor import is_customer_large
from masu.processor.tasks import cleanup_aws_bills as cleanup_aws_bills_task
from masu.processor.tasks import PRIORITY_QUEUE
from masu.processor.tasks import PRIORITY_QUEUE_XL
from masu.processor.tasks import QUEUE_LIST


LOG = logging.getLogger(__name__)
REPORT_DATA_KEY = "cleanup_aws_bills Task IDs"


@never_cache
@api_view(http_method_names=["GET"])
@permission_classes((AllowAny,))
@renderer_classes(tuple(api_settings.DEFAULT_RENDERER_CLASSES))
def aws_bill_cleanup(request):
    params = request.query_params
    schema_name = params.get("schema")
    bill_date = params.get("bill_date")
    fallback_queue = PRIORITY_QUEUE
    if is_customer_large(schema_name):
        fallback_queue = PRIORITY_QUEUE_XL
    queue_name = params.get("queue") or fallback_queue

    if queue_name not in QUEUE_LIST:
        errmsg = f"'queue' must be one of {QUEUE_LIST}."
        return Response({"Error": errmsg}, status=status.HTTP_400_BAD_REQUEST)
    if bill_date is None:
        errmsg = "bill_date is a required parameter."
        return Response({"Error": errmsg}, status=status.HTTP_400_BAD_REQUEST)

    if schema_name:
        providers = Provider.objects.filter(customer__schema_name=schema_name).filter(
            type__in=[Provider.PROVIDER_AWS, Provider.PROVIDER_AWS_LOCAL]
        )
    else:
        providers = Provider.objects.filter(type__in=[Provider.PROVIDER_AWS, Provider.PROVIDER_AWS_LOCAL])
    tracing_id = str(uuid4())
    schema_dict = defaultdict(list)
    LOG.info(log_json(tracing_id, msg="kicking off bill cleanup tasks per provider", provider_count=len(providers)))
    for provider in providers:
        schema = provider.customer.schema_name
        provider_uuid = provider.uuid
        async_result = cleanup_aws_bills_task.s(schema, provider_uuid, bill_date, tracing_id).apply_async(
            queue=queue_name
        )
        schema_dict[schema].append({"provider_uuid": str(provider_uuid), "task_id": str(async_result)})
    return Response({"bill_date": str(bill_date), REPORT_DATA_KEY: schema_dict})
