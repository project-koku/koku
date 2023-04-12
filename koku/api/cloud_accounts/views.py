#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View for Cloud Account."""
import copy

from rest_framework import permissions
from rest_framework.decorators import api_view
from rest_framework.decorators import permission_classes
from rest_framework.decorators import renderer_classes
from rest_framework.renderers import JSONRenderer
from rest_framework.settings import api_settings

from api.cloud_accounts import CLOUD_ACCOUNTS
from api.common.pagination import ListPaginator
from api.metrics.serializers import QueryParamsSerializer


"""View for Cloud Accounts."""


@api_view(["GET"])
@permission_classes((permissions.AllowAny,))
@renderer_classes([JSONRenderer] + api_settings.DEFAULT_RENDERER_CLASSES)
def cloud_accounts(request):
    """View for cloud accounts."""
    serializer = QueryParamsSerializer(data=request.query_params)
    serializer.is_valid(raise_exception=True)
    cloud_accounts_copy = copy.deepcopy(CLOUD_ACCOUNTS)
    paginator = ListPaginator(cloud_accounts_copy, request)
    return paginator.paginated_response
