#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""GCP Report Serializers."""
from rest_framework import serializers

from api.report.serializers import ExcludeSerializer as BaseExcludeSerializer
from api.report.serializers import FilterSerializer as BaseFilterSerializer
from api.report.serializers import GroupSerializer
from api.report.serializers import OrderSerializer
from api.report.serializers import ReportQueryParamSerializer
from api.report.serializers import StringOrListField


class GCPGroupBySerializer(GroupSerializer):
    """Serializer for handling query parameter group_by."""

    _opfields = ("account", "region", "service", "gcp_project", "instance_type")

    account = StringOrListField(child=serializers.CharField(), required=False)
    region = StringOrListField(child=serializers.CharField(), required=False)
    service = StringOrListField(child=serializers.CharField(), required=False)
    gcp_project = StringOrListField(child=serializers.CharField(), required=False)
    instance_type = StringOrListField(child=serializers.CharField(), required=False)


class GCPOrderBySerializer(OrderSerializer):
    """Serializer for handling query parameter order_by."""

    _opfields = ("account", "region", "service", "gcp_project", "date")

    account = serializers.ChoiceField(choices=OrderSerializer.ORDER_CHOICES, required=False)
    region = serializers.ChoiceField(choices=OrderSerializer.ORDER_CHOICES, required=False)
    service = serializers.ChoiceField(choices=OrderSerializer.ORDER_CHOICES, required=False)
    gcp_project = serializers.ChoiceField(choices=OrderSerializer.ORDER_CHOICES, required=False)
    date = serializers.DateField(required=False)


class GCPFilterSerializer(BaseFilterSerializer):
    """Serializer for handling query parameter filter."""

    _opfields = ("account", "service", "region", "gcp_project")

    account = StringOrListField(child=serializers.CharField(), required=False)
    service = StringOrListField(child=serializers.CharField(), required=False)
    region = StringOrListField(child=serializers.CharField(), required=False)
    gcp_project = StringOrListField(child=serializers.CharField(), required=False)


class GCPExcludeSerializer(BaseExcludeSerializer):
    """Serializer for handling query parameter exclude."""

    _opfields = ("account", "service", "region", "gcp_project")

    account = StringOrListField(child=serializers.CharField(), required=False)
    service = StringOrListField(child=serializers.CharField(), required=False)
    region = StringOrListField(child=serializers.CharField(), required=False)
    gcp_project = StringOrListField(child=serializers.CharField(), required=False)


class GCPQueryParamSerializer(ReportQueryParamSerializer):
    """Serializer for handling GCP query parameters."""

    GROUP_BY_SERIALIZER = GCPGroupBySerializer
    ORDER_BY_SERIALIZER = GCPOrderBySerializer
    FILTER_SERIALIZER = GCPFilterSerializer
    EXCLUDE_SERIALIZER = GCPExcludeSerializer

    # Tuples are (key, display_name)
    DELTA_CHOICES = (("usage", "usage"), ("cost", "cost"), ("cost_total", "cost_total"))

    delta = serializers.ChoiceField(choices=DELTA_CHOICES, required=False)
