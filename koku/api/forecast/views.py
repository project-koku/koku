#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Forecast Views."""
import logging

from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from rest_framework import status
from rest_framework.response import Response
from rest_framework.serializers import ValidationError
from rest_framework.views import APIView

from api.common.pagination import ForecastListPaginator
from api.common.permissions import AwsAccessPermission
from api.common.permissions import AzureAccessPermission
from api.common.permissions import GcpAccessPermission
from api.common.permissions import OpenShiftAccessPermission
from api.common.permissions.openshift_all_access import OpenshiftAllAccessPermission
from api.forecast.serializers import AWSCostForecastParamSerializer
from api.forecast.serializers import AzureCostForecastParamSerializer
from api.forecast.serializers import GCPCostForecastParamSerializer
from api.forecast.serializers import OCPAllCostForecastParamSerializer
from api.forecast.serializers import OCPAWSCostForecastParamSerializer
from api.forecast.serializers import OCPAzureCostForecastParamSerializer
from api.forecast.serializers import OCPCostForecastParamSerializer
from api.forecast.serializers import OCPGCPCostForecastParamSerializer
from api.query_params import QueryParameters
from forecast import AWSForecast
from forecast import AzureForecast
from forecast import GCPForecast
from forecast import OCPAllForecast
from forecast import OCPAWSForecast
from forecast import OCPAzureForecast
from forecast import OCPForecast
from forecast import OCPGCPForecast
from reporting.models import AzureTagsSummary
from reporting.models import GCPTagsSummary
from reporting.models import OCPAWSTagsSummary
from reporting.models import OCPAzureTagsSummary
from reporting.models import OCPGCPTagsSummary
from reporting.models import OCPStorageVolumeLabelSummary
from reporting.models import OCPUsagePodLabelSummary
from reporting.provider.aws.models import AWSTagsSummary

LOG = logging.getLogger(__name__)


class ForecastView(APIView):
    """Base forecast view class."""

    report = "forecast"

    @method_decorator(never_cache)
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

        paginator = ForecastListPaginator(output, request)
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


class OCPGCPCostForecastView(ForecastView):
    """OCP+GCP Cost Forecast View."""

    permission_classes = (GcpAccessPermission, OpenShiftAccessPermission)
    query_handler = OCPGCPForecast
    serializer = OCPGCPCostForecastParamSerializer
    tag_handler = [OCPGCPTagsSummary]


class OCPAllCostForecastView(ForecastView):
    """OCP+All Cost Forecast View."""

    permission_classes = (OpenshiftAllAccessPermission,)
    query_handler = OCPAllForecast
    serializer = OCPAllCostForecastParamSerializer
    tag_handler = [OCPAWSTagsSummary, OCPAzureTagsSummary]


class GCPForecastCostView(ForecastView):
    """GCP Cost Forecast View."""

    permission_classes = (GcpAccessPermission,)
    query_handler = GCPForecast
    serializer = GCPCostForecastParamSerializer
    tag_handler = [GCPTagsSummary]
