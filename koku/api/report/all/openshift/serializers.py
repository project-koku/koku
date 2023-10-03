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
from masu.processor import get_customer_group_by_limit


class OCPAllGroupBySerializer(awsser.AWSGroupBySerializer, ocpser.OCPGroupBySerializer):
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


class OCPAllOrderBySerializer(awsser.AWSOrderBySerializer, ocpser.OCPOrderBySerializer):
    """Serializer for handling query parameter order_by."""

    pass


class OCPAllFilterSerializer(awsser.AWSFilterSerializer, ocpser.OCPFilterSerializer):
    """Serializer for handling query parameter filter."""

    _opfields = (
        "account",
        "az",
        "instance_type",
        "region",
        "service",
        "storage_type",
        "product_family",
        "cluster",
        "node",
        "source_type",
    )

    source_type = StringOrListField(child=serializers.CharField(), required=False)


class OCPAllExcludeSerializer(awsser.AWSExcludeSerializer, ocpser.OCPExcludeSerializer):
    """Serializer for handling query parameter filter."""

    _opfields = (
        "account",
        "az",
        "instance_type",
        "region",
        "service",
        "storage_type",
        "product_family",
        "cluster",
        "node",
        "source_type",
    )

    source_type = StringOrListField(child=serializers.CharField(), required=False)


class OCPAllQueryParamSerializer(awsser.AWSQueryParamSerializer):
    """Serializer for handling query parameters."""

    GROUP_BY_SERIALIZER = OCPAllGroupBySerializer
    ORDER_BY_SERIALIZER = OCPAllOrderBySerializer
    FILTER_SERIALIZER = OCPAllFilterSerializer
    EXCLUDE_SERIALIZER = OCPAllExcludeSerializer

    def validate_group_by(self, value):
        """Validate incoming group_by data.

        Args:
            data    (Dict): data to be validated
        Returns:
            (Dict): Validated data
        Raises:
            (ValidationError): if group_by field inputs are invalid

        """
        max_value = get_customer_group_by_limit(self.schema)
        if len(value) > max_value:
            error = {"group_by": (f"Cost Management supports a max of {max_value} group_by options.")}
            raise serializers.ValidationError(error)
        validate_field(self, "group_by", self.GROUP_BY_SERIALIZER, value, tag_keys=self.tag_keys)
        return value
