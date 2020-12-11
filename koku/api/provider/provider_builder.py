#
# Copyright 2019 Red Hat, Inc.
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
"""Provider Builder."""
import json
import logging
from base64 import b64decode

from django.db import connection
from rest_framework.exceptions import ValidationError

from api.models import Customer
from api.models import Provider
from api.models import Tenant
from api.models import User
from api.provider.provider_manager import ProviderManager
from api.provider.provider_manager import ProviderManagerError
from api.provider.serializers import ProviderSerializer
from koku.middleware import IdentityHeaderMiddleware
from sources.config import Config


LOG = logging.getLogger(__name__)


class ProviderBuilderError(ValidationError):
    """ProviderBuilder Error."""

    pass


class ProviderBuilder:
    """Provider Builder to create koku providers."""

    def __init__(self, auth_header):
        """Initialize the client."""
        self._base_url = Config.KOKU_API_URL
        if isinstance(auth_header, dict) and auth_header.get("x-rh-identity"):
            self._identity_header = auth_header
        else:
            header = {"x-rh-identity": auth_header, "sources-client": "True"}
            self._identity_header = header

    def _get_dict_from_text_field(self, value):
        try:
            db_dict = json.loads(value)
        except ValueError:
            db_dict = {}
        return db_dict

    def _build_credentials_auth(self, authentication):
        credentials = authentication.get("credentials")
        if credentials and isinstance(credentials, dict):
            auth = {"credentials": credentials}
        else:
            raise ProviderBuilderError("Missing credentials")
        return auth

    def _build_provider_data_source(self, billing_source):
        data_source = billing_source.get("data_source")
        if data_source and isinstance(data_source, dict):
            billing = {"data_source": data_source}
        else:
            raise ProviderBuilderError("Missing data_source")
        return billing

    def get_billing_source_for_provider(self, provider_type, billing_source):
        """Build billing source json data for provider type."""
        provider_type = Provider.PROVIDER_CASE_MAPPING.get(provider_type.lower())
        if provider_type == Provider.PROVIDER_OCP:
            return {}
        else:
            return self._build_provider_data_source(billing_source)

    def _create_context(self):
        """Create request context object."""
        user = None
        customer = None
        encoded_auth_header = self._identity_header.get("x-rh-identity")
        if encoded_auth_header:
            identity = json.loads(b64decode(encoded_auth_header))
            account = identity.get("identity", {}).get("account_number")
            username = identity.get("identity", {}).get("user", {}).get("username")
            email = identity.get("identity", {}).get("user", {}).get("email")

            try:
                customer = Customer.objects.filter(account_id=account).get()
            except Customer.DoesNotExist:
                customer = IdentityHeaderMiddleware.create_customer(account)
            try:
                user = User.objects.get(username=username)
            except User.DoesNotExist:
                user = IdentityHeaderMiddleware.create_user(username, email, customer, None)

        context = {"user": user, "customer": customer}
        return context, customer, user

    def create_provider_from_source(self, source):
        """Call to create provider."""
        connection.set_schema_to_public()
        context, customer, _ = self._create_context()
        tenant, created = Tenant.objects.get_or_create(schema_name=customer.schema_name)
        if created:
            msg = f"Created tenant {customer.schema_name}"
            LOG.info(msg)
        provider_type = source.source_type
        json_data = {
            "name": source.name,
            "type": provider_type.lower(),
            "authentication": self._build_credentials_auth(source.authentication),
            "billing_source": self.get_billing_source_for_provider(provider_type, source.billing_source),
        }
        if source.source_uuid:
            json_data["uuid"] = str(source.source_uuid)

        connection.set_tenant(tenant)
        serializer = ProviderSerializer(data=json_data, context=context)
        try:
            if serializer.is_valid(raise_exception=True):
                instance = serializer.save()
        except ValidationError as error:
            connection.set_schema_to_public()
            raise error
        connection.set_schema_to_public()
        return instance

    def update_provider_from_source(self, source):
        """Call to update provider."""
        connection.set_schema_to_public()
        context, customer, _ = self._create_context()
        tenant = Tenant.objects.get_or_create(schema_name=customer.schema_name)
        provider_type = source.source_type
        json_data = {
            "name": source.name,
            "type": provider_type.lower(),
            "authentication": self._build_credentials_auth(source.authentication),
            "billing_source": self.get_billing_source_for_provider(provider_type, source.billing_source),
        }
        connection.set_tenant(tenant)
        instance = Provider.objects.get(uuid=source.koku_uuid)
        serializer = ProviderSerializer(instance=instance, data=json_data, partial=False, context=context)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        connection.set_schema_to_public()
        return instance

    def destroy_provider(self, provider_uuid):
        """Call to destroy provider."""
        connection.set_schema_to_public()
        _, customer, user = self._create_context()
        tenant = Tenant.objects.get_or_create(schema_name=customer.schema_name)
        connection.set_tenant(tenant)
        try:
            manager = ProviderManager(provider_uuid)
        except ProviderManagerError:
            LOG.info("Provider does not exist, skipping Provider delete.")
        else:
            manager.remove(user=user, from_sources=True)
        connection.set_schema_to_public()
