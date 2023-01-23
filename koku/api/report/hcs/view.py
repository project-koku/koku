#
# Copyright 2023 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View for HCS report posting."""
# from api.report.hcs.query_handler import HCSReportQueryHandler
import logging
from uuid import UUID

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from api.common.permissions.hcs_access import HCSAccessPermission
from api.report.hcs.serializers import HCSReportSerializer
from reporting.hcs.models import HCSReport

LOG = logging.getLogger(__name__)


class HCSDetailView(APIView):
    """
    View to fetch HCS report details for specific provider
    """

    permission_classes = [HCSAccessPermission]

    def get_object(self, provider):
        """
        Helper method to get reports with given provider
        """
        try:
            return HCSReport.objects.filter(provider=provider)
        except HCSReport.DoesNotExist:
            return None

    def get(self, request, provider, *args, **kwargs):
        """
        Return HCS reports for provider.
        """
        try:
            UUID(provider)
        except ValueError:
            return Response({"Error": "Invalid provider uuid."}, status=status.HTTP_400_BAD_REQUEST)
        hcsreport_instance = self.get_object(provider)
        if not hcsreport_instance:
            return Response({"Error": "Provider uuid not found."}, status=status.HTTP_400_BAD_REQUEST)

        serializer = HCSReportSerializer(hcsreport_instance, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class HCSView(APIView):
    """
    View to interact with settings for a customer.
    """

    permission_classes = [HCSAccessPermission]

    def get(self, request, *args, **kwargs):
        """
        Return list of HCS providers.
        """
        hcs_reports = HCSReport.objects.filter()
        serializer = HCSReportSerializer(hcs_reports, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        """Handle posted HCS reports."""
        data = {
            "provider": request.data.get("provider"),
            "reports_list": request.data.get("reports_list"),
        }
        serializer = HCSReportSerializer(data=data)
        if serializer.is_valid():
            serializer.save()
            HCSReport.ingest(data)
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
