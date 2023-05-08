#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""AWS Report Serializers."""
from django.utils.translation import ugettext as _
from rest_framework import serializers

from api.report.serializers import ExcludeSerializer as BaseExcludeSerializer
from api.report.serializers import FilterSerializer as BaseFilterSerializer
from api.report.serializers import GroupSerializer
from api.report.serializers import OrderSerializer
from api.report.serializers import ReportQueryParamSerializer
from api.report.serializers import StringOrListField
from api.report.serializers import validate_field
from api.utils import get_cost_type


class AWSGroupBySerializer(GroupSerializer):
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
    # Tells the parent class to add prefixed
    # aws_category param to the allowable fields list
    _aws_category = True

    # account field will accept both account number and account alias.
    account = StringOrListField(child=serializers.CharField(), required=False)
    az = StringOrListField(child=serializers.CharField(), required=False)
    instance_type = StringOrListField(child=serializers.CharField(), required=False)
    region = StringOrListField(child=serializers.CharField(), required=False)
    service = StringOrListField(child=serializers.CharField(), required=False)
    storage_type = StringOrListField(child=serializers.CharField(), required=False)
    product_family = StringOrListField(child=serializers.CharField(), required=False)
    org_unit_id = StringOrListField(child=serializers.CharField(), required=False)


class AWSOrderBySerializer(OrderSerializer):
    """Serializer for handling query parameter order_by."""

    _opfields = ("usage", "account_alias", "region", "service", "product_family", "date")
    _aws_category = True

    usage = serializers.ChoiceField(choices=OrderSerializer.ORDER_CHOICES, required=False)
    # ordering by alias is supported, but ordering by account is not due to the
    # probability that a human-recognizable alias is more useful than account number.
    account_alias = serializers.ChoiceField(choices=OrderSerializer.ORDER_CHOICES, required=False)
    region = serializers.ChoiceField(choices=OrderSerializer.ORDER_CHOICES, required=False)
    service = serializers.ChoiceField(choices=OrderSerializer.ORDER_CHOICES, required=False)
    product_family = serializers.ChoiceField(choices=OrderSerializer.ORDER_CHOICES, required=False)
    date = serializers.DateField(required=False)


class AWSFilterSerializer(BaseFilterSerializer):
    """Serializer for handling query parameter filter."""

    _opfields = ("account", "service", "region", "az", "product_family", "org_unit_id")
    _aws_category = True

    account = StringOrListField(child=serializers.CharField(), required=False)
    service = StringOrListField(child=serializers.CharField(), required=False)
    region = StringOrListField(child=serializers.CharField(), required=False)
    az = StringOrListField(child=serializers.CharField(), required=False)
    product_family = StringOrListField(child=serializers.CharField(), required=False)
    org_unit_id = StringOrListField(child=serializers.CharField(), required=False)


class AWSExcludeSerializer(BaseExcludeSerializer):
    """Serializer for handling query parameter exclude."""

    _opfields = ("account", "service", "region", "az", "product_family", "org_unit_id")
    _aws_category = True

    account = StringOrListField(child=serializers.CharField(), required=False)
    service = StringOrListField(child=serializers.CharField(), required=False)
    region = StringOrListField(child=serializers.CharField(), required=False)
    az = StringOrListField(child=serializers.CharField(), required=False)
    product_family = StringOrListField(child=serializers.CharField(), required=False)
    org_unit_id = StringOrListField(child=serializers.CharField(), required=False)


class AWSQueryParamSerializer(ReportQueryParamSerializer):
    """Serializer for handling query parameters."""

    GROUP_BY_SERIALIZER = AWSGroupBySerializer
    ORDER_BY_SERIALIZER = AWSOrderBySerializer
    FILTER_SERIALIZER = AWSFilterSerializer
    EXCLUDE_SERIALIZER = AWSExcludeSerializer

    # Tuples are (key, display_name)
    DELTA_CHOICES = (("usage", "usage"), ("cost", "cost"), ("cost_total", "cost_total"))
    COST_TYPE_CHOICE = (
        ("blended_cost", "blended_cost"),
        ("unblended_cost", "unblended_cost"),
        ("savingsplan_effective_cost", "savingsplan_effective_cost"),
    )

    delta = serializers.ChoiceField(choices=DELTA_CHOICES, required=False)
    cost_type = serializers.ChoiceField(choices=COST_TYPE_CHOICE, required=False)

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
        validate_field(
            self,
            "group_by",
            self.GROUP_BY_SERIALIZER,
            value,
            tag_keys=self.tag_keys,
        )
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
