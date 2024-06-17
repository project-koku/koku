#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View for expired_data endpoint."""
import logging

from django.views.decorators.cache import never_cache
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.decorators import permission_classes
from rest_framework.decorators import renderer_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.settings import api_settings

from masu.config import Config
from masu.processor.orchestrator import Orchestrator
from masu.processor.tasks import remove_expired_trino_migrations

LOG = logging.getLogger(__name__)


@never_cache
@api_view(http_method_names=["GET", "DELETE"])
@permission_classes((AllowAny,))
@renderer_classes(tuple(api_settings.DEFAULT_RENDERER_CLASSES))
def expired_data(request):
    """Return expired data."""
    simulate = True
    if request.method == "DELETE" and Config.DEBUG:
        simulate = False
    LOG.info("Simulate Flag: %s", simulate)

    orchestrator = Orchestrator()
    async_delete_results = orchestrator.remove_expired_report_data(simulate=simulate)
    response_key = "Async jobs for expired data removal"
    if simulate:
        response_key = response_key + " (simulated)"
    return Response({response_key: str(async_delete_results)})


@never_cache
@api_view(http_method_names=["GET", "DELETE"])
@permission_classes((AllowAny,))
@renderer_classes(tuple(api_settings.DEFAULT_RENDERER_CLASSES))
def expired_trino_migrations(request):
    """Return expired data."""
    params = request.query_params
    schema_name = params.get("schema")
    provider_type = params.get("provider_type")
    provider_uuid = params.get("provider_uuid")
    simulate = params.get("simulate")
    simulate = True

    if request.method == "DELETE" and Config.DEBUG:
        simulate = False
    LOG.info("Simulate Flag: %s", simulate)
    if schema_name is None:
        errmsg = "schema is a required parameter."
        return Response({"Error": errmsg}, status=status.HTTP_400_BAD_REQUEST)

    async_delete_results = remove_expired_trino_migrations.delay(schema_name, provider_type, simulate, provider_uuid)
    response_key = "Async jobs for expired data removal"
    if simulate:
        response_key = response_key + " (simulated)"
    return Response({response_key: str(async_delete_results)})
