#
# Copyright 2024 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View for temporary force check of infra map."""
import logging

from django.views.decorators.cache import never_cache
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.decorators import permission_classes
from rest_framework.decorators import renderer_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.settings import api_settings

from api.models import Provider
from masu.processor.ocp.ocp_cloud_updater_base import OCPCloudUpdaterBase

LOG = logging.getLogger(__name__)


@never_cache
@api_view(http_method_names=["GET"])
@permission_classes((AllowAny,))
@renderer_classes(tuple(api_settings.DEFAULT_RENDERER_CLASSES))
def recheck_infra_map(request):
    """Checks to see if a cloud provider should be mapped to an Openshift Source.

    The start and end date used here is for the inframap sql and be a small range of days
    you know have correlation.
    """
    params = request.query_params
    if not params:
        errmsg = "Parameter missing. Required: cloud_provider, start_date, end_date"
        return Response({"Error": errmsg}, status=status.HTTP_400_BAD_REQUEST)

    cloud_provider = params.get("cloud_provider")
    start_date = params.get("start_date")
    end_date = params.get("end_date")

    try:
        provider = Provider.objects.get(uuid=cloud_provider)
        provider_schema = provider.account.get("schema_name")
    except Provider.DoesNotExist:
        errmsg = f"cloud_provider {cloud_provider} does not exist"
        return Response({"Error": errmsg}, status=status.HTTP_400_BAD_REQUEST)

    ocp_updater = OCPCloudUpdaterBase(provider_schema, provider, None)
    # a manifest is not needed to recheck the infra map
    infra_map = ocp_updater._generate_ocp_infra_map_from_sql_trino(start_date, end_date, False)
    return Response({"Infrastructure map": str(infra_map)})
