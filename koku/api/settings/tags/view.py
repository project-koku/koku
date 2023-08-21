import logging

from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django_filters import ModelMultipleChoiceFilter
from django_filters import MultipleChoiceFilter
from django_filters.fields import MultipleChoiceField
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import generics
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from api.common.pagination import ListPaginator
from api.common.permissions.settings_access import SettingsAccessPermission
from api.settings.tags.serializers import SettingsTagIDSerializer
from api.settings.tags.serializers import SettingsTagSerializer
from api.settings.utils import SettingsFilter
from masu.config import Config
from reporting.provider.all.models import EnabledTagKeys

LOG = logging.getLogger(__name__)


class NonValidatingMultipleChoiceField(MultipleChoiceField):
    def validate(self, value):
        pass


class NonValidatedMultipleChoiceFilter(MultipleChoiceFilter):
    field_class = NonValidatingMultipleChoiceField


class SettingsTagFilter(SettingsFilter):
    key = NonValidatedMultipleChoiceFilter(lookup_expr="icontains")
    source_type = ModelMultipleChoiceFilter(
        to_field_name="provider_type",
        queryset=EnabledTagKeys.objects.all(),
    )

    class Meta:
        model = EnabledTagKeys
        fields = ("enabled", "uuid")
        default_ordering = ["provider_type", "-enabled"]
        translation: dict[str, str] = {
            "source_type": "provider_type",
        }


class SettingsTagView(generics.GenericAPIView):
    queryset = EnabledTagKeys.objects.all()
    serializer_class = SettingsTagSerializer
    permission_classes = [SettingsAccessPermission]
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
        if serializer.is_valid():
            if Config.ENABLED_TAG_LIMIT > 0:
                if self.enabled_tags_count >= Config.ENABLED_TAG_LIMIT:
                    return Response(
                        {
                            "error": (
                                f"Maximum number of enabled tags exceeded. There are {self.enabled_tags_count} "
                                f"tags enabled and the limit is {Config.ENABLED_TAG_LIMIT}."
                            )
                        },
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
