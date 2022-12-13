#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""OCP-on-AWS Report Serializers."""
import api.report.aws.serializers as awsser
import api.report.ocp.serializers as ocpser
from api.report.serializers import validate_field


class OCPAWSGroupBySerializer(awsser.AWSGroupBySerializer, ocpser.OCPGroupBySerializer):
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


class OCPAWSOrderBySerializer(awsser.AWSOrderBySerializer, ocpser.OCPOrderBySerializer):
    """Serializer for handling query parameter order_by."""

    pass


class OCPAWSFilterSerializer(awsser.AWSFilterSerializer, ocpser.OCPFilterSerializer):
    """Serializer for handling query parameter filter."""

    pass


class OCPAWSExcludeSerializer(awsser.AWSExcludeSerializer, ocpser.OCPExcludeSerializer):
    """Serializer for handling query parameter filter."""

    pass


class OCPAWSQueryParamSerializer(awsser.AWSQueryParamSerializer):
    """Serializer for handling query parameters."""

    GROUP_BY_SERIALIZER = OCPAWSGroupBySerializer
    ORDER_BY_SERIALIZER = OCPAWSOrderBySerializer
    FILTER_SERIALIZER = OCPAWSFilterSerializer
    EXCLUDE_SERIALIZER = OCPAWSExcludeSerializer

    def __init__(self, *args, **kwargs):
        """Initialize the OCP query param serializer."""
        super().__init__(*args, **kwargs)
        self._init_tagged_fields(
            filter=OCPAWSFilterSerializer,
            group_by=OCPAWSGroupBySerializer,
            order_by=OCPAWSOrderBySerializer,
            exclude=OCPAWSExcludeSerializer,
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
        validate_field(self, "group_by", self.GROUP_BY_SERIALIZER, value, tag_keys=self.tag_keys)
        return value
