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
    RBAC_FILTER = {"field": "usage_account_id", "operation": "in", "composition_key": "account_filter"}

    def check_user_access(self):
        """
        Checks to see if we need to filter the account access.

        Always returns a QueryFilterCollection
        """

        def build_query_collection(check_user_access=None):
            """Creates a query_filter of the account."""
            query_collection = QueryFilterCollection()
            if account_param := self.request.query_params.get("account"):
                if check_user_access and account_param not in check_user_access:
                    # ensure the user has access to the filtered value
                    LOG.warning(
                        "User does not have permissions for the requested params: %s. Current access: %s.",
                        account_param,
                        check_user_access,
                    )
                    raise PermissionDenied()
                for filter in self.FILTER_MAP.get("account"):
                    account_filter = QueryFilter(parameter=account_param, **filter)
                    query_collection.add(account_filter)
            elif check_user_access:  # default to user access kwargs
                # use the account filter if passed in instead of deault RBAC.
                access_filter = QueryFilter(parameter=check_user_access, **self.RBAC_FILTER)
                query_collection.add(access_filter)
            return query_collection

        if settings.ENHANCED_ORG_ADMIN and self.request.user.admin:
            return build_query_collection()
        elif self.request.user.access:
            check_user_access = self.request.user.access.get("aws.account", {}).get("read", [])
            if check_user_access and check_user_access[0] != "*":
                return build_query_collection(check_user_access)
        return build_query_collection()

    def build_filters(self):
        """Builds the query filters"""
        filters = self.check_user_access()
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
