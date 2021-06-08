#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View for Source cleanup."""
import logging

from django.views.decorators.cache import never_cache
from rest_framework.decorators import api_view
from rest_framework.decorators import permission_classes
from rest_framework.decorators import renderer_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.settings import api_settings
from tenant_schemas.utils import schema_context

from api.provider.models import Provider
from api.provider.models import Sources
from masu.processor.tasks import refresh_materialized_views
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
    cleaning_list = build_list()
    response = {}

    providers_without_sources = []
    for provider in cleaning_list.get("providers_without_sources"):
        providers_without_sources.append(f"{provider.name} ({provider.uuid})")

    out_of_order_delete = []
    for source in cleaning_list.get("out_of_order_deletes"):
        out_of_order_delete.append(f"Source ID: {source.source_id})")

    missing_sources = []
    for source in cleaning_list.get("missing_sources"):
        missing_sources.append(f"Source ID: {source.source_id})")

    response["providers_without_sources"] = providers_without_sources
    response["out_of_order_deletes"] = out_of_order_delete
    response["missing_sources"] = missing_sources

    params = request.query_params

    if request.method == "DELETE":
        if "providers_without_sources" in params.keys():
            cleanup_provider_without_source(cleaning_list)
        if "out_of_order_deletes" in params.keys():
            cleanup_out_of_order_deletes(cleaning_list)
        if "missing_sources" in params.keys():
            cleanup_missing_sources(cleaning_list)

    return Response(response)


def cleanup_provider_without_source(cleaning_list):
    provider_without_source = cleaning_list.get("providers_without_sources")

    if provider_without_source:
        materialized_views_to_update = []
        for provider in provider_without_source:
            schema_name = provider.customer.schema_name
            provider_type = provider.type
            with schema_context(schema_name):
                LOG.info(f"Removing Provider without Source: {str(provider.name)} ({str(provider.uuid)}")
                Provider.objects.get(uuid=provider.uuid).delete()
                mat_view_dict = {"schema": schema_name, "type": provider_type}
                if mat_view_dict not in materialized_views_to_update:
                    materialized_views_to_update.append(mat_view_dict)

        for mat_view in materialized_views_to_update:
            LOG.info(f"Refreshing Materialized Views: {str(mat_view)}")
            refresh_materialized_views(mat_view.get("schema"), mat_view.get("type"))


def cleanup_out_of_order_deletes(cleaning_list):
    out_of_order_deletes = cleaning_list.get("out_of_order_deletes")

    if out_of_order_deletes:
        for source in out_of_order_deletes:
            LOG.info(f"Removing out of order delete Source: {str(source)}")
            Sources.objects.get(source_id=source.source_id).delete()


def cleanup_missing_sources(cleaning_list):
    missing_sources = cleaning_list.get("missing_sources")

    if missing_sources:
        for source in missing_sources:
            LOG.info(f"Removing missing Source: {str(source)}")
            Sources.objects.get(source_id=source.source_id).delete()


def _providers_without_sources():
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


def _missing_sources():
    sources = Sources.objects.all()

    missing_sources = []
    for source in sources:
        try:
            sources_client = SourcesHTTPClient(source.auth_header, source.source_id)
            _ = sources_client.get_source_details()
        except SourceNotFoundError:
            LOG.info(
                f"Source {source.name} ID: {source.source_id} UUID: {source.source_uuid} not found in plaform sources"
            )
            missing_sources.append(source)
        except SourcesHTTPClientError:
            LOG.info("Unable to reach platform sources")
    return missing_sources


def build_list():
    providers_without_sources = _providers_without_sources()
    sources_out_of_order_delete = _sources_out_of_order_deletes()
    missing_sources = _missing_sources()

    response = {}
    response["providers_without_sources"] = providers_without_sources
    response["out_of_order_deletes"] = sources_out_of_order_delete
    response["missing_sources"] = missing_sources
    return response
