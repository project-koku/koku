#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View for UserAccess."""
import dataclasses
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


# Backwards Compatability Statement:
# This endpoint currently supports a type param to show permissions
# for a single access key. Currently this param has a different
# return structure than a get on `/user_access/`. However, the
# type param is used by console dot to show nav links here:
# https://console.redhat.com/settings/applications/cost-management

# Therefore, we may be able to remove the type param after the transition
# or atleast modify its return to be the same as when we use `/user_access/`
# I have marked areas where we are special casing to return the structure
# console dot expects for now.


@dataclasses.dataclass
class AccessMapping:
    aws: tuple[str, str] = ("aws.account", "aws.organizational_unit")
    azure: tuple[str] = ("azure.subscription_guid",)
    gcp: tuple[str, str] = ("gcp.account", "gcp.project")
    ocp: tuple[str, str, str] = ("openshift.cluster", "openshift.node", "openshift.project")
    cost_model: tuple[str] = ("cost_model",)
    settings: tuple[str] = ("settings",)
    any: tuple[str, ...] = None

    def __post_init__(self):
        result = []
        for field in dataclasses.fields(self):
            if field.name in ["any", "cost_model", "settings"]:
                continue

            result.extend(getattr(self, field.name))

        # any is any cloud provider.
        self.any = tuple(result)

    def __getitem__(self, item):
        return getattr(self, item)

    def get(self, item, default=None):
        return getattr(self, item, default)


ACCESS_KEY_MAPPING = AccessMapping()


class UIFeatureAccess:
    """Class for determining a user's access to a UI feature.

    This class enables the UI and platform to query for whether a user has access to certain resources.

    The purpose of this API is two things:
        1. to keep UI and API in sync about RBAC permissions
        2. to provide the UI (both our UI and the platform's chroming) with a simple boolean response regarding whether
            a user has access to specific features of the UI.
    """

    PRERELEASE = []

    def __init__(self, access, admin_user):
        """Class Constructor.

        Args:
            access (dict) - an RBAC dict; see: koku.koku.middleware.IdentityHeaderMiddleware
            admin_user (boolean) - Indicates if the user is an admin

        """
        self.access_key_list = list(dataclasses.asdict(ACCESS_KEY_MAPPING))
        self.access_dict = access if access else {}
        self.admin_user = admin_user

    def check_if_valid_param(self, query_param):
        if query_param := ACCESS_KEY_MAPPING.get(query_param):
            return True
        return False

    def set_access_key_to_query_param(self, query_param):
        """Sets the access key list to what is passed."""
        self.access_key_list = [query_param]

    def _get_access_value(self, key1, key2, default=None):
        """Return the access value from the inner dict."""
        return self.access_dict.get(key1, {}).get(key2, default)

    def _check_access(self, pre_release_feature, access_key):
        """Access property returns whether the user has the requested access.

        Return:
            (access, write)
            acesss = bool
            write = bool
        """

        if pre_release_feature and not settings.ENABLE_PRERELEASE_FEATURES:
            return False, False
        if self.admin_user:
            return True, True
        for rbac_setting in ACCESS_KEY_MAPPING[access_key]:
            if self._get_access_value(rbac_setting, "write"):
                return True, True
            elif self._get_access_value(rbac_setting, "read"):
                return True, False
        return False, False

    def generate_data(self):
        data = []
        for access_key in self.access_key_list:
            pre_release_feature = access_key in self.PRERELEASE
            access, write = self._check_access(pre_release_feature, access_key)
            data.append({"type": access_key, "access": access, "write": write})

        if len(self.access_key_list) == 1:
            # For backwards compatability.
            data = {"data": access, "access": access, "write": write}
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
        if access_type := query_params.get("type"):
            access_type = access_type.lower()
            if not ui_feature_access.check_if_valid_param(access_type):
                return Response(
                    {f"Unknown source type: {query_params.get('type')}"}, status=status.HTTP_400_BAD_REQUEST
                )
            ui_feature_access.set_access_key_to_query_param(access_type)

        data = ui_feature_access.generate_data()
        if isinstance(data, dict):
            # backwards compatability
            return Response(data)

        paginator = ListPaginator(data, request)

        return paginator.get_paginated_response(data)
