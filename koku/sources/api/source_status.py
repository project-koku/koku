#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""View for Source status."""
import logging

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.views.decorators.cache import never_cache
from rest_framework import serializers
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.decorators import permission_classes
from rest_framework.decorators import renderer_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.serializers import ValidationError
from rest_framework.settings import api_settings

from api.common import error_obj as error_object
from api.provider.models import Provider
from api.provider.models import Sources
from providers.provider_access import ProviderAccessor
from providers.provider_errors import ProviderErrors
from providers.provider_errors import SkipStatusPush
from sources.sources_http_client import SourceNotFoundError
from sources.sources_http_client import SourcesHTTPClient
from sources.sources_http_client import SourcesHTTPClientError
from sources.sources_provider_coordinator import SourcesProviderCoordinator
from sources.storage import source_settings_complete

LOG = logging.getLogger(__name__)


class SourceStatus:
    """Source Status."""

    def __init__(self, source_id):
        """Initialize source id."""
        self.source_id = source_id
        self.source: Sources = Sources.objects.get(source_id=source_id)
        if not source_settings_complete(self.source) or self.source.pending_delete:
            raise ObjectDoesNotExist(f"Source ID: {self.source_id} not ready for status")
        self.sources_client = SourcesHTTPClient(self.source.auth_header, source_id=source_id)

    @property
    def sources_response(self):
        return self.sources_client.build_source_status(self.status())

    def _set_provider_active_status(self, active_status):
        """Set provider active status."""
        if self.source.koku_uuid:
            prov_exists = True
            try:
                provider = Provider.objects.get(uuid=self.source.koku_uuid)
                provider.active = active_status
                provider.save()
            except Provider.DoesNotExist:
                LOG.info(f"No provider found for Source ID: {self.source.source_id}")
                prov_exists = False
            return prov_exists

    def determine_status(self, provider_type, source_authentication, source_billing_source):
        """Check cloud configuration status."""
        interface = ProviderAccessor(provider_type)
        error_obj = None
        try:
            if self.source.account_id not in settings.DEMO_ACCOUNTS:
                interface.cost_usage_source_ready(source_authentication, source_billing_source)
            prov_exists = self._set_provider_active_status(True)
        except ValidationError as validation_error:
            prov_exists = self._set_provider_active_status(False)
            error_obj = validation_error
        if not error_obj and not prov_exists:
            key = ProviderErrors.PROVIDER_NOT_FOUND
            msg = "Something went wrong creating your source, please try again."
            error_obj = serializers.ValidationError(error_object(key, msg))

        self.source.refresh_from_db()
        return error_obj

    def status(self):
        """Find the source's availability status."""
        source_billing_source = self.source.billing_source.get("data_source") or {}
        source_authentication = self.source.authentication.get("credentials") or {}
        provider_type = self.source.source_type
        return self.determine_status(provider_type, source_authentication, source_billing_source)

    @transaction.atomic
    def update_source_name(self):
        """Update source name if it is out of sync with platform."""
        source_details = self.sources_client.get_source_details()
        if source_details.get("name") != self.source.name:
            self.source.name = source_details.get("name")
            self.source.save()
            builder = SourcesProviderCoordinator(
                self.source_id, self.source.auth_header, self.source.account_id, self.source.org_id
            )
            builder.update_account(self.source)

    def push_status(self):
        """Push status_msg to platform sources."""
        try:
            status_obj = self.status()
            if self.source.source_type in (Provider.PROVIDER_GCP, Provider.PROVIDER_GCP_LOCAL):
                builder = SourcesProviderCoordinator(
                    self.source.source_id, self.source.auth_header, self.source.account_id, self.source.org_id
                )
                if not status_obj:
                    if self.source.koku_uuid:
                        status_obj = self.try_catch_validation_error(status_obj, builder.update_account)
                    elif self.source.billing_source.get("data_source", {}).get("table_id"):
                        status_obj = self.try_catch_validation_error(status_obj, builder.create_account)
            self.sources_client.set_source_status(status_obj)
            self.update_source_name()
            LOG.info(f"Source status for Source ID: {str(self.source_id)}: Status: {str(status_obj)}")
        except SkipStatusPush as error:
            LOG.info(f"Platform sources status push skipped. Reason: {str(error)}")
        except (SourcesHTTPClientError, SourceNotFoundError) as error:
            err_msg = f"Unable to push source status. Reason: {str(error)}"
            LOG.warning(err_msg)

    def try_catch_validation_error(self, status_obj, func):
        try:
            func(self.source)
            return status_obj
        except ValidationError as validation_error:
            return validation_error


def _get_source_id_from_request(request):
    """Get source id from request."""
    if request.method == "GET":
        source_id = request.query_params.get("source_id", None)
    elif request.method == "POST":
        source_id = request.data.get("source_id", None)
    else:
        raise status.HTTP_405_METHOD_NOT_ALLOWED
    return source_id


def _deliver_status(request, status_obj):
    """Deliver status depending on request."""
    if request.method == "GET":
        return Response(status_obj.sources_response, status=status.HTTP_200_OK)
    elif request.method == "POST":
        status_obj.push_status()
        return Response(status=status.HTTP_204_NO_CONTENT)
    else:
        raise status.HTTP_405_METHOD_NOT_ALLOWED


@never_cache
@api_view(http_method_names=["GET", "POST"])
@permission_classes((AllowAny,))
@renderer_classes(tuple(api_settings.DEFAULT_RENDERER_CLASSES))
def source_status(request):
    """
    Source availability status endpoint for Platform Sources to get cost management source status.

    Parameter:
        source_id corresponds to the table api_sources

    Returns:
        status (Dict): {'availability_status': 'unavailable/available',
                        'availability_status_error': ValidationError-detail}
    """
    LOG.info(f"{{'method': {request.method}, 'path': {request.path}, 'body': {request.data}}}")

    source_id = _get_source_id_from_request(request)

    if source_id is None:
        return Response(data="Missing query parameter source_id", status=status.HTTP_400_BAD_REQUEST)

    try:
        int(source_id)
    except ValueError:
        # source_id must be an integer
        return Response(data="source_id must be an integer", status=status.HTTP_400_BAD_REQUEST)

    try:
        source_status_obj = SourceStatus(source_id)
    except ObjectDoesNotExist:
        # Source isn't in our database, return 404.
        return Response(status=status.HTTP_404_NOT_FOUND)

    return _deliver_status(request, source_status_obj)
