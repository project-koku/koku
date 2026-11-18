#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View for GCP accounts."""
from django.db.models import F
from django.utils.decorators import method_decorator
from django.views.decorators.vary import vary_on_headers
from rest_framework import status
from rest_framework.response import Response

from api.common import CACHE_RH_IDENTITY_HEADER
from api.common.permissions.gcp_access import GcpAccessPermission
from api.common.permissions.gcp_access import GcpProjectPermission
from api.resource_types.view import ResourceTypesGenericListView
from reporting.provider.gcp.models import GCPTopology
from reporting.provider.gcp.openshift.models import OCPGCPCostSummaryByAccountP


class GCPAccountView(ResourceTypesGenericListView):
    """API GET list view for GCP accounts."""

    queryset = GCPTopology.objects.annotate(**{"value": F("account_id")}).values("value").distinct()
    permission_classes = [GcpAccessPermission | GcpProjectPermission]
    access_map = {
        "gcp.account": "account_id__in",
        "gcp.project": "project_id__in",
    }
    ocp_queryset = (
        OCPGCPCostSummaryByAccountP.objects.annotate(**{"value": F("account_id")}).values("value").distinct()
    )

    @method_decorator(vary_on_headers(CACHE_RH_IDENTITY_HEADER))
    def list(self, request):
        self.supported_query_params = self.supported_query_params + ["openshift"]
        error_message = {}
        for key in self.request.query_params:
            if key not in self.supported_query_params:
                error_message[key] = [{"Unsupported parameter"}]
                return Response(error_message, status=status.HTTP_400_BAD_REQUEST)

        if self.request.query_params.get("openshift") == "true":
            self.queryset = self.ocp_queryset

        if not self.has_admin_access(request):
            self.queryset = self.filter_by_access(self.access_map, request, self.queryset)

        return super().list(request)
