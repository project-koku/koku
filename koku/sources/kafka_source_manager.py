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
"""Kafka Source Manager."""
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


class KafkaSourceManagerError(ValidationError):
    """KafkaSourceManager Error."""

    pass


class KafkaSourceManagerNonRecoverableError(Exception):
    """KafkaSourceManager Unrecoverable Error."""

    pass


class KafkaSourceManager:
    """Kafka Source Manager to create koku providers."""

    def __init__(self, auth_header):
        """Initialize the client."""
        self._base_url = Config.KOKU_API_URL
        header = {"x-rh-identity": auth_header, "sources-client": "True"}
        self._identity_header = header

    def _get_dict_from_text_field(self, value):
        try:
            db_dict = json.loads(value)
        except ValueError:
            db_dict = {}
        return db_dict

    def _build_provider_resource_name_auth(self, authentication):
        if authentication.get("resource_name"):
            auth = {"provider_resource_name": authentication.get("resource_name")}
        else:
            raise KafkaSourceManagerError("Missing provider_resource_name")
        return auth

    def _build_credentials_auth(self, authentication):
        if authentication.get("credentials"):
            auth = {"credentials": authentication.get("credentials")}
        else:
            raise KafkaSourceManagerError("Missing credentials")
        return auth

    def _authentication_for_aws(self, authentication):
        return self._build_provider_resource_name_auth(authentication)

    def _authentication_for_ocp(self, authentication):
        return self._build_provider_resource_name_auth(authentication)

    def _authentication_for_azure(self, authentication):
        return self._build_credentials_auth(authentication)

    def get_authentication_for_provider(self, provider_type, authentication):
        """Build authentication json data for provider type."""
        provider_type = Provider.PROVIDER_CASE_MAPPING.get(provider_type.lower())
        provider_map = {
            Provider.PROVIDER_AWS: self._authentication_for_aws,
            Provider.PROVIDER_AWS_LOCAL: self._authentication_for_aws,
            Provider.PROVIDER_OCP: self._authentication_for_ocp,
            Provider.PROVIDER_AZURE: self._authentication_for_azure,
            Provider.PROVIDER_AZURE_LOCAL: self._authentication_for_azure,
        }
        provider_fn = provider_map.get(provider_type)
        if provider_fn:
            return provider_fn(authentication)

    def _build_provider_bucket(self, billing_source):
        if billing_source.get("bucket") is not None:
            billing = {"bucket": billing_source.get("bucket")}
        else:
            raise KafkaSourceManagerError("Missing bucket")
        return billing

    def _build_provider_data_source(self, billing_source):
        if billing_source.get("data_source"):
            billing = {"data_source": billing_source.get("data_source")}
        else:
            raise KafkaSourceManagerError("Missing data_source")
        return billing

    def _billing_source_for_aws(self, billing_source):
        return self._build_provider_bucket(billing_source)

    def _billing_source_for_ocp(self, billing_source):
        if not billing_source:
            billing_source = {}
        billing_source["bucket"] = ""
        return self._build_provider_bucket(billing_source)

    def _billing_source_for_azure(self, billing_source):
        return self._build_provider_data_source(billing_source)

    def get_billing_source_for_provider(self, provider_type, billing_source):
        """Build billing source json data for provider type."""
        provider_type = Provider.PROVIDER_CASE_MAPPING.get(provider_type.lower())
        provider_map = {
            Provider.PROVIDER_AWS: self._billing_source_for_aws,
            Provider.PROVIDER_AWS_LOCAL: self._billing_source_for_aws,
            Provider.PROVIDER_OCP: self._billing_source_for_ocp,
            Provider.PROVIDER_AZURE: self._billing_source_for_azure,
            Provider.PROVIDER_AZURE_LOCAL: self._billing_source_for_azure,
        }
        provider_fn = provider_map.get(provider_type)
        if provider_fn:
            return provider_fn(billing_source)

    def _handle_bad_requests(self, response):
        """Raise an exception with error message string for Platform Sources."""
        if response.status_code == 401 or response.status_code == 403:
            raise KafkaSourceManagerNonRecoverableError("Insufficient Permissions")
        if response.status_code == 400:
            detail_msg = "Unknown Error"
            errors = response.json().get("errors")
            if errors:
                detail_msg = errors[0].get("detail")
            raise KafkaSourceManagerNonRecoverableError(detail_msg)

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

    def create_provider(self, name, provider_type, authentication, billing_source, source_uuid=None):
        """Call to create provider."""
        connection.set_schema_to_public()
        context, customer, user = self._create_context()
        tenant = Tenant.objects.get(schema_name=customer.schema_name)
        json_data = {
            "name": name,
            "type": provider_type.lower(),
            "authentication": self.get_authentication_for_provider(provider_type, authentication),
            "billing_source": self.get_billing_source_for_provider(provider_type, billing_source),
        }
        if source_uuid:
            json_data["uuid"] = str(source_uuid)

        connection.set_tenant(tenant)
        serializer = ProviderSerializer(data=json_data, context=context)
        if serializer.is_valid(raise_exception=True):
            instance = serializer.save()
        connection.set_schema_to_public()
        return instance

    def update_provider(self, provider_uuid, name, provider_type, authentication, billing_source):
        """Call to update provider."""
        connection.set_schema_to_public()
        context, customer, _ = self._create_context()
        tenant = Tenant.objects.get(schema_name=customer.schema_name)
        json_data = {
            "name": name,
            "type": provider_type.lower(),
            "authentication": self.get_authentication_for_provider(provider_type, authentication),
            "billing_source": self.get_billing_source_for_provider(provider_type, billing_source),
        }
        connection.set_tenant(tenant)
        instance = Provider.objects.get(uuid=provider_uuid)
        serializer = ProviderSerializer(instance=instance, data=json_data, partial=False, context=context)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        connection.set_schema_to_public()
        return instance

    def destroy_provider(self, provider_uuid):
        """Call to destroy provider."""
        connection.set_schema_to_public()
        _, customer, user = self._create_context()
        tenant = Tenant.objects.get(schema_name=customer.schema_name)
        connection.set_tenant(tenant)
        try:
            manager = ProviderManager(provider_uuid)
        except ProviderManagerError:
            LOG.info("Provider does not exist, skipping Provider delete.")
        else:
            manager.remove(user=user, from_sources=True)
        connection.set_schema_to_public()
