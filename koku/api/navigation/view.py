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
"""View for Navigation."""
import logging
from django.utils.decorators import method_decorator
from django.views.decorators.vary import vary_on_headers
from rest_framework.views import APIView
from api.navigation.serializers import NavigationSerializer

from api.common import CACHE_RH_IDENTITY_HEADER
from api.common.pagination import ListPaginator
from api.query_params import get_tenant
from rest_framework.permissions import AllowAny
from api.query_handler import WILDCARD

LOGGER = logging.getLogger(__name__)


class NavigationAccess():
    def check_access(self, access_list):
        if access_list:
            if WILDCARD in access_list:
                return True
            elif access_list.get("read"):
                if WILDCARD in access_list.get("read"):
                    return True
        return False

class AWSNavigationAccess(NavigationAccess):
    def __init__(self, access):
        self.account_access = access.get("aws.account")

    @property
    def access(self):
        import pdb; pdb.set_trace()
        if self.check_access(self.account_access):
            return True
        return False


class OCPNavigationAccess(NavigationAccess):
    def __init__(self, access):
        self.cluster_access = access.get("openshift.cluster")
        self.node_access = access.get("openshift.node")
        self.project_access = access.get("openshift.project")
    
    @property
    def access(self):
        if self.check_access(self.cluster_access) or self.check_access(self.node_access) or self.check_access(self.project_access):
            return True
        return False


class GCPNavigationAccess(NavigationAccess):
    def __init__(self, access):
        self.account_access = access.get("gcp.account")
        self.project_access = access.get("gcp.project")

    @property
    def access(self):
        if self.check_access(self.account_access) or self.check_access(self.project_access):
            return True
        return False


class NavigationView(APIView):
    """API GET view for Navigation API."""

    permission_classes = [AllowAny]
    serializer = NavigationSerializer

    @method_decorator(vary_on_headers(CACHE_RH_IDENTITY_HEADER))
    def get(self, request, **kwargs):
        tenant = get_tenant(request.user)
        user_access = request.user.access
        user_org_admin = request.user.admin

        source_types = [{"type": "AWS", "access_class": AWSNavigationAccess},
                        {"type": "OCP", "access_class": OCPNavigationAccess},
                        {"type": "GCP", "access_class": GCPNavigationAccess}]
        data = []
        for source_type in source_types:
            user_access = False
            if user_org_admin:
                user_access = True
            else:
                user_access = source_type.get("access_class")(user_access)
            data.append({source_type.get("type"): user_access})

        paginator = ListPaginator(data, request)

        return paginator.get_paginated_response(data)
