#
# Copyright 2023 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Serializers for Masu API `manifest`."""
from rest_framework import serializers

from api.provider.models import Provider
from reporting.provider.all.models import EnabledTagKeys


class SettingsTagSerializer(serializers.Serializer):
    """Serializer for Tag Settings."""

    uuid = serializers.UUIDField()
    key = serializers.CharField()
    enabled = serializers.BooleanField()
    provider_type = serializers.ChoiceField(choices=Provider.PROVIDER_CHOICES)

    class Meta:
        model = EnabledTagKeys

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["source_type"] = data.pop("provider_type")
        return data


class ListUUIDSerializer(serializers.ListField):
    child = serializers.UUIDField(error_messages={"invalid": "invalid uuid supplied."})


class SettingsTagIDSerializer(serializers.Serializer):
    """Serializer for id list for enabling/disabling tags"""

    id_list = ListUUIDSerializer(allow_empty=False, min_length=1)
