#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View for AWS organizational units."""
from django.db.models import F
from django.utils.decorators import method_decorator
from django.views.decorators.vary import vary_on_headers
from rest_framework import filters
from rest_framework import generics

from api.common import CACHE_RH_IDENTITY_HEADER
from api.common.permissions.aws_access import AWSOUAccessPermission
from api.resource_types.serializers import ResourceTypeSerializer
from reporting.provider.aws.models import AWSOrganizationalUnit


class AWSOrganizationalUnitView(generics.ListAPIView):
    """API GET list view for AWS organizational units."""

    queryset = (
        AWSOrganizationalUnit.objects.filter(deleted_timestamp__isnull=True)
        .annotate(**{"value": F("org_unit_id")})
        .values("value")
        .distinct()
    )
    serializer_class = ResourceTypeSerializer
    permission_classes = [AWSOUAccessPermission]
    filter_backends = [filters.OrderingFilter, filters.SearchFilter]
    ordering = ["value"]
    search_fields = ["$value"]

    @method_decorator(vary_on_headers(CACHE_RH_IDENTITY_HEADER))
    def list(self, request):
        # Reads the users values for org unit id and displays values related to what the user has access to
        user_access = []
        if request.user.admin:
            return super().list(request)
        elif request.user.access:
            user_access = request.user.access.get("aws.organizational_unit", {}).get("read", [])
        self.queryset = self.queryset.values("value").filter(org_unit_id__in=user_access)
        return super().list(request)
