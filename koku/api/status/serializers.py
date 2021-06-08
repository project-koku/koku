#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Serializer to capture server status."""
from rest_framework import serializers

from .models import Status


class StatusSerializer(serializers.Serializer):
    """Serializer for the Status model."""

    api_version = serializers.IntegerField()
    commit = serializers.CharField()
    modules = serializers.DictField()
    platform_info = serializers.DictField()
    python_version = serializers.CharField()
    rbac_cache_ttl = serializers.CharField()

    class Meta:
        """Metadata for the serializer."""

        model = Status
        fields = "__all__"
