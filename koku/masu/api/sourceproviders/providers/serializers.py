#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Serializers for Masu API `manifest`."""
from rest_framework import serializers

from api.provider.models import Provider


class ProviderSerializer(serializers.Serializer):
    """Serializer for Providers."""

    class Meta:
        model = Provider

    uuid = serializers.UUIDField()
    name = serializers.CharField()
    type = serializers.CharField()
    setup_complete = serializers.BooleanField()
    created_timestamp = serializers.DateTimeField()
    data_updated_timestamp = serializers.DateTimeField()
    active = serializers.BooleanField()
    authentication_id = serializers.PrimaryKeyRelatedField(read_only=True)
    billing_source_id = serializers.PrimaryKeyRelatedField(read_only=True)
    created_by_id = serializers.PrimaryKeyRelatedField(read_only=True)
    customer_id = serializers.PrimaryKeyRelatedField(read_only=True)
    infrastructure_id = serializers.PrimaryKeyRelatedField(read_only=True)
    paused = serializers.BooleanField()
