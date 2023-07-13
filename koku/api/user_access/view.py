#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
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
    """

    PRERELEASE = ["ibm"]

    def __init__(self, access, admin_user, access_key_list=None):
        """Class Constructor.

        Args:
            access (dict) - an RBAC dict; see: koku.koku.middleware.IdentityHeaderMiddleware

        """
        if not access_key_list:
            self.access_key_list = self.access_key_mapping.keys()
        self.access_dict = access if access else {}
        self.admin_user = admin_user
        self.access_key_list = []

    def set_access_key_list(self, query_param):
        """Checks the access key list."""
        if query_param:
            if query_param in self.access_key_mapping:
                self.access_key_list = [query_param]
        else:
            self.access_key_list = self.access_key_mapping.keys()
        return bool(self.access_key_list)

    @property
    def access_key_mapping(self):
        mapping = {}
        mapping["aws"] = ["aws.account", "aws.organizational_unit"]
        mapping["ocp"] = ["openshift.cluster", "openshift.node", "openshift.project"]
        mapping["azure"] = ["azure.subscription_guid"]
        mapping["gcp"] = ["gcp.account", "gcp.project"]
        mapping["oci"] = ["oci.payer_tenant_id"]
        mapping["ibm"] = ["ibm.account"]
        mapping["cost_model"] = ["cost_model"]
        mapping["settings"] = ["settings"]
        mapping["any"] = mapping["aws"] + mapping["azure"] + mapping["gcp"] + mapping["oci"] + mapping["ocp"]
        return mapping

    def _get_access_value(self, key1, key2, default=None):
        """Return the access value from the inner dict."""
        return self.access_dict.get(key1, {}).get(key2, default)

    def _check_access(self, pre_release_feature, access_key):
        """Access property returns whether the user has the requested access.

        Return:
            (access, read_only)
            acesss = bool or None
            read_only = bool or none
        """

        if pre_release_feature and not settings.ENABLE_PRERELEASE_FEATURES:
            return False, None
        if self.admin_user:
            return True, False
        for rbac_setting in self.access_key_mapping[access_key]:
            if self._get_access_value(rbac_setting, "write"):
                return True, False
            elif self._get_access_value(rbac_setting, "read"):
                return True, True
        return False, None

    def generate_data(self):
        data = []
        for access_key in self.access_key_list:
            pre_release_feature = bool(access_key in self.PRERELEASE)
            access, read_only = self._check_access(pre_release_feature, access_key)
            data.append({"type": access_key, "access": access, "read_only": read_only})

        if len(self.access_key_list) == 1:
            # For backwards compatability.
            data = {"data": access, "access": access, "read_only": read_only}
        return data


class UserAccessView(APIView):
    """View class for handling requests to determine a user's access to a resource."""

    permission_classes = [AllowAny]

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
        admin_user = request.user.admin
        beta = request.user.beta
        LOG.debug(f"User Access RBAC permissions: {str(user_access)}. Org Admin: {str(admin_user)}. Beta: {str(beta)}")

        flag = query_params.get("beta", "False")  # query_params are strings, not bools.
        if flag.lower() == "true" and not beta:
            return Response({"data": False})

        ui_feature_access = UIFeatureAccess(user_access, admin_user)
        is_valid_param = ui_feature_access.set_access_key_list(query_params.get("type"))
        if not is_valid_param:
            return Response({f"Unknown source type: {query_params.get('type')}"}, status=status.HTTP_400_BAD_REQUEST)
        data = ui_feature_access.generate_data()
        if isinstance(data, dict):
            # backwards compatability
            return Response(data)

        paginator = ListPaginator(data, request)

        return paginator.get_paginated_response(data)
