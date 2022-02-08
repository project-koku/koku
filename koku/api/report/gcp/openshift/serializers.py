#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""OCP-on-GCP Report Serializers."""
from rest_framework import serializers

import api.report.gcp.serializers as gcpser
import api.report.ocp.serializers as ocpser
from api.report.serializers import StringOrListField
from api.report.serializers import validate_field


class OCPGCPGroupBySerializer(gcpser.GCPGroupBySerializer, ocpser.GroupBySerializer):
    """Serializer for handling query parameter group_by."""

    _opfields = ("account", "region", "service", "project", "instance_type", "cluster", "node", "gcp_project")


class OCPGCPOrderBySerializer(gcpser.GCPOrderBySerializer, ocpser.OrderBySerializer):
    """Serializer for handling query parameter order_by."""

    pass


class OCPGCPFilterSerializer(gcpser.GCPFilterSerializer, ocpser.FilterSerializer):
    """Serializer for handling query parameter filter."""

    _opfields = ("account", "region", "service", "project", "instance_type", "cluster", "node", "gcp_project")

    instance_type = StringOrListField(child=serializers.CharField(), required=False)


class OCPGCPQueryParamSerializer(gcpser.GCPQueryParamSerializer):
    """Serializer for handling query parameters."""

    def __init__(self, *args, **kwargs):
        """Initialize the OCP query param serializer."""
        super().__init__(*args, **kwargs)
        self._init_tagged_fields(
            filter=OCPGCPFilterSerializer, group_by=OCPGCPGroupBySerializer, order_by=OCPGCPOrderBySerializer
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
        validate_field(self, "group_by", OCPGCPGroupBySerializer, value, tag_keys=self.tag_keys)
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
        validate_field(self, "order_by", OCPGCPOrderBySerializer, value)
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
        validate_field(self, "filter", OCPGCPFilterSerializer, value, tag_keys=self.tag_keys)
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
