#
# Copyright 2023 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Serializers for Tag Mappings."""
from django.db.models import Q
from rest_framework import serializers

from reporting.provider.all.models import EnabledTagKeys
from reporting.provider.all.models import TagMapping


class EnabledTagKeysSerializer(serializers.ModelSerializer):
    source_type = serializers.CharField(source="provider_type")

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


class AddChildSerializer(serializers.Serializer):
    parent = serializers.UUIDField()
    children = serializers.ListField(child=serializers.UUIDField())

    def validate(self, data):
        """This function validates the options and returns the enabled tag rows."""
        children_list = data["children"]
        combined_list = [data["parent"]] + children_list
        mappings = TagMapping.objects.filter(Q(parent__uuid__in=combined_list) | Q(child__uuid__in=combined_list))
        for tag_mapping in mappings:
            if tag_mapping.parent.uuid in children_list:
                raise serializers.ValidationError("A parent can't become a child.")
            if tag_mapping.child.uuid == data["parent"]:
                raise serializers.ValidationError("A child can't become a parent.")
            if tag_mapping.child.uuid in children_list:
                children_list.remove(tag_mapping.child.uuid)
                combined_list.remove(tag_mapping.child.uuid)
        if len(children_list) == 0:
            raise serializers.ValidationError("No new children to add.")

        enabled_rows = EnabledTagKeys.objects.filter(uuid__in=combined_list, enabled=True)
        if len(combined_list) != enabled_rows.count():
            # Ensure that the parent & child uuids are enabled.
            raise serializers.ValidationError("Invalid or disabled uuid provided.")

        data["children"] = children_list
        return data


class TagMappingListSerializer(serializers.Serializer):
    def to_representation(self, instance):
        return {"data": [TagMappingSerializer(item).data for item in instance]}
