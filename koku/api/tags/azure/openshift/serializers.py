#
# Copyright 2022 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
from api.report.serializers import add_operator_specified_fields
from api.tags.azure.serializers import AZURE_FILTER_OP_FIELDS
from api.tags.azure.serializers import AzureExcludeSerializer
from api.tags.azure.serializers import AzureFilterSerializer
from api.tags.azure.serializers import AzureTagsQueryParamSerializer
from api.tags.ocp.serializers import OCP_FILTER_OP_FIELDS
from api.tags.ocp.serializers import OCPExcludeSerializer
from api.tags.ocp.serializers import OCPFilterSerializer
from api.tags.ocp.serializers import OCPTagsQueryParamSerializer


class OCPAzureFilterSerializer(AzureFilterSerializer, OCPFilterSerializer):
    """Serializer for handling tag query parameter filter."""

    def __init__(self, *args, **kwargs):
        """Initialize the AzureFilterSerializer."""
        super().__init__(*args, **kwargs)
        add_operator_specified_fields(self.fields, AZURE_FILTER_OP_FIELDS + OCP_FILTER_OP_FIELDS)


class OCPAzureExcludeSerializer(AzureExcludeSerializer, OCPExcludeSerializer):
    """Serializer for handling tag query parameter filter."""

    def __init__(self, *args, **kwargs):
        """Initialize the AzureExcludeSerializer."""
        super().__init__(*args, **kwargs)
        add_operator_specified_fields(self.fields, AZURE_FILTER_OP_FIELDS + OCP_FILTER_OP_FIELDS)


class OCPAzureTagsQueryParamSerializer(AzureTagsQueryParamSerializer, OCPTagsQueryParamSerializer):
    """Serializer for handling OCP-on-Azure tag query parameters."""

    exclude = OCPAzureExcludeSerializer(required=False)
    filter = OCPAzureFilterSerializer(required=False)
