#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View for running_celery_tasks endpoint."""
import datetime
import logging

import ciso8601
import pytz
from django.views.decorators.cache import never_cache
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.decorators import permission_classes
from rest_framework.decorators import renderer_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.settings import api_settings

from api.utils import DateHelper
from hcs.tasks import collect_hcs_report_data
from hcs.tasks import HCS_QUEUE

# flake8: noqa

LOG = logging.getLogger(__name__)


@never_cache
@api_view(http_method_names=["GET"])
@permission_classes((AllowAny,))
@renderer_classes(tuple(api_settings.DEFAULT_RENDERER_CLASSES))
def hcs_report_data(request):
    params = request.query_params
    start_date = params.get("start_date")
    end_date = params.get("end_date")

    if start_date is None:
        errmsg = "start_date is a required parameter."
        return Response({"Error": errmsg}, status=status.HTTP_400_BAD_REQUEST)

    try:
        start_date = ciso8601.parse_datetime(start_date).replace(tzinfo=pytz.UTC)
        end_date = ciso8601.parse_datetime(end_date).replace(tzinfo=pytz.UTC) if end_date else DateHelper().today
    except ValueError as err:
        LOG.info(f"Invalid date format: {err}")
        return Response({"Error": f"Invalid date format: {err}"}, status=status.HTTP_400_BAD_REQUEST)

    months = DateHelper().list_month_tuples(start_date, end_date)
    num_months = len(months)
    first_month = months[0]
    months[0] = (start_date, first_month[1])
    last_month = months[num_months - 1]
    months[num_months - 1] = (last_month[0], end_date)

    # need to format all the date times into strings with the format "%Y-%m-%d" for the celery task
    for i, month in enumerate(months):
        start, end = month
        start_date = start.date().strftime("%Y-%m-%d")
        end_date = end.date().strftime("%Y-%m-%d")
        months[i] = (start_date, end_date)

    LOG.info("Calling collect_hcs_report_data async task.")
    async_result = collect_hcs_report_data.s(start_date, end_date).apply_async(queue=HCS_QUEUE)

    return Response({"Report Data Task ID": str(async_result)})
