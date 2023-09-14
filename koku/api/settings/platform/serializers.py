#
# Copyright 2023 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
from rest_framework import serializers


class ListStringSerializer(serializers.ListField):
    child = serializers.CharField()


class NonEmptyListSerializer(serializers.Serializer):
    projects = ListStringSerializer(allow_empty=False, min_length=1)
