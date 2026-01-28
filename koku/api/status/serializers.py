#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Serializer to capture server status."""
from rest_framework import serializers

from .models import Status


class ConfigSerializer(serializers.Serializer):
    """Serializer for the Config class"""

    debug = serializers.BooleanField(source="DEBUG", read_only=True)
    masu_retain_num_months = serializers.IntegerField(source="MASU_RETAIN_NUM_MONTHS", read_only=True)


class StatusSerializer(serializers.Serializer):
    """Serializer for the Status model."""

    config = ConfigSerializer()

    class Meta:
        """Metadata for the serializer."""

        model = Status
        fields = "__all__"
