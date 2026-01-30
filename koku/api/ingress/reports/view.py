#
# Copyright 2023 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View for report posting."""
import logging
from uuid import UUID

from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from api.common import log_json
from api.common.pagination import ListPaginator
from api.common.permissions.ingress_access import IngressAccessPermission
from api.ingress.reports.serializers import IngressReportsSerializer
from api.provider.models import Sources
from masu.processor import is_ingress_rbac_grace_period_enabled
from reporting.ingress.models import IngressReports

LOG = logging.getLogger(__name__)


def has_customer_object(request):
    return getattr(request.user, "customer", None)


class IngressReportsDetailView(APIView):
    """
    View to fetch report details for specific source
    """

    permission_classes = [AllowAny]

    def get(self, request, *args, **kwargs):
        """
        Return reports for source.
        """
        if not has_customer_object(request):
            LOG.warning("Unauthorized ingress report read. User has no customer attribute.")
            return Response({"Error": "Invalid request."}, status=status.HTTP_400_BAD_REQUEST)

        source = kwargs["source"]
        try:
            UUID(source)
        except ValueError:
            LOG.warning(log_json(msg="Invalid source UUID in ingress report detail view.", source=source))
            return Response({"Error": "Invalid request."}, status=status.HTTP_400_BAD_REQUEST)

        # scope to schema_name to prevent cross-tenant data exposure
        schema_name = request.user.customer.schema_name
        context = {"schema": schema_name, "source": source}

        report_instance = IngressReports.objects.filter(source=source, schema_name=request.user.customer)
        first_report = report_instance.first()
        if not first_report:
            LOG.warning(log_json(msg="Source not found in ingress report detail view.", **context))
            return Response({"Error": "Source not found."}, status=status.HTTP_404_NOT_FOUND)

        if is_ingress_rbac_grace_period_enabled(schema_name) or IngressAccessPermission.has_access(
            request, first_report.source.type
        ):
            serializer = IngressReportsSerializer(report_instance, many=True)
            paginator = ListPaginator(serializer.data, request)
            return paginator.get_paginated_response(serializer.data)

        LOG.warning(log_json(msg="unauthorized ingress report read access.", **context))
        return Response({"Error": "Invalid request."}, status=status.HTTP_400_BAD_REQUEST)


class IngressReportsView(APIView):
    """
    View to interact with settings for a customer.
    """

    permission_classes = [AllowAny]

    def get(self, request, *args, **kwargs):
        """
        Return list of sources.
        """

        if not has_customer_object(request):
            LOG.warning("Unauthorized ingress report read. User has no customer attribute.")
            return Response({"Error": "Invalid request."}, status=status.HTTP_400_BAD_REQUEST)

        schema_name = request.user.customer.schema_name
        if is_ingress_rbac_grace_period_enabled(schema_name) or IngressAccessPermission.has_any_read_access(request):
            reports = IngressReports.objects.filter(schema_name=schema_name)
            serializer = IngressReportsSerializer(reports, many=True)
            paginator = ListPaginator(serializer.data, request)
            return paginator.get_paginated_response(serializer.data)

        LOG.warning(log_json(msg="Unauthorized ingress report read access.", schema=schema_name))
        return Response({"Error": "Invalid request."}, status=status.HTTP_400_BAD_REQUEST)

    def post(self, request):
        """Handle posted reports."""

        if not has_customer_object(request):
            LOG.warning("Unauthorized ingress report post. User has no customer attribute.")
            return Response({"Error": "Invalid request."}, status=status.HTTP_400_BAD_REQUEST)

        source_ref = request.data.get("source")
        schema_name = request.user.customer.schema_name
        context = {"schema": schema_name, "source": source_ref}
        if not source_ref:
            LOG.info(log_json(msg="Ingress report post failed. Missing source reference.", **context))
            return Response({"Error": "Invalid request."}, status=status.HTTP_400_BAD_REQUEST)

        lookup = {"source_id": source_ref} if str(source_ref).isdigit() else {"koku_uuid": source_ref}
        source = Sources.objects.filter(org_id=request.user.customer.org_id, **lookup).first()

        if not source:
            LOG.info(log_json(msg="Ingress report post failed. Source not found.", **context))
            return Response({"Error": "Invalid request."}, status=status.HTTP_400_BAD_REQUEST)

        if is_ingress_rbac_grace_period_enabled(schema_name) or IngressAccessPermission.has_access(
            request, source.source_type, write=True
        ):
            data = {
                "source": source.koku_uuid,
                "source_id": source.source_id,
                "reports_list": request.data.get("reports_list"),
                "bill_year": request.data.get("bill_year"),
                "bill_month": request.data.get("bill_month"),
                "schema_name": schema_name,
            }
            serializer = IngressReportsSerializer(data=data)
            serializer.is_valid(raise_exception=True)
            serializer.save()
            data["ingress_report_uuid"] = serializer.data.get("uuid")
            data["status"] = serializer.data.get("status")
            IngressReports.ingest(data)
            paginator = ListPaginator(data, request)
            LOG.info(
                log_json(
                    msg="Ingress report validated and ingestion triggered.",
                    ingress_report_uuid=data["ingress_report_uuid"],
                    bill_period=f"{data['bill_year']}-{data['bill_month']}",
                    **context,
                )
            )
            return paginator.get_paginated_response(data)

        LOG.warning(log_json(msg="Unauthorized ingress report post access.", **context))
        return Response({"Error": "Invalid request."}, status=status.HTTP_400_BAD_REQUEST)
