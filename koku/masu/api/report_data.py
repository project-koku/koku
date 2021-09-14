#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View for report_data endpoint."""
# flake8: noqa
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
from masu.database.provider_db_accessor import ProviderDBAccessor
from masu.processor.tasks import PRIORITY_QUEUE
from masu.processor.tasks import QUEUE_LIST
from masu.processor.tasks import remove_expired_data
from masu.processor.tasks import update_all_summary_tables
from masu.processor.tasks import update_summary_tables

LOG = logging.getLogger(__name__)
REPORT_DATA_KEY = "Report Data Task IDs"


@never_cache
@api_view(http_method_names=["GET", "DELETE"])
@permission_classes((AllowAny,))
@renderer_classes(tuple(api_settings.DEFAULT_RENDERER_CLASSES))
def report_data(request):
    """Update report summary tables in the database."""
    if request.method == "GET":
        async_results = []
        params = request.query_params
        async_result = None
        all_providers = False
        provider_uuid = params.get("provider_uuid")
        provider_type = params.get("provider_type")
        schema_name = params.get("schema")
        start_date = params.get("start_date")
        end_date = params.get("end_date")
        queue_name = params.get("queue") or PRIORITY_QUEUE
        if provider_uuid is None and provider_type is None:
            errmsg = "provider_uuid or provider_type must be supplied as a parameter."
            return Response({"Error": errmsg}, status=status.HTTP_400_BAD_REQUEST)
        if queue_name not in QUEUE_LIST:
            errmsg = f"'queue' must be one of {QUEUE_LIST}."
            return Response({"Error": errmsg}, status=status.HTTP_400_BAD_REQUEST)

        if provider_uuid == "*":
            all_providers = True
        elif provider_uuid:
            with ProviderDBAccessor(provider_uuid) as provider_accessor:
                provider = provider_accessor.get_type()
        else:
            provider = provider_type

        if start_date is None:
            errmsg = "start_date is a required parameter."
            return Response({"Error": errmsg}, status=status.HTTP_400_BAD_REQUEST)

        start_date = ciso8601.parse_datetime(start_date).replace(tzinfo=pytz.UTC)
        end_date = ciso8601.parse_datetime(end_date).replace(tzinfo=pytz.UTC) if end_date else DateHelper().today
        months = DateHelper().list_month_tuples(start_date, end_date)
        num_months = len(months)
        first_month = months[0]
        months[0] = (start_date, first_month[1])

        last_month = months[num_months - 1]
        months[num_months - 1] = (last_month[0], end_date)

        # need to format all the datetimes into strings with the format "%Y-%m-%d" for the celery task
        for i, month in enumerate(months):
            start, end = month
            start_date = start.date().strftime("%Y-%m-%d")
            end_date = end.date().strftime("%Y-%m-%d")
            months[i] = (start_date, end_date)

        if not all_providers:
            if schema_name is None:
                errmsg = "schema is a required parameter."
                return Response({"Error": errmsg}, status=status.HTTP_400_BAD_REQUEST)

            if provider is None:
                errmsg = "Unable to determine provider type."
                return Response({"Error": errmsg}, status=status.HTTP_400_BAD_REQUEST)

            if provider_type and provider_type != provider:
                errmsg = "provider_uuid and provider_type have mismatched provider types."
                return Response({"Error": errmsg}, status=status.HTTP_400_BAD_REQUEST)

            for month in months:
                async_result = update_summary_tables.s(
                    schema_name, provider, provider_uuid, month[0], month[1], queue_name=queue_name
                ).apply_async(queue=queue_name or PRIORITY_QUEUE)
                async_results.append({str(month): str(async_result)})
        else:
            for month in months:
                async_result = update_all_summary_tables.delay(month[0], month[1])
                async_results.append({str(month): str(async_result)})
        return Response({REPORT_DATA_KEY: async_results})

    if request.method == "DELETE":
        params = request.query_params

        schema_name = params.get("schema")
        provider = params.get("provider")
        provider_uuid = params.get("provider_uuid")
        simulate = params.get("simulate")

        if schema_name is None:
            errmsg = "schema is a required parameter."
            return Response({"Error": errmsg}, status=status.HTTP_400_BAD_REQUEST)

        if provider is None:
            errmsg = "provider is a required parameter."
            return Response({"Error": errmsg}, status=status.HTTP_400_BAD_REQUEST)

        if provider_uuid is None:
            errmsg = "provider_uuid is a required parameter."
            return Response({"Error": errmsg}, status=status.HTTP_400_BAD_REQUEST)

        if simulate is not None and simulate.lower() not in ("true", "false"):
            errmsg = "simulate must be a boolean."
            return Response({"Error": errmsg}, status=status.HTTP_400_BAD_REQUEST)

        if simulate is not None and simulate.lower() == "true":
            simulate = True
        else:
            simulate = False

        LOG.info("Calling remove_expired_data async task.")

        async_result = remove_expired_data.delay(schema_name, provider, simulate, provider_uuid)

        return Response({"Report Data Task ID": str(async_result)})
