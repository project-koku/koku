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
from api.resource_types.aws_category.serializers import AWSCategoryKeyOnlySerializer
from api.resource_types.aws_category.serializers import AWSCategorySerializer
from reporting.provider.aws.models import AWSCategorySummary
from reporting.provider.aws.models import AWSEnabledCategoryKeys
from reporting.provider.aws.openshift.models import OCPAWSCategorySummary

LOG = logging.getLogger(__name__)


class AWSCategoryView(generics.ListAPIView):
    """
    Get a list of category key value pairs.

    Note:
        Although, this class lives in the resource_types directory
        it has not been added to the ResourceTypeView.
        This class is solely for type ahead functionality, and
        will differ from the other views due to needing to return
        key value pairs. It is modeled after the Tags endpoint
        instead.
    """

    permission_classes = [
        AwsAccessPermission,
    ]
    # Note: Unnesting to remove duplicate values
    annotations = {
        "unnested_value": Func(F("values"), function="unnest"),
        "enabled": Exists(AWSEnabledCategoryKeys.objects.filter(key=OuterRef("key")).filter(enabled=True)),
    }
    pagination_class = ResourceTypeViewPaginator

    FILTER_MAP = {
        "search": {"field": "key", "operation": "icontains", "composition_key": "key_filter"},
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
    KEY_ONLY_PARAM = "key_only"
    OPENSHIFT_PARAM = "openshift"
    SUPPORTED_FILTERS = ["limit", KEY_ONLY_PARAM, OPENSHIFT_PARAM] + list(FILTER_MAP.keys())
    RBAC_FILTER = {"field": "usage_account_id", "operation": "in", "composition_key": "account_filter"}

    @property
    def key_only_check(self):
        """
        Check to switch to key only queryset
        """
        if key_only := self.request.query_params.get(self.KEY_ONLY_PARAM):
            if key_only.lower() == "true":
                return True
        return False

    @property
    def openshift_check(self):
        """
        Check if openshift filter is requested
        """
        if openshift := self.request.query_params.get(self.OPENSHIFT_PARAM):
            if openshift.lower() == "true":
                return True
        return False

    def get_serializer_class(self):
        """Decide which serializer class to use."""
        return AWSCategoryKeyOnlySerializer if self.key_only_check else AWSCategorySerializer

    def build_query_collection(self, check_user_access=None):
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

    def build_filters(self):
        """Builds the query filters"""
        check_user_access = False
        if not (settings.ENHANCED_ORG_ADMIN and self.request.user.admin):
            read_access_list = self.request.user.access.get("aws.account", {}).get("read")
            if "*" not in read_access_list:
                # only check if the aws.account.read != *
                check_user_access = read_access_list

        filters = self.build_query_collection(check_user_access)

        for key, value in self.request.query_params.items():
            if key == "account":
                # account filter is handle when we build the query collection
                # to check if they have rbac access to filter on the account
                continue
            if filter_kwargs := self.FILTER_MAP.get(key):
                query_filter = QueryFilter(parameter=value, **filter_kwargs)
                filters.add(query_filter)
        return filters.compose()

    def get_queryset(self):
        """Get the appropriate queryset based on openshift parameter."""
        if self.openshift_check:
            # Use OCPAWSCategorySummary when openshift=true
            return OCPAWSCategorySummary.objects.values("key").annotate(**self.annotations).distinct()
        # Default to AWSCategorySummary
        return AWSCategorySummary.objects.values("key").annotate(**self.annotations).distinct()

    @method_decorator(vary_on_headers(CACHE_RH_IDENTITY_HEADER))
    def list(self, request):
        error_message = {}
        # Set queryset based on openshift parameter
        self.queryset = self.get_queryset()

        if self.key_only_check:
            annotate = {
                "enabled": Exists(AWSEnabledCategoryKeys.objects.filter(key=OuterRef("key")).filter(enabled=True))
            }
            if self.openshift_check:
                self.queryset = (
                    OCPAWSCategorySummary.objects.values_list("key", flat=True)
                    .annotate(**annotate)
                    .filter(enabled=True)
                    .distinct()
                )
            else:
                self.queryset = (
                    AWSCategorySummary.objects.values_list("key", flat=True)
                    .annotate(**annotate)
                    .filter(enabled=True)
                    .distinct()
                )
            self.SUPPORTED_FILTERS = ["limit", self.KEY_ONLY_PARAM, self.OPENSHIFT_PARAM, "account"]
        # Check for only supported query_params
        if self.request.query_params:
            for key in self.request.query_params:
                if key not in self.SUPPORTED_FILTERS:
                    error_message[key] = [{"Unsupported parameter"}]
                    return Response(error_message, status=status.HTTP_400_BAD_REQUEST)
        filters = self.build_filters()
        if filters:
            self.queryset = self.queryset.filter(filters)
        return super().list(request)

    # Overwrite generics.ListAPIView paginate_queryset
    def paginate_queryset(self, queryset):
        """
        Return a single page of results, or `None` if pagination is disabled.
        """
        if self.key_only_check:
            return self.paginator.paginate_queryset(queryset, self.request, view=self)
        # combine unnested distinct values into a single array.
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
