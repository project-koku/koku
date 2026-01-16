#
# Copyright 2024 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View for AWS EC2 operating systems."""
from django.conf import settings
from django.db.models import F
from django.utils.decorators import method_decorator
from django.views.decorators.vary import vary_on_headers
from rest_framework import filters
from rest_framework import generics
from rest_framework import status
from rest_framework.response import Response

from api.common import CACHE_RH_IDENTITY_HEADER
from api.common.filters import SearchFilterResourceTypes
from api.common.pagination import ResourceTypeViewPaginator
from api.common.permissions.aws_access import AwsAccessPermission
from api.resource_types.serializers import ResourceTypeSerializer
from reporting.provider.aws.models import AWSCostEntryLineItemSummaryByEC2ComputeP


class AWSEC2ComputeOperatingSystemView(generics.ListAPIView):
    """API GET list view for AWS EC2 compute operating systems."""

    queryset = (
        AWSCostEntryLineItemSummaryByEC2ComputeP.objects.annotate(value=F("operating_system"))
        .values("value")
        .distinct()
        .filter(operating_system__isnull=False)
    )

    serializer_class = ResourceTypeSerializer
    permission_classes = [AwsAccessPermission]
    filter_backends = [filters.OrderingFilter, SearchFilterResourceTypes]
    ordering = ["value"]
    search_fields = ["value"]
    pagination_class = ResourceTypeViewPaginator

    @method_decorator(vary_on_headers(CACHE_RH_IDENTITY_HEADER))
    def list(self, request):
        # Reads the aws ec2 compute instance info and displays values related to what the user has access to.
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
