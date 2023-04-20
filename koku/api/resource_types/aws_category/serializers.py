#
# Copyright 2023 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Serializer for aws category resource types."""
from rest_framework import serializers


class AWSCategorySerializer(serializers.Serializer):
    """Serializer for resource-specific resource-type APIs."""

    key = serializers.CharField()
    values = serializers.ListField()
    enabled = serializers.CharField()


class AWSCategoryKeyOnlySerializer(serializers.BaseSerializer):
    child = serializers.CharField()

    def to_representation(self, data):
        return data
