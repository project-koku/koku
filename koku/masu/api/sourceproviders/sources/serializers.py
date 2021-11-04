#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Serializers for Masu API `manifest`."""
from rest_framework import serializers

from api.provider.models import Sources


class SourceSerializer(serializers.Serializer):
    """Serializer for Soruces."""

    class Meta:
        model = Sources

    source_id = serializers.IntegerField()
    source_uuid = serializers.UUIDField()
    name = serializers.CharField()
    auth_header = serializers.CharField()
    offset = serializers.IntegerField()
    account_id = serializers.IntegerField()
    source_type = serializers.CharField()
    authentication = serializers.JSONField()
    billing_source = serializers.JSONField()
    koku_uuid = serializers.UUIDField()
    pending_delete = serializers.BooleanField()
    pending_update = serializers.BooleanField()
    out_of_order_delete = serializers.BooleanField()
    status = serializers.JSONField()
    paused = serializers.BooleanField()
