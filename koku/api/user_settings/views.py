#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View for Settings."""
from rest_framework import permissions
from rest_framework.decorators import api_view
from rest_framework.decorators import permission_classes
from rest_framework.decorators import renderer_classes
from rest_framework.renderers import JSONRenderer
from rest_framework.settings import api_settings

from api.common.pagination import CustomMetaPagination
from api.user_settings.settings import COST_TYPES
from koku.settings import KOKU_DEFAULT_COST_TYPE
from reporting.user_settings.models import UserSettings


def get_selected_cost_type():
    if not UserSettings.objects.exists():
        cost_type = KOKU_DEFAULT_COST_TYPE
    else:
        cost_type = UserSettings.objects.all().first().settings["cost_type"]
    return cost_type


@api_view(("GET",))
@permission_classes((permissions.AllowAny,))
@renderer_classes([JSONRenderer] + api_settings.DEFAULT_RENDERER_CLASSES)
def get_cost_type(request):
    """Gets a list for all supported cost_typs currently available."""
    user_preferred_cost = {"cost-type": get_selected_cost_type()}
    return CustomMetaPagination(COST_TYPES, request, user_preferred_cost).get_paginated_response()
