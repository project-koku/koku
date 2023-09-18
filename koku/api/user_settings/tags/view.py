import logging
import typing as t

from django.db.models.query import QuerySet
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django_filters import ModelMultipleChoiceFilter
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import generics
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from api.common.pagination import ListPaginator
from api.common.permissions.settings_access import SettingsAccessPermission
from api.user_settings.tags.serializers import SettingsTagIDSerializer
from api.user_settings.tags.serializers import SettingsTagSerializer
from api.user_settings.utils import NonValidatedMultipleChoiceFilter
from api.user_settings.utils import SettingsFilter
from masu.config import Config
from reporting.provider.all.models import EnabledTagKeys

ENABLED_TAG_KEYS_QS = EnabledTagKeys.objects.all()
LOG = logging.getLogger(__name__)


class SettingsTagFilter(SettingsFilter):
    key = NonValidatedMultipleChoiceFilter(lookup_expr="icontains")
    uuid = ModelMultipleChoiceFilter(to_field_name="uuid", queryset=ENABLED_TAG_KEYS_QS)
    provider_type = ModelMultipleChoiceFilter(to_field_name="provider_type", queryset=ENABLED_TAG_KEYS_QS)
    source_type = ModelMultipleChoiceFilter(
        field_name="provider_type",
        to_field_name="provider_type",
        queryset=ENABLED_TAG_KEYS_QS,
    )

    class Meta:
        model = EnabledTagKeys
        fields = ("enabled",)
        default_ordering = ["provider_type", "-enabled"]


class SettingsTagView(generics.GenericAPIView):
    queryset = EnabledTagKeys.objects.all()
    serializer_class = SettingsTagSerializer
    permission_classes = (SettingsAccessPermission,)
    filter_backends = (DjangoFilterBackend,)
    filterset_class = SettingsTagFilter

    @method_decorator(never_cache)
    def get(self, request: Request, **kwargs):
        filtered_qset = self.filter_queryset(self.get_queryset())
        serializer = self.serializer_class(filtered_qset, many=True)

        paginator = ListPaginator(serializer.data, request)
        paginated_data = paginator.paginate_queryset(serializer.data, request)

        return paginator.get_paginated_response(paginated_data)


class SettingsTagUpdateView(APIView):
    permission_classes = [SettingsAccessPermission]

    def put(self, request: Request, **kwargs) -> Response:
        uuid_list = request.data.get("ids", [])
        serializer = SettingsTagIDSerializer(data={"id_list": uuid_list})
        serializer.is_valid(raise_exception=True)

        objects = EnabledTagKeys.objects.filter(uuid__in=uuid_list)
        if response := self._check_limit(objects):
            return response

        objects.update(enabled=self.enabled)
        EnabledTagKeys.objects.bulk_update(objects, ["enabled"])

        return Response(status=status.HTTP_204_NO_CONTENT)


class SettingsEnableTagView(SettingsTagUpdateView):
    enabled = True

    def _check_limit(self, qs: QuerySet) -> t.Optional[Response]:
        if Config.ENABLED_TAG_LIMIT > 0:
            # Only count UUIDs requested to be enabled that are currently disabled.
            records_to_update_count = qs.filter(enabled=False).count()
            future_enabled_tags_count = self.enabled_tags_count + records_to_update_count
            if future_enabled_tags_count > Config.ENABLED_TAG_LIMIT:
                return Response(
                    {
                        "error": f"The maximum number of enabled tags is {Config.ENABLED_TAG_LIMIT}.",
                        "enabled": self.enabled_tags_count,
                        "limit": Config.ENABLED_TAG_LIMIT,
                    },
                    status=status.HTTP_412_PRECONDITION_FAILED,
                )

    @property
    def enabled_tags_count(self):
        return EnabledTagKeys.objects.filter(enabled=True).count()


class SettingsDisableTagView(SettingsTagUpdateView):
    enabled = False

    def _check_limit(self, qs):
        pass
