#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Sources-Provider Coordinator."""
import logging

from rest_framework.exceptions import ValidationError

from api.provider.provider_builder import ProviderBuilder
from api.provider.provider_builder import ProviderBuilderError
from sources.storage import add_provider_koku_uuid
from sources.storage import destroy_source_event

LOG = logging.getLogger(__name__)


class SourcesProviderCoordinatorError(ValidationError):
    """SourcesProviderCoordinator Error."""

    pass


class SourcesProviderCoordinator:
    """Coordinator to control source and provider operations."""

    def __init__(self, source_id, auth_header, account_number, org_id):
        """Initialize the client."""
        header = {"x-rh-identity": auth_header, "sources-client": "True"}
        self._source_id = source_id
        self._identity_header = header
        self._account_number = account_number
        self._org_id = org_id
        self._provider_builder = ProviderBuilder(self._identity_header, self._account_number, self._org_id)

    def create_account(self, source):
        """Call to create provider."""
        try:
            LOG.info(f"Creating Provider for Source ID: {str(self._source_id)}")
            provider = self._provider_builder.create_provider_from_source(source)
            add_provider_koku_uuid(self._source_id, provider.uuid)
        except ProviderBuilderError as provider_err:
            raise SourcesProviderCoordinatorError(str(provider_err))
        return provider

    def update_account(self, source):
        """Call to update provider."""
        try:
            LOG.info(f"Updating Provider for Source ID: {str(self._source_id)}")
            provider = self._provider_builder.update_provider_from_source(source)
        except ProviderBuilderError as provider_err:
            raise SourcesProviderCoordinatorError(str(provider_err))
        return provider

    def destroy_account(self, koku_uuid, retry_count=None):
        """Call to destroy provider."""
        try:
            self._provider_builder.destroy_provider(koku_uuid, retry_count=retry_count)
            destroy_source_event(self._source_id)
        except ProviderBuilderError as provider_err:
            LOG.error(f"Failed to remove provider. Error: {str(provider_err)}")
