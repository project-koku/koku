#
# Copyright 2023 Red Hat Inc.
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

from api.provider.models import Provider
from masu.api.upgrade_trino.task_handler import fix_parquet_data_types_task_builder

LOG = logging.getLogger(__name__)


class RequiredParametersError(Exception):
    """Handle require parameters error."""


def build_task_handler_kwargs(query_params):
    """Validates the expected query parameters."""
    uuid_or_type_provided = False  # used to check if provider uuid or type supplied
    reprocess_kwargs = {}
    if start_date := query_params.get("start_date"):
        reprocess_kwargs["bill_date"] = start_date
    else:
        raise RequiredParametersError("start_date must be supplied as a parameter.")
    if provider_uuid := query_params.get("provider_uuid"):
        uuid_or_type_provided = True
        provider = Provider.objects.filter(uuid=provider_uuid).first()
        if not provider:
            raise RequiredParametersError(f"The provider_uuid {provider_uuid} does not exist.")
        reprocess_kwargs["provider_uuid"] = provider_uuid
    if provider_type := query_params.get("provider_type"):
        uuid_or_type_provided = True
        reprocess_kwargs["provider_type"] = provider_type
    if not uuid_or_type_provided:
        raise RequiredParametersError("provider_uuid or provider_type must be supplied")
    return reprocess_kwargs


@never_cache
@api_view(http_method_names=["GET", "DELETE"])
@permission_classes((AllowAny,))
@renderer_classes(tuple(api_settings.DEFAULT_RENDERER_CLASSES))
def fix_parquet(request):
    """Return expired data."""
    simulate = False
    params = request.query_params
    try:
        task_handler_kwargs = build_task_handler_kwargs(params)
        async_fix_results = fix_parquet_data_types_task_builder(**task_handler_kwargs)
    except RequiredParametersError as errmsg:
        return Response({"Error": str(errmsg)}, status=status.HTTP_400_BAD_REQUEST)
    response_key = "Async jobs for fix parquet files"
    if simulate:
        response_key = response_key + " (simulated)"
    return Response({response_key: str(async_fix_results)})
