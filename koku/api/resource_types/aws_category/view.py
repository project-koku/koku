#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View for AWS organizational units."""
# import copy
import logging

from django.conf import settings
from django.contrib.postgres.aggregates import ArrayAgg
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

# from django.db import connection
# from django.views.decorators.cache import never_cache
# from rest_framework import filters
# from rest_framework.views import APIView
# from tenant_schemas.utils import tenant_context
# from api.common.permissions.aws_access import AWSOUAccessPermission
# from api.query_params import get_tenant
# from api.resource_types.serializers import ResourceTypeSerializer

LOG = logging.getLogger(__name__)


class AWSCategoryView(generics.ListAPIView):
    """
    Get a list of category key value pairs
    """

    permission_classes = [
        AwsAccessPermission,
    ]
    # Note: Unnesting to remove duplicate values
    # Example:
    custom_annotations = {
        "values": Func(F("values"), function="unnest"),
        "enabled": Exists(AWSEnabledCategoryKeys.objects.filter(key=OuterRef("key")).filter(enabled=True)),
        "keys": F("key"),
    }
    aggregate = {
        "values": ArrayAgg("values"),
    }

    queryset = AWSCategorySummary.objects.values("key").annotate(**custom_annotations).distinct()
    SUPPORTED_FILTERS = ["key", "value", "account", "enabled", "search", "limit"]
    pagination_class = ResourceTypeViewPaginator
    serializer_class = AWSCategorySerializer

    # def _format_query_response(self, request):
    #     """Format the query response with data.

    #     Returns:
    #         (Dict): Dictionary response of query params, data, and total

    #     """
    #     LOG.info("here")
    #     deduplicated_values = {}
    #     for row in self.get_queryset():
    #         key = row.get("key")
    #         if metadata := deduplicated_values.get(key):
    #             metadata["values"].update(set(row.get("values")))
    #         else:
    #             deduplicated_values[key] = {
    #                 "values": set(row.get("values")),
    #                 "enabled": row.get("enabled")
    #             }
    #     result = []
    #     for key, values in deduplicated_values.items():
    #         values['key'] = key
    #         result.append(values)
    #     self.queryset = result
    #     return super().list(request)

    @method_decorator(vary_on_headers(CACHE_RH_IDENTITY_HEADER))
    def list(self, request):
        # Reads the users values for org unit id and displays values related to what the user has access to
        supported_query_params = ["search", "limit"]
        user_access = []
        error_message = {}

        # result = AWSCategorySummary.objects.values("key").annotate(**self.custom_annotations).distinct()
        # print(result)
        # self.get_queryset()

        from django.db import connection

        readable_queries = []
        for dikt in connection.queries:
            for key, item in dikt.items():
                item = item.replace('"', "")
                item = item.replace("\\", "")
                readable_queries.append({key: item})
        LOG.info(readable_queries)

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

    # Overwrite generics.ListAPIView paginate_queryset to aggregate before response return.
    def paginate_queryset(self, queryset):
        """
        Return a single page of results, or `None` if pagination is disabled.
        """
        if self.paginator is None:
            return None
        # queryset = queryset.aggregate(**self.aggregate)
        return self.paginator.paginate_queryset(queryset, self.request, view=self)
