#
# Copyright 2023 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View for AWS category resource types."""
import logging

from django.conf import settings
from django.core.exceptions import PermissionDenied
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
from api.query_filter import QueryFilter
from api.query_filter import QueryFilterCollection
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
    pagination_class = ResourceTypeViewPaginator
    serializer_class = AWSCategorySerializer

    FILTER_MAP = {
        "key": {"field": "key", "operation": "icontains", "composition_key": "key_filter"},
        "value": {"field": "values", "operation": "icontains", "composition_key": "value_filter"},
        "account": [
            {
                "field": "account_alias__account_alias",
                "operation": "icontains",
                "composition_key": "account_filter",
            },
            {"field": "usage_account_id", "operation": "icontains", "composition_key": "account_filter"},
        ],
    }
    SUPPORTED_FILTERS = ["limit"] + list(FILTER_MAP.keys())

    def check_user_access(self):
        """
        Checks to see if we need to filter the account access.
        """
        account_filter = self.request.query_params.get("account")
        if not isinstance(account_filter, list):
            account_filter = [account_filter]
        if settings.ENHANCED_ORG_ADMIN and self.request.user.admin:
            return account_filter
        elif self.request.user.access:
            user_access = self.request.user.access.get("aws.account", {}).get("read", [])

        if user_access and user_access[0] == "*":
            return account_filter
        if user_access and account_filter:
            for account in account_filter:
                if account not in user_access:
                    LOG.warning(
                        "User does not have permissions for the requested params: %s. Current access: %s.",
                        account,
                        user_access,
                    )
                    raise PermissionDenied()
        return user_access

    def build_filters(self):
        """Builds the query filters"""
        filters = QueryFilterCollection()
        accounts = self.check_user_access()
        if accounts:
            for filter in self.FILTER_MAP.get("account"):
                account_filter = QueryFilter(parameter=accounts, **filter)
                filters.add(account_filter)
        for key, value in self.request.query_params.items():
            if key in ["account", "limit"]:
                # we set account separately
                continue
            filter_kwargs = self.FILTER_MAP.get(key)
            query_filter = QueryFilter(parameter=value, **filter_kwargs)
            filters.add(query_filter)
        return filters.compose()

    @method_decorator(vary_on_headers(CACHE_RH_IDENTITY_HEADER))
    def list(self, request):
        error_message = {}
        # # Test for only supported query_params
        if self.request.query_params:
            for key in self.request.query_params:
                if key not in self.SUPPORTED_FILTERS:
                    error_message[key] = [{"Unsupported parameter"}]
                    return Response(error_message, status=status.HTTP_400_BAD_REQUEST)
        filters = self.build_filters()
        if filters:
            self.queryset = self.queryset.filter(filters)
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
