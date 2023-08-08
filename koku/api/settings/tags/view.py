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
    key = django_filters.MultipleChoiceFilter(lookup_expr="icontains")
    provider_type = django_filters.ModelMultipleChoiceFilter(queryset=EnabledTagKeys.objects.all())

    class Meta:
        model = EnabledTagKeys
        fields = ("enabled", "uuid")

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

        return ["provider_type", "-enabled"]

    def filter_queryset(self, queryset: QuerySet) -> QuerySet:
        order_by = self._get_order_by()

        if self.request:
            query_params = parser.parse(self.request.query_params.urlencode(safe=URL_ENCODED_SAFE))
            filter_params = query_params.get("filter", {})

            # Multiple choice filter fields need to be a list. If only one filter
            # is provided, it will be a string.
            for field in ("key", "provider_type"):
                if isinstance(filter_params.get(field), str):
                    filter_params[field] = [filter_params[field]]

            # Use the filter parameters from the request for filtering.
            #
            # The default behavior is to use the URL params directly for filtering.
            # Since our APIs expect filters to be in the filter dict, extract those
            # values and merge them with cleaned_data which is used for filtering.
            self.form.cleaned_data.update(filter_params)

            order_by = self._get_order_by(query_params.get("order_by"))

        return super().filter_queryset(queryset).order_by(*order_by)


class SettingsTagView(generics.GenericAPIView):
    queryset = EnabledTagKeys.objects.all()
    serializer_class = SettingsTagSerializer
    permission_classes = [SettingsAccessPermission]
    filter_backends = (django_filters.rest_framework.DjangoFilterBackend,)
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
