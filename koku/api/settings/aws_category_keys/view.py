#
# Copyright 2023 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
import logging

from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import generics
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from api.common.pagination import ListPaginator
from api.common.permissions.settings_access import SettingsAccessPermission
from api.provider.models import Provider
from api.settings.aws_category_keys.serializers import SettingsAWSCategoryKeyIDSerializer
from api.settings.aws_category_keys.serializers import SettingsAWSCategoryKeySerializer
from api.settings.utils import NonValidatedMultipleChoiceFilter
from api.settings.utils import SettingsFilter
from koku.cache import invalidate_view_cache_for_tenant_and_source_type
from reporting.provider.aws.models import AWSEnabledCategoryKeys

LOG = logging.getLogger(__name__)


class SettingsAWSCategoryFilter(SettingsFilter):
    key = NonValidatedMultipleChoiceFilter(lookup_expr="icontains")

    class Meta:
        model = AWSEnabledCategoryKeys
        fields = ("enabled", "uuid")
        default_ordering = ["key", "-enabled"]


class SettingsAWSCategoryKeyView(generics.GenericAPIView):
    queryset = AWSEnabledCategoryKeys.objects.all()
    serializer_class = SettingsAWSCategoryKeySerializer
    permission_classes = [SettingsAccessPermission]
    filter_backends = (DjangoFilterBackend,)
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
