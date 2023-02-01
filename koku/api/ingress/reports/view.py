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

from api.ingress.reports.serializers import IngressReportsSerializer
from reporting.ingress.models import IngressReports

LOG = logging.getLogger(__name__)


class IngressReportsDetailView(APIView):
    """
    View to fetch report details for specific source
    """

    permission_classes = [AllowAny]

    def get_object(self, source):
        """
        Helper method to get reports with given source
        """
        try:
            return IngressReports.objects.filter(source=source)
        except IngressReports.DoesNotExist:
            return None

    def get(self, request, *args, **kwargs):
        """
        Return reports for source.
        """
        source = kwargs["source"]
        try:
            UUID(source)
        except ValueError:
            return Response({"Error": "Invalid source uuid."}, status=status.HTTP_400_BAD_REQUEST)
        report_instance = self.get_object(source)
        if not report_instance:
            return Response({"Error": "Provider uuid not found."}, status=status.HTTP_400_BAD_REQUEST)

        serializer = IngressReportsSerializer(report_instance, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class IngressReportsView(APIView):
    """
    View to interact with settings for a customer.
    """

    permission_classes = [AllowAny]

    def get(self, request, *args, **kwargs):
        """
        Return list of sources.
        """
        reports = IngressReports.objects.filter()
        serializer = IngressReportsSerializer(reports, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        """Handle posted reports."""
        data = {
            "source": request.data.get("source"),
            "reports_list": request.data.get("reports_list"),
        }
        serializer = IngressReportsSerializer(data=data)
        if serializer.is_valid(raise_exception=True):
            serializer.save()
            data["ingress_report_uuid"] = serializer.data.get("uuid")
            IngressReports.ingest(data)
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
