import logging

import django_filters
from django.db.models import QuerySet
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from querystring_parser import parser
from rest_framework import generics
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from api.common.pagination import ListPaginator
from api.common.permissions.settings_access import SettingsAccessPermission
from api.report.constants import URL_ENCODED_SAFE
from api.settings.tags.serializers import SettingsTagIDSerializer
from api.settings.tags.serializers import SettingsTagSerializer
from masu.config import Config
from reporting.provider.all.models import EnabledTagKeys

LOG = logging.getLogger(__name__)


class SettingsTagFilter(django_filters.rest_framework.FilterSet):
    key = django_filters.CharFilter(lookup_expr="icontains")

    class Meta:
        model = EnabledTagKeys
        fields = ("uuid", "enabled", "provider_type")

    def filter_queryset(self, queryset: QuerySet) -> QuerySet:
        if self.request:
            query_params = parser.parse(self.request.query_params.urlencode(safe=URL_ENCODED_SAFE))
            filter = query_params.get("filter", {})
            order_by = query_params.get("order_by", "provider_type")
            # Use the filter parameters from the request for filtering
            self.form.cleaned_data.update(filter)

        # FIXME: Need to account for order_by when there is no request
        return super().filter_queryset(queryset).order_by(order_by)


class SettingsTagView(generics.GenericAPIView):
    queryset = EnabledTagKeys.objects.all()
    permission_classes = [SettingsAccessPermission]
    filter_backends = (django_filters.rest_framework.DjangoFilterBackend,)
    filterset_class = SettingsTagFilter

    @method_decorator(never_cache)
    def get(self, request: Request, **kwargs):
        filtered_qset = self.filter_queryset(self.get_queryset())
        serializer = SettingsTagSerializer(filtered_qset, many=True)

        paginator = ListPaginator(serializer.data, request)
        paginated_data = paginator.paginate_queryset(serializer.data, request)

        return paginator.get_paginated_response(paginated_data)


class SettingsTagUpdateView(APIView):
    permission_classes = [SettingsAccessPermission]

    def put(self, request: Request, **kwargs) -> Response:
        uuid_list = request.data.get("ids", [])
        serializer = SettingsTagIDSerializer(data={"id_list": uuid_list})
        if serializer.is_valid(raise_exception=True):
            if self.enabled_tags_count > Config.ENABLED_TAG_LIMIT:
                return Response(
                    f"Maximum number of enabled tags exceeded. There are {self.enabled_tags_count} "
                    f"tags enabled and the limit is {Config.ENABLED_TAG_LIMIT}.",
                    status=status.HTTP_400_BAD_REQUEST,
                )

            data = EnabledTagKeys.objects.filter(uuid__in=uuid_list)
            data.update(enabled=self.enabled)
            EnabledTagKeys.objects.bulk_update(data, ["enabled"])

            return Response(status=status.HTTP_204_NO_CONTENT)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class SettingsEnableTagView(SettingsTagUpdateView):
    enabled = True

    @property
    def enabled_tags_count(self):
        return EnabledTagKeys.objects.filter(enabled=True).count()


class SettingsDisableTagView(SettingsTagUpdateView):
    enabled = False
    enabled_tags_count = -1
