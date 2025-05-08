#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Provider Builder."""
import json
import logging
from base64 import b64decode

from django.db import connection
from django_tenants.utils import schema_exists
from rest_framework.exceptions import ValidationError

from api.models import Customer
from api.models import Provider
from api.models import Tenant
from api.models import User
from api.provider.provider_manager import ProviderManager
from api.provider.provider_manager import ProviderManagerAuthorizationError
from api.provider.provider_manager import ProviderManagerError
from api.provider.serializers import ProviderSerializer
from koku.cache import invalidate_cache_for_tenant_and_cache_key
from koku.cache import SOURCES_CACHE_PREFIX
from koku.middleware import IdentityHeaderMiddleware

LOG = logging.getLogger(__name__)


class ProviderBuilderError(ValidationError):
    """ProviderBuilder Error."""

    pass


class ProviderBuilder:
    """Provider Builder to create koku providers."""

    def __init__(self, auth_header, account_number, org_id):
        """Initialize the client."""
        self.account_number = account_number
        self.org_id = org_id
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

    def _build_credentials_auth(self, provider_type, authentication):
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
        if encoded_auth_header := self._identity_header.get("x-rh-identity"):
            identity = json.loads(b64decode(encoded_auth_header)).get("identity", {})
            username = identity.get("user", {}).get("username")
            email = identity.get("user", {}).get("email")
            identity_type = identity.get("type", "User")
            auth_type = identity.get("auth_type")

            if identity_type == "System" and auth_type == "uhc-auth":
                username = identity.get("system", {}).get("cluster_id")
                email = ""

            if identity_type == "ServiceAccount":
                username = identity.get("service_account", {}).get("username")
                email = ""

            try:
                customer = Customer.objects.filter(org_id=self.org_id).get()
            except Customer.DoesNotExist:
                customer = IdentityHeaderMiddleware.create_customer(self.account_number, self.org_id, "POST")
            user = User(username=username, email=email, customer=customer)

        context = {"user": user, "customer": customer}
        return context, customer, user

    def _tenant_for_schema(self, schema_name):
        """Get or create tenant for schema."""
        tenant, _ = Tenant.objects.get_or_create(schema_name=schema_name)
        if not schema_exists(schema_name):
            tenant.create_schema()
            msg = f"Created tenant {schema_name}"
            LOG.info(msg)
        return tenant

    def create_provider_from_source(self, source):
        """Call to create provider."""
        connection.set_schema_to_public()
        context, customer, _ = self._create_context()
        tenant = self._tenant_for_schema(customer.schema_name)
        provider_type = source.source_type
        json_data = {
            "name": source.name,
            "type": provider_type.lower(),
            "authentication": self._build_credentials_auth(provider_type, source.authentication),
            "billing_source": self.get_billing_source_for_provider(provider_type, source.billing_source),
        }
        if source.source_uuid:
            json_data["uuid"] = str(source.source_uuid)

        connection.set_tenant(tenant)
        serializer = ProviderSerializer(data=json_data, context=context)
        try:
            if serializer.is_valid(raise_exception=True):
                instance = serializer.save()
        finally:
            invalidate_cache_for_tenant_and_cache_key(customer.schema_name, SOURCES_CACHE_PREFIX)
            connection.set_schema_to_public()
        return instance

    def update_provider_from_source(self, source):
        """Call to update provider."""
        connection.set_schema_to_public()
        context, customer, _ = self._create_context()
        tenant = self._tenant_for_schema(customer.schema_name)
        provider_type = source.source_type
        json_data = {
            "name": source.name,
            "type": provider_type.lower(),
            "authentication": self._build_credentials_auth(provider_type, source.authentication),
            "billing_source": self.get_billing_source_for_provider(provider_type, source.billing_source),
            "paused": source.paused,
        }
        connection.set_tenant(tenant)
        instance = Provider.objects.get(uuid=source.koku_uuid)
        serializer = ProviderSerializer(instance=instance, data=json_data, partial=False, context=context)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        connection.set_schema_to_public()
        invalidate_cache_for_tenant_and_cache_key(customer.schema_name, SOURCES_CACHE_PREFIX)
        return instance

    def destroy_provider(self, provider_uuid, retry_count=None):
        """Call to destroy provider."""
        connection.set_schema_to_public()
        _, customer, user = self._create_context()
        tenant = self._tenant_for_schema(customer.schema_name)
        connection.set_tenant(tenant)
        try:
            manager = ProviderManager(provider_uuid)
        except ProviderManagerError:
            LOG.info("Provider does not exist, skipping Provider delete.")
            manager = None
        if manager:
            try:
                manager.remove(user=user, from_sources=True, retry_count=retry_count)
            except ProviderManagerAuthorizationError as err:
                LOG.warning(str(err), exc_info=err)

        invalidate_cache_for_tenant_and_cache_key(customer.schema_name, SOURCES_CACHE_PREFIX)
        connection.set_schema_to_public()
