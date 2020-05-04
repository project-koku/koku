#
# Copyright 2020 Red Hat, Inc.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
"""Sources-Provider Coordinator."""
import logging

from rest_framework.exceptions import ValidationError

from api.provider.provider_builder import ProviderBuilder
from api.provider.provider_builder import ProviderBuilderError
from sources.storage import add_provider_koku_uuid
from sources.storage import clear_update_flag
from sources.storage import destroy_source_event

LOG = logging.getLogger(__name__)


class SourcesProviderCoordinatorError(ValidationError):
    """SourcesProviderCoordinator Error."""

    pass


class SourcesProviderCoordinator:
    """Coordinator to control source and provider operations."""

    def __init__(self, source_id, auth_header):
        """Initialize the client."""
        header = {"x-rh-identity": auth_header, "sources-client": "True"}
        self._source_id = source_id
        self._identity_header = header
        self._provider_builder = ProviderBuilder(self._identity_header)

    def create_account(self, name, provider_type, authentication, billing_source, source_uuid=None):
        """Call to create provider."""
        try:
            provider = self._provider_builder.create_provider(
                name, provider_type, authentication, billing_source, source_uuid
            )
            add_provider_koku_uuid(self._source_id, provider.uuid)
        except ProviderBuilderError as provider_err:
            raise SourcesProviderCoordinatorError(str(provider_err))
        return provider

    def update_account(self, provider_uuid, name, provider_type, authentication, billing_source):
        """Call to update provider."""
        try:
            provider = self._provider_builder.update_provider(
                provider_uuid, name, provider_type, authentication, billing_source
            )
            clear_update_flag(self._source_id)
        except ProviderBuilderError as provider_err:
            raise SourcesProviderCoordinatorError(str(provider_err))
        return provider

    def destroy_account(self, provider_uuid):
        """Call to destroy provider."""
        self._provider_builder.destroy_provider(provider_uuid)
        destroy_source_event(self._source_id)
