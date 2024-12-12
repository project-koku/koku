#
# Copyright 2022 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
from api.report.serializers import add_operator_specified_fields
from api.tags.aws.serializers import AWS_FILTER_OP_FIELDS
from api.tags.aws.serializers import AWSExcludeSerializer
from api.tags.aws.serializers import AWSFilterSerializer
from api.tags.aws.serializers import AWSTagsQueryParamSerializer
from api.tags.azure.serializers import AZURE_FILTER_OP_FIELDS
from api.tags.azure.serializers import AzureExcludeSerializer
from api.tags.azure.serializers import AzureFilterSerializer
from api.tags.ocp.serializers import OCP_FILTER_OP_FIELDS
from api.tags.ocp.serializers import OCPExcludeSerializer
from api.tags.ocp.serializers import OCPFilterSerializer
from api.tags.ocp.serializers import OCPTagsQueryParamSerializer


class OCPAllFilterSerializer(AWSFilterSerializer, AzureFilterSerializer, OCPFilterSerializer):
    """Serializer for handling tag query parameter filter."""

    def __init__(self, *args, **kwargs):
        """Initialize the OCPAllFilterSerializer."""
        super().__init__(*args, **kwargs)
        add_operator_specified_fields(
            self.fields, AWS_FILTER_OP_FIELDS + AZURE_FILTER_OP_FIELDS + OCP_FILTER_OP_FIELDS
        )


class OCPAllExcludeSerializer(AWSExcludeSerializer, AzureExcludeSerializer, OCPExcludeSerializer):
    """Serializer for handling tag query parameter filter."""

    def __init__(self, *args, **kwargs):
        """Initialize the OCPAllExcludeSerializer."""
        super().__init__(*args, **kwargs)
        add_operator_specified_fields(
            self.fields, AWS_FILTER_OP_FIELDS + AZURE_FILTER_OP_FIELDS + OCP_FILTER_OP_FIELDS
        )


class OCPAllTagsQueryParamSerializer(AWSTagsQueryParamSerializer, OCPTagsQueryParamSerializer):
    """Serializer for handling OCP-on-All tag query parameters."""

    exclude = OCPAllExcludeSerializer(required=False)
    filter = OCPAllFilterSerializer(required=False)
