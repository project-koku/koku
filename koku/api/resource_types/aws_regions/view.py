#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View for AWS by regions."""
import boto3
from django.conf import settings
from django.db.models import F
from django.utils.decorators import method_decorator
from django.views.decorators.vary import vary_on_headers
from rest_framework import filters
from rest_framework import generics
from rest_framework import status
from rest_framework import views
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from api.common import CACHE_RH_IDENTITY_HEADER
from api.common.pagination import ResourceTypeViewPaginator
from api.common.permissions.aws_access import AwsAccessPermission
from api.resource_types.serializers import ResourceTypeSerializer
from reporting.provider.aws.models import AWSCostSummaryByRegionP


class AWSAccountRegionView(generics.ListAPIView):
    """API GET list view for AWS by region"""

    queryset = (
        AWSCostSummaryByRegionP.objects.annotate(**{"value": F("region")})
        .values("value")
        .distinct()
        .filter(region__isnull=False)
    )
    serializer_class = ResourceTypeSerializer
    permission_classes = [AwsAccessPermission]
    filter_backends = [filters.OrderingFilter, filters.SearchFilter]
    ordering = ["value"]
    search_fields = ["value"]
    pagination_class = ResourceTypeViewPaginator

    @method_decorator(vary_on_headers(CACHE_RH_IDENTITY_HEADER))
    def list(self, request):
        # Reads the users values for aws.accounts and displays values related to what the user has access to
        supported_query_params = ["search", "limit"]
        user_access = []
        error_message = {}
        # Test for only supported query_params
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


class AWSAllRegionView(views.APIView):
    """API GET list view for AWS of all regions"""

    permission_classes = [AllowAny]

    @method_decorator(vary_on_headers(CACHE_RH_IDENTITY_HEADER))
    def get(self, request):
        supported_query_params = ["limit", "offset", "search"]
        error_message = {}
        search_values = []
        # Test for only supported query_params
        if self.request.query_params:
            for key in self.request.query_params:
                if key not in supported_query_params:
                    error_message[key] = [{"Unsupported parameter"}]
                    return Response(error_message, status=status.HTTP_400_BAD_REQUEST)
        search_value_str = self.request.query_params.get("search")
        if search_value_str:
            search_values = search_value_str.split(",")
        regions = boto3.Session().get_available_regions("s3")
        filtered_regions = []
        for region in regions:
            if any(value in region for value in search_values):
                filtered_regions.append(region)
        if not filtered_regions:
            filtered_regions = regions
        filtered_regions = list(set(filtered_regions))
        queryset = [{"value": region} for region in filtered_regions]
        paginator = ResourceTypeViewPaginator()
        paginated_queryset = paginator.paginate_queryset(queryset, request)
        serializer = ResourceTypeSerializer(paginated_queryset, many=True)
        return paginator.get_paginated_response(serializer.data)
