#
# Copyright 2023 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
import logging
import typing as t

import django_filters
from django.db.models import QuerySet
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from querystring_parser import parser
from rest_framework import generics
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import ValidationError
from rest_framework.views import APIView

from api.common.pagination import ListPaginator
from api.common.permissions.settings_access import SettingsAccessPermission
from api.provider.models import Provider
from api.report.constants import URL_ENCODED_SAFE
from api.settings.aws_category_keys.serializers import SettingsAWSCategoryKeyIDSerializer
from api.settings.aws_category_keys.serializers import SettingsAWSCategoryKeySerializer
from koku.cache import invalidate_view_cache_for_tenant_and_source_type
from reporting.provider.aws.models import AWSEnabledCategoryKeys

LOG = logging.getLogger(__name__)


class SettingsFilter(django_filters.rest_framework.FilterSet):
    def _get_order_by(self, order_by_params: t.Union[str, dict[str, str], None] = None) -> list[str]:
        # If only one order_by parameter was given, it is a string.
        # Ensure it is a list of values.
        if isinstance(order_by_params, str):
            return [order_by_params]

        # Support order_by[field]=desc
        if isinstance(order_by_params, dict):
            result = set()
            for field, order in order_by_params.items():
                try:
                    # If a field is provided more than once, take the first sorting parameter
                    order = order.pop(0)
                except AttributeError:
                    # Already a str
                    pass

                # Technically we accept "asc" and "desc". Only testing for "desc" to make
                # the API more resilient.
                prefix = "-" if order.lower().startswith("desc") else ""
                result.add(f"{prefix}{field}")

            return list(result)

        return ["key", "-enabled"]

    def filter_queryset(self, queryset: QuerySet) -> QuerySet:
        order_by = self._get_order_by()

        if self.request:
            query_params = parser.parse(self.request.query_params.urlencode(safe=URL_ENCODED_SAFE))
            filter_params = query_params.get("filter", {})

            # Check valid keys
            invalid_params = set(filter_params).difference(set(self.base_filters))
            if invalid_params:
                raise ValidationError({invalid_params.pop(): "Unsupported parameter or invalid value"})

            # Multiple choice filter fields need to be a list. If only one filter
            # is provided, it will be a string.
            for field in self.base_filters:
                if isinstance(filter_params.get(field), str) and isinstance(
                    self.base_filters.get(field), django_filters.MultipleChoiceFilter
                ):
                    filter_params[field] = [filter_params[field]]

            # Use the filter parameters from the request for filtering.
            #
            # The default behavior is to use the URL params directly for filtering.
            # Since our APIs expect filters to be in the filter dict, extract those
            # values and merge them with cleaned_data which is used for filtering.
            self.form.cleaned_data.update(filter_params)

            order_by = self._get_order_by(query_params.get("order_by"))

        return super().filter_queryset(queryset).order_by(*order_by)


class SettingsAWSCategoryFilter(SettingsFilter):
    key = django_filters.MultipleChoiceFilter(lookup_expr="icontains")

    class Meta:
        model = AWSEnabledCategoryKeys
        fields = ("enabled", "uuid")


class SettingsAWSCategoryKeyView(generics.GenericAPIView):
    queryset = AWSEnabledCategoryKeys.objects.all()
    serializer_class = SettingsAWSCategoryKeySerializer
    permission_classes = [SettingsAccessPermission]
    filter_backends = (django_filters.rest_framework.DjangoFilterBackend,)
    filterset_class = SettingsAWSCategoryFilter

    @method_decorator(never_cache)
    def get(self, request: Request, **kwargs):
        filtered_qset = self.filter_queryset(self.get_queryset())
        serializer = self.serializer_class(filtered_qset, many=True)
        paginator = ListPaginator(serializer.data, request)
        paginated_data = paginator.paginate_queryset(serializer.data, request)
        return paginator.get_paginated_response(paginated_data)


class SettingsAWSCategoryKeyUpdateView(APIView):
    permission_classes = [SettingsAccessPermission]

    def put(self, request, **kwargs):
        uuid_list = request.data.get("ids", [])
        serializer = SettingsAWSCategoryKeyIDSerializer(data={"id_list": uuid_list})
        if serializer.is_valid(raise_exception=True):
            data = AWSEnabledCategoryKeys.objects.filter(uuid__in=uuid_list)
            data.update(enabled=self.enabled)
            AWSEnabledCategoryKeys.objects.bulk_update(data, ["enabled"])
            schema_name = self.request.user.customer.schema_name
            invalidate_view_cache_for_tenant_and_source_type(schema_name, Provider.PROVIDER_AWS)
            return Response(status=status.HTTP_204_NO_CONTENT)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class SettingsEnableAWSCategoryKeyView(SettingsAWSCategoryKeyUpdateView):
    enabled = True


class SettingsDisableAWSCategoryKeyView(SettingsAWSCategoryKeyUpdateView):
    enabled = False
