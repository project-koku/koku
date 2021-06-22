#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Serializer for Resource Types."""
from rest_framework import serializers


class ResourceTypeSerializer(serializers.Serializer):
    """Serializer for resource-specific resource-type APIs."""

    value = serializers.CharField()
