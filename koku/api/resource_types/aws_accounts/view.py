#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View for AWS accounts."""
from django.db.models import F
from django.utils.decorators import method_decorator
from django.views.decorators.vary import vary_on_headers
from rest_framework import filters
from rest_framework import generics

from api.common import CACHE_RH_IDENTITY_HEADER
from api.common.permissions.aws_access import AwsAccessPermission
from api.resource_types.serializers import ResourceTypeSerializer
from reporting.provider.aws.models import AWSCostSummaryByAccount


class AWSAccountView(generics.ListAPIView):
    """API GET list view for AWS accounts."""

    queryset = AWSCostSummaryByAccount.objects.annotate(**{"value": F("usage_account_id")}).values("value").distinct()
    serializer_class = ResourceTypeSerializer
    permission_classes = [AwsAccessPermission]
    filter_backends = [filters.OrderingFilter, filters.SearchFilter]
    ordering = ["value"]
    search_fields = ["$value"]

    @method_decorator(vary_on_headers(CACHE_RH_IDENTITY_HEADER))
    def list(self, request):
        # Reads the users values for aws account and rand displays values related to what the user has access to
        if request.user.access:
            user_access = request.user.access.get("aws.account", {}).get("read", [])
        else:
            user_access = []
        self.queryset = self.queryset.values("value").filter(usage_account_id__in=user_access)
        return super().list(request)
