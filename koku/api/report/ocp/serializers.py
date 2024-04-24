#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""OCP Report Serializers."""
from django.utils.translation import gettext
from rest_framework import serializers

from api.models import Provider
from api.report.serializers import ExcludeSerializer as BaseExcludeSerializer
from api.report.serializers import FilterSerializer as BaseFilterSerializer
from api.report.serializers import GroupSerializer
from api.report.serializers import OrderSerializer
from api.report.serializers import ReportQueryParamSerializer
from api.report.serializers import StringOrListField

DISTRIBUTED_COST_INTERNAL = {"distributed_cost": "cost_total_distributed"}


def order_by_field_requires_group_by(data, order_name, group_by_key):
    error = {}
    if order_name in data.get("order_by", {}) and group_by_key not in data.get("group_by", {}):
        error["order_by"] = gettext(f"Cannot order by field {order_name} without grouping by {group_by_key}.")
        raise serializers.ValidationError(error)


class OCPGroupBySerializer(GroupSerializer):
    """Serializer for handling query parameter group_by."""

    _opfields = ("project", "cluster", "node", "persistentvolumeclaim", "storageclass")

    cluster = StringOrListField(child=serializers.CharField(), required=False)
    project = StringOrListField(child=serializers.CharField(), required=False)
    node = StringOrListField(child=serializers.CharField(), required=False)
    persistentvolumeclaim = StringOrListField(child=serializers.CharField(), required=False)
    storageclass = StringOrListField(child=serializers.CharField(), required=False)


class OCPOrderBySerializer(OrderSerializer):
    """Serializer for handling query parameter order_by."""

    _opfields = ("project", "cluster", "node", "date", "distributed_cost")
    _op_mapping = DISTRIBUTED_COST_INTERNAL

    cluster = serializers.ChoiceField(choices=OrderSerializer.ORDER_CHOICES, required=False)
    project = serializers.ChoiceField(choices=OrderSerializer.ORDER_CHOICES, required=False)
    node = serializers.ChoiceField(choices=OrderSerializer.ORDER_CHOICES, required=False)
    date = serializers.DateField(required=False)
    cost_total_distributed = serializers.ChoiceField(choices=OrderSerializer.ORDER_CHOICES, required=False)
    persistentvolumeclaim = serializers.ChoiceField(choices=OrderSerializer.ORDER_CHOICES, required=False)
    storage_class = serializers.ChoiceField(choices=OrderSerializer.ORDER_CHOICES, required=False)


class InventoryOrderBySerializer(OCPOrderBySerializer):
    """Order By Serializer for CPU and Memory endpoints."""

    _opfields = ("project", "cluster", "node", "usage", "request", "limit")

    usage = serializers.ChoiceField(choices=OCPOrderBySerializer.ORDER_CHOICES, required=False)
    request = serializers.ChoiceField(choices=OCPOrderBySerializer.ORDER_CHOICES, required=False)
    limit = serializers.ChoiceField(choices=OCPOrderBySerializer.ORDER_CHOICES, required=False)


class OCPFilterSerializer(BaseFilterSerializer):
    """Serializer for handling query parameter filter."""

    INFRASTRUCTURE_CHOICES = (("aws", "aws"), ("azure", "azure"), ("gcp", "gcp"))

    _opfields = ("project", "cluster", "node", "infrastructures", "category", "persistentvolumeclaim", "storageclass")

    project = StringOrListField(child=serializers.CharField(), required=False)
    cluster = StringOrListField(child=serializers.CharField(), required=False)
    node = StringOrListField(child=serializers.CharField(), required=False)
    infrastructures = serializers.ChoiceField(choices=INFRASTRUCTURE_CHOICES, required=False)
    category = StringOrListField(child=serializers.CharField(), required=False)
    persistentvolumeclaim = StringOrListField(child=serializers.CharField(), required=False)
    storageclass = StringOrListField(child=serializers.CharField(), required=False)

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

    _opfields = ("project", "cluster", "node", "infrastructures", "category", "persistentvolumeclaim")

    project = StringOrListField(child=serializers.CharField(), required=False)
    cluster = StringOrListField(child=serializers.CharField(), required=False)
    node = StringOrListField(child=serializers.CharField(), required=False)
    infrastructures = serializers.ChoiceField(choices=INFRASTRUCTURE_CHOICES, required=False)
    category = StringOrListField(child=serializers.CharField(), required=False)
    persistentvolumeclaim = StringOrListField(child=serializers.CharField(), required=False)

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

    def to_internal_value(self, data):
        """Send to internal value."""
        if delta_value := data.get("delta"):
            if isinstance(delta_value, str):
                if internal_value := DISTRIBUTED_COST_INTERNAL.get(delta_value):
                    data["delta"] = internal_value
                if delta_value == "cost":
                    data["delta"] = "cost_total"
        return super().to_internal_value(data)

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
            error["order_by"] = gettext("Cannot order by delta without a delta param")
            raise serializers.ValidationError(error)
        order_by_field_requires_group_by(data, DISTRIBUTED_COST_INTERNAL["distributed_cost"], "project")
        order_by_field_requires_group_by(data, "storage_class", "persistentvolumeclaim")
        order_by_field_requires_group_by(data, "persistentvolumeclaim", "persistentvolumeclaim")
        if data.get("delta") == DISTRIBUTED_COST_INTERNAL["distributed_cost"] and "project" not in data.get(
            "group_by", {}
        ):
            error["delta"] = gettext("Cannot use distributed_cost delta without grouping by project.")
            raise serializers.ValidationError(error)
        return data

    def validate_delta(self, value):
        """Validate incoming delta value based on path."""
        valid_deltas = ["usage"]
        request = self.context.get("request")
        if request and "costs" in request.path:
            valid_deltas = ["cost_total", DISTRIBUTED_COST_INTERNAL["distributed_cost"]]
        if value not in valid_deltas:
            error = {"delta": f'"{value}" is not a valid choice.'}
            raise serializers.ValidationError(error)
        return value


class OCPInventoryQueryParamSerializer(OCPQueryParamSerializer):
    """Serializer for handling inventory query parameters."""

    ORDER_BY_SERIALIZER = InventoryOrderBySerializer

    delta_choices = ("cost", "usage", "request", "cost_total", DISTRIBUTED_COST_INTERNAL["distributed_cost"])

    delta_fields = ("usage", "request", "limit", "capacity", DISTRIBUTED_COST_INTERNAL["distributed_cost"])

    delta = serializers.CharField(required=False)

    def validate_delta(self, value):
        """Validate delta is valid."""
        error = {}
        if "__" in value:
            values = value.split("__")
            if len(values) != 2:
                error[value] = gettext("Only two fields may be compared")
                raise serializers.ValidationError(error)
            for val in values:
                if val not in self.delta_fields:
                    error[value] = gettext("Unsupported parameter")
                    raise serializers.ValidationError(error)
        else:
            if value not in self.delta_choices:
                error[value] = gettext("Unsupported parameter")
                raise serializers.ValidationError(error)
        return value


class OCPCostQueryParamSerializer(OCPQueryParamSerializer):
    """Serializer for handling cost query parameters."""

    DELTA_CHOICES = (
        ("cost", "cost"),
        ("cost_total", "cost_total"),
        (DISTRIBUTED_COST_INTERNAL["distributed_cost"], DISTRIBUTED_COST_INTERNAL["distributed_cost"]),
    )

    delta = serializers.ChoiceField(choices=DELTA_CHOICES, required=False)
