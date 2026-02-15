#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View for Source Types (CMMO compatibility)."""
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from sources.api.source_type_mapping import CMMO_ID_TO_SOURCE_NAME


class SourceTypesView(APIView):
    """Source Types View for CMMO compatibility."""

    permission_classes = (AllowAny,)

    def get(self, request):
        """List source types with optional filter[name] support."""
        # Build source types list from mapping
        source_types = [{"id": id, "name": name} for id, name in CMMO_ID_TO_SOURCE_NAME.items()]

        # Support filter[name] query parameter
        filter_name = request.query_params.get("filter[name]")
        if filter_name:
            source_types = [st for st in source_types if st["name"] == filter_name]

        response = Response({"meta": {"count": len(source_types)}, "data": source_types})
        return response
