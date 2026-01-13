#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View for Application Types (CMMO compatibility)."""
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView


# Cost Management is the only supported application type
APPLICATION_TYPES = [{"id": "0", "name": "/insights/platform/cost-management"}]


class ApplicationTypesView(APIView):
    """Application Types View for CMMO compatibility."""

    permission_classes = (AllowAny,)

    def get(self, request):
        """List application types with optional filter[name] support."""
        app_types = APPLICATION_TYPES.copy()

        # Support filter[name] query parameter
        filter_name = request.query_params.get("filter[name]")
        if filter_name:
            app_types = [at for at in app_types if at["name"] == filter_name]

        return Response({"meta": {"count": len(app_types)}, "data": app_types})
