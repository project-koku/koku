#
# Copyright 2024 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View for Openshift virtual machines."""
from django.db.models import F
from django.utils.decorators import method_decorator
from django.views.decorators.vary import vary_on_headers
from rest_framework import status
from rest_framework.response import Response

from api.common import CACHE_RH_IDENTITY_HEADER
from api.common.permissions.openshift_access import OpenShiftAccessPermission
from api.common.permissions.openshift_access import OpenShiftProjectPermission
from api.resource_types.view import ResourceTypesGenericListView
from reporting.provider.ocp.models import OCPVirtualMachineSummaryP


class OCPVirtualMachinesView(ResourceTypesGenericListView):
    """API GET list view for Openshift virtual machines."""

    permission_classes = [OpenShiftProjectPermission | OpenShiftAccessPermission]
    access_map = {"openshift.cluster": "cluster_id__in", "openshift.project": "namespace__in"}
    query_filter_keys = ["cluster_id", "cluster_alias", "namespace", "node"]

    @method_decorator(vary_on_headers(CACHE_RH_IDENTITY_HEADER))
    def list(self, request):
        # Reads the users values for Openshift virtual machines, displays values related to the users access
        self.supported_query_params.extend(self.query_filter_keys)
        query_filter_map = {"vm_name__isnull": False}
        error_message = {}

        # check for only supported query_params
        if self.request.query_params:
            for key in self.request.query_params:
                if key not in self.supported_query_params:
                    error_message[key] = [{"Unsupported parameter"}]
                    return Response(error_message, status=status.HTTP_400_BAD_REQUEST)
                if key in self.query_filter_keys:
                    query_filter_map[f"{key}__icontains"] = self.request.query_params.get(key)

        queryset = (
            OCPVirtualMachineSummaryP.objects.annotate(value=F("vm_name"))
            .values("value")
            .distinct()
            .filter(**query_filter_map)
        )

        if not self.has_admin_access(request):
            queryset = self.filter_by_access(self.access_map, request, queryset)

        self.queryset = queryset
        return super().list(request)
