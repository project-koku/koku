#
# Copyright 2020 Red Hat, Inc.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
"""Forecast Views."""
import logging

from django.utils.decorators import method_decorator
from django.views.decorators.vary import vary_on_headers
from rest_framework import status
from rest_framework.response import Response
from rest_framework.serializers import ValidationError
from rest_framework.views import APIView

from api.common import CACHE_RH_IDENTITY_HEADER
from api.common.pagination import ListPaginator
from api.common.permissions import AwsAccessPermission
from api.common.permissions import AzureAccessPermission
from api.common.permissions import OpenShiftAccessPermission
from api.common.permissions.openshift_all_access import OpenshiftAllAccessPermission
from api.forecast.serializers import AWSCostForecastParamSerializer
from api.forecast.serializers import AzureCostForecastParamSerializer
from api.forecast.serializers import OCPAllCostForecastParamSerializer
from api.forecast.serializers import OCPAWSCostForecastParamSerializer
from api.forecast.serializers import OCPAzureCostForecastParamSerializer
from api.forecast.serializers import OCPCostForecastParamSerializer
from api.query_params import QueryParameters
from forecast import AWSForecast
from forecast import AzureForecast
from forecast import OCPAllForecast
from forecast import OCPAWSForecast
from forecast import OCPAzureForecast
from forecast import OCPForecast
from reporting.models import AzureTagsSummary
from reporting.models import OCPAWSTagsSummary
from reporting.models import OCPAzureTagsSummary
from reporting.models import OCPStorageVolumeLabelSummary
from reporting.models import OCPUsagePodLabelSummary
from reporting.provider.aws.models import AWSTagsSummary

LOG = logging.getLogger(__name__)


class ForecastView(APIView):
    """Base forecast view class."""

    report = "forecast"

    @method_decorator(vary_on_headers(CACHE_RH_IDENTITY_HEADER))
    def get(self, request, **kwargs):
        """Respond to GET requests."""
        LOG.debug(f"API: {request.path} USER: {request.user.username}")

        try:
            params = QueryParameters(request=request, caller=self, **kwargs)
        except ValidationError as exc:
            return Response(data=exc.detail, status=status.HTTP_400_BAD_REQUEST)

        handler = self.query_handler(params)
        output = handler.predict()
        LOG.debug(f"DATA: {output}")

        paginator = ListPaginator(output, request)
        paginated_result = paginator.paginate_queryset(output, request)
        return paginator.get_paginated_response(paginated_result)


class AWSCostForecastView(ForecastView):
    """AWS Cost Forecast View."""

    permission_classes = (AwsAccessPermission,)
    query_handler = AWSForecast
    serializer = AWSCostForecastParamSerializer
    tag_handler = [AWSTagsSummary]


class AzureCostForecastView(ForecastView):
    """Azure Cost Forecast View."""

    permission_classes = (AzureAccessPermission,)
    query_handler = AzureForecast
    serializer = AzureCostForecastParamSerializer
    tag_handler = [AzureTagsSummary]


class OCPCostForecastView(ForecastView):
    """OCP Cost Forecast View."""

    permission_classes = (OpenShiftAccessPermission,)
    query_handler = OCPForecast
    serializer = OCPCostForecastParamSerializer
    tag_handler = [OCPUsagePodLabelSummary, OCPStorageVolumeLabelSummary]


class OCPAWSCostForecastView(ForecastView):
    """OCP+AWS Cost Forecast View."""

    permission_classes = (AwsAccessPermission, OpenShiftAccessPermission)
    query_handler = OCPAWSForecast
    serializer = OCPAWSCostForecastParamSerializer
    tag_handler = [OCPAWSTagsSummary]


class OCPAzureCostForecastView(ForecastView):
    """OCP+Azure Cost Forecast View."""

    permission_classes = (AzureAccessPermission, OpenShiftAccessPermission)
    query_handler = OCPAzureForecast
    serializer = OCPAzureCostForecastParamSerializer
    tag_handler = [OCPAzureTagsSummary]


class OCPAllCostForecastView(ForecastView):
    """OCP+All Cost Forecast View."""

    permission_classes = (OpenshiftAllAccessPermission,)
    query_handler = OCPAllForecast
    serializer = OCPAllCostForecastParamSerializer
    tag_handler = [OCPAWSTagsSummary, OCPAzureTagsSummary]
