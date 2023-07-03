#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View for Settings."""
from dataclasses import dataclass
from dataclasses import field

from django.utils.decorators import method_decorator
from django.utils.encoding import force_text
from django.views.decorators.cache import never_cache
from rest_framework import permissions
from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.response import Response
from rest_framework.views import APIView

from api.common.pagination import ListPaginator
from api.provider.models import Provider
from api.settings.utils import set_cost_type
from api.settings.utils import set_currency
from api.user_settings.serializer import UserSettingSerializer
from api.user_settings.serializer import UserSettingUpdateCostTypeSerializer
from api.user_settings.serializer import UserSettingUpdateCurrencySerializer
from api.user_settings.settings import COST_TYPES
from api.utils import get_account_settings
from api.utils import get_cost_type
from api.utils import get_currency
from koku.cache import invalidate_view_cache_for_tenant_and_all_source_types
from koku.cache import invalidate_view_cache_for_tenant_and_source_type


class SettingsInvalidFilterException(APIException):
    """Invalid parameter value"""

    def __init__(self, message):
        """Initialize with status code 404."""
        self.status_code = status.HTTP_404_NOT_FOUND
        self.detail = {"detail": force_text(message)}


@dataclass
class SettingParamsHandler:
    setting: str
    get_param: object = field(init=False)
    update_param: object = field(init=False)

    def __post_init__(self):
        if self.setting in ["cost-type"]:
            self.setting = self.setting.replace("-", "_")
            self.update_param = self.update_cost_type
            self.get_param = get_cost_type
        elif self.setting == "currency":
            self.update_param = self.update_currency
            self.get_param = get_currency
        else:
            raise SettingsInvalidFilterException("Invalid not a user setting")

    def update_cost_type(self, request_data, schema_name):
        serializer = UserSettingUpdateCostTypeSerializer(schema_name, request_data)
        if serializer.is_valid(raise_exception=True):
            set_cost_type(schema_name, request_data.get(self.setting))
            invalidate_view_cache_for_tenant_and_source_type(schema_name, Provider.PROVIDER_AWS)
            return Response(status=status.HTTP_204_NO_CONTENT)

    def update_currency(self, request_data, schema_name):
        serializer = UserSettingUpdateCurrencySerializer(schema_name, request_data)
        if serializer.is_valid(raise_exception=True):
            set_currency(schema_name, request_data.get(self.setting))
            invalidate_view_cache_for_tenant_and_all_source_types(schema_name)
            return Response(status=status.HTTP_204_NO_CONTENT)

    def retrieve_user_settings(self, request):
        users_setting = {"settings": {self.setting: self.get_param(request)}}
        users_setting = UserSettingSerializer(users_setting, many=False).data
        return Response(users_setting)


class AccountSettings(APIView):
    """Settings views for all user settings."""

    permission_classes = [permissions.AllowAny]

    def get(self, request, *args, **kwargs):
        """Gets a list of users current settings."""
        if not kwargs:
            user_settings = get_account_settings(request)
        else:
            param_handler = SettingParamsHandler(kwargs["setting"])
            user_settings = param_handler.retrieve_user_settings(request).data
        user_settings = UserSettingSerializer(user_settings, many=False).data
        paginated = ListPaginator(user_settings, request)
        return paginated.get_paginated_response(user_settings["settings"])

    def put(self, request, **kwargs):
        """Set the user cost type preference."""
        if not kwargs:
            return Response(status=status.HTTP_405_METHOD_NOT_ALLOWED)
        param_handler = SettingParamsHandler(kwargs["setting"])
        return param_handler.update_param(request.data, self.request.user.customer.schema_name)


class UserCostTypeSettings(APIView):
    """Settings views for user cost_type."""

    permission_classes = [permissions.AllowAny]

    @method_decorator(never_cache)
    def get(self, request):
        """Gets a list for all supported cost_typs currently available."""
        return ListPaginator(COST_TYPES, request).paginated_response
