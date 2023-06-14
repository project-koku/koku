#
# Copyright 2023 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Serializers for Masu API `manifest`."""
from rest_framework import serializers

from reporting.provider.aws.models import AWSEnabledCategoryKeys


class SettingsAWSCategoryKeySerializer(serializers.Serializer):
    """Serializer for Tag Settings."""

    uuid = serializers.UUIDField()
    key = serializers.CharField()
    enabled = serializers.BooleanField()

    class Meta:
        model = AWSEnabledCategoryKeys


class SettingsAWSCategoryKeyIDSerializer(serializers.Serializer):
    """Serializer for id list for enabling/disabling tags"""

    id_list = serializers.ListField(child=serializers.UUIDField(error_messages={"invalid": "invalid uuid supplied."}))
