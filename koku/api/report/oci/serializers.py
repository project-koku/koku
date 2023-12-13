#
# Copyright 2022 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""OCI Report Serializers."""
from django.utils.translation import gettext
from rest_framework import serializers

from api.report.serializers import ExcludeSerializer as BaseExcludeSerializer
from api.report.serializers import FilterSerializer as BaseFilterSerializer
from api.report.serializers import GroupSerializer
from api.report.serializers import OrderSerializer
from api.report.serializers import ReportQueryParamSerializer
from api.report.serializers import StringOrListField
from api.utils import get_cost_type


class OCIGroupBySerializer(GroupSerializer):
    """Serializer for handling query parameter group_by."""

    _opfields = (
        "payer_tenant_id",
        "instance_type",
        "region",
        "product_service",
    )

    payer_tenant_id = StringOrListField(child=serializers.CharField(), required=False)
    instance_type = StringOrListField(child=serializers.CharField(), required=False)
    region = StringOrListField(child=serializers.CharField(), required=False)
    product_service = StringOrListField(child=serializers.CharField(), required=False)


class OCIOrderBySerializer(OrderSerializer):
    """Serializer for handling query parameter order_by."""

    _opfields = ("payer_tenant_id", "usage_amount", "instance_type", "region", "product_service", "date")

    payer_tenant_id = serializers.ChoiceField(choices=OrderSerializer.ORDER_CHOICES, required=False)
    usage_amount = serializers.ChoiceField(choices=OrderSerializer.ORDER_CHOICES, required=False)
    instance_type = serializers.ChoiceField(choices=OrderSerializer.ORDER_CHOICES, required=False)
    region = serializers.ChoiceField(choices=OrderSerializer.ORDER_CHOICES, required=False)
    product_service = serializers.ChoiceField(choices=OrderSerializer.ORDER_CHOICES, required=False)
    date = serializers.DateField(required=False)


class OCIFilterSerializer(BaseFilterSerializer):
    """Serializer for handling query parameter filter."""

    _opfields = ("payer_tenant_id", "instance_type", "product_service", "region")

    payer_tenant_id = StringOrListField(child=serializers.CharField(), required=False)
    instance_type = StringOrListField(child=serializers.CharField(), required=False)
    product_service = StringOrListField(child=serializers.CharField(), required=False)
    region = StringOrListField(child=serializers.CharField(), required=False)


class OCIExcludeSerializer(BaseExcludeSerializer):
    """Serializer for handling query parameter exclude."""

    _opfields = ("payer_tenant_id", "instance_type", "product_service", "region")

    payer_tenant_id = StringOrListField(child=serializers.CharField(), required=False)
    instance_type = StringOrListField(child=serializers.CharField(), required=False)
    product_service = StringOrListField(child=serializers.CharField(), required=False)
    region = StringOrListField(child=serializers.CharField(), required=False)


class OCIQueryParamSerializer(ReportQueryParamSerializer):
    """Serializer for handling query parameters."""

    GROUP_BY_SERIALIZER = OCIGroupBySerializer
    ORDER_BY_SERIALIZER = OCIOrderBySerializer
    FILTER_SERIALIZER = OCIFilterSerializer
    EXCLUDE_SERIALIZER = OCIExcludeSerializer

    # Tuples are (key, display_name)
    DELTA_CHOICES = (("usage", "usage"), ("cost", "cost"), ("cost_total", "cost_total"))

    delta = serializers.ChoiceField(choices=DELTA_CHOICES, required=False)

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
            error["order_by"] = gettext("Cannot order by delta without a delta param")
            raise serializers.ValidationError(error)
        return data
