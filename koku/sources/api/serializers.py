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
from uuid import uuid4

from django.db import transaction
from django.utils.translation import ugettext as _
from rest_framework import serializers

from api.provider.models import Provider
from api.provider.models import Sources
from api.provider.serializers import LCASE_PROVIDER_CHOICE_LIST
from sources.api import get_account_from_header
from sources.api import get_auth_header
from sources.kafka_source_manager import KafkaSourceManager
from sources.storage import SourcesStorageError


def error_obj(key, message):
    """Create an error object."""
    error = {key: [_(message)]}
    return error


def validate_field(data, valid_fields, key):
    """Validate a field."""
    message = "One or more required fields is invalid/missing. " + f"Required fields are {valid_fields}"
    diff = set(valid_fields) - set(data)
    if not diff:
        return data
    raise serializers.ValidationError(error_obj(key, message))


class SourcesSerializer(serializers.ModelSerializer):
    """Serializer for the Sources model."""

    source_id = serializers.IntegerField(required=False, read_only=True)
    name = serializers.CharField(max_length=256, required=False, allow_null=False, allow_blank=False, read_only=True)
    authentication = serializers.JSONField(required=False)
    billing_source = serializers.JSONField(required=False)
    source_type = serializers.CharField(
        max_length=50, required=False, allow_null=False, allow_blank=False, read_only=True
    )
    koku_uuid = serializers.CharField(
        max_length=512, required=False, allow_null=False, allow_blank=False, read_only=True
    )
    source_uuid = serializers.CharField(
        max_length=512, required=False, allow_null=False, allow_blank=False, read_only=True
    )

    # pylint: disable=too-few-public-methods
    class Meta:
        """Metadata for the serializer."""

        model = Sources
        fields = ("source_id", "name", "source_type", "authentication", "billing_source", "koku_uuid", "source_uuid")

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
        if instance.source_type not in (Provider.PROVIDER_AWS, Provider.PROVIDER_AZURE):
            raise SourcesStorageError(f"Option not supported by " f"source type {instance.source_type}.")
        self._validate_billing_source(instance.source_type, billing_source)
        instance.billing_source = billing_source
        if instance.koku_uuid:
            instance.pending_update = True
            instance.save(update_fields=["billing_source", "pending_update"])
        else:
            instance.save()

    def _update_authentication(self, instance, authentication):
        if instance.source_type not in (Provider.PROVIDER_AZURE,):
            raise SourcesStorageError(f"Option not supported by " f"source type {instance.source_type}.")
        auth_dict = instance.authentication
        if not auth_dict.get("credentials"):
            auth_dict["credentials"] = {"subscription_id": None}
        subscription_id = authentication.get("credentials", {}).get("subscription_id")
        auth_dict["credentials"]["subscription_id"] = subscription_id
        instance.authentication = auth_dict
        if instance.koku_uuid:
            instance.pending_update = True
            instance.save(update_fields=["authentication", "pending_update"])
        else:
            instance.save()

    def update(self, instance, validated_data):
        """Update a Provider instance from validated data."""
        billing_source = validated_data.get("billing_source")
        authentication = validated_data.get("authentication")

        if billing_source:
            self._update_billing_source(instance, billing_source)

        if authentication:
            self._update_authentication(instance, authentication)

        return instance


class AdminSourcesSerializer(SourcesSerializer):
    """Source serializer specific to administration."""

    name = serializers.CharField(max_length=256, required=False, allow_null=False, allow_blank=False)
    source_type = serializers.CharField(max_length=50, required=False, allow_null=False, allow_blank=False)

    def validate_source_type(self, source_type):
        """Validate credentials field."""
        if source_type.lower() in LCASE_PROVIDER_CHOICE_LIST:
            return source_type
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
        data["source_id"] = self._validate_source_id(data.get("source_id"))
        data["offset"] = self._validate_offset(data.get("offset"))
        data["account_id"] = self._validate_account_id(data.get("account_id"))
        data["source_uuid"] = uuid4()
        return data

    @transaction.atomic
    def create(self, validated_data):
        """Create a source from validated data."""
        auth_header = get_auth_header(self.context.get("request"))
        manager = KafkaSourceManager(auth_header)
        provider = manager.create_provider(
            validated_data.get("name"),
            validated_data.get("source_type"),
            validated_data.get("authentication"),
            validated_data.get("billing_source"),
            validated_data.get("source_uuid"),
        )
        validated_data["koku_uuid"] = provider.uuid
        source = Sources.objects.create(**validated_data)
        return source
