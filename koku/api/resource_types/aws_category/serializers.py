#
# Copyright 2023 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Serializer for aws category resource types."""
from rest_framework import serializers


class AWSCategorySerializer(serializers.Serializer):
    """Serializer for resource-specific resource-type APIs."""

    key = serializers.CharField(required=False)
    values = serializers.ListField(required=False)
    enabled = serializers.CharField(required=False)
    value = serializers.CharField(required=False)
