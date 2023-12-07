#
# Copyright 2023 Red Hat Inc.
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

from api.provider.models import Provider
from koku.cache import get_cached_reprocess_by_provider_type
from koku.cache import set_cached_reprocess_by_provider_type
from masu.celery.tasks import reprocess_csv_reports as reprocess_task


LOG = logging.getLogger(__name__)


class RequiredParametersError(Exception):
    """Handle require parameters error."""


def build_reprocess_kwargs(query_params):
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
        key_exist, timeout = get_cached_reprocess_by_provider_type(provider_type)
        if key_exist:
            err_msg = f"provider_type ({provider_type}) still disabled for {round(timeout/60, 2)} minutes"
            raise RequiredParametersError(err_msg)
        set_cached_reprocess_by_provider_type(provider_type)
        uuid_or_type_provided = True
        reprocess_kwargs["provider_type"] = provider_type
    if not uuid_or_type_provided:
        raise RequiredParametersError("provider_uuid or provider_type must be supplied")
    return reprocess_kwargs


@never_cache
@api_view(http_method_names=["GET"])
@permission_classes((AllowAny,))
@renderer_classes(tuple(api_settings.DEFAULT_RENDERER_CLASSES))
def reprocess_csv_reports(request):
    """trigger a task to reprocess monthly csv files into parquet files for a provider."""
    params = request.query_params
    try:
        reprocess_kwargs = build_reprocess_kwargs(params)
    except RequiredParametersError as errmsg:
        return Response({"Error": errmsg}, status=status.HTTP_400_BAD_REQUEST)
    summarize_reports = params.get("summarize_reports", "true").lower()
    reprocess_kwargs["summarize_reports"] = True if summarize_reports == "true" else False
    async_reprocess_reports = reprocess_task.delay(**reprocess_kwargs)
    # TODO
    # 2. The ability to trigger multiple months for a/each provider.
    # Do we actually want this?
    return Response({"Reprocess CSV Task ID": str(async_reprocess_reports)})
