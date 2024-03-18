#
# Copyright 2024 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Serializers for Tag Mappings."""
from collections import defaultdict

from django.db.models import Q
from rest_framework import serializers

from reporting.provider.all.models import EnabledTagKeys
from reporting.provider.all.models import TagMapping


class ViewOptionsSerializer(serializers.ModelSerializer):
    """Intended to be used in conjuntion with the CostModelAnnotationMixin."""

    source_type = serializers.CharField(source="provider_type")
    cost_model_id = serializers.UUIDField()

    class Meta:
        model = EnabledTagKeys
        fields = ["uuid", "key", "source_type", "cost_model_id"]


class TagMappingSerializer(serializers.ModelSerializer):
    class Meta:
        model = TagMapping
        fields = ["parent", "child"]

    def to_representation(self, instance):
        return {
            "parent": {
                "uuid": instance.parent.uuid,
                "key": instance.parent.key,
                "source_type": instance.parent.provider_type,
            },
            "child": {
                "uuid": instance.child.uuid,
                "key": instance.child.key,
                "source_type": instance.child.provider_type,
            },
        }


class AddChildSerializer(serializers.Serializer):
    parent = serializers.UUIDField()
    children = serializers.ListField(child=serializers.UUIDField())

    def validate(self, data):
        """This function validates the options and returns the enabled tag rows."""
        children_list = data["children"]
        combined_list = [data["parent"]] + children_list
        enabled_rows = EnabledTagKeys.objects.filter(uuid__in=combined_list, enabled=True)
        if len(combined_list) != enabled_rows.count() or not children_list:
            # Ensure that the parent & child uuids are enabled.
            raise serializers.ValidationError("Invalid, disabled, or missing uuid provided.")
        mappings = TagMapping.objects.filter(Q(parent__uuid__in=combined_list) | Q(child__uuid__in=combined_list))
        errors = defaultdict(list)
        for tag_mapping in mappings:
            if tag_mapping.parent.uuid in children_list:
                errors["a parent cannot become a child:"].append(str(tag_mapping.parent.uuid))
            if tag_mapping.child.uuid == data["parent"]:
                errors["a child cannot become a parent:"].append(str(tag_mapping.child.uuid))
            if tag_mapping.child.uuid in children_list:
                errors["child already linked to a parent:"].append(str(tag_mapping.child.uuid))

        # Checks if a child key is associated with a cost model
        child_keys = enabled_rows.exclude(uuid=data["parent"]).values_list("key", flat=True)
        intersecting_tags = set(child_keys) & set(self.context.keys())
        for intersecting_tag in intersecting_tags:
            metadata = {}
            metadata["cost_model_id"] = self.context[intersecting_tag].get("cost_model_id")
            metadata["child_key"] = intersecting_tag
            errors["child is being used in a cost model:"].append(metadata)
        if errors:
            formatted_errors = [f"{log_msg} {log_list}" for log_msg, log_list in errors.items()]
            raise serializers.ValidationError(formatted_errors)
        return data
