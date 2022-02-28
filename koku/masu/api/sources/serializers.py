#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Serializers for Masu sources API."""
from rest_framework import serializers

from api.iam.models import Customer
from api.provider.models import Provider
from api.provider.models import ProviderInfrastructureMap
from api.provider.models import Sources


class CustomerSerializer(serializers.Serializer):
    """Serializer for Customer."""

    class Meta:
        model = Customer

    id = serializers.IntegerField()
    schema_name = serializers.CharField()


class ProviderInfrastructureSerializer(serializers.Serializer):
    """Serializer for ProviderInfrastructureMap."""

    class Meta:
        model = ProviderInfrastructureMap

    id = serializers.IntegerField()
    infrastructure_type = serializers.CharField()
    infrastructure_provider_id = serializers.UUIDField()


class ProviderSerializer(serializers.Serializer):
    """Serializer for Provider."""

    class Meta:
        model = Provider

    uuid = serializers.UUIDField()
    setup_complete = serializers.BooleanField()
    created_timestamp = serializers.DateTimeField()
    data_updated_timestamp = serializers.DateTimeField()
    active = serializers.BooleanField()
    paused = serializers.BooleanField()
    customer = CustomerSerializer()
    infrastructure = ProviderInfrastructureSerializer(required=False)


class SourceSerializer(serializers.Serializer):
    """Serializer for Soruces."""

    class Meta:
        model = Sources

    source_id = serializers.IntegerField()
    source_uuid = serializers.UUIDField()
    name = serializers.CharField()
    auth_header = serializers.CharField()
    offset = serializers.IntegerField()
    account_id = serializers.CharField()
    source_type = serializers.CharField()
    authentication = serializers.JSONField()
    billing_source = serializers.JSONField()
    koku_uuid = serializers.UUIDField()
    pending_delete = serializers.BooleanField()
    pending_update = serializers.BooleanField()
    out_of_order_delete = serializers.BooleanField()
    status = serializers.JSONField()
    paused = serializers.BooleanField()
    provider = ProviderSerializer()
