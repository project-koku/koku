#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""OCP-on-AWS Report Serializers."""
from rest_framework import serializers

import api.report.aws.serializers as awsser
import api.report.ocp.serializers as ocpser
from api.report.serializers import validate_field


class OCPAWSGroupBySerializer(awsser.GroupBySerializer, ocpser.GroupBySerializer):
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
    )


class OCPAWSOrderBySerializer(awsser.OrderBySerializer, ocpser.OrderBySerializer):
    """Serializer for handling query parameter order_by."""

    pass


class OCPAWSFilterSerializer(awsser.FilterSerializer, ocpser.FilterSerializer):
    """Serializer for handling query parameter filter."""

    pass


class OCPAWSQueryParamSerializer(awsser.QueryParamSerializer):
    """Serializer for handling query parameters."""

    def __init__(self, *args, **kwargs):
        """Initialize the OCP query param serializer."""
        super().__init__(*args, **kwargs)
        self._init_tagged_fields(
            filter=OCPAWSFilterSerializer, group_by=OCPAWSGroupBySerializer, order_by=OCPAWSOrderBySerializer
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
        validate_field(self, "group_by", OCPAWSGroupBySerializer, value, tag_keys=self.tag_keys)
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
        validate_field(self, "order_by", OCPAWSOrderBySerializer, value)
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
        validate_field(self, "filter", OCPAWSFilterSerializer, value, tag_keys=self.tag_keys)
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

    def validate(self, data):
        """Validate incoming data.
        Args:
            data    (Dict): data to be validated
        Returns:
            (Dict): Validated data
        Raises:
            (ValidationError): if field inputs are invalid
        """
        # we will need to remove this when we add support for ocp aws cost type
        if data.get("cost_type"):
            error = {"cost_type": ["Unsupported parameter or invalid value"]}
            raise serializers.ValidationError(error)
        super().validate(data)
        return data
