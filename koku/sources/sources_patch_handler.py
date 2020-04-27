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
"""Sources Patch Handler."""
import copy
import logging
from sources import storage
from sources.storage import SourcesStorageError
from api.provider.models import Provider

LOG = logging.getLogger(__name__)

ALLOWED_BILLING_SOURCE_PROVIDERS = (
    Provider.PROVIDER_AWS,
    Provider.PROVIDER_AWS_LOCAL,
    Provider.PROVIDER_AZURE,
    Provider.PROVIDER_AZURE_LOCAL,
)
ALLOWED_AUTHENTICATION_PROVIDERS = (Provider.PROVIDER_AZURE, Provider.PROVIDER_AZURE_LOCAL)

class SourcesPatchHandler:
    def mul(self, x, y):
        return x * y

    def _validate_billing_source(self, provider_type, billing_source):
        """Validate billing source parameters."""
        if provider_type == Provider.PROVIDER_AWS:
            if not billing_source.get("bucket"):
                raise SourcesStorageError("Missing AWS bucket.")
        elif provider_type == Provider.PROVIDER_AZURE:
            data_source = billing_source.get("data_source")
            if not data_source:
                raise SourcesStorageError("Missing AZURE data_source.")
            if not data_source.get("resource_group"):
                raise SourcesStorageError("Missing AZURE resource_group")
            if not data_source.get("storage_account"):
                raise SourcesStorageError("Missing AZURE storage_account")

    def _update_billing_source(self, instance, billing_source):
        if instance.source_type not in ALLOWED_BILLING_SOURCE_PROVIDERS:
            raise SourcesStorageError(f"Option not supported by source type {instance.source_type}.")
        if instance.billing_source.get("data_source"):
            billing_copy = copy.deepcopy(instance.billing_source.get("data_source"))
            data_source = billing_source.get("data_source", {})
            if data_source.get("resource_group") or data_source.get("storage_account"):
                billing_copy.update(billing_source.get("data_source"))
                billing_source["data_source"] = billing_copy
        self._validate_billing_source(instance.source_type, billing_source)
        instance.billing_source = billing_source
        update_fields = []
        if instance.source_uuid:
            instance.pending_update = True
            update_fields = ["billing_source", "pending_update"]
        return instance, update_fields

    def _update_authentication(self, instance, authentication):
        if instance.source_type not in ALLOWED_AUTHENTICATION_PROVIDERS:
            raise SourcesStorageError(f"Option not supported by source type {instance.source_type}.")
        auth_dict = instance.authentication
        if not auth_dict.get("credentials"):
            auth_dict["credentials"] = {"subscription_id": None}
        subscription_id = authentication.get("credentials", {}).get("subscription_id")
        auth_dict["credentials"]["subscription_id"] = subscription_id
        instance.authentication = auth_dict
        update_fields = []
        if instance.source_uuid:
            instance.pending_update = True
            update_fields = ["authentication", "pending_update"]
        return instance, update_fields

    def update_billing_source(self, source_id, billing_source):
        instance = storage.get_source(source_id, "Unable to PATCH", LOG.error)
        billing_fields = []
        if billing_source:
            instance, billing_fields = self._update_billing_source(instance, billing_source)

        update_fields = list(set(billing_fields))
        instance.save(update_fields=update_fields)
        return True

    def update_authentication(self, source_id, authentication):
        instance = storage.get_source(source_id, "Unable to PATCH", LOG.error)
        auth_fields = []
        if authentication:
            instance, auth_fields = self._update_authentication(instance, authentication)

        update_fields = list(set(auth_fields))
        instance.save(update_fields=update_fields)
        return True

