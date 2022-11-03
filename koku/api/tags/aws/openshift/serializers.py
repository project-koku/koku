#
# Copyright 2022 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
from api.report.serializers import add_operator_specified_fields
from api.tags.aws.serializers import AWS_FILTER_OP_FIELDS
from api.tags.aws.serializers import AWSExcludeSerializer
from api.tags.aws.serializers import AWSFilterSerializer
from api.tags.aws.serializers import AWSTagsQueryParamSerializer
from api.tags.ocp.serializers import OCP_FILTER_OP_FIELDS
from api.tags.ocp.serializers import OCPExcludeSerializer
from api.tags.ocp.serializers import OCPFilterSerializer
from api.tags.ocp.serializers import OCPTagsQueryParamSerializer


class OCPAWSFilterSerializer(AWSFilterSerializer, OCPFilterSerializer):
    """Serializer for handling tag query parameter filter."""

    def __init__(self, *args, **kwargs):
        """Initialize the AWSFilterSerializer."""
        super().__init__(*args, **kwargs)
        add_operator_specified_fields(self.fields, AWS_FILTER_OP_FIELDS + OCP_FILTER_OP_FIELDS)


class OCPAWSExcludeSerializer(AWSExcludeSerializer, OCPExcludeSerializer):
    """Serializer for handling tag query parameter exclude."""

    def __init__(self, *args, **kwargs):
        """Initialize the AWSExcludeSerializer."""
        super().__init__(*args, **kwargs)
        add_operator_specified_fields(self.fields, AWS_FILTER_OP_FIELDS + OCP_FILTER_OP_FIELDS)


class OCPAWSTagsQueryParamSerializer(AWSTagsQueryParamSerializer, OCPTagsQueryParamSerializer):
    """Serializer for handling OCP-on-AWS tag query parameters."""

    exclude = OCPAWSExcludeSerializer(required=False)
    filter = OCPAWSFilterSerializer(required=False)
