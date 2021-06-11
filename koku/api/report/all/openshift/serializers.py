#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""OCP-on-All infrastructure Report Serializers."""
from rest_framework import serializers

import api.report.aws.serializers as awsser
import api.report.ocp.serializers as ocpser
from api.report.serializers import StringOrListField
from api.report.serializers import validate_field


class OCPAllGroupBySerializer(awsser.GroupBySerializer, ocpser.GroupBySerializer):
    """Serializer for handling query parameter group_by."""

    _opfields = (
        "account",
        "az",
        "instance_type",
        "region",
        "service",
        "storage_type",
        "product_family",
        "project",
        "cluster",
        "node",
        "source_type",
    )


class OCPAllOrderBySerializer(awsser.OrderBySerializer, ocpser.OrderBySerializer):
    """Serializer for handling query parameter order_by."""

    pass


class OCPAllFilterSerializer(awsser.FilterSerializer, ocpser.FilterSerializer):
    """Serializer for handling query parameter filter."""

    _opfields = ("source_type",)

    source_type = StringOrListField(child=serializers.CharField(), required=False)


class OCPAllQueryParamSerializer(awsser.QueryParamSerializer):
    """Serializer for handling query parameters."""

    def __init__(self, *args, **kwargs):
        """Initialize the OCP query param serializer."""
        super().__init__(*args, **kwargs)
        self._init_tagged_fields(
            filter=OCPAllFilterSerializer, group_by=OCPAllGroupBySerializer, order_by=OCPAllOrderBySerializer
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
        validate_field(self, "group_by", OCPAllGroupBySerializer, value, tag_keys=self.tag_keys)
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
        validate_field(self, "order_by", OCPAllOrderBySerializer, value)
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
        validate_field(self, "filter", OCPAllFilterSerializer, value, tag_keys=self.tag_keys)
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
