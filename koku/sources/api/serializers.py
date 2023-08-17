#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Sources Model Serializers."""
import logging
from uuid import uuid4

from django.db import transaction
from rest_framework import serializers

from api.common import error_obj
from api.provider.models import Provider
from api.provider.models import Sources
from api.provider.provider_builder import ProviderBuilder
from api.provider.serializers import LCASE_PROVIDER_CHOICE_LIST
from providers.provider_errors import SkipStatusPush
from sources.api import get_auth_header
from sources.api import get_param_from_header


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
        if not sources_set:
            return 1
        ordered_id = Sources.objects.all().order_by("-source_id").first().source_id
        return ordered_id + 1

    def _validate_offset(self, offset):
        sources_set = Sources.objects.all()
        if not sources_set:
            return 1
        ordered_offset = Sources.objects.all().order_by("-offset").first().offset
        return ordered_offset + 1

    def _validate_account_id(self, account_id):
        return get_param_from_header(self.context.get("request"), "account_number")

    def _validate_org_id(self, account_id):
        return get_param_from_header(self.context.get("request"), "org_id")

    def validate(self, data):
        data["source_id"] = self._validate_source_id(data.get("id"))
        data["offset"] = self._validate_offset(data.get("offset"))
        data["account_id"] = self._validate_account_id(data.get("account_id"))
        data["org_id"] = self._validate_org_id(data.get("org_id"))
        data["source_uuid"] = uuid4()
        return data

    @transaction.atomic
    def create(self, validated_data):
        """Create a source from validated data."""
        auth_header = get_auth_header(self.context.get("request"))
        manager = ProviderBuilder(auth_header, validated_data["account_id"], validated_data["org_id"])
        validated_data["auth_header"] = auth_header
        source = Sources.objects.create(**validated_data)
        try:
            provider = manager.create_provider_from_source(source)
        except SkipStatusPush:
            raise serializers.ValidationError("GCP billing table not ready")
        source.koku_uuid = provider.uuid
        source.provider = provider
        source.save()
        LOG.info("Admin created Source and Provider.")
        return source
