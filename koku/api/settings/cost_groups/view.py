#
# Copyright 2023 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from rest_framework import status
from rest_framework.response import Response
from rest_framework.serializers import ValidationError
from rest_framework.views import APIView

from api.common.pagination import ListPaginator
from api.common.permissions.settings_access import SettingsAccessPermission
from api.deprecated_settings.settings import Settings
from api.provider.models import Provider
from api.query_params import QueryParameters
from api.settings.cost_groups.query_handler import CostGroupsQueryHandler
from api.settings.cost_groups.serializers import CostGroupQueryParamSerializer
from api.settings.serializers import NonEmptyListSerializer
from api.utils import DateHelper
from masu.processor import is_customer_large
from masu.processor.tasks import OCP_QUEUE
from masu.processor.tasks import OCP_QUEUE_XL
from masu.processor.tasks import update_summary_tables

SETTINGS_GENERATORS = {"settings": Settings}


class CostGroupsView(APIView):
    """View to manage custom cost groups

    Projects added will be considered part of the Platform cost group.

    Default projects may not be deleted.
    """

    permission_classes = (SettingsAccessPermission,)
    _date_helper = DateHelper()
    serializer = CostGroupQueryParamSerializer
    tag_providers = []
    query_handler = CostGroupsQueryHandler

    @method_decorator(never_cache)
    def get(self, request, **kwargs):
        """Get Report Data.

        This method is responsible for passing request data to the reporting APIs.

        Args:
            request (Request): The HTTP request object

        Returns:
            (Response): The report in a Response object

        """

        try:
            params = QueryParameters(request=request, caller=self, **kwargs)
        except ValidationError as exc:
            return Response(data=exc.detail, status=status.HTTP_400_BAD_REQUEST)
        handler = self.query_handler(params)
        output = handler.execute_query()
        paginator = ListPaginator(output, request)
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
