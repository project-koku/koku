#
# Copyright 2020 Red Hat, Inc.
#
# This program is free software: you can redistribute it and/or modify
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
"""View for organizations."""
from django.utils.decorators import method_decorator
from django.views.decorators.vary import vary_on_headers
from rest_framework.response import Response
from rest_framework.views import APIView
from tenant_schemas.utils import tenant_context

from api.common import CACHE_RH_IDENTITY_HEADER
from api.common.permissions.resource_type_access import ResourceTypeAccessPermission
from api.query_params import get_tenant
from cost_models.models import CostModel
from reporting.provider.aws.models import AWSCostSummaryByAccount
from reporting.provider.aws.models import AWSOrganizationalUnit
from reporting.provider.azure.models import AzureCostSummaryByAccount
from reporting.provider.ocp.models import OCPCostSummary
from reporting.provider.ocp.models import OCPCostSummaryByNode
from reporting.provider.ocp.models import OCPCostSummaryByProject


class ResourceTypeView(APIView):
    """API GET view for resource-types API."""

    permission_classes = [ResourceTypeAccessPermission]

    @method_decorator(vary_on_headers(CACHE_RH_IDENTITY_HEADER))
    def get(self, request, **kwargs):

        tenant = get_tenant(request.user)
        with tenant_context(tenant):

            aws_account_count = AWSCostSummaryByAccount.objects.values("usage_account_id").distinct().count()
            aws_org_unit_count = (
                AWSOrganizationalUnit.objects.filter(deleted_timestamp__isnull=True)
                .values("org_unit_id")
                .distinct()
                .count()
            )
            azure_sub_guid_count = AzureCostSummaryByAccount.objects.values("subscription_guid").distinct().count()
            ocp_cluster_count = OCPCostSummary.objects.values("cluster_id").distinct().count()
            ocp_node_count = OCPCostSummaryByNode.objects.values("node").distinct().count()
            ocp_project_count = OCPCostSummaryByProject.objects.values("namespace").distinct().count()
            cost_model_count = CostModel.objects.count()

            data = {
                "aws_account_count": aws_account_count,
                "aws_org_unit_count": aws_org_unit_count,
                "azure_sub_guid_count": azure_sub_guid_count,
                "ocp_cluster_count": ocp_cluster_count,
                "ocp_node_count": ocp_node_count,
                "ocp_project_count": ocp_project_count,
                "cost_model_count": cost_model_count,
            }

            return Response(data)

        """
        {
            "meta": {
                "count": 30
            },
            "links": {
                "first": "/api/cost-management/v1/resource-types/?offset=0",
                "previous": "/api/cost-management/v1/resource-types/?offset=20",
                "next": "/api/cost-management/v1/resource-types/?offset=40",
                "last": "/api/cost-management/v1/resource-types/?offset=100"
            },
            "data": [
                {
                "value": "aws.account",
                "path": "/api/cost-management/v1/resource-types/aws-accounts/",
                "count": 10
                },
                {
                "value": "aws.organizational_unit",
                "path": "/api/cost-management/v1/resource-types/aws-organizational-units/",
                "count": 2
                },
                {
                "value": "azure.subscription_guid",
                "path": "/api/cost-management/v1/resource-types/azure-subscription-guids/",
                "count": 0
                },
                {
                "value": "openshift.cluster",
                "path": "/api/cost-management/v1/resource-types/openshift-clusters/",
                "count": 3
                },
                {
                "value": "openshift.node",
                "path": "/api/cost-management/v1/resource-types/openshift-nodes/",
                "count": 12
                },
                {
                "value": "openshift.project",
                "path": "/api/cost-management/v1/resource-types/openshift-projects/",
                "count": 47
                },
                {
                "value": "rate",
                "path": "/api/cost-management/v1/resource-types/rates/",
                "count": 4
                }
            ]
            }
            """
