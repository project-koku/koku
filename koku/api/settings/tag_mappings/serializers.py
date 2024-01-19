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
