#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View for Settings."""
from django.utils.decorators import method_decorator
from django.utils.encoding import force_text
from django.views.decorators.cache import never_cache
from rest_framework import permissions
from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.response import Response
from rest_framework.views import APIView

from api.common.pagination import CustomMetaPagination
from api.common.pagination import ListPaginator
from api.user_settings.serializer import UserSettingSerializer
from api.user_settings.settings import COST_TYPES
from api.utils import get_account_settings
from api.utils import get_cost_type
from api.utils import get_currency


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
        user_preferred_cost = {"cost-type": get_cost_type(request)}
        return CustomMetaPagination(COST_TYPES, request, user_preferred_cost).get_paginated_response()
