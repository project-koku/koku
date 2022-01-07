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
from tenant_schemas.utils import schema_context

from api.common.pagination import CustomMetaPagination
from api.user_settings.settings import COST_TYPES
from api.user_settings.settings import USER_SETTINGS
from api.utils import get_cost_type
from api.utils import get_currency
from reporting.user_settings.models import UserSettings


class SettingsInvalidFilterException(APIException):
    """Invalid parameter value"""

    def __init__(self, message):
        """Initialize with status code 400."""
        self.status_code = status.HTTP_400_BAD_REQUEST
        self.detail = {"detail": force_text(message)}


class AllUserSettings(APIView):
    """Settings views for all user settings."""

    permission_classes = [permissions.AllowAny]

    def get(self, request, *args, **kwargs):
        """Gets a list of users current settings."""
        param = kwargs
        if not param:
            user_settings = self.get_user_settings(request)
        else:
            setting = param["setting"]
            self.validate_setting(setting)
            user_settings = self.get_user_setting(request, setting)
        return Response(user_settings)

    @staticmethod
    def validate_setting(setting):
        """Check if filter parameters are valid"""
        valid_query_params = ["cost-type", "currency"]
        if setting not in valid_query_params:
            raise SettingsInvalidFilterException("Invalid Filter Parameter")

    def get_user_setting(self, request, setting):
        """Returns specific setting that is being filtered"""
        if setting == "cost-type":
            users_setting = {"cost_type": get_cost_type(request)}
        elif setting == "currency":
            users_setting = {"currency": get_currency(request)}
        return users_setting

    def get_user_settings(self, request):
        """Returns users settings from the schema or the default settings"""
        with schema_context(request.user.customer.schema_name):
            query_settings = UserSettings.objects.all().first().settings
        if not query_settings:
            user_settings = USER_SETTINGS
        else:
            user_settings = query_settings
        return user_settings


class UserCostTypeSettings(APIView):
    """Settings views for user cost_type."""

    permission_classes = [permissions.AllowAny]

    @method_decorator(never_cache)
    def get(self, request):
        """Gets a list for all supported cost_typs currently available."""
        user_preferred_cost = {"cost-type": get_cost_type(request)}
        return CustomMetaPagination(COST_TYPES, request, user_preferred_cost).get_paginated_response()
