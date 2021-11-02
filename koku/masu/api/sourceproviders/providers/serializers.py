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

    uuid = serializers.IntegerField()
    name = serializers.CharField()
    authentication = serializers.PrimaryKeyRelatedField(read_only=True)
    billing_source = serializers.PrimaryKeyRelatedField(read_only=True)
    customer = serializers.PrimaryKeyRelatedField(read_only=True)
    created_by = serializers.PrimaryKeyRelatedField(read_only=True)
    setup_complete = serializers.BooleanField()
    created_timestamp = serializers.DateTimeField()
    data_updated_timestamp = serializers.DateTimeField()
    active = serializers.BooleanField()
    paused = serializers.BooleanField()
    infrastructure = serializers.PrimaryKeyRelatedField(read_only=True)
