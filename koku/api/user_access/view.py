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

from django.conf import settings
from django.utils.decorators import method_decorator
from django.views.decorators.vary import vary_on_headers
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from api.common import CACHE_RH_IDENTITY_HEADER
from api.common.pagination import ListPaginator

LOG = logging.getLogger(__name__)


class UIFeatureAccess:
    """Class for determining a user's access to a UI feature.

    This class enables the UI and platform to query for whether a user has access to certain resources.

    The purpose of this API is two things:
        1. to keep UI and API in sync about RBAC permissions
        2. to provide the UI (both our UI and the platform's chroming) with a simple boolean response regarding whether
            a user has access to specific features of the UI.

    Class attributes:

        access_keys (list) - a list of access keys to check. must be implemented by sub-classes.
                             multiple keys will be ORed; i.e. if a user has access to anything in the list,
                             this API returns True
    """

    def __init__(self, access):
        """Class Constructor.

        Args:
            access (dict) - an RBAC dict; see: koku.koku.middleware.IdentityHeaderMiddleware

        """
        self.access_dict = access if access else {}

    def _get_access_value(self, key1, key2, default=None):
        """Return the access value from the inner dict."""
        return self.access_dict.get(key1, {}).get(key2, default)

    @property
    def access(self):
        """Access property returns whether the user has the requested access.

        Return:
            (bool)
        """
        for key in self.access_keys:
            if self._get_access_value(key, "read") or self._get_access_value(key, "write"):
                return True
        return False


class AWSUserAccess(UIFeatureAccess):
    """Access to AWS UI Features."""

    access_keys = ["aws.account"]


class OCPUserAccess(UIFeatureAccess):
    """Access to OCP UI Features."""

    access_keys = ["openshift.cluster", "openshift.node", "openshift.project"]


class AzureUserAccess(UIFeatureAccess):
    """Access to Azure UI Features."""

    access_keys = ["azure.subscription_guid"]


class GCPUserAccess(UIFeatureAccess):
    """Access to GCP UI Features."""

    access_keys = ["gcp.account", "gcp.project"]


class CostModelUserAccess(UIFeatureAccess):
    """Access to Cost Model UI Features."""

    access_keys = ["cost_model"]


class AnyUserAccess(UIFeatureAccess):
    """Check for if the user has access to any features."""

    access_keys = (
        AWSUserAccess.access_keys + AzureUserAccess.access_keys + GCPUserAccess.access_keys + OCPUserAccess.access_keys
    )


class UserAccessView(APIView):
    """View class for handling requests to determine a user's access to a resource."""

    permission_classes = [AllowAny]

    _source_types = [
        {"type": "any", "access_class": AnyUserAccess},
        {"type": "aws", "access_class": AWSUserAccess},
        {"type": "azure", "access_class": AzureUserAccess},
        {"type": "cost_model", "access_class": CostModelUserAccess},
        {"type": "gcp", "access_class": GCPUserAccess},
        {"type": "ocp", "access_class": OCPUserAccess},
    ]

    @method_decorator(vary_on_headers(CACHE_RH_IDENTITY_HEADER))
    def get(self, request, **kwargs):
        """Respond to HTTP GET requests.

        Args:
            request (Request) HTTP Request object
                - request.query_params (dict)
                    - type (str) - the name of the feature; feature type
                    - beta (bool) - feature flag; this signals that this is a pre-release feature.
            kwargs (dict) optional keyword args
        """
        query_params = request.query_params
        user_access = request.user.access
        LOG.info(f"User Access RBAC permissions: {str(user_access)}. Org Admin: {str(request.user.admin)}")
        admin_user = request.user.admin
        LOG.info(f"User Access admin user: {str(admin_user)}")

        # only show pre-release features in approved environments
        flag = query_params.get("beta", "False")  # query_params are strings, not bools.
        if flag.lower() == "true" and not settings.ENABLE_PRERELEASE_FEATURES:
            return Response({"data": False})

        source_type = query_params.get("type")
        if source_type:
            source_accessor = next(
                (item for item in self._source_types if item.get("type") == source_type.lower()), False
            )
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
        for source_type in self._source_types:
            access_granted = False
            if admin_user:
                access_granted = True
            else:
                access_granted = source_type.get("access_class")(user_access).access
            data.append({"type": source_type.get("type"), "access": access_granted})

        paginator = ListPaginator(data, request)

        return paginator.get_paginated_response(data)
