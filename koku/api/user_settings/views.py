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


@dataclass
class SettingUpdater:
    setting: str
    schema_name: str
    is_valid: bool = False
    serializer_class: object = field(init=False)
    update_method: object = field(init=False)
    invalidate_cache: object = field(init=False)
    cache_kwargs: dict = field(init=False)

    def __post_init__(self):
        if self.setting == "cost_type":
            self.serializer_class = UserSettingUpdateCostTypeSerializer
            self.update_method = set_cost_type
            self.invalidate_cache = invalidate_view_cache_for_tenant_and_source_type
            self.cache_kwargs = {"schema_name": self.schema_name, "source_type": Provider.PROVIDER_AWS}
            self.is_valid = True
        elif self.setting == "currency":
            self.serializer_class = UserSettingUpdateCurrencySerializer
            self.update_method = set_currency
            self.invalidate_cache = invalidate_view_cache_for_tenant_and_all_source_types
            self.cache_kwargs = {"schema_name": self.schema_name}
            self.is_valid = True

    def init_serializer(self, data):
        return self.serializer_class(self.schema_name, data)

    def update(self, data):
        self.update_method(self.schema_name, data)
        self.invalidate_cache(**self.cache_kwargs)


class SettingsInvalidFilterException(APIException):
    """Invalid parameter value"""

    def __init__(self, message):
        """Initialize with status code 404."""
        self.status_code = status.HTTP_404_NOT_FOUND
        self.detail = {"detail": force_text(message)}


class AccountSettings(APIView):
    """Settings views for all user settings."""

    permission_classes = [permissions.AllowAny]

    def get(self, request, *args, **kwargs):
        """Gets a list of users current settings."""
        if not kwargs:
            user_settings = get_account_settings(request)
        else:
            setting = kwargs["setting"]
            self.validate_setting(setting)
            user_settings = self.get_account_setting(request, setting).data
        user_settings = UserSettingSerializer(user_settings, many=False).data
        paginated = ListPaginator(user_settings, request)
        return paginated.get_paginated_response(user_settings["settings"])

    def put(self, request, **kwargs):
        """Set the user cost type preference."""
        if not kwargs:
            return Response(status=status.HTTP_405_METHOD_NOT_ALLOWED)
        setting = kwargs["setting"]
        updater = SettingUpdater(setting, self.request.user.customer.schema_name)
        if not updater.is_valid:
            error = {"error": f"Unknown setting:{setting}"}
            return Response(data=error, status=status.HTTP_400_BAD_REQUEST)
        serializer = updater.init_serializer(request.data)
        if serializer.is_valid(raise_exception=True):
            if setting_value := request.data.get(setting):
                updater.update(setting_value)
            return Response(status=status.HTTP_204_NO_CONTENT)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @staticmethod
    def validate_setting(setting):
        """Check if filter parameters are valid"""
        valid_query_params = ["cost-type", "currency"]
        if setting not in valid_query_params:
            raise SettingsInvalidFilterException("Invalid not a user setting")

    def get_account_setting(self, request, setting):
        """Returns specific setting that is being filtered"""
        if setting == "cost-type":
            users_setting = {"settings": {"cost_type": get_cost_type(request)}}
        elif setting == "currency":
            users_setting = {"settings": {"currency": get_currency(request)}}
        users_setting = UserSettingSerializer(users_setting, many=False).data
        return Response(users_setting)


class UserCostTypeSettings(APIView):
    """Settings views for user cost_type."""

    permission_classes = [permissions.AllowAny]

    @method_decorator(never_cache)
    def get(self, request):
        """Gets a list for all supported cost_typs currently available."""
        return ListPaginator(COST_TYPES, request).paginated_response
