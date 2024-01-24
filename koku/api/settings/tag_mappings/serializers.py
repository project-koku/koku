#
# Copyright 2023 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Serializers for Tag Mappings."""
from rest_framework import serializers
from reporting.provider.all.models import TagMapping, EnabledTagKeys


class EnabledTagKeysSerializer(serializers.ModelSerializer):
    source_type = serializers.CharField(source='provider_type')

    class Meta:
        model = EnabledTagKeys
        fields = ["uuid", "key", "source_type"]


class TagMappingSerializer(serializers.Serializer):
    parent = EnabledTagKeysSerializer()
    child = EnabledTagKeysSerializer()

    def to_representation(self, instance):
        return {
            "parent": EnabledTagKeysSerializer(instance.parent).data,
            "child": EnabledTagKeysSerializer(instance.child).data,
        }

    def validate(self, data):
        parent = data["parent"]
        child = data["child"]

        if TagMapping.objects.filter(child=parent["uuid"]).exists():
            raise serializers.ValidationError("A child can't become a parent.")

        if TagMapping.objects.filter(parent=child["uuid"]).exists():
            raise serializers.ValidationError("A parent can't become a child.")

        return data


class TagMappingListSerializer(serializers.Serializer):
    def to_representation(self, instance):
        return {"data": [TagMappingSerializer(item).data for item in instance]}
