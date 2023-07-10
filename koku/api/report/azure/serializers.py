#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Azure Report Serializers."""
from rest_framework import serializers

from api.report.serializers import ExcludeSerializer as BaseExcludeSerializer
from api.report.serializers import FilterSerializer as BaseFilterSerializer
from api.report.serializers import GroupSerializer
from api.report.serializers import OrderSerializer
from api.report.serializers import ReportQueryParamSerializer
from api.report.serializers import StringOrListField


class AzureGroupBySerializer(GroupSerializer):
    """Serializer for handling query parameter group_by."""

    _opfields = ("subscription_guid", "resource_location", "instance_type", "service_name")

    subscription_guid = StringOrListField(child=serializers.CharField(), required=False)
    resource_location = StringOrListField(child=serializers.CharField(), required=False)
    instance_type = StringOrListField(child=serializers.CharField(), required=False)
    service_name = StringOrListField(child=serializers.CharField(), required=False)


class AzureOrderBySerializer(OrderSerializer):
    """Serializer for handling query parameter order_by."""

    _opfields = (
        "subscription_guid",
        "subscription_name",
        "resource_location",
        "instance_type",
        "service_name",
        "date",
    )

    subscription_guid = serializers.ChoiceField(choices=OrderSerializer.ORDER_CHOICES, required=False)
    subscription_name = serializers.ChoiceField(choices=OrderSerializer.ORDER_CHOICES, required=False)
    resource_location = serializers.ChoiceField(choices=OrderSerializer.ORDER_CHOICES, required=False)
    instance_type = serializers.ChoiceField(choices=OrderSerializer.ORDER_CHOICES, required=False)
    service_name = serializers.ChoiceField(choices=OrderSerializer.ORDER_CHOICES, required=False)
    date = serializers.DateField(required=False)


class AzureFilterSerializer(BaseFilterSerializer):
    """Serializer for handling query parameter filter."""

    _opfields = ("subscription_guid", "resource_location", "instance_type", "service_name")

    subscription_guid = StringOrListField(child=serializers.CharField(), required=False)
    resource_location = StringOrListField(child=serializers.CharField(), required=False)
    instance_type = StringOrListField(child=serializers.CharField(), required=False)
    service_name = StringOrListField(child=serializers.CharField(), required=False)


class AzureExcludeSerializer(BaseExcludeSerializer):
    """Serializer for handling query parameter exclude."""

    _opfields = ("subscription_guid", "resource_location", "instance_type", "service_name")

    subscription_guid = StringOrListField(child=serializers.CharField(), required=False)
    resource_location = StringOrListField(child=serializers.CharField(), required=False)
    instance_type = StringOrListField(child=serializers.CharField(), required=False)
    service_name = StringOrListField(child=serializers.CharField(), required=False)


class AzureQueryParamSerializer(ReportQueryParamSerializer):
    """Serializer for handling query parameters."""

    GROUP_BY_SERIALIZER = AzureGroupBySerializer
    ORDER_BY_SERIALIZER = AzureOrderBySerializer
    FILTER_SERIALIZER = AzureFilterSerializer
    EXCLUDE_SERIALIZER = AzureExcludeSerializer

    # Tuples are (key, display_name)
    DELTA_CHOICES = (("usage", "usage"), ("cost", "cost"))

    delta = serializers.ChoiceField(choices=DELTA_CHOICES, required=False)
