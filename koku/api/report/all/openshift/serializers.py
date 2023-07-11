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
        if len(value) > 2:
            # Max support group_bys is 2
            error = {"group_by": ("Cost Management supports a max of two group_by options.")}
            raise serializers.ValidationError(error)
        validate_field(self, "group_by", self.GROUP_BY_SERIALIZER, value, tag_keys=self.tag_keys)
        return value
