#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View for Source cleanup."""
import logging
from dataclasses import dataclass
from uuid import UUID

from django.views.decorators.cache import never_cache
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.decorators import permission_classes
from rest_framework.decorators import renderer_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.settings import api_settings

from api.common.pagination import ListPaginator
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
    if not params or all(
        x not in params for x in ["providers_without_sources", "out_of_order_deletes", "missing_sources"]
    ):
        errmsg = "Parameter missing. Options: providers_without_sources, out_of_order_deletes, or missing_sources"
        return Response({"Error": errmsg}, status=status.HTTP_400_BAD_REQUEST)

    params._mutable = True
    lo = LimitOffset(int(params.get("limit") or 10), int(params.get("offset") or 0))
    params["limit"] = lo.limit
    params["offset"] = lo.offset
    params._mutable = False

    source_uuid = params.get("uuid")
    if source_uuid:
        try:
            UUID(source_uuid)
        except ValueError as error:
            LOG.info(str(error))
            errmsg = "Invalid uuid."
            return Response({"Error": errmsg}, status=status.HTTP_400_BAD_REQUEST)

    LOG.info(f"Source Cleanup for UUID: {source_uuid}")

    if "providers_without_sources" in params.keys():
        return handle_providers_without_sources_response(request, _providers_without_sources(source_uuid), lo)

    if "out_of_order_deletes" in params.keys():
        return handle_out_of_order_deletes_response(request, _sources_out_of_order_deletes(source_uuid), lo)

    if "missing_sources" in params.keys():
        return handle_missing_sources_response(request, _missing_sources(source_uuid, lo.limit, lo.offset), lo)


@dataclass(frozen=True, order=True)
class LimitOffset:
    limit: int = 10
    offset: int = 0


class SimplePaginate(ListPaginator):
    @property
    def paginated_data_set(self):
        return self.data_set


def handle_providers_without_sources_response(request, dataset, limit_offset):
    if request.method == "DELETE":
        cleanup_provider_without_source(
            dataset[limit_offset.offset : limit_offset.offset + limit_offset.limit]
        )
        return Response({"job_queued": "providers_without_sources"})
    else:
        providers_without_sources = [f"{provider.name} ({provider.uuid})" for provider in dataset]
        return ListPaginator(providers_without_sources, request).paginated_response


def handle_out_of_order_deletes_response(request, dataset, limit_offset):
    if request.method == "DELETE":
        cleanup_out_of_order_deletes(
            dataset[limit_offset.offset : limit_offset.offset + limit_offset.limit]
        )
        return Response({"job_queued": "out_of_order_deletes"})
    else:
        out_of_order_delete = [f"Source ID: {source.source_id}" for source in dataset]
        return ListPaginator(out_of_order_delete, request).paginated_response


def handle_missing_sources_response(request, sources_dataset, limit_offset):
    all_sources, dataset = sources_dataset
    if request.method == "DELETE":
        cleanup_missing_sources(dataset)
        return Response({"job_queued": "missing_sources"})
    else:
        missing_sources = [f"Source ID: {source.source_id} Source UUID: {source.source_uuid}" for source in dataset]
        paginator = SimplePaginate(missing_sources, request)
        paginator.count = len(all_sources)
        return paginator.paginated_response


def cleanup_provider_without_source(cleaning_list):
    for provider in cleaning_list:
        async_id = delete_provider_async.delay(provider.name, provider.uuid, provider.customer.schema_name)
        LOG.info(f"Queuing delete for {str(provider.name)}: {str(provider.uuid)}.  Async ID: {str(async_id)}")


def cleanup_out_of_order_deletes(cleaning_list):
    for source in cleaning_list:
        async_id = out_of_order_source_delete_async.delay(source.source_id)
        LOG.info(f"Queuing delete for out-of-order Source ID: {str(source.source_id)}.  Async ID: {str(async_id)}")


def cleanup_missing_sources(cleaning_list):
    for source in cleaning_list:
        async_id = missing_source_delete_async.delay(source.source_id)
        LOG.info(f"Queuing missing source delete Source ID: {str(source.source_id)}.  Async ID: {str(async_id)}")


def _providers_without_sources(provider_uuid=None):
    if provider_uuid:
        providers = Provider.objects.filter(uuid=provider_uuid)
    else:
        providers = Provider.objects.all().order_by("uuid")

    providers_without_sources = []
    for provider in providers:
        try:
            Sources.objects.get(koku_uuid=provider.uuid)
        except Sources.DoesNotExist:
            LOG.debug(f"No Source found for Provider {provider.name} ({provider.uuid})")
            providers_without_sources.append(provider)
    return providers_without_sources


def _sources_out_of_order_deletes(source_uuid=None):
    if source_uuid:
        sources = Sources.objects.filter(source_uuid=source_uuid, out_of_order_delete=True, koku_uuid=None)
    else:
        sources = Sources.objects.filter(out_of_order_delete=True, koku_uuid=None).all().order_by("source_id")

    return list(sources)


def _missing_sources(source_uuid=None, limit=10, offset=0):
    if source_uuid:
        sources = Sources.objects.filter(source_uuid=source_uuid)
    else:
        sources = Sources.objects.all().order_by("source_id")

    missing_sources = []
    # the request to sources-api is a "slow" process.
    # Use limits and offsets to prevent too many requests from causing a gateway timeout.
    for source in sources[offset : offset + limit]:
        try:
            sources_client = SourcesHTTPClient(source.auth_header, source.source_id, source.account_id)
            _ = sources_client.get_source_details()
        except SourceNotFoundError:
            LOG.debug(
                f"Source {source.name} ID: {source.source_id} UUID: {source.source_uuid} not found in platform sources"
            )
            missing_sources.append(source)
        except SourcesHTTPClientError as e:
            LOG.info(f"Unable to reach platform sources: {e}")
    return sources, missing_sources
