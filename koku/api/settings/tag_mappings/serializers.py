#
# Copyright 2023 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Serializers for Tag Mappings."""
from rest_framework import serializers
from reporting.provider.all.models import TagMapping


class TagMappingSerializer(serializers.ModelSerializer):
    class Meta:
        model = TagMapping
        fields = ['parent', 'child']

        from rest_framework import serializers


from reporting.provider.all.models import TagMapping


class TagMappingSerializer(serializers.ModelSerializer):
    class Meta:
        model = TagMapping
        fields = ['parent', 'child']

    def validate(self, data):
        parent = data.get('parent')
        child = data.get('child')

        if TagMapping.objects.filter(child=parent).exists():
            raise serializers.ValidationError("A child can't become a parent.")

        if TagMapping.objects.filter(parent=child).exists():
            raise serializers.ValidationError("A parent can't become a child.")

        return data
