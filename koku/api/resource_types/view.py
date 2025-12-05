#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View for Resource Types."""
from django.conf import settings
from django.utils.decorators import method_decorator
from django.views.decorators.vary import vary_on_headers
from django_tenants.utils import tenant_context
from rest_framework import filters
from rest_framework import generics
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from api.common import CACHE_RH_IDENTITY_HEADER
from api.common.pagination import ResourceTypePaginator
from api.common.pagination import ResourceTypeViewPaginator
from api.common.permissions.openshift_access import OpenShiftAccessPermission
from api.common.permissions.openshift_access import OpenShiftProjectPermission
from api.query_params import get_tenant
from api.resource_types.serializers import ResourceTypeSerializer
from cost_models.models import CostModel
from reporting.provider.aws.models import AWSCostSummaryByAccountP
from reporting.provider.aws.models import AWSOrganizationalUnit
from reporting.provider.azure.models import AzureCostSummaryByAccountP
from reporting.provider.gcp.models import GCPCostSummaryByAccountP
from reporting.provider.gcp.models import GCPCostSummaryByProjectP
from reporting.provider.ocp.models import OCPCostSummaryByNodeP
from reporting.provider.ocp.models import OCPCostSummaryByProjectP
from reporting.provider.ocp.models import OCPCostSummaryP


class ResourceTypeView(APIView):
    """API GET view for resource-types API."""

    permission_classes = [AllowAny]

    @method_decorator(vary_on_headers(CACHE_RH_IDENTITY_HEADER))
    def get(self, request, **kwargs):

        tenant = get_tenant(request.user)
        with tenant_context(tenant):

            aws_account_count = AWSCostSummaryByAccountP.objects.values("usage_account_id").distinct().count()
            gcp_account_count = GCPCostSummaryByAccountP.objects.values("account_id").distinct().count()
            gcp_project_count = GCPCostSummaryByProjectP.objects.values("project_id").distinct().count()
            aws_org_unit_count = (
                AWSOrganizationalUnit.objects.filter(deleted_timestamp__isnull=True)
                .values("org_unit_id")
                .distinct()
                .count()
            )

            azure_sub_guid_count = AzureCostSummaryByAccountP.objects.values("subscription_guid").distinct().count()
            ocp_cluster_count = OCPCostSummaryP.objects.values("cluster_id").distinct().count()
            ocp_node_count = OCPCostSummaryByNodeP.objects.values("node").distinct().count()
            ocp_project_count = OCPCostSummaryByProjectP.objects.values("namespace").distinct().count()

            cost_model_count = CostModel.objects.count()

            aws_account_dict = {
                "value": "aws.account",
                "path": "/api/cost-management/v1/resource-types/aws-accounts/",
                "count": aws_account_count,
            }
            aws_org_unit_dict = {
                "value": "aws.organizational_unit",
                "path": "/api/cost-management/v1/resource-types/aws-organizational-units/",
                "count": aws_org_unit_count,
            }
            azure_sub_guid_dict = {
                "value": "azure.subscription_guid",
                "path": "/api/cost-management/v1/resource-types/azure-subscription-guids/",
                "count": azure_sub_guid_count,
            }
            ocp_cluster_dict = {
                "value": "openshift.cluster",
                "path": "/api/cost-management/v1/resource-types/openshift-clusters/",
                "count": ocp_cluster_count,
            }
            ocp_node_dict = {
                "value": "openshift.node",
                "path": "/api/cost-management/v1/resource-types/openshift-nodes/",
                "count": ocp_node_count,
            }
            ocp_project_dict = {
                "value": "openshift.project",
                "path": "/api/cost-management/v1/resource-types/openshift-projects/",
                "count": ocp_project_count,
            }
            gcp_account_dict = {
                "value": "gcp.account",
                "path": "/api/cost-management/v1/resource-types/gcp-accounts/",
                "count": gcp_account_count,
            }
            gcp_project_dict = {
                "value": "gcp.project",
                "path": "/api/cost-management/v1/resource-types/gcp-projects/",
                "count": gcp_project_count,
            }
            cost_model_dict = {
                "value": "cost_model",
                "path": "/api/cost-management/v1/resource-types/cost-models/",
                "count": cost_model_count,
            }
            settings_dict = {
                "value": "settings",
                "count": 1,
            }
            data = [
                aws_account_dict,
                aws_org_unit_dict,
                azure_sub_guid_dict,
                ocp_cluster_dict,
                ocp_node_dict,
                ocp_project_dict,
                gcp_account_dict,
                gcp_project_dict,
                cost_model_dict,
                settings_dict,
            ]
            paginator = ResourceTypePaginator(data, request)

            return paginator.get_paginated_response(data)


class ResourceTypesGenericListView(generics.ListAPIView):
    """API generic list view for resource types."""

    ordering = ["value"]
    search_fields = ["value"]
    supported_query_params = ["search", "limit"]
    serializer_class = ResourceTypeSerializer
    pagination_class = ResourceTypeViewPaginator
    filter_backends = [filters.OrderingFilter, filters.SearchFilter]

    def has_admin_access(self, request):
        """Check if the user has admin access."""
        return settings.ENHANCED_ORG_ADMIN and request.user.admin

    def filter_by_access(self, subset_map, request, queryset):
        """
        Filter the queryset by the user's access rights.
        subset_map: A dictionary mapping the access key to the model field.
                    Example: {"openshift.project": "namespace__in"}
        """
        if request.user.access:
            for access_key, model_field in subset_map.items():
                access_list = request.user.access.get(access_key, {}).get("read", [])
                if access_list and access_list[0] != "*":
                    queryset = queryset.filter(**{model_field: access_list})
        return queryset


class OCPGpuResourceTypesView(ResourceTypesGenericListView):
    """API GET list view for Openshift GPU resource types."""

    access_map = {
        "openshift.cluster": "cluster_id__in",
        "openshift.project": "namespace__in",
    }
    query_filter_keys = ["cluster_id", "cluster_alias", "namespace", "node"]
    permission_classes = [OpenShiftProjectPermission | OpenShiftAccessPermission]

    @method_decorator(vary_on_headers(CACHE_RH_IDENTITY_HEADER))
    def list(self, request):
        # Reads the users values for Openshift GPU vendors, displays values related to the users access
        print(self.query_filter_keys)
        self.supported_query_params.extend(self.query_filter_keys)
        query_filter_map = {}
        error_message = {}

        # check for only supported query_params
        if self.request.query_params:
            for key in self.request.query_params:
                if key not in self.supported_query_params:
                    error_message[key] = [{"Unsupported parameter"}]
                    return Response(error_message, status=status.HTTP_400_BAD_REQUEST)
                if key in self.query_filter_keys:
                    query_filter_map[f"{key}__icontains"] = self.request.query_params.get(key)

        queryset = self.queryset.filter(**query_filter_map)

        if not self.has_admin_access(request):
            queryset = self.filter_by_access(self.access_map, request, queryset)

        self.queryset = queryset
        return super().list(request)
