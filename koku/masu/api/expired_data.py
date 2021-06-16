#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View for expired_data endpoint."""
import json
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

    params = request.query_params
    acceptabools = ["true", "false"]
    line_items_only = params.get("line_items_only", "false").lower()
    if line_items_only not in acceptabools:
        errmsg = "The param line_items_only must be {}.".format(str(acceptabools))
        return Response({"Error": errmsg}, status=status.HTTP_400_BAD_REQUEST)
    line_items_only = json.loads(line_items_only)
    orchestrator = Orchestrator()
    async_delete_results = orchestrator.remove_expired_report_data(simulate=simulate, line_items_only=line_items_only)
    response_key = "Async jobs for expired data removal"
    if simulate:
        response_key = response_key + " (simulated)"
    return Response({response_key: str(async_delete_results)})
