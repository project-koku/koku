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
"""Sources Model Serializers."""
import logging
from socket import gaierror
from uuid import uuid4
from xmlrpc.client import Fault
from xmlrpc.client import ProtocolError
from xmlrpc.client import ServerProxy

from django.db import transaction
from rest_framework import serializers

from api.common import error_obj
from api.provider.models import Provider
from api.provider.models import Sources
from api.provider.provider_builder import ProviderBuilder
from api.provider.serializers import LCASE_PROVIDER_CHOICE_LIST
from koku.settings import SOURCES_CLIENT_BASE_URL
from providers.provider_errors import SkipStatusPush
from sources.api import get_account_from_header
from sources.api import get_auth_header
from sources.storage import _update_authentication
from sources.storage import _update_billing_source
from sources.storage import get_source_instance
from sources.storage import SourcesStorageError


LOG = logging.getLogger(__name__)

ALLOWED_BILLING_SOURCE_PROVIDERS = (
    Provider.PROVIDER_AWS,
    Provider.PROVIDER_AWS_LOCAL,
    Provider.PROVIDER_AZURE,
    Provider.PROVIDER_AZURE_LOCAL,
    Provider.PROVIDER_GCP,
    Provider.PROVIDER_GCP_LOCAL,
)
ALLOWED_AUTHENTICATION_PROVIDERS = (Provider.PROVIDER_AZURE, Provider.PROVIDER_AZURE_LOCAL)


class SourcesDependencyError(Exception):
    """General Exception for sources dependency errors."""


def validate_field(data, valid_fields, key):
    """Validate a field."""
    message = f"One or more required fields is invalid/missing. Required fields are {valid_fields}"
    diff = set(valid_fields) - set(data)
    if not diff:
        return data
    raise serializers.ValidationError(error_obj(key, message))


class SourcesSerializer(serializers.ModelSerializer):
    """Serializer for the Sources model."""

    id = serializers.SerializerMethodField("get_source_id", read_only=True)
    name = serializers.CharField(max_length=256, required=False, allow_null=False, allow_blank=False, read_only=True)
    authentication = serializers.JSONField(required=False)
    billing_source = serializers.JSONField(required=False)
    source_type = serializers.CharField(
        max_length=50, required=False, allow_null=False, allow_blank=False, read_only=True
    )
    uuid = serializers.SerializerMethodField("get_source_uuid", read_only=True)

    class Meta:
        """Metadata for the serializer."""

        model = Sources
        fields = ("id", "uuid", "name", "source_type", "authentication", "billing_source")

    def get_source_id(self, obj):
        """Get the source_id."""
        return obj.source_id

    def get_source_uuid(self, obj):
        """Get the source_uuid."""
        return obj.source_uuid

    def update(self, instance, validated_data):
        """Update a Provider instance from validated data."""
        billing_source = validated_data.get("billing_source")
        authentication = validated_data.get("authentication")

        try:
            with ServerProxy(SOURCES_CLIENT_BASE_URL) as sources_client:
                if billing_source:
                    billing_source = _update_billing_source(instance, billing_source)
                    sources_client.update_billing_source(instance.source_id, billing_source)
                if authentication:
                    authentication = _update_authentication(instance, authentication)
                    sources_client.update_authentication(instance.source_id, authentication)
        except Fault as error:
            LOG.error(f"Sources update error: {error}")
            raise SourcesStorageError(str(error))
        except (ConnectionRefusedError, gaierror, ProtocolError) as error:
            LOG.error(f"Sources update dependency error: {error}")
            raise SourcesDependencyError(f"Sources-client: {error}")
        return get_source_instance(instance.source_id)


class AdminSourcesSerializer(SourcesSerializer):
    """Source serializer specific to administration."""

    name = serializers.CharField(max_length=256, required=True, allow_null=False, allow_blank=False)
    source_type = serializers.CharField(max_length=50, required=True, allow_null=False, allow_blank=False)

    def validate_source_type(self, source_type):
        """Validate credentials field."""
        if source_type.lower() in LCASE_PROVIDER_CHOICE_LIST:
            return Provider.PROVIDER_CASE_MAPPING.get(source_type.lower())
        key = "source_type"
        message = f"Invalid source_type, {source_type}, provided."
        raise serializers.ValidationError(error_obj(key, message))

    def _validate_source_id(self, source_id):
        sources_set = Sources.objects.all()
        if sources_set:
            ordered_id = Sources.objects.all().order_by("-source_id").first().source_id
            return ordered_id + 1
        else:
            return 1

    def _validate_offset(self, offset):
        sources_set = Sources.objects.all()
        if sources_set:
            ordered_offset = Sources.objects.all().order_by("-offset").first().offset
            return ordered_offset + 1
        else:
            return 1

    def _validate_account_id(self, account_id):
        return get_account_from_header(self.context.get("request"))

    def validate(self, data):
        data["source_id"] = self._validate_source_id(data.get("id"))
        data["offset"] = self._validate_offset(data.get("offset"))
        data["account_id"] = self._validate_account_id(data.get("account_id"))
        data["source_uuid"] = uuid4()
        return data

    @transaction.atomic
    def create(self, validated_data):
        """Create a source from validated data."""
        auth_header = get_auth_header(self.context.get("request"))
        manager = ProviderBuilder(auth_header)
        validated_data["auth_header"] = auth_header
        source = Sources.objects.create(**validated_data)
        try:
            provider = manager.create_provider_from_source(source)
        except SkipStatusPush:
            raise serializers.ValidationError("GCP billing table not ready")
        source.koku_uuid = provider.uuid
        source.save()
        LOG.info("Admin created Source and Provider.")
        return source
