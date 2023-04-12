#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""OCP Report Serializers."""
from django.utils.translation import ugettext as _
from rest_framework import serializers

from api.models import Provider
from api.report.serializers import ExcludeSerializer as BaseExcludeSerializer
from api.report.serializers import FilterSerializer as BaseFilterSerializer
from api.report.serializers import GroupSerializer
from api.report.serializers import OrderSerializer
from api.report.serializers import ReportQueryParamSerializer
from api.report.serializers import StringOrListField


class OCPGroupBySerializer(GroupSerializer):
    """Serializer for handling query parameter group_by."""

    _opfields = ("project", "cluster", "node")

    cluster = StringOrListField(child=serializers.CharField(), required=False)
    project = StringOrListField(child=serializers.CharField(), required=False)
    node = StringOrListField(child=serializers.CharField(), required=False)


class OCPOrderBySerializer(OrderSerializer):
    """Serializer for handling query parameter order_by."""

    _opfields = ("project", "cluster", "node", "date")

    cluster = serializers.ChoiceField(choices=OrderSerializer.ORDER_CHOICES, required=False)
    project = serializers.ChoiceField(choices=OrderSerializer.ORDER_CHOICES, required=False)
    node = serializers.ChoiceField(choices=OrderSerializer.ORDER_CHOICES, required=False)
    date = serializers.DateField(required=False)


class InventoryOrderBySerializer(OCPOrderBySerializer):
    """Order By Serializer for CPU and Memory endpoints."""

    _opfields = ("project", "cluster", "node", "usage", "request", "limit")

    usage = serializers.ChoiceField(choices=OCPOrderBySerializer.ORDER_CHOICES, required=False)
    request = serializers.ChoiceField(choices=OCPOrderBySerializer.ORDER_CHOICES, required=False)
    limit = serializers.ChoiceField(choices=OCPOrderBySerializer.ORDER_CHOICES, required=False)


class OCPFilterSerializer(BaseFilterSerializer):
    """Serializer for handling query parameter filter."""

    INFRASTRUCTURE_CHOICES = (("aws", "aws"), ("azure", "azure"), ("gcp", "gcp"))

    _opfields = ("project", "cluster", "node", "infrastructures", "category")

    project = StringOrListField(child=serializers.CharField(), required=False)
    cluster = StringOrListField(child=serializers.CharField(), required=False)
    node = StringOrListField(child=serializers.CharField(), required=False)
    infrastructures = serializers.ChoiceField(choices=INFRASTRUCTURE_CHOICES, required=False)
    category = StringOrListField(child=serializers.CharField(), required=False)

    def validate(self, data):
        """Validate incoming data.

        Args:
            data    (Dict): data to be validated
        Returns:
            (Dict): Validated data
        Raises:
            (ValidationError): if filter inputs are invalid

        """
        super().validate(data)

        if data.get("infrastructures"):
            infra_value = data["infrastructures"]
            data["infrastructures"] = [Provider.PROVIDER_CASE_MAPPING.get(infra_value.lower())]

        return data


class OCPExcludeSerializer(BaseExcludeSerializer):
    """Serializer for handling query parameter exclude."""

    INFRASTRUCTURE_CHOICES = (("aws", "aws"), ("azure", "azure"))

    _opfields = ("project", "cluster", "node", "infrastructures", "category")

    project = StringOrListField(child=serializers.CharField(), required=False)
    cluster = StringOrListField(child=serializers.CharField(), required=False)
    node = StringOrListField(child=serializers.CharField(), required=False)
    infrastructures = serializers.ChoiceField(choices=INFRASTRUCTURE_CHOICES, required=False)
    category = StringOrListField(child=serializers.CharField(), required=False)

    def validate(self, data):
        """Validate incoming data.

        Args:
            data    (Dict): data to be validated
        Returns:
            (Dict): Validated data
        Raises:
            (ValidationError): if filter inputs are invalid

        """
        super().validate(data)

        if data.get("infrastructures"):
            infra_value = data["infrastructures"]
            data["infrastructures"] = [Provider.PROVIDER_CASE_MAPPING.get(infra_value.lower())]

        return data


class OCPQueryParamSerializer(ReportQueryParamSerializer):
    """Serializer for handling query parameters."""

    GROUP_BY_SERIALIZER = OCPGroupBySerializer
    ORDER_BY_SERIALIZER = OCPOrderBySerializer
    FILTER_SERIALIZER = OCPFilterSerializer
    EXCLUDE_SERIALIZER = OCPExcludeSerializer

    def validate(self, data):
        """Validate incoming data.

        Args:
            data    (Dict): data to be validated
        Returns:
            (Dict): Validated data
        Raises:
            (ValidationError): if field inputs are invalid

        """
        super().validate(data)
        error = {}
        if "delta" in data.get("order_by", {}) and "delta" not in data:
            error["order_by"] = _("Cannot order by delta without a delta param")
            raise serializers.ValidationError(error)
        return data


class OCPInventoryQueryParamSerializer(OCPQueryParamSerializer):
    """Serializer for handling inventory query parameters."""

    ORDER_BY_SERIALIZER = InventoryOrderBySerializer

    delta_choices = ("cost", "usage", "request", "cost_total", "distributed_cost")

    delta_fields = ("usage", "request", "limit", "capacity", "distributed_cost")

    delta = serializers.CharField(required=False)

    def validate_delta(self, value):
        """Validate delta is valid."""
        error = {}
        if "__" in value:
            values = value.split("__")
            if len(values) != 2:
                error[value] = _("Only two fields may be compared")
                raise serializers.ValidationError(error)
            for val in values:
                if val not in self.delta_fields:
                    error[value] = _("Unsupported parameter")
                    raise serializers.ValidationError(error)
        else:
            if value == "cost":
                return "cost_total"
            if value not in self.delta_choices:
                error[value] = _("Unsupported parameter")
                raise serializers.ValidationError(error)
        return value


class OCPCostQueryParamSerializer(OCPQueryParamSerializer):
    """Serializer for handling cost query parameters."""

    DELTA_CHOICES = (("cost", "cost"), ("cost_total", "cost_total"))

    delta = serializers.ChoiceField(choices=DELTA_CHOICES, required=False)
