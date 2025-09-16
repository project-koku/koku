#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View for Resource Types."""
from django.utils.decorators import method_decorator
from django.views.decorators.vary import vary_on_headers
from django_tenants.utils import tenant_context
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from api.common import CACHE_RH_IDENTITY_HEADER
from api.common.pagination import ResourceTypePaginator
from api.query_params import get_tenant
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
                "path": "/api/cost-management/v1/settings/",
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
