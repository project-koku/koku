#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View for Applications (CMMO compatibility)."""
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from api.provider.models import Sources


class ApplicationsView(APIView):
    """Applications View for CMMO compatibility.

    Applications represent the association between a source and an application type.
    Since Cost Management is the only supported application (application_type_id=0),
    this is handled entirely in the API layer without database storage.
    """

    permission_classes = (AllowAny,)

    def get(self, request):
        """List applications with optional filter[source_id] and filter[application_type_id] support."""
        org_id = request.user.customer.org_id
        queryset = Sources.objects.filter(org_id=org_id)

        # Support filter[source_id] query parameter
        filter_source_id = request.query_params.get("filter[source_id]")
        if filter_source_id:
            queryset = queryset.filter(source_id=filter_source_id)

        # Support filter[application_type_id] - only "0" is valid
        filter_app_type_id = request.query_params.get("filter[application_type_id]")
        if filter_app_type_id and filter_app_type_id != "0":
            # No sources match non-zero application_type_id
            return Response({"meta": {"count": 0}, "data": []})

        # Build applications list from sources
        applications = [
            {
                "id": str(source.source_id),
                "source_id": str(source.source_id),
                "application_type_id": "0",
            }
            for source in queryset
        ]

        response = Response({"meta": {"count": len(applications)}, "data": applications})
        return response

    def post(self, request):
        """Create an application association.

        Since application_type_id is always 0, this just validates input and returns success.
        """
        source_id = request.data.get("source_id")
        application_type_id = request.data.get("application_type_id")

        if not source_id:
            return Response(
                {"error": "source_id is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if application_type_id and application_type_id != "0":
            return Response(
                {"error": "Only application_type_id '0' (cost-management) is supported"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Verify source exists
        org_id = request.user.customer.org_id
        try:
            source = Sources.objects.get(org_id=org_id, source_id=source_id)
        except Sources.DoesNotExist:
            return Response(
                {"error": f"Source {source_id} not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Return success - no database storage needed
        response = Response(
            {
                "id": str(source.source_id),
                "source_id": str(source.source_id),
                "application_type_id": "0",
            },
            status=status.HTTP_201_CREATED,
        )
        return response
