#
# Copyright 2023 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from querystring_parser import parser
from rest_framework.views import APIView

from api.common.pagination import ListPaginator
from api.common.permissions.settings_access import SettingsAccessPermission
from api.deprecated_settings.settings import Settings
from api.report.constants import URL_ENCODED_SAFE
from api.settings.serializers import NonEmptyListSerializer
from reporting.provider.ocp.models import OpenshiftCostCategory

SETTINGS_GENERATORS = {"settings": Settings}


class PlatformFilter:
    valid_fields = {"name", "kind", "project"}
    _default_platform_projects = ("kube-%", "openshift-%", "Platform unallocated")

    def __init__(self, request):
        self.request = request
        self._order_by = None
        self._filter_params = None
        self._query_params = None

    @property
    def query_params(self):
        if self._query_params is None:
            self._query_params = parser.parse(self.request.query_params.urlencode(safe=URL_ENCODED_SAFE))

        return self._query_params

    @property
    def order_by(self):
        if self._order_by is None:
            self._order_by = self.query_params.get("order_by", {"name": "asc"})

        return self._order_by

    @property
    def filter_params(self):
        if self._filter_params is None:
            self._filter_params = self.query_params.get("filter", {})

        return self._filter_params

    def filter_data(self, data):
        result = []
        for item in data:
            group = "default" if item in self._default_platform_projects else "platform"
            result.append({"group": group, "name": item})

        for key, value in self.filter_params.items():
            # FIXME: This needs to do a logical OR for multiple filters of the same field
            result = [item for item in result if value.lower() in item.get(key, "")]

        field, order = next(iter(self.order_by.items()))
        reverse = order.lower().startswith("desc")

        def _sort_key(value):
            return value.get(field, "name")

        result.sort(key=_sort_key, reverse=reverse)

        return result


class PlatformCategoriesView(APIView):
    """View to manage platform categories

    Projects added will be considered part of the platform cost.
    Default projects may not be deleted.
    """

    permission_classes = (SettingsAccessPermission,)
    filter_class = PlatformFilter

    @property
    def _platform_record(self):
        return OpenshiftCostCategory.objects.get(name="Platform")

    @method_decorator(never_cache)
    def get(self, request):
        filter_class = self.filter_class(request)
        data = filter_class.filter_data(self._platform_record.namespace)
        paginator = ListPaginator(data, request)

        return paginator.paginated_response

    def put(self, request):
        serializer = NonEmptyListSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        filter_class = self.filter_class(request)

        projects = serializer.validated_data["projects"]
        platform_record = self._platform_record
        platform_record.namespace = list(set(platform_record.namespace).union(projects))
        platform_record.save()

        paginator = ListPaginator(filter_class.filter_data(platform_record.namespace), request)

        return paginator.paginated_response

    def delete(self, request):
        serializer = NonEmptyListSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        filter_class = self.filter_class(request)

        projects = serializer.validated_data["projects"]
        request_without_defaults = set(projects).difference(self.filter_class._default_platform_projects)
        platform_record = self._platform_record
        platform_record.namespace = list(set(platform_record.namespace).difference(request_without_defaults))
        platform_record.save()

        paginator = ListPaginator(filter_class.filter_data(platform_record.namespace), request)

        return paginator.paginated_response
