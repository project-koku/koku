#
# Copyright 2023 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Serializer for aws category resource types."""
import logging

from rest_framework import serializers

LOG = logging.getLogger(__name__)


class AWSCategorySerializer(serializers.Serializer):
    """Serializer for resource-specific resource-type APIs."""

    key = serializers.CharField()
    values = serializers.ListField()
    enabled = serializers.CharField(required=False)
