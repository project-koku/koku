#
# Copyright 2023 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View for ingress_data endpoint."""
# flake8: noqa
import logging

from django.views.decorators.cache import never_cache
from django_tenants.utils import schema_context
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.decorators import permission_classes
from rest_framework.decorators import renderer_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.settings import api_settings

from api.common.pagination import ListPaginator
from api.ingress.reports.serializers import IngressReportsSerializer
from masu.celery.tasks import check_report_updates_single_source
from masu.processor.tasks import GET_REPORT_FILES_QUEUE
from masu.processor.tasks import QUEUE_LIST
from reporting.ingress.models import IngressReports

LOG = logging.getLogger(__name__)
REPORT_DATA_KEY = "Ingress Report Download Task IDs"


@never_cache
@api_view(http_method_names=["GET"])
@permission_classes((AllowAny,))
@renderer_classes(tuple(api_settings.DEFAULT_RENDERER_CLASSES))
def ingress_reports(request):
    """Update report summary tables in the database."""
    if request.method == "GET":
        params = request.query_params
        async_result = None
        ingress_uuid = params.get("ingress_uuid")
        provider_uuid = params.get("provider_uuid")
        schema_name = params.get("schema_name")

        queue_name = params.get("queue") or GET_REPORT_FILES_QUEUE
        if schema_name is None:
            errmsg = "schema_name must be supplied as a parameter."
            return Response({"Error": errmsg}, status=status.HTTP_400_BAD_REQUEST)
        if queue_name not in QUEUE_LIST:
            errmsg = f"'queue' must be one of {QUEUE_LIST}."
            return Response({"Error": errmsg}, status=status.HTTP_400_BAD_REQUEST)

        if "download" in params.keys():
            if not ingress_uuid:
                errmsg = "ingress_uuid must be supplied as a parameter for downloads."
                return Response({"Error": errmsg}, status=status.HTTP_400_BAD_REQUEST)
            with schema_context(schema_name):
                ingress_report = IngressReports.objects.filter(uuid=ingress_uuid).first()
                async_result = check_report_updates_single_source.delay(
                    provider_uuid=ingress_report.source_id,
                    bill_date=f"{ingress_report.bill_year}{ingress_report.bill_month}",
                    ingress_reports=ingress_report.reports_list,
                    ingress_report_uuid=ingress_uuid,
                )
            return Response({"Ingress Reports Download Request Task ID": str(async_result)})

        else:
            with schema_context(schema_name):
                if not provider_uuid:
                    errmsg = "provider_uuid must be supplied as a parameter for fetching reports."
                    return Response({"Error": errmsg}, status=status.HTTP_400_BAD_REQUEST)
                ingress_reports = IngressReports.objects.filter(source_id=provider_uuid)
                serializer = IngressReportsSerializer(ingress_reports, many=True)
                paginator = ListPaginator(serializer.data, request)
                return paginator.get_paginated_response(serializer.data)
