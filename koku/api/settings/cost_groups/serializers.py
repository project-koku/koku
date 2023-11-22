#
# Copyright 2023 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Serializers for Masu API `manifest`."""
from rest_framework import serializers

from api.report.serializers import ExcludeSerializer
from api.report.serializers import FilterSerializer
from api.report.serializers import OrderSerializer
from api.report.serializers import ReportQueryParamSerializer


class CostGroupFilterSerializer(FilterSerializer):
    """Serializer for Cost Group Settings."""

    project_name = serializers.CharField(required=False)
    group = serializers.CharField(required=False)
    default = serializers.BooleanField(required=False)


class CostGroupExcludeSerializer(ExcludeSerializer):
    """Serializer for Cost Group Settings."""

    project_name = serializers.CharField(required=False)
    group = serializers.CharField(required=False)
    default = serializers.BooleanField(required=False)


class CostGroupOrderSerializer(OrderSerializer):
    """Serializer for Cost Group Settings."""

    ORDER_CHOICES = (("asc", "asc"), ("desc", "desc"))

    project_name = serializers.ChoiceField(choices=ORDER_CHOICES, required=False)
    group = serializers.ChoiceField(choices=ORDER_CHOICES, required=False)
    default = serializers.ChoiceField(choices=ORDER_CHOICES, required=False)


class CostGroupQueryParamSerializer(ReportQueryParamSerializer):
    """Serializer for handling query parameters."""

    FILTER_SERIALIZER = CostGroupFilterSerializer
    EXCLUDE_SERIALIZER = CostGroupExcludeSerializer
    ORDER_BY_SERIALIZER = CostGroupOrderSerializer

    order_by_allowlist = ("project_name", "group", "default")
