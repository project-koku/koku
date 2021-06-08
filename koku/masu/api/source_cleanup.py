#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View for Source cleanup."""
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
from api.provider.models import Sources
from masu.celery.tasks import delete_provider_async
from masu.celery.tasks import missing_source_delete_async
from masu.celery.tasks import out_of_order_source_delete_async
from sources.sources_http_client import SourceNotFoundError
from sources.sources_http_client import SourcesHTTPClient
from sources.sources_http_client import SourcesHTTPClientError

LOG = logging.getLogger(__name__)


@never_cache
@api_view(http_method_names=["GET", "DELETE"])
@permission_classes((AllowAny,))
@renderer_classes(tuple(api_settings.DEFAULT_RENDERER_CLASSES))
def cleanup(request):
    """Return download file async task ID."""
    params = request.query_params
    if not params:
        errmsg = "Parameter missing. Options: providers_without_sources, out_of_order_deletes, or missing_sources"
        return Response({"Error": errmsg}, status=status.HTTP_400_BAD_REQUEST)

    source_uuid = params.get("uuid")
    LOG.info(f"Source Cleanup for UUID: {source_uuid}")
    response = {}
    if "providers_without_sources" in params.keys():
        response["providers_without_sources"] = _providers_without_sources(source_uuid)
        return handle_providers_without_sources_response(request, response, source_uuid)

    if "out_of_order_deletes" in params.keys():
        response["out_of_order_deletes"] = _sources_out_of_order_deletes()
        return handle_out_of_order_deletes_response(request, response)

    if "missing_sources" in params.keys():
        response["missing_sources"] = _missing_sources(source_uuid)
        return handle_missing_sources_response(request, response, source_uuid)


def handle_providers_without_sources_response(request, response, source_uuid):
    if request.method == "DELETE":
        cleanup_provider_without_source(response)
        return Response({"job_queued": "providers_without_sources"})
    else:
        providers_without_sources = []
        for provider in response["providers_without_sources"]:
            providers_without_sources.append(f"{provider.name} ({provider.uuid})")
            response["providers_without_sources"] = providers_without_sources
        return Response(response)


def handle_out_of_order_deletes_response(request, response):
    if request.method == "DELETE":
        cleanup_out_of_order_deletes(response)
        return Response({"job_queued": "out_of_order_deletes"})
    else:
        out_of_order_delete = []
        for source in response["out_of_order_deletes"]:
            out_of_order_delete.append(f"Source ID: {source.source_id})")
            response["out_of_order_deletes"] = out_of_order_delete
        return Response(response)


def handle_missing_sources_response(request, response, source_uuid):
    if request.method == "DELETE":
        cleanup_missing_sources(response)
        return Response({"job_queued": "missing_sources"})
    else:
        missing_sources = []
        for source in response["missing_sources"]:
            missing_sources.append(f"Source ID: {source.source_id})")
            response["missing_sources"] = missing_sources
        return Response(response)


def cleanup_provider_without_source(cleaning_list):
    provider_without_source = cleaning_list.get("providers_without_sources")
    if provider_without_source:
        for provider in provider_without_source:
            async_id = delete_provider_async.delay(provider.name, provider.uuid, provider.customer.schema_name)
            LOG.info(f"Queuing delete for {str(provider.name)}: {str(provider.uuid)}.  Async ID: {str(async_id)}")


def cleanup_out_of_order_deletes(cleaning_list):
    out_of_order_deletes = cleaning_list.get("out_of_order_deletes")
    if out_of_order_deletes:
        for source in out_of_order_deletes:
            async_id = out_of_order_source_delete_async.delay(source.source_id)
            LOG.info(f"Queuing delete for out-of-order Source ID: {str(source.source_id)}.  Async ID: {str(async_id)}")


def cleanup_missing_sources(cleaning_list):
    missing_sources = cleaning_list.get("missing_sources")
    if missing_sources:
        for source in missing_sources:
            async_id = missing_source_delete_async(source.source_id)
            LOG.info(f"Queuing missing source delete Source ID: {str(source.source_id)}.  Async ID: {str(async_id)}")


def _providers_without_sources(provider_uuid=None):
    if provider_uuid:
        providers = Provider.objects.filter(uuid=provider_uuid)
    else:
        providers = Provider.objects.all()

    providers_without_sources = []
    for provider in providers:
        try:
            Sources.objects.get(koku_uuid=provider.uuid)
        except Sources.DoesNotExist:
            LOG.info(f"No Source found for Provider {provider.name} ({provider.uuid})")
            providers_without_sources.append(provider)
    return providers_without_sources


def _sources_out_of_order_deletes():
    sources_out_of_order_delete = []
    try:
        out_of_order_list = Sources.objects.filter(out_of_order_delete=True, koku_uuid=None).all()
        for source in out_of_order_list:
            LOG.info(f"Out of order source: {str(source)}")
            sources_out_of_order_delete.append(source)
    except Sources.DoesNotExist:
        pass
    return sources_out_of_order_delete


def _missing_sources(source_uuid):
    if source_uuid:
        sources = Sources.objects.filter(source_uuid=source_uuid)
    else:
        sources = Sources.objects.all()

    missing_sources = []
    for source in sources:
        try:
            sources_client = SourcesHTTPClient(source.auth_header, source.source_id)
            _ = sources_client.get_source_details()
        except SourceNotFoundError:
            LOG.info(
                f"Source {source.name} ID: {source.source_id} UUID: {source.source_uuid} not found in platform sources"
            )
            missing_sources.append(source)
        except SourcesHTTPClientError:
            LOG.info("Unable to reach platform sources")
    return missing_sources
