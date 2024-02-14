#
# Copyright 2024 Red Hat Inc.
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
        children_to_parent = []
        parent_to_children = []
        already_children = []
        for tag_mapping in mappings:
            if tag_mapping.parent.uuid in children_list:
                parent_to_children.append(str(tag_mapping.parent.uuid))
            if tag_mapping.child.uuid == data["parent"]:
                children_to_parent.append(str(tag_mapping.child.uuid))
            if tag_mapping.child.uuid in children_list:
                already_children.append(str(tag_mapping.child.uuid))
        errors = []
        if parent_to_children:
            errors.append(f"a parent cannot become a child: {parent_to_children}")
        if children_to_parent:
            errors.append(f"a child cannot become a parent: {children_to_parent}")
        if already_children:
            errors.append(f"child already linked to a parent: {already_children}")
        if errors:
            raise serializers.ValidationError(errors)

        enabled_rows = EnabledTagKeys.objects.filter(uuid__in=combined_list, enabled=True)
        if len(combined_list) != enabled_rows.count():
            # Ensure that the parent & child uuids are enabled.
            raise serializers.ValidationError("Invalid or disabled uuid provided.")

        return data


class TagMappingListSerializer(serializers.Serializer):
    def to_representation(self, instance):
        return {"data": [TagMappingSerializer(item).data for item in instance]}
