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
from api.provider.models import Provider
from api.report.constants import URL_ENCODED_SAFE
from api.settings.serializers import NonEmptyListSerializer
from api.utils import DateHelper
from masu.processor import is_customer_large
from masu.processor.tasks import OCP_QUEUE
from masu.processor.tasks import OCP_QUEUE_XL
from masu.processor.tasks import update_summary_tables
from reporting.provider.ocp.models import OpenshiftCostCategory

SETTINGS_GENERATORS = {"settings": Settings}

def _get_return_data(group_name: str="Platform") -> list:
    cost_category_obj = OpenshiftCostCategory.objects.get(name=group_name)
    namespaces = OCPCostSummaryByProjectP.objects.values(project_name=F("namespace")).annotate(
        default=Case(
            When(namespace__startswith="kube-", then=Value(True)),
            When(namespace__startswith="openshift-", then=Value(True)),
            When(namespace="Platform unallocated", then=Value(True)),
            When(cost_category_id=cost_category_obj.id, then=Value(False)),
            output_field=BooleanField(null=True),
        ),
        clusters=ArrayAgg(Coalesce("cluster_alias", "cluster_id"),  distinct=True),
        group=Case(
            When(namespace__startswith="kube-", then=Value(group_name, output_field=CharField())),
            When(namespace__startswith="openshift-", then=Value(group_name, output_field=CharField())),
            When(namespace="Platform unallocated", then=Value(group_name, output_field=CharField())),
            When(cost_category_id=cost_category_obj.id, then=Value(group_name, output_field=CharField())),
            output_field=CharField(),
        ),
    ).distinct()

    return list(namespaces)


class CostGroupsFilter:
    valid_fields = {"name", "kind", "project"}
    _default_platform_projects = frozenset(("kube-%", "openshift-%", "Platform unallocated"))

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

    def filter_data(self):
        result = _get_return_data()

#         for key, value in self.filter_params.items():
#             # FIXME: This needs to do a logical OR for multiple filters of the same field
#             result = [item for item in result if value.lower() in item.get(key, "")]
#
#         field, order = next(iter(self.order_by.items()))
#         reverse = order.lower().startswith("desc")
#
#         def _sort_key(value):
#             return value.get(field, "name")
#
#         result.sort(key=_sort_key, reverse=reverse)

        return result


class CostGroupsView(APIView):
    """View to manage custom cost groups

    Projects added will be considered part of the Platform cost group.

    Default projects may not be deleted.
    """

    permission_classes = (SettingsAccessPermission,)
    filter_class = CostGroupsFilter
    _date_helper = DateHelper()

    @property
    def _platform_record(self):
        return OpenshiftCostCategory.objects.get(name="Platform")

    @method_decorator(never_cache)
    def get(self, request):
        filter_class = self.filter_class(request)
        data = filter_class.filter_data()
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

        self._summarize_current_month(request)

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

        self._summarize_current_month(request)

        paginator = ListPaginator(filter_class.filter_data(platform_record.namespace), request)

        return paginator.paginated_response

    def _summarize_current_month(self, request):
        """Resummarize OCP data for the current month"""

        ocp_queue = OCP_QUEUE
        schema_name = request.user.customer.schema_name
        provider_type = Provider.PROVIDER_OCP
        if is_customer_large(schema_name):
            ocp_queue = OCP_QUEUE_XL

        providers = Provider.objects.filter(
            type=provider_type,
            customer_id=request.user.customer.id,
        )

        async_ids = []
        for provider in providers:
            async_result = update_summary_tables.s(
                schema_name,
                provider_type=provider_type,
                provider_uuid=str(provider.uuid),
                start_date=self._date_helper.this_month_start,
            ).apply_async(queue=ocp_queue)

            async_ids.append(str(async_result))

        return async_ids
