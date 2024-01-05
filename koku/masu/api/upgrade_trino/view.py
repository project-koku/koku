#
# Copyright 2024 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View for fixing parquet files endpoint."""
import logging

from django.views.decorators.cache import never_cache
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.decorators import permission_classes
from rest_framework.decorators import renderer_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.settings import api_settings

from masu.api.upgrade_trino.util.task_handler import FixParquetTaskHandler
from masu.api.upgrade_trino.util.task_handler import RequiredParametersError

LOG = logging.getLogger(__name__)


@never_cache
@api_view(http_method_names=["GET", "DELETE"])
@permission_classes((AllowAny,))
@renderer_classes(tuple(api_settings.DEFAULT_RENDERER_CLASSES))
def fix_parquet(request):
    """Fix parquet files so that we can upgrade Trino."""
    try:
        task_handler = FixParquetTaskHandler.from_query_params(request.query_params)
        async_fix_results = task_handler.build_celery_tasks()
    except RequiredParametersError as errmsg:
        return Response({"Error": str(errmsg)}, status=status.HTTP_400_BAD_REQUEST)
    response_key = "Async jobs for fix parquet files"
    if task_handler.simulate:
        response_key = response_key + " (simulated)"
    return Response({response_key: str(async_fix_results)})
