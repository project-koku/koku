#
# Copyright 2023 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import ValidationError
from rest_framework.views import APIView

from api.common.pagination import ListPaginator
from api.common.permissions.settings_access import SettingsAccessPermission
from api.provider.models import Provider
from api.query_params import QueryParameters
from api.settings.cost_groups.query_handler import CostGroupsQueryHandler
from api.settings.cost_groups.query_handler import delete_openshift_namespaces
from api.settings.cost_groups.query_handler import put_openshift_namespaces
from api.settings.cost_groups.serializers import CostGroupProjectSerializer
from api.settings.cost_groups.serializers import CostGroupQueryParamSerializer
from api.utils import DateHelper
from common.queues import get_customer_queue
from common.queues import OCPQueue
from masu.processor.tasks import update_summary_tables
from reporting.provider.ocp.models import OCPProject


class CostGroupsView(APIView):
    """View to manage custom cost groups

    Projects added will be considered part of the Platform cost group.

    Default projects may not be deleted.
    """

    permission_classes = (SettingsAccessPermission,)
    _date_helper = DateHelper()
    serializer = CostGroupQueryParamSerializer
    tag_providers: list[str] = []
    query_handler = CostGroupsQueryHandler
    report = "cost_group"

    @method_decorator(never_cache)
    def get(self, request: Request, **kwargs) -> Response:
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

    def _summarize_current_month(self, schema_name: str, projects: list[dict[str, str]]) -> list[str]:
        """Resummarize OCP data for the current month."""
        projects_to_summarize = [proj["project"] for proj in projects]
        ocp_queue = get_customer_queue(schema_name, OCPQueue)

        provider_uuids = (
            OCPProject.objects.filter(project__in=projects_to_summarize)
            .values_list("cluster__provider__uuid", flat=True)
            .distinct()
        )
        async_ids = []
        for provider_uuid in provider_uuids:
            async_result = update_summary_tables.s(
                schema_name,
                provider_type=Provider.PROVIDER_OCP,
                provider_uuid=provider_uuid,
                start_date=self._date_helper.this_month_start,
            ).apply_async(queue=ocp_queue)
            async_ids.append(str(async_result))

        return async_ids


class CostGroupsAddView(CostGroupsView):
    def put(self, request: Request) -> Response:
        serializer = CostGroupProjectSerializer(data=request.data, many=True)
        serializer.is_valid(raise_exception=True)

        projects = put_openshift_namespaces(serializer.validated_data)
        self._summarize_current_month(request.user.customer.schema_name, projects)

        return Response(status=status.HTTP_204_NO_CONTENT)


class CostGroupsRemoveView(CostGroupsView):
    def put(self, request: Request) -> Response:
        serializer = CostGroupProjectSerializer(data=request.data, many=True)
        serializer.is_valid(raise_exception=True)

        projects = delete_openshift_namespaces(serializer.validated_data)
        self._summarize_current_month(request.user.customer.schema_name, projects)

        return Response(status=status.HTTP_204_NO_CONTENT)
