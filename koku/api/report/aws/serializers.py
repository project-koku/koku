#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""AWS Report Serializers."""
from django.utils.translation import ugettext as _
from pint.errors import UndefinedUnitError
from rest_framework import serializers

from api.report.serializers import FilterSerializer as BaseFilterSerializer
from api.report.serializers import GroupSerializer
from api.report.serializers import OrderSerializer
from api.report.serializers import ParamSerializer
from api.report.serializers import StringOrListField
from api.report.serializers import validate_field
from api.utils import get_cost_type
from api.utils import UnitConverter


class GroupBySerializer(GroupSerializer):
    """Serializer for handling query parameter group_by."""

    _opfields = (
        "account",
        "az",
        "instance_type",
        "region",
        "service",
        "storage_type",
        "product_family",
        "org_unit_id",
    )

    # account field will accept both account number and account alias.
    account = StringOrListField(child=serializers.CharField(), required=False)
    az = StringOrListField(child=serializers.CharField(), required=False)
    instance_type = StringOrListField(child=serializers.CharField(), required=False)
    region = StringOrListField(child=serializers.CharField(), required=False)
    service = StringOrListField(child=serializers.CharField(), required=False)
    storage_type = StringOrListField(child=serializers.CharField(), required=False)
    product_family = StringOrListField(child=serializers.CharField(), required=False)
    org_unit_id = StringOrListField(child=serializers.CharField(), required=False)


class OrderBySerializer(OrderSerializer):
    """Serializer for handling query parameter order_by."""

    _opfields = ("usage", "account_alias", "region", "service", "product_family", "date")

    usage = serializers.ChoiceField(choices=OrderSerializer.ORDER_CHOICES, required=False)
    # ordering by alias is supported, but ordering by account is not due to the
    # probability that a human-recognizable alias is more useful than account number.
    account_alias = serializers.ChoiceField(choices=OrderSerializer.ORDER_CHOICES, required=False)
    region = serializers.ChoiceField(choices=OrderSerializer.ORDER_CHOICES, required=False)
    service = serializers.ChoiceField(choices=OrderSerializer.ORDER_CHOICES, required=False)
    product_family = serializers.ChoiceField(choices=OrderSerializer.ORDER_CHOICES, required=False)
    date = serializers.DateField(required=False)


class FilterSerializer(BaseFilterSerializer):
    """Serializer for handling query parameter filter."""

    _opfields = ("account", "service", "region", "az", "product_family", "org_unit_id")

    account = StringOrListField(child=serializers.CharField(), required=False)
    service = StringOrListField(child=serializers.CharField(), required=False)
    region = StringOrListField(child=serializers.CharField(), required=False)
    az = StringOrListField(child=serializers.CharField(), required=False)
    product_family = StringOrListField(child=serializers.CharField(), required=False)
    org_unit_id = StringOrListField(child=serializers.CharField(), required=False)


class QueryParamSerializer(ParamSerializer):
    """Serializer for handling query parameters."""

    # Tuples are (key, display_name)
    DELTA_CHOICES = (("usage", "usage"), ("cost", "cost"), ("cost_total", "cost_total"))
    COST_TYPE_CHOICE = (
        ("blended_cost", "blended_cost"),
        ("unblended_cost", "unblended_cost"),
        ("savingsplan_effective_cost", "savingsplan_effective_cost"),
    )

    delta = serializers.ChoiceField(choices=DELTA_CHOICES, required=False)
    cost_type = serializers.ChoiceField(choices=COST_TYPE_CHOICE, required=False)
    units = serializers.CharField(required=False)
    compute_count = serializers.NullBooleanField(required=False, default=False)
    check_tags = serializers.BooleanField(required=False, default=False)

    def __init__(self, *args, **kwargs):
        """Initialize the AWS query param serializer."""
        super().__init__(*args, **kwargs)
        self._init_tagged_fields(filter=FilterSerializer, group_by=GroupBySerializer, order_by=OrderBySerializer)

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
        if not data.get("cost_type"):
            data["cost_type"] = get_cost_type(self.context.get("request"))
        error = {}
        if "delta" in data.get("order_by", {}) and "delta" not in data:
            error["order_by"] = _("Cannot order by delta without a delta param")
            raise serializers.ValidationError(error)
        return data

    def validate_group_by(self, value):
        """Validate incoming group_by data.

        Args:
            data    (Dict): data to be validated
        Returns:
            (Dict): Validated data
        Raises:
            (ValidationError): if group_by field inputs are invalid

        """
        validate_field(self, "group_by", GroupBySerializer, value, tag_keys=self.tag_keys)
        # Org unit id validation
        group_by_params = self.initial_data.get("group_by", {})
        org_unit_group_keys = ["org_unit_id", "or:org_unit_id"]
        group_by_keys = group_by_params.keys()

        key_used = []
        for acceptable_key in org_unit_group_keys:
            if acceptable_key in group_by_keys:
                key_used.append(acceptable_key)
        if key_used:
            if len(key_used) > 1:
                # group_by[org_unit_id]=x&group_by[or:org_unit_id]=OU_001 is invalid
                # If we ever want to change this we need to decide what would be appropriate to see
                # here.
                error = {"or_unit_id": _("Multiple org_unit_id must be represented with the or: prefix.")}
                raise serializers.ValidationError(error)
            key_used = key_used[0]
            request = self.context.get("request")
            if "costs" not in request.path or self.initial_data.get("group_by", {}).get(key_used, "") == "*":
                # Additionally, since we only have the org_unit_id group_by available for cost reports
                # we must explicitly raise a validation error if it is a different report type
                # or if we are grouping by org_unit_id with the * since that is essentially grouping by
                # accounts. If we ever want to change this we need to decide what would be appropriate to see
                # here. Such as all org units or top level org units
                error = {"org_unit_id": _("Unsupported parameter or invalid value")}
                raise serializers.ValidationError(error)
            if "or:" not in key_used:
                if isinstance(group_by_params.get(key_used), list):
                    if len(group_by_params.get(key_used)) > 1:
                        # group_by[org_unit_id]=x&group_by[org_unit_id]=OU_001 is invalid
                        # because no child nodes would ever intersect due to the tree structure.
                        error = {"or_unit_id": _("Multiple org_unit_id must be represented with the or: prefix.")}
                        raise serializers.ValidationError(error)
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
        validate_field(self, "order_by", OrderBySerializer, value)
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
        validate_field(self, "filter", FilterSerializer, value, tag_keys=self.tag_keys)
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

    def validate_cost_type(self, value):
        """Validate incoming cost_type value based on path."""

        valid_cost_type = [choice[0] for choice in self.COST_TYPE_CHOICE]
        if value not in valid_cost_type:
            error = {"cost_type": f'"{value}" is not a valid choice.'}
            raise serializers.ValidationError(error)
        return value
