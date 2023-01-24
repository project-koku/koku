#
# Copyright 2023 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View for Minimal report posting."""
import logging
from uuid import UUID

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from api.common.permissions.minimal_report_access import MinimalReportAccessPermission
from api.ingress.minimal_report.serializers import MinimalReportSerializer
from reporting.minimal_report.models import MinimalReport

LOG = logging.getLogger(__name__)


class MinimalReportDetailView(APIView):
    """
    View to fetch Minimal report details for specific source
    """

    permission_classes = [MinimalReportAccessPermission]

    def get_object(self, source):
        """
        Helper method to get reports with given source
        """
        try:
            return MinimalReport.objects.filter(source=source)
        except MinimalReport.DoesNotExist:
            return None

    def get(self, request, source, *args, **kwargs):
        """
        Return Minimal reports for source.
        """
        try:
            UUID(source)
        except ValueError:
            return Response({"Error": "Invalid source uuid."}, status=status.HTTP_400_BAD_REQUEST)
        minimalreport_instance = self.get_object(source)
        if not minimalreport_instance:
            return Response({"Error": "Provider uuid not found."}, status=status.HTTP_400_BAD_REQUEST)

        serializer = MinimalReportSerializer(minimalreport_instance, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class MinimalReportView(APIView):
    """
    View to interact with settings for a customer.
    """

    permission_classes = [MinimalReportAccessPermission]

    def get(self, request, *args, **kwargs):
        """
        Return list of Minimal sources.
        """
        minimal_reports = MinimalReport.objects.filter()
        serializer = MinimalReportSerializer(minimal_reports, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        """Handle posted Minimal reports."""
        data = {
            "source": request.data.get("source"),
            "reports_list": request.data.get("reports_list"),
        }
        serializer = MinimalReportSerializer(data=data)
        if serializer.is_valid():
            serializer.save()
            MinimalReport.ingest(data)
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
