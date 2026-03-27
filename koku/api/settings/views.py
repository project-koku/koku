#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View for Settings."""
import os
import typing as t
from dataclasses import dataclass
from dataclasses import field

from django.db import transaction
from django.utils.decorators import method_decorator
from django.utils.encoding import force_str
from django.views.decorators.cache import never_cache
from django_tenants.utils import schema_context
from rest_framework import permissions
from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from api.common.pagination import ListPaginator
from api.common.permissions.settings_access import SettingsAccessPermission
from api.provider.models import Provider
from api.settings.serializers import TenantSettingsSerializer
from api.settings.serializers import UserSettingSerializer
from api.settings.serializers import UserSettingUpdateCostTypeSerializer
from api.settings.serializers import UserSettingUpdateCurrencySerializer
from api.settings.settings import COST_TYPES
from api.settings.utils import get_data_retention_months
from api.settings.utils import set_cost_type
from api.settings.utils import set_currency
from api.utils import get_account_settings
from api.utils import get_cost_type
from api.utils import get_currency
from koku.cache import invalidate_view_cache_for_tenant_and_all_source_types
from koku.cache import invalidate_view_cache_for_tenant_and_source_type
from reporting.tenant_settings.models import TenantSettings


class SettingsInvalidFilterException(APIException):
    """Invalid parameter value"""

    def __init__(self, message):
        """Initialize with status code 404."""
        self.status_code = status.HTTP_404_NOT_FOUND
        self.detail = {"detail": force_str(message)}


@dataclass
class SettingParamsHandler:
    setting: str
    request: Request
    get_param: t.Callable = field(init=False)
    update_param: t.Callable = field(init=False)

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

    def update_cost_type(self, schema_name):
        serializer = UserSettingUpdateCostTypeSerializer(schema_name, self.request.data)
        if serializer.is_valid(raise_exception=True):
            set_cost_type(schema_name, self.request.data.get(self.setting))
            invalidate_view_cache_for_tenant_and_source_type(schema_name, Provider.PROVIDER_AWS)
            return Response(status=status.HTTP_204_NO_CONTENT)

    def update_currency(self, schema_name):
        serializer = UserSettingUpdateCurrencySerializer(schema_name, self.request.data)
        if serializer.is_valid(raise_exception=True):
            set_currency(schema_name, self.request.data.get(self.setting))
            invalidate_view_cache_for_tenant_and_all_source_types(schema_name)
            return Response(status=status.HTTP_204_NO_CONTENT)

    def get_user_settings(self):
        users_setting = {"settings": {self.setting: self.get_param(self.request)}}
        users_setting = UserSettingSerializer(users_setting, many=False).data
        return Response(users_setting)


class AccountSettings(APIView):
    """Settings views for all user settings."""

    permission_classes = [SettingsAccessPermission]

    def get(self, request, *args, **kwargs):
        """Gets a list of users current settings."""
        if not kwargs:
            user_settings = get_account_settings(request)
        else:
            param_handler = SettingParamsHandler(kwargs["setting"], request)
            user_settings = param_handler.get_user_settings().data
        user_settings = UserSettingSerializer(user_settings, many=False).data
        paginated = ListPaginator(user_settings, request)
        return paginated.get_paginated_response(user_settings["settings"])

    def put(self, request, **kwargs):
        """Set the user cost type preference."""
        if not kwargs:
            return Response(status=status.HTTP_405_METHOD_NOT_ALLOWED)
        param_handler = SettingParamsHandler(kwargs["setting"], request)
        return param_handler.update_param(self.request.user.customer.schema_name)


class GlobalSettingsView(APIView):
    """Tenant-scoped data-retention settings (ONPREM only)."""

    permission_classes = [SettingsAccessPermission]

    def get(self, request):
        schema = request.user.customer.schema_name
        env_override = os.environ.get("RETAIN_NUM_MONTHS") is not None
        effective = get_data_retention_months(schema)
        if effective is None:
            return Response(
                {"error": "Unable to read retention settings."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response({"data_retention_months": effective, "env_override": env_override})

    def put(self, request):
        if os.environ.get("RETAIN_NUM_MONTHS") is not None:
            return Response(
                {
                    "error": (
                        "Data retention is controlled by the RETAIN_NUM_MONTHS "
                        "environment variable and cannot be modified via the API."
                    )
                },
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = TenantSettingsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        new_value = serializer.validated_data["data_retention_months"]
        schema = request.user.customer.schema_name
        with schema_context(schema), transaction.atomic():
            settings_row, created = TenantSettings.objects.select_for_update().get_or_create(
                defaults={"data_retention_months": new_value},
            )
            if not created:
                settings_row.data_retention_months = new_value
                settings_row.full_clean()
                settings_row.save()
        invalidate_view_cache_for_tenant_and_all_source_types(schema)
        return Response(status=status.HTTP_204_NO_CONTENT)


class UserCostTypeSettings(APIView):
    """Settings views for user cost_type."""

    permission_classes = [permissions.AllowAny]

    @method_decorator(never_cache)
    def get(self, request):
        """Gets a list for all supported cost_typs currently available."""
        return ListPaginator(COST_TYPES, request).paginated_response
