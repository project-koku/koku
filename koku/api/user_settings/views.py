#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View for Settings."""
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from rest_framework import permissions
from rest_framework.views import APIView

from api.common.pagination import ListPaginator
from api.user_settings.settings import COST_TYPES


class UserCostTypeSettings(APIView):
    """Settings views for user cost_type."""

    permission_classes = [permissions.AllowAny]

    @method_decorator(never_cache)
    def get(self, request):
        """Gets a list for all supported cost_typs currently available."""
        return ListPaginator(COST_TYPES, request).paginated_response
