#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View for Source Types (CMMO compatibility)."""
from django.conf import settings
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from masu.processor import is_events_source_enabled
from sources.api.source_type_mapping import CMMO_ID_TO_SOURCE_NAME

# On-prem Cost Management supports OpenShift sources by default, plus Events when enabled.
ONPREM_SOURCE_TYPE_IDS = frozenset({"1"})
ONPREM_EVENTS_SOURCE_TYPE_ID = "5"


class SourceTypesView(APIView):
    """Source Types View for CMMO compatibility."""

    permission_classes = (AllowAny,)

    def get(self, request):
        """List source types with optional filter[name] support."""
        # Build source types list from mapping
        source_types = [{"id": id, "name": name} for id, name in CMMO_ID_TO_SOURCE_NAME.items()]
        if settings.ONPREM:
            allowed_ids = set(ONPREM_SOURCE_TYPE_IDS)
            if is_events_source_enabled():
                allowed_ids.add(ONPREM_EVENTS_SOURCE_TYPE_ID)
            source_types = [st for st in source_types if st["id"] in allowed_ids]

        # Support filter[name] query parameter
        filter_name = request.query_params.get("filter[name]")
        if filter_name:
            source_types = [st for st in source_types if st["name"] == filter_name]

        response = Response({"meta": {"count": len(source_types)}, "data": source_types})
        return response
