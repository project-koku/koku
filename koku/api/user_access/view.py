#
# Copyright 2021 Red Hat, Inc.
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
"""View for UserAccess."""
import logging

from django.utils.decorators import method_decorator
from django.views.decorators.vary import vary_on_headers
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from api.common import CACHE_RH_IDENTITY_HEADER
from api.common.pagination import ListPaginator

LOG = logging.getLogger(__name__)


class UserAccess:
    def check_access(self, access_list):
        LOG.info(f"Access List: {str(access_list)}")
        if access_list.get("read") or access_list.get("write"):
            return True
        return False


class AWSUserAccess(UserAccess):
    def __init__(self, access):
        self.account_access = access.get("aws.account")

    @property
    def access(self):
        if self.check_access(self.account_access):
            return True
        return False


class OCPUserAccess(UserAccess):
    def __init__(self, access):
        self.cluster_access = access.get("openshift.cluster")
        self.node_access = access.get("openshift.node")
        self.project_access = access.get("openshift.project")

    @property
    def access(self):
        if (
            self.check_access(self.cluster_access)
            or self.check_access(self.node_access)
            or self.check_access(self.project_access)
        ):
            return True
        return False


class AzureUserAccess(UserAccess):
    def __init__(self, access):
        self.subscription_access = access.get("azure.subscription_guid")

    @property
    def access(self):
        if self.check_access(self.subscription_access):
            return True
        return False


class GCPUserAccess(UserAccess):
    def __init__(self, access):
        self.account_access = access.get("gcp.account")
        self.project_access = access.get("gcp.project")

    @property
    def access(self):
        if self.check_access(self.account_access) or self.check_access(self.project_access):
            return True
        return False


class CostModelUserAccess(UserAccess):
    def __init__(self, access):
        self.subscription_access = access.get("cost_model")

    @property
    def access(self):
        if self.check_access(self.subscription_access):
            return True
        return False


class UserAccessView(APIView):
    """API GET view for User API."""

    permission_classes = [AllowAny]

    @method_decorator(vary_on_headers(CACHE_RH_IDENTITY_HEADER))
    def get(self, request, **kwargs):
        query_params = request.query_params
        user_access = request.user.access
        LOG.info(f"User Access RBAC permissions: {str(user_access)}. Org Admin: {str(request.user.admin)}")
        admin_user = request.user.admin
        LOG.info(f"User Access admin user: {str(admin_user)}")

        source_types = [
            {"type": "aws", "access_class": AWSUserAccess},
            {"type": "ocp", "access_class": OCPUserAccess},
            {"type": "gcp", "access_class": GCPUserAccess},
            {"type": "azure", "access_class": AzureUserAccess},
            {"type": "cost_model", "access_class": CostModelUserAccess},
        ]

        source_type = query_params.get("type")
        if source_type:
            source_accessor = next((item for item in source_types if item.get("type") == source_type.lower()), False)
            if source_accessor:
                access_class = source_accessor.get("access_class")
                if admin_user:
                    access_granted = True
                else:
                    access_granted = access_class(user_access).access
                return Response({"data": access_granted})
            else:
                return Response({f"Unknown source type: {source_type}"}, status=status.HTTP_400_BAD_REQUEST)

        data = []
        for source_type in source_types:
            access_granted = False
            if admin_user:
                access_granted = True
            else:
                access_granted = source_type.get("access_class")(user_access).access
            data.append({"type": source_type.get("type"), "access": access_granted})

        paginator = ListPaginator(data, request)

        return paginator.get_paginated_response(data)
