#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Azure Report Serializers."""
from pint.errors import UndefinedUnitError
from rest_framework import serializers

from api.report.serializers import FilterSerializer as BaseFilterSerializer
from api.report.serializers import GroupSerializer
from api.report.serializers import OrderSerializer
from api.report.serializers import ParamSerializer
from api.report.serializers import StringOrListField
from api.report.serializers import validate_field
from api.utils import UnitConverter


class AzureGroupBySerializer(GroupSerializer):
    """Serializer for handling query parameter group_by."""

    _opfields = ("subscription_guid", "resource_location", "instance_type", "service_name")

    subscription_guid = StringOrListField(child=serializers.CharField(), required=False)
    resource_location = StringOrListField(child=serializers.CharField(), required=False)
    instance_type = StringOrListField(child=serializers.CharField(), required=False)
    service_name = StringOrListField(child=serializers.CharField(), required=False)


class AzureOrderBySerializer(OrderSerializer):
    """Serializer for handling query parameter order_by."""

    _opfields = ("subscription_guid", "resource_location", "instance_type", "service_name")

    subscription_guid = serializers.ChoiceField(choices=OrderSerializer.ORDER_CHOICES, required=False)
    resource_location = serializers.ChoiceField(choices=OrderSerializer.ORDER_CHOICES, required=False)
    instance_type = serializers.ChoiceField(choices=OrderSerializer.ORDER_CHOICES, required=False)
    service_name = serializers.ChoiceField(choices=OrderSerializer.ORDER_CHOICES, required=False)


class AzureFilterSerializer(BaseFilterSerializer):
    """Serializer for handling query parameter filter."""

    _opfields = ("subscription_guid", "resource_location", "instance_type", "service_name")

    subscription_guid = StringOrListField(child=serializers.CharField(), required=False)
    resource_location = StringOrListField(child=serializers.CharField(), required=False)
    instance_type = StringOrListField(child=serializers.CharField(), required=False)
    service_name = StringOrListField(child=serializers.CharField(), required=False)


class AzureQueryParamSerializer(ParamSerializer):
    """Serializer for handling query parameters."""

    # Tuples are (key, display_name)
    DELTA_CHOICES = (("usage", "usage"), ("cost", "cost"))

    delta = serializers.ChoiceField(choices=DELTA_CHOICES, required=False)
    units = serializers.CharField(required=False)

    def __init__(self, *args, **kwargs):
        """Initialize the Azure query param serializer."""
        super().__init__(*args, **kwargs)
        self._init_tagged_fields(
            filter=AzureFilterSerializer, group_by=AzureGroupBySerializer, order_by=AzureOrderBySerializer
        )

    def validate_group_by(self, value):
        """Validate incoming group_by data.

        Args:
            data    (Dict): data to be validated
        Returns:
            (Dict): Validated data
        Raises:
            (ValidationError): if group_by field inputs are invalid

        """
        validate_field(self, "group_by", AzureGroupBySerializer, value, tag_keys=self.tag_keys)
        return value

    def validate_order_by(self, value):
        """Validate incoming order_by data.

        Args:
            data    (Dict): data to be validated
        Returns:
            (Dict): Validated data
        Raises:
            (ValidationError): if order_by field inputs are invalid

        """
        super().validate_order_by(value)
        validate_field(self, "order_by", AzureOrderBySerializer, value)
        return value

    def validate_filter(self, value):
        """Validate incoming filter data.

        Args:
            data    (Dict): data to be validated
        Returns:
            (Dict): Validated data
        Raises:
            (ValidationError): if filter field inputs are invalid

        """
        validate_field(self, "filter", AzureFilterSerializer, value, tag_keys=self.tag_keys)
        return value

    def validate_units(self, value):
        """Validate incoming units data.

        Args:
            data    (Dict): data to be validated
        Returns:
            (Dict): Validated data
        Raises:
            (ValidationError): if units field inputs are invalid

        """
        unit_converter = UnitConverter()
        try:
            unit_converter.validate_unit(value)
        except (AttributeError, UndefinedUnitError):
            error = {"units": f"{value} is not a supported unit"}
            raise serializers.ValidationError(error)

        return value

    def validate_delta(self, value):
        """Validate incoming delta value based on path."""
        valid_delta = "usage"
        request = self.context.get("request")
        if request and "costs" in request.path:
            valid_delta = "cost_total"
            if value == "cost":
                return valid_delta
        if value != valid_delta:
            error = {"delta": f'"{value}" is not a valid choice.'}
            raise serializers.ValidationError(error)
        return value
