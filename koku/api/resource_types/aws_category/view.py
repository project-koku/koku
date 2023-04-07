#
# Copyright 2023 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View for AWS category resource types."""
# import copy
import logging

from django.conf import settings
from django.db.models import Exists
from django.db.models import F
from django.db.models import Func
from django.db.models import OuterRef
from django.utils.decorators import method_decorator
from django.views.decorators.vary import vary_on_headers
from rest_framework import generics
from rest_framework import status
from rest_framework.response import Response

from api.common import CACHE_RH_IDENTITY_HEADER
from api.common.pagination import ResourceTypeViewPaginator
from api.common.permissions import AwsAccessPermission
from api.resource_types.aws_category.serializers import AWSCategorySerializer
from reporting.provider.aws.models import AWSCategorySummary
from reporting.provider.aws.models import AWSEnabledCategoryKeys


LOG = logging.getLogger(__name__)


class AWSCategoryView(generics.ListAPIView):
    """
    Get a list of category key value pairs
    """

    permission_classes = [
        AwsAccessPermission,
    ]
    # Note: Unnesting to remove duplicate values
    annotations = {
        "unnested_value": Func(F("values"), function="unnest"),
        "enabled": Exists(AWSEnabledCategoryKeys.objects.filter(key=OuterRef("key")).filter(enabled=True)),
    }
    queryset = AWSCategorySummary.objects.values("key").annotate(**annotations).distinct()
    SUPPORTED_FILTERS = ["key", "value", "account", "enabled", "search", "limit"]
    pagination_class = ResourceTypeViewPaginator
    serializer_class = AWSCategorySerializer

    @method_decorator(vary_on_headers(CACHE_RH_IDENTITY_HEADER))
    def list(self, request):
        supported_query_params = ["search", "limit"]
        user_access = []
        error_message = {}

        # # Test for only supported query_params
        if self.request.query_params:
            for key in self.request.query_params:
                if key not in supported_query_params:
                    error_message[key] = [{"Unsupported parameter"}]
                    return Response(error_message, status=status.HTTP_400_BAD_REQUEST)
        if settings.ENHANCED_ORG_ADMIN and request.user.admin:
            return super().list(request)
        elif request.user.access:
            user_access = request.user.access.get("aws.account", {}).get("read", [])
        if user_access and user_access[0] == "*":
            return super().list(request)
        self.queryset = self.queryset.filter(usage_account_id__in=user_access)

        return super().list(request)

    # Overwrite generics.ListAPIView paginate_queryset to
    # combine values before return
    def paginate_queryset(self, queryset):
        """
        Return a single page of results, or `None` if pagination is disabled.
        """
        key_to_values = {}
        for row in queryset:
            key = row.get("key")
            if metadata := key_to_values.get(key):
                metadata["values"].update({row.get("unnested_value")})
            else:
                key_to_values[key] = {"values": {row.get("unnested_value")}, "enabled": row.get("enabled")}
        result = []
        for key, values in key_to_values.items():
            values["key"] = key
            result.append(values)
        return self.paginator.paginate_queryset(result, self.request, view=self)
