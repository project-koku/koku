#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Serializer for Resource Types."""
from rest_framework import serializers


class ResourceTypeSerializer(serializers.Serializer):
    """Serializer for resource-specific resource-type APIs."""

    extra_kwargs = {"test": {"error_messages": {"required": "Give yourself a username"}}}
    cluster_alias = serializers.CharField(source="ocp_cluster_alias", required=False)
    account_alias = serializers.CharField(source="alias", required=False)
    instance_name = serializers.CharField(source="ec2_instance_name", required=False)
    value = serializers.CharField()
