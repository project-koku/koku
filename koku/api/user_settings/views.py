#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View for Settings."""
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from tenant_schemas.utils import schema_context

from api.common.pagination import CustomMetaPagination
from api.user_settings.settings import COST_TYPES
from api.user_settings.settings import USER_SETTINGS
from api.utils import get_cost_type
from reporting.user_settings.models import UserSettings


class AllUserSettings(APIView):
    """Settings views for all user settings."""

    permission_classes = [permissions.AllowAny]

    @method_decorator(never_cache)
    def get(self, request):
        """Gets a list of users current settings."""
        user_settings = self.get_user_settings(self, request)
        return Response(user_settings)

    def get_user_settings(self, _, request):
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
