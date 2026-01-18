#
# Copyright 2023 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View for report posting."""
from uuid import UUID

from django.db.models import Q
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from api.common.pagination import ListPaginator
from api.ingress.reports.serializers import IngressReportsSerializer
from api.provider.models import Sources
from reporting.ingress.models import IngressReports


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
            return Response({"Error": "Source not found."}, status=status.HTTP_404_NOT_FOUND)

        # scope to schema_name to prevent cross-tenant data exposure
        report_instance = IngressReports.objects.filter(source=source, schema_name=request.user.customer.schema_name)
        if not report_instance:
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
        reports = IngressReports.objects.filter(schema_name=request.user.customer.schema_name)
        serializer = IngressReportsSerializer(reports, many=True)
        paginator = ListPaginator(serializer.data, request)
        return paginator.get_paginated_response(serializer.data)

    def post(self, request):
        """Handle posted reports."""

        if not getattr(request.user, "customer", None):
            return Response({"Error": "Unauthorized."}, status=status.HTTP_401_UNAUTHORIZED)

        source_ref = request.data.get("source")
        source_lookup = Q(source_id=source_ref) if str(source_ref).isdigit() else Q(koku_uuid=source_ref)

        tenant_filter = Q()
        account_id = request.user.customer.account_id
        org_id = request.user.customer.org_id
        if account_id:
            tenant_filter |= Q(account_id=account_id)
        if org_id:
            tenant_filter |= Q(org_id=org_id)

        source = Sources.objects.filter(source_lookup & tenant_filter).first()
        if not source:
            return Response({"Error": "Source not found."}, status=status.HTTP_404_NOT_FOUND)

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
            return paginator.get_paginated_response(data)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
