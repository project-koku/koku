#
# Copyright 2023 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
import logging

from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from querystring_parser import parser
from rest_framework import generics
from rest_framework import status
from rest_framework.response import Response
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


class SettingsAWSCategoryKeyView(generics.GenericAPIView):
    queryset = AWSEnabledCategoryKeys.objects.all()
    permission_classes = [SettingsAccessPermission]
    default_order = {"key": "asc"}
    order_map = {"asc": "", "desc": "-"}

    @method_decorator(never_cache)
    def get(self, request, **kwargs):
        qset = self.get_queryset()
        query_filter = parser.parse(request.GET.urlencode(safe=URL_ENCODED_SAFE))
        filtered_qset = self.filter_queryset(qset, query_filter)
        ordered_qset = self.order_queryset(filtered_qset, query_filter)
        serializer = SettingsAWSCategoryKeySerializer(ordered_qset, many=True)
        paginator = ListPaginator(serializer.data, request)
        paginated_data = paginator.paginate_queryset(serializer.data, request)
        return paginator.get_paginated_response(paginated_data)

    def filter_queryset(self, queryset, q_params):
        filters_dict = q_params.get("filter", {})
        for key, value in filters_dict.items():
            key += "__icontains"
            queryset = queryset.filter(**{key: value})
        return queryset

    def order_queryset(self, queryset, q_params):
        order_dict = q_params.get("order_by", self.default_order)
        order_keys = []
        for key, direction in order_dict.items():
            order_key = f"{self.order_map[direction]}{key}"
            order_keys.append(order_key)
        return queryset.order_by(*order_keys)


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
