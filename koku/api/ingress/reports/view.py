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


class IngressReportsDetailView(APIView):
    """
    View to fetch report details for specific source
    """

    permission_classes = [AllowAny]

    def get(self, request, *args, **kwargs):
        """
        Return reports for source.
        """
        source = kwargs["source"]
        try:
            UUID(source)
        except ValueError:
            LOG.warning(log_json(msg="invalid source UUID in ingress report detail view", source=source))
            return Response({"Error": "Source not found."}, status=status.HTTP_404_NOT_FOUND)

        # scope to schema_name to prevent cross-tenant data exposure
        schema_name = request.user.customer.schema_name
        report_instance = IngressReports.objects.filter(source=source, schema_name=schema_name)

        first_report = report_instance.first()
        if not first_report:
            LOG.warning(log_json(msg="source not found in ingress report detail view", source=source))
            return Response({"Error": "Source not found."}, status=status.HTTP_404_NOT_FOUND)

        if not IngressAccessPermission.has_access(request, first_report.source.type):
            LOG.warning(
                log_json(msg="rbac read access denied for ingress source", schema_name=schema_name, source=source)
            )
            return Response({"Error": "Source not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = IngressReportsSerializer(report_instance, many=True)
        paginator = ListPaginator(serializer.data, request)
        return paginator.get_paginated_response(serializer.data)


class IngressReportsView(APIView):
    """
    View to interact with settings for a customer.
    """

    permission_classes = [AllowAny]

    def get(self, request, *args, **kwargs):
        """
        Return list of sources.
        """
        if not IngressAccessPermission.has_any_read_access(request):
            LOG.warning(log_json(msg="ingress report read access denied", user=request.user.username))
            return Response({"Error": "Not authorized."}, status=status.HTTP_403_FORBIDDEN)

        reports = IngressReports.objects.filter(schema_name=request.user.customer.schema_name)
        serializer = IngressReportsSerializer(reports, many=True)
        paginator = ListPaginator(serializer.data, request)
        return paginator.get_paginated_response(serializer.data)

    def post(self, request):
        """Handle posted reports."""

        if not getattr(request.user, "customer", None):
            LOG.warning("unauthorized ingress report post: user has no customer attribute")
            return Response({"Error": "Unauthorized."}, status=status.HTTP_401_UNAUTHORIZED)

        org_id = request.user.customer.org_id
        source_ref = request.data.get("source")

        if not source_ref:
            LOG.info(
                log_json(msg="ingress report post missing source reference", source_ref=source_ref, org_id=org_id)
            )
            return Response({"Error": "Source not found."}, status=status.HTTP_404_NOT_FOUND)

        lookup = {"source_id": source_ref} if str(source_ref).isdigit() else {"koku_uuid": source_ref}
        source = Sources.objects.filter(org_id=org_id, **lookup).first()

        if not source:
            LOG.info(log_json(msg="ingress report post source not found", source_ref=source_ref, org_id=org_id))
            return Response({"Error": "Source not found."}, status=status.HTTP_404_NOT_FOUND)

        if not IngressAccessPermission.has_access(request, source.source_type, write=True):
            if not is_ingress_rbac_grace_period_enabled(org_id):
                LOG.warning(
                    log_json(
                        msg="access denied for ingress report posting",
                        source=source.koku_uuid,
                        org_id=org_id,
                    )
                )
                return Response({"Error": "Not authorized for source."}, status=status.HTTP_403_FORBIDDEN)

        data = {
            "source": source.koku_uuid,
            "source_id": source.source_id,
            "reports_list": request.data.get("reports_list"),
            "bill_year": request.data.get("bill_year"),
            "bill_month": request.data.get("bill_month"),
            "schema_name": request.user.customer.schema_name,
        }
        serializer = IngressReportsSerializer(data=data)
        if serializer.is_valid(raise_exception=True):
            serializer.save()
            data["ingress_report_uuid"] = serializer.data.get("uuid")
            data["status"] = serializer.data.get("status")
            IngressReports.ingest(data)
            paginator = ListPaginator(data, request)
            LOG.info(
                log_json(
                    msg="ingress report validated and ingestion triggered",
                    ingress_report_uuid=data["ingress_report_uuid"],
                    source=source.koku_uuid,
                    bill_period=f"{data['bill_year']}-{data['bill_month']}",
                )
            )
            return paginator.get_paginated_response(data)

        LOG.warning(
            log_json(msg="ingress report validation failed", source_ref=source_ref, org_id=org_id),
            exc_info=serializer.errors,
        )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
