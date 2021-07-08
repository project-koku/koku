#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View for AWS accounts."""
from django.db.models import F
from django.db.models.functions import Coalesce
from django.utils.decorators import method_decorator
from django.views.decorators.vary import vary_on_headers
from rest_framework import filters
from rest_framework import generics

from api.common import CACHE_RH_IDENTITY_HEADER
from api.common.permissions.openshift_access import OpenShiftAccessPermission
from api.common.permissions.resource_type_access import ResourceTypeAccessPermission
from api.resource_types.serializers import ResourceTypeSerializer
from reporting.provider.aws.models import AWSCostSummaryByAccount
from reporting.provider.aws.openshift.models import OCPAWSCostSummaryByAccount


class AWSAccountView(generics.ListAPIView):
    """API GET list view for AWS accounts."""

    queryset = (
        AWSCostSummaryByAccount.objects.annotate(
            **(
                {
                    "value": F("usage_account_id"),
                    "alias": Coalesce(F("account_alias__account_alias"), "usage_account_id"),
                }
            )
        )
        .values("value", "alias")
        .distinct()
    )

    serializer_class = ResourceTypeSerializer
    permission_classes = [ResourceTypeAccessPermission, OpenShiftAccessPermission]
    filter_backends = [filters.OrderingFilter, filters.SearchFilter]
    ordering = ["value", "alias"]
    search_fields = ["$value", "$alias"]

    @method_decorator(vary_on_headers(CACHE_RH_IDENTITY_HEADER))
    def list(self, request):
        openshift = self.request.query_params.get("openshift")
        if openshift:
            self.queryset = (
                OCPAWSCostSummaryByAccount.objects.annotate(
                    **{"value": F("usage_account_id"), "alias": F("account_alias__account_alias")}
                )
                .values("value", "alias")
                .distinct()
            )
        return super().list(request)


# filter(usage_account_id__in=user_access)
